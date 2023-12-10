"""TKTrio - Run trio on top of Tkinter."""

# Programmed by CoolCat467

__title__ = "TKTrio"
__author__ = "CoolCat467"
__license__ = "GPLv3"
__version__ = "0.1.0"

import sys
import tkinter as tk
import weakref
from collections.abc import Awaitable, Callable
from enum import IntEnum, auto
from functools import partial, wraps
from tkinter import messagebox
from traceback import print_exception
from typing import Any, TypeGuard

from idlemypyextension.moduleguard import guard_imports

with guard_imports({"trio", "outcome", "exceptiongroup"}):
    import trio
    from outcome import Outcome

    if sys.version_info < (3, 11):
        from exceptiongroup import ExceptionGroup


def install_protocol_override(
    root: tk.Wm,
    override: Callable[
        [
            str | None,
            Callable[[], None] | None,
            Callable[[str | None, Callable[[], None] | None], str],
        ],
        str,
    ],
) -> None:
    """Install protocol override.

    Basically, whenever root.protocol is called, instead it calls
    override with the name and function to bind and also passes the
    original root.protocol function
    """
    uninstall_protocol_override(root)
    original = root.protocol

    @wraps(original)
    def new_protocol(
        name: str | None = None,
        func: Callable[[], None] | None = None,
    ) -> str:
        return override(name, func, original)  # type: ignore[arg-type]

    root.protocol = new_protocol  # type: ignore[assignment]


def uninstall_protocol_override(root: tk.Wm) -> None:
    """Uninstall protocol override if it exists.

    If root.protocol has the __wrapped__ attribute, reset it
    to what it was originally
    """
    if hasattr(root.protocol, "__wrapped__"):
        root.protocol = root.protocol.__wrapped__  # type: ignore


class RunStatus(IntEnum):
    """Enum for trio run status.

    NO_TASK is when there is no task and not running
    TRIO_RUNNING is when there is task and running
    TRIO_RUNNING_CANCELED is when there is task and running but in the process
    of canceling task
    """

    TRIO_RUNNING_CANCELED = auto()
    TRIO_RUNNING = auto()
    TRIO_STARTING = auto()
    NO_TASK = auto()


def evil_does_trio_have_runner() -> bool:
    """Evil function to see if trio has a runner."""
    core = getattr(trio, "_core", None)
    if core is None:
        return False
    run = getattr(core, "_run", None)
    if run is None:
        return False
    global_run_context = getattr(run, "GLOBAL_RUN_CONTEXT", None)
    if global_run_context is None:
        return False
    return hasattr(global_run_context, "runner")


class TKMiscWmSubclass(tk.Misc, tk.Wm):
    """Subclass of both tkinter Misc and tkinter Wm."""

    __slots__ = ()


def is_tk_wm_and_misc_subclass(
    val: tk.Tk | tk.BaseWidget | tk.Wm | tk.Misc,
) -> TypeGuard[TKMiscWmSubclass]:
    """Return if value is an instance of both tk.Misc and tk.Wm."""
    return isinstance(val, tk.Misc) and isinstance(val, tk.Wm)


class TkTrioRunner:
    """Tk Trio Runner - Run Trio on top of Tkinter's main loop."""

    __slots__ = (
        "root",
        "call_tk_close",
        "nursery",
        "run_status",
        "recieved_loop_close_request",
        "installed_proto_override",
        "__weakref__",
    )

    def __new__(
        cls,
        root: tk.Misc,
        *args: Any,
        **kwargs: Any,
    ) -> "TkTrioRunner":
        """Either return new instance or get existing runner from root."""
        if not is_tk_wm_and_misc_subclass(root):
            raise ValueError("Must be subclass of both tk.Misc and tk.Wm")
        ref = getattr(root, "__trio__", None)
        if ref is not None:
            obj = ref()
            if isinstance(obj, cls):
                return obj
        return super().__new__(cls)

    def __init__(
        self,
        root: tk.Misc | tk.Wm,
        restore_close: Callable[[], Any] | None = None,
    ) -> None:
        """Initialize trio runner."""
        if not is_tk_wm_and_misc_subclass(root):
            raise ValueError("Must be subclass of both tk.Misc and tk.Wm")
        if (
            hasattr(root, "__trio__")
            and getattr(root, "__trio__", lambda: None)() is self
        ):
            return
        self.root = root
        self.call_tk_close = restore_close or root.destroy

        self.nursery: trio.Nursery
        self.run_status = RunStatus.NO_TASK
        self.recieved_loop_close_request = False
        self.installed_proto_override = False

        root.__trio__ = weakref.ref(self)  # type: ignore[attr-defined]

    def schedule_task(self, function: Callable[..., Any], *args: Any) -> None:
        """Schedule task in Tkinter's event loop."""
        try:
            self.root.after_idle(function, *args)
        except RuntimeError as exc:
            print_exception(exc)
            # probably "main thread is not in main loop" error
            self.cancel_current_task()

    def cancel_current_task(self) -> None:
        """Cancel current task if one is running."""
        if self.run_status == RunStatus.NO_TASK:
            # No need to reschedule, is already closed.
            return
        if self.run_status == RunStatus.TRIO_STARTING:
            # Reschedule close for later, in process of starting.
            self.schedule_task(self.cancel_current_task)
            return
        self.nursery.cancel_scope.cancel()
        self.run_status = RunStatus.TRIO_RUNNING_CANCELED

    def _start_async_task(
        self,
        function: Callable[[], Awaitable[Any]],
    ) -> None:
        """Internal start task running so except block can catch errors."""
        if evil_does_trio_have_runner():
            self.show_warning_trio_already_running()
            return

        @trio.lowlevel.disable_ki_protection
        async def run_nursery() -> None:
            """Run nursery."""
            assert self.run_status == RunStatus.TRIO_STARTING
            async with trio.open_nursery(True) as nursery:
                self.nursery = nursery
                self.run_status = RunStatus.TRIO_RUNNING
                self.nursery.start_soon(function)
                ##try:
                ##    while not self.nursery.cancel_scope.cancel_called:
                ##        await trio.sleep(0)
                ##finally:
                ##    self.run_status = RunStatus.TRIO_RUNNING_CANCELED
            return

        def done_callback(outcome: Outcome[None]) -> None:
            """Handle when trio is done running."""
            assert self.run_status in {
                RunStatus.TRIO_RUNNING_CANCELED,
                RunStatus.TRIO_RUNNING,
            }
            self.run_status = RunStatus.NO_TASK
            del self.nursery
            try:
                outcome.unwrap()
            except ExceptionGroup as exc:
                print_exception(exc)

        # if evil_spawn:
        #     trio.lowlevel.spawn_system_task(
        #         wrap_in_cancel, True,
        #     )
        #     return

        assert self.run_status == RunStatus.NO_TASK

        self.run_status = RunStatus.TRIO_STARTING

        trio.lowlevel.start_guest_run(
            run_nursery,
            done_callback=done_callback,
            run_sync_soon_threadsafe=self.schedule_task,
            host_uses_signal_set_wakeup_fd=False,
            restrict_keyboard_interrupt_to_checkpoints=True,
            strict_exception_groups=True,
        )

    def get_del_window_proto(
        self,
        new_protocol: Callable[[], None] | None,
    ) -> Callable[[], None]:
        """Create new WM_DELETE_WINDOW protocol to shut down trio properly."""

        def shutdown_then_call() -> None:
            # If this is first time, withdraw root
            if not self.recieved_loop_close_request:
                self.root.withdraw()
            self.recieved_loop_close_request = True
            # If a task is still running
            if self.run_status == RunStatus.TRIO_RUNNING:
                # Cancel it if not already canceled
                self.cancel_current_task()
            if self.run_status != RunStatus.NO_TASK:
                # Rerun this function again in the future until no task running.
                self.schedule_task(shutdown_then_call)
                return None
            # No more tasks
            # Make sure to uninstall override or IDLE gets mad
            uninstall_protocol_override(self.root)
            self.installed_proto_override = False
            # If close function exists, call it.
            if new_protocol is not None:
                return new_protocol()
            return None

        return shutdown_then_call

    def host_loop_close_override(
        self,
        name: str | None,
        new_protocol: Callable[[], None] | None,
        original_bind_proto: Callable[
            [str | None, Callable[[], None] | None],
            str,
        ],
    ) -> str:
        """Override for new protocols on tkinter root.

        Catch new protocols for `WM_DELETE_WINDOW` and replace them
        with our own that will cancel trio run and make sure it closes, and
        then call the new protocol
        """
        if name != "WM_DELETE_WINDOW":
            # Not important to us
            return original_bind_proto(name, new_protocol)
        return original_bind_proto(
            name,
            self.get_del_window_proto(new_protocol),
        )

    def show_warning_trio_already_running(self) -> None:
        """Show warning that trio is already running."""
        messagebox.showerror(
            title="Error: Trio is already running",
            message="Trio is already running from somewhere else, "
            "please try again later.",
            parent=self.root,
        )

    def no_start_trio_is_stopping(self) -> None:
        """Show warning that previous trio run needs to stop."""
        messagebox.showwarning(
            title="Warning: Trio is stopping a previous run",
            message="Trio is in the process of stopping, "
            "please try again later.",
            parent=self.root,
        )

    def __call__(self, function: Callable[[], Awaitable[Any]]) -> None:
        """Schedule async function for the future."""
        # If host loop requested to close, do not run any more tasks.
        if self.recieved_loop_close_request:
            return None

        if self.run_status == RunStatus.TRIO_RUNNING_CANCELED:
            ### Task run is in the process of stopping
            ### self.no_start_trio_is_stopping()
            # Reschedule starting task
            self.schedule_task(self.__call__, function)
            return None

        if self.run_status == RunStatus.TRIO_STARTING:
            # Reschedule starting task
            self.schedule_task(self.__call__, function)
            return None

        # If there is a task running
        if self.run_status == RunStatus.TRIO_RUNNING:
            self.nursery.start_soon(function)
            return None

        if self.run_status != RunStatus.NO_TASK:
            raise RuntimeError("Invalid run status")

        # If we have not installed the protocol override,
        if not self.installed_proto_override:
            # Install it
            install_protocol_override(self.root, self.host_loop_close_override)
            self.installed_proto_override = True
            # Make sure new handler is now applied
            self.root.protocol("WM_DELETE_WINDOW", self.call_tk_close)

        # Start running new task
        return self._start_async_task(function)


def run() -> None:
    """Run test of module."""

    # A tiny Trio program
    async def trio_test_program(run: int) -> str:
        for i in range(5):
            print(f"Hello from Trio! ({i}) ({run = })")
            # This is inside Trio, so we have to use Trio APIs
            try:
                await trio.sleep(1)
            except trio.Cancelled:
                print(f"Run {run} canceled.")
                raise
        return "trio done!"

    root = tk.Tk(className="ClassName")

    def trigger_trio_runs() -> None:
        trio_run = TkTrioRunner(root)
        trio_run(partial(trio_test_program, 0))
        trio_run_2 = TkTrioRunner(root)
        trio_run_2(partial(trio_test_program, 1))
        trio_run_2(partial(trio_test_program, 2))
        trio_run(partial(trio_test_program, 3))

    # Wait a tiny bit so main loop is running from main thread
    root.after(10, trigger_trio_runs)
    print("synchronous after trio run start")
    root.mainloop()


if __name__ == "__main__":
    print(f"{__title__}\nProgrammed by {__author__}.\n")
    run()

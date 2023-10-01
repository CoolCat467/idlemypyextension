"""TKTrio - Run trio on top of Tkinter."""

# Programmed by CoolCat467

__title__ = "TKTrio"
__author__ = "CoolCat467"
__license__ = "GPLv3"
__version__ = "0.1.0"

import tkinter as tk
import weakref
from collections.abc import Awaitable, Callable
from enum import IntEnum, auto
from functools import partial, wraps
from queue import Queue
from tkinter import messagebox
from traceback import print_exception
from typing import Any, TypeGuard

from idlemypyextension.moduleguard import guard_imports

with guard_imports({"trio", "outcome"}):
    import trio
    from outcome import Error, Outcome, Value


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
        "cancel_scope",
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

        self.cancel_scope: trio.CancelScope
        self.run_status = RunStatus.NO_TASK
        self.recieved_loop_close_request = False
        self.installed_proto_override = False

        root.__trio__ = weakref.ref(self)  # type: ignore[attr-defined]

    def schedule_task(self, function: Callable[..., Any], *args: Any) -> None:
        """Schedule task in Tkinter's event loop."""
        try:
            self.root.after_idle(function, *args)
        except RuntimeError:
            # probably "main thread is not in main loop" error
            self.cancel_current_task()

    def call_on_trio_done(self, trio_outcome: "Outcome[Any]") -> None:
        """Called when trio guest run is complete."""
        self.run_status = RunStatus.NO_TASK

        try:
            trio_outcome.unwrap()
        except Exception as exc:
            print_exception(exc)

    def cancel_current_task(self) -> bool:
        """Cancel current task if one exists, otherwise do nothing.

        Return True if canceled a task
        """
        if self.run_status == RunStatus.TRIO_RUNNING:
            self.run_status = RunStatus.TRIO_RUNNING_CANCELED
            try:
                self.cancel_scope.cancel()
            except RuntimeError as exc:
                self.call_on_trio_done(Error(exc))
            return True
        return False

    def _start_async_task(
        self,
        function: Callable[[], Awaitable[Any]],
    ) -> None:
        """Internal start task running so except block can catch errors."""
        # evil_spawn = False
        if evil_does_trio_have_runner():
            self.show_warning_trio_already_running()
            # evil_spawn = True
            return

        self.cancel_scope = trio.CancelScope()

        @trio.lowlevel.disable_ki_protection  # type: ignore[misc]
        async def wrap_in_cancel(is_evil: bool) -> Any:
            value = None
            try:
                with self.cancel_scope:
                    value = await function()
            finally:
                if is_evil:
                    self.call_on_trio_done(Value(value))
            return value

        # if evil_spawn:
        #     trio.lowlevel.spawn_system_task(
        #         wrap_in_cancel, True,
        #     )
        #     return

        trio.lowlevel.start_guest_run(
            wrap_in_cancel,
            False,
            run_sync_soon_threadsafe=self.schedule_task,
            done_callback=self.call_on_trio_done,
        )

    def run_async_task(self, function: Callable[[], Awaitable[Any]]) -> None:
        """Start trio guest mode run for given async function."""
        if self.run_status != RunStatus.NO_TASK:
            raise RuntimeError(
                "Each host loop can only have one guest run at a time",
            )

        self.run_status = RunStatus.TRIO_RUNNING

        try:
            self._start_async_task(function)
        except Exception as ex:
            self.run_status = RunStatus.NO_TASK
            print_exception(ex, limit=-1)

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
            if self.run_status != RunStatus.NO_TASK:
                # Cancel it if not already canceled
                self.cancel_current_task()
                # Rerun this function again in the future
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

    def ask_ok_to_cancel(self) -> bool:
        """Ask if it is ok to cancel current task."""
        msg = "Only one async task at once\n" + "OK to Cancel Current Task?"
        confirm: bool = messagebox.askokcancel(
            title="Cancel Before New Task",
            message=msg,
            default=messagebox.OK,
            parent=self.root,
        )
        return confirm

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
            # Task run is in the process of stopping
            # self.no_start_trio_is_stopping()
            return None

        # If there is a task running
        if self.run_status == RunStatus.TRIO_RUNNING:
            # Ask if we can cancel it
            can_cancel = self.ask_ok_to_cancel()
            if not can_cancel:
                # If we can't, don't run new task
                return None
            # If we can, cancel current task
            self.cancel_current_task()

            # Then trigger new task to run later
            def trigger_run_when_current_done(
                function: Callable[[], Awaitable[Any]],
            ) -> None:
                # If still a task, reschedule
                if self.run_status != RunStatus.NO_TASK:
                    self.schedule_task(trigger_run_when_current_done, function)
                    return None
                # Task done, ok to start
                return self(function)

            trigger_run_when_current_done(function)
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
        try:
            return self.run_async_task(function)
        except RuntimeError as ex:
            print_exception(ex)


class TkTrioMultiRunner(TkTrioRunner):
    """Tk Trio Multi Runner - Allow multiple async tasks to run."""

    __slots__ = ("call_queue", "queue_handler_running")

    def __init__(
        self,
        root: tk.Tk,
        restore_close: Callable[[], None] | None = None,
    ) -> None:
        """Initialize runner."""
        if (
            hasattr(root, "__trio__")
            and getattr(root, "__trio__", lambda: None)() is self
        ):
            return
        super().__init__(root, restore_close)

        self.call_queue: Queue[Callable[[], Awaitable[Any]]] = Queue()
        self.queue_handler_running = False

    def call_on_trio_done(self, trio_outcome: "Outcome[Any]") -> None:
        """Queue handler is no longer running."""
        try:
            super().call_on_trio_done(trio_outcome)
        finally:
            self.queue_handler_running = False

    def cancel_current_task(self) -> bool:
        """Cancel current task. Return True if canceled."""
        canceled = super().cancel_current_task()
        if not canceled:
            return canceled
        if self.recieved_loop_close_request:
            self.queue_handler_running = False
            return canceled
        return canceled

    async def handle_queue(self) -> None:
        """Run all async functions in the queue until exausted."""
        while not self.call_queue.empty():
            async with trio.open_nursery() as nursery:
                while not self.call_queue.empty():
                    nursery.start_soon(self.call_queue.get_nowait())

    def start_queue(self) -> None:
        """Start handling the queue if it's not already happening."""
        if not self.queue_handler_running:
            self.queue_handler_running = True
            super().__call__(self.handle_queue)

    def __call__(self, function: Callable[[], Awaitable[Any]]) -> None:
        """Schedule async function for the future."""
        self.call_queue.put(function)
        self.schedule_task(self.start_queue)


def run() -> None:
    """Run test of module."""

    # A tiny Trio program
    async def trio_test_program(run: int) -> str:
        for i in range(5):
            print(f"Hello from Trio! ({i}) ({run = })")
            # This is inside Trio, so we have to use Trio APIs
            await trio.sleep(1)
        return "trio done!"

    root = tk.Tk(className="ClassName")

    def trigger_trio_runs() -> None:
        trio_run = TkTrioMultiRunner(root)
        trio_run(partial(trio_test_program, 0))
        trio_run_2 = TkTrioMultiRunner(root)
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

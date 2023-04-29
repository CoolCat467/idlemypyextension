#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# TKTrio - Run trio on top of Tkinter

"TKTrio"

# Programmed by CoolCat467

__title__ = "TKTrio"
__author__ = "CoolCat467"
__version__ = "0.0.0"

import tkinter as tk
import weakref
from enum import IntEnum
from functools import partial, wraps
from queue import Queue
from tkinter import messagebox
from typing import Any, Awaitable, Callable

import trio
from outcome import Outcome


def install_protocol_override(
    root: tk.Tk,
    override: Callable[
        [
            str | None,
            Callable[[], None] | None,
            Callable[[str | None, Callable[[], None] | None], str],
        ],
        str,
    ],
) -> None:
    """Install protocol override"""
    uninstall_protocol_override(root)
    original = root.protocol

    @wraps(original)
    def new_protocol(
        name: str | None = None, func: Callable[[], None] | None = None
    ) -> str:
        return override(name, func, original)  # type: ignore[arg-type]

    root.protocol = new_protocol  # type: ignore[assignment]


def uninstall_protocol_override(root: tk.Tk) -> None:
    """Uninstall protocol override if it exists"""
    if hasattr(root.wm_protocol, "__wrapped__"):
        root.protocol = root.protocol.__wrapped__  # type: ignore


class RunStatus(IntEnum):
    """Enum for trio run status"""

    NO_TASK = 0
    TRIO_RUNNING = 1
    TRIO_RUNNING_CANCELED = 2


def evil_does_trio_have_runner() -> bool:
    """Evil function to see if trio has a runner"""
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


class TkTrioRunner:
    """Tk Trio Runner - Run Trio on top of Tkinter's main loop"""

    __slots__ = (
        "root",
        "call_tk_close",
        "cancel_scope",
        "run_status",
        "recieved_loop_close_request",
        "installed_proto_override",
        "__weakref__",
    )

    def __new__(cls, root: tk.Tk, *args: Any, **kwargs: Any) -> "TkTrioRunner":
        ref = getattr(root, "__trio__", None)
        if ref is not None:
            obj = ref()
            if isinstance(obj, cls):
                return obj
        return super(TkTrioRunner, cls).__new__(cls)

    def __init__(
        self, root: tk.Tk, restore_close: Callable[[], None] | None = None
    ) -> None:
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

        if not hasattr(root, "__trio__"):
            root.__trio__ = weakref.ref(self)  # type: ignore[attr-defined]

    def schedule_task(self, function: Callable[..., Any], *args: Any) -> None:
        """Schedule task in Tkinter's event loop"""
        self.root.after_idle(function, *args)

    def call_on_trio_done(self, trio_outcome: "Outcome[Any]") -> None:
        """Called when trio guest run is complete"""
        self.run_status = RunStatus.NO_TASK

        trio_outcome.unwrap()

    def cancel_current_task(self) -> bool:
        """Cancel current task if one exists, otherwise do nothing.

        Return True if canceled a task"""
        if self.run_status == RunStatus.TRIO_RUNNING:
            self.run_status = RunStatus.TRIO_RUNNING_CANCELED
            self.cancel_scope.cancel()
            return True
        return False

    def run_async_task(self, function: Callable[[], Awaitable[Any]]) -> None:
        """Start trio guest mode run for given async function"""
        if self.run_status != RunStatus.NO_TASK:
            raise RuntimeError(
                "Each host loop can only have one guest run at a time"
            )

        self.run_status = RunStatus.TRIO_RUNNING
        self.cancel_scope = trio.CancelScope()

        async def wrap_in_cancel() -> Any:
            with self.cancel_scope:
                return await function()

        if evil_does_trio_have_runner():
            raise RuntimeError("Trio is already running from somewhere else!")

        trio.lowlevel.start_guest_run(
            wrap_in_cancel,
            run_sync_soon_threadsafe=self.schedule_task,
            done_callback=self.call_on_trio_done,
        )

    def get_del_window_proto(
        self, new_protocol: Callable[[], None] | None
    ) -> Callable[[], None]:
        """Create new WM_DELETE_WINDOW protocol to shut down trio properly"""

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
                return
            # No more tasks
            # Make sure to uninstall override or IDLE gets mad
            uninstall_protocol_override(self.root)
            self.installed_proto_override = False
            # If close function exists, call it.
            if new_protocol is not None:
                return new_protocol()

        return shutdown_then_call

    def host_loop_close_override(
        self,
        name: str | None,
        new_protocol: Callable[[], None] | None,
        original_bind_proto: Callable[
            [str | None, Callable[[], None] | None], str
        ],
    ) -> str:
        """Override for new protocols on tkinter root

        Catch new protocols for `WM_DELETE_WINDOW` and replace them
        with our own that will cancel trio run and make sure it closes, and
        then call the new protocol"""
        if name != "WM_DELETE_WINDOW":
            # Not important to us
            return original_bind_proto(name, new_protocol)
        return original_bind_proto(
            name, self.get_del_window_proto(new_protocol)
        )

    def ask_ok_to_cancel(self) -> bool:
        """Ask if it is ok to cancel current task"""
        msg = (
            "Only one async task at once\n"
            + 5 * " "
            + "OK to Cancel Current Task?"
        )
        confirm: bool = messagebox.askokcancel(
            title="Cancel Before New Task",
            message=msg,
            default=messagebox.OK,
            parent=self.root,
        )
        return confirm

    def __call__(self, function: Callable[[], Awaitable[Any]]) -> None:
        """Schedule async function for the future"""
        # If host loop requested to close, do not run any more tasks.
        if self.recieved_loop_close_request:
            return

        # If we have not installed the protocol override,
        if not self.installed_proto_override:
            # Install it
            install_protocol_override(self.root, self.host_loop_close_override)
            self.installed_proto_override = True
            # Make sure new handler is now applied
            self.root.protocol("WM_DELETE_WINDOW", self.call_tk_close)

        # If there is a task running
        if self.run_status != RunStatus.NO_TASK:
            # Ask if we can canel it
            can_cancel = self.ask_ok_to_cancel()
            if not can_cancel:
                # If we can't, don't run new task
                return
            # If we can, cancel current task
            self.cancel_current_task()

            # Then trigger new task to run later
            def trigger_run_when_current_done(
                function: Callable[[], Awaitable[Any]]
            ) -> None:
                # If still a task, reschedule
                if self.run_status != RunStatus.NO_TASK:
                    self.schedule_task(trigger_run_when_current_done, function)
                    return
                # Task done, ok to start
                return self(function)

            return trigger_run_when_current_done(function)

        # Start running new task
        return self.run_async_task(function)


class TkTrioMultiRunner(TkTrioRunner):
    """Tk Trio Multi Runner - Allow multiple async tasks to run"""

    __slots__ = ("call_queue", "queue_handler_running")

    def __init__(
        self, root: tk.Tk, restore_close: Callable[[], None] | None = None
    ) -> None:
        if (
            hasattr(root, "__trio__")
            and getattr(root, "__trio__", lambda: None)() is self
        ):
            return
        super().__init__(root, restore_close)

        self.call_queue: Queue[Callable[[], Awaitable[Any]]] = Queue()
        self.queue_handler_running = False

    def call_on_trio_done(self, trio_outcome: "Outcome[Any]") -> None:
        try:
            super().call_on_trio_done(trio_outcome)
        finally:
            self.queue_handler_running = False

    def cancel_current_task(self) -> bool:
        canceled = super().cancel_current_task()
        if not canceled:
            return canceled
        if self.recieved_loop_close_request:
            self.queue_handler_running = False
            return canceled
        return canceled

    async def handle_queue(self) -> None:
        while not self.call_queue.empty():
            async with trio.open_nursery() as nursery:
                while not self.call_queue.empty():
                    nursery.start_soon(self.call_queue.get_nowait())

    def start_queue(self) -> None:
        if not self.queue_handler_running:
            self.queue_handler_running = True
            super().__call__(self.handle_queue)

    def __call__(self, function: Callable[[], Awaitable[Any]]) -> None:
        self.call_queue.put(function)
        self.schedule_task(self.start_queue)


def run() -> None:
    "Run test of module"

    # A tiny Trio program
    async def trio_test_program(run: int) -> str:
        for i in range(5):
            print(f"Hello from Trio! ({i}) ({run})")
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

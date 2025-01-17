from __future__ import annotations

from collections.abc import Callable
from functools import partial
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
import trio

from idlemypyextension.tktrio import RunStatus, TkTrioRunner

if TYPE_CHECKING:
    import tkinter as tk
    from collections.abc import Callable

    from typing_extensions import TypeVarTuple, Unpack

    PosArgT = TypeVarTuple("PosArgT")


@pytest.fixture(autouse=True)
def mock_extension_log() -> MagicMock:
    """Fixture to override extension_log with an empty function."""
    with patch(
        "idlemypyextension.utils.extension_log",
        return_value=None,
    ) as mock_log:
        yield mock_log


class FakeTK:
    """Fake tkinter root."""

    __slots__ = ("__dict__", "should_stop", "tasks")

    def __init__(self) -> None:
        """Initialize self."""
        self.tasks: list[Callable[..., object]] = []
        self.should_stop = False

    def after_idle(
        self,
        function: Callable[[Unpack[PosArgT]], object],
        *args: Unpack[PosArgT],
    ) -> None:
        """Add function to run queue."""
        self.tasks.append(partial(function, *args))

    def update(self) -> None:
        """Run one task from queue."""
        if self.should_stop:
            raise RuntimeError(f"{self.should_stop = }")
        if self.tasks:
            self.tasks.pop(0)()

    def destroy(self) -> None:
        """Mark update to fail if called again."""
        self.should_stop = True

    def withdraw(self) -> None:
        """Fake hide window."""

    def protocol(
        self,
        name: str | None,
        func: Callable[[], None] | None = None,
    ) -> None:
        """Fake protocol."""


@pytest.fixture
def mock_tk() -> FakeTK:
    """Fixture to create a mock tkinter root."""
    return FakeTK()


@pytest.fixture
def trio_runner(mock_tk: tk.Tk) -> TkTrioRunner:
    """Fixture to create a TkTrioRunner instance."""
    with patch(
        "idlemypyextension.tktrio.is_tk_wm_and_misc_subclass",
        return_value=True,
    ):
        return TkTrioRunner(mock_tk)


def test_initialization(trio_runner: TkTrioRunner) -> None:
    """Test initialization of TkTrioRunner."""
    assert trio_runner.run_status == RunStatus.NO_TASK
    assert trio_runner.root is not None


def test_new_gives_copy(mock_tk: tk.Tk) -> None:
    with patch(
        "idlemypyextension.tktrio.is_tk_wm_and_misc_subclass",
        return_value=True,
    ):
        runner = TkTrioRunner(mock_tk)
        runner2 = TkTrioRunner(mock_tk)
        assert runner is runner2


def test_invalid_initialization() -> None:
    """Test initialization with invalid root."""
    with pytest.raises(
        ValueError,
        match=r"^Must be subclass of both tk\.Misc and tk\.Wm$",
    ):
        TkTrioRunner(None)


def test_schedule_task_threadsafe(trio_runner: TkTrioRunner) -> None:
    """Test scheduling a task in the Tkinter event loop."""
    mock_function = MagicMock()
    trio_runner.schedule_task_threadsafe(mock_function)

    # Process the scheduled tasks
    trio_runner.root.update()

    mock_function.assert_called_once()


def test_cancel_current_task(trio_runner: TkTrioRunner) -> None:
    """Test canceling the current task."""
    assert trio_runner.run_status != RunStatus.TRIO_RUNNING

    async def test() -> None:
        while True:
            await trio.lowlevel.checkpoint()

    trio_runner(test)

    while trio_runner.run_status == RunStatus.TRIO_STARTING:
        trio_runner.root.update()

    nursery = trio_runner.nursery

    trio_runner.cancel_current_task()

    assert trio_runner.run_status == RunStatus.TRIO_RUNNING_CANCELED

    while trio_runner.run_status != RunStatus.NO_TASK:
        trio_runner.root.update()

    assert nursery.cancel_scope.cancel_called

    trio_runner.cancel_current_task()


def test_get_del_window_proto(trio_runner: TkTrioRunner) -> None:
    """Test the WM_DELETE_WINDOW protocol."""
    new_protocol = MagicMock()
    shutdown_function = trio_runner.get_del_window_proto(new_protocol)

    # Call the shutdown function
    shutdown_function()

    # Check if the new protocol was called
    new_protocol.assert_called_once()


def test_show_warning_trio_already_running(trio_runner: TkTrioRunner) -> None:
    """Test showing warning when Trio is already running."""
    with patch("tkinter.messagebox.showerror") as mock_showerror:
        trio_runner.show_warning_trio_already_running()
        mock_showerror.assert_called_once_with(
            title="Error: Trio is already running",
            message="Trio is already running from somewhere else, please try again later.",
            parent=trio_runner.root,
        )


def test_no_start_trio_is_stopping(trio_runner: TkTrioRunner) -> None:
    """Test showing warning when Trio is stopping."""
    with patch("tkinter.messagebox.showwarning") as mock_showwarning:
        trio_runner.no_start_trio_is_stopping()
        mock_showwarning.assert_called_once_with(
            title="Warning: Trio is stopping a previous run",
            message="Trio is in the process of stopping, please try again later.",
            parent=trio_runner.root,
        )

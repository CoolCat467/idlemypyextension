from collections.abc import Callable
from tkinter import Tk, Widget
from typing import Any

class WidgetRedirector:
    widget: Widget
    tk: Tk
    orig: str
    def __init__(self, widget: Widget) -> None: ...
    def close(self) -> None: ...
    def register(
        self,
        operation: str,
        function: Callable[..., Any],
    ) -> OriginalCommand: ...
    def unregister(self, operation: str) -> Callable[..., Any] | None: ...
    def dispatch(self, operation: str, *args: Any) -> Any: ...

class OriginalCommand:
    redir: WidgetRedirector
    operation: str
    tk: Tk
    orig: str
    tk_call: Callable[..., Any]
    orig_and_operation: tuple[str, str]
    def __init__(self, redir: WidgetRedirector, operation: str) -> None: ...
    def __call__(self, *args: Any) -> Any: ...

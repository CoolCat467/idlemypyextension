from idlelib.delegator import Delegator as Delegator
from idlelib.redirector import WidgetRedirector as WidgetRedirector
from tkinter import Text
from typing import Any

class Percolator:
    text: Text
    redir: WidgetRedirector
    top: Delegator
    bottom: Delegator
    filters: list[Any]  # Unused list, likely a remnant of older code
    def __init__(self, text: Text) -> None: ...
    def close(self) -> None: ...
    def insert(
        self,
        index: str,
        chars: str,
        tags: tuple[str, ...] | None = ...,
    ) -> None: ...
    def delete(self, index1: str, index2: str | None = ...) -> None: ...
    def insertfilter(self, filter: Delegator) -> None: ...
    def insertfilterafter(
        self,
        filter: Delegator,
        after: Delegator,
    ) -> None: ...
    def removefilter(self, filter: Delegator) -> None: ...

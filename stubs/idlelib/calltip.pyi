from idlelib import calltip_w as calltip_w
from idlelib.hyperparser import HyperParser as HyperParser
from idlelib.pyshell import PyShellEditorWindow
from tkinter import Event, Text
from typing import Any

class Calltip:
    editwin: PyShellEditorWindow
    text: Text
    active_calltip: calltip_w.CalltipWindow | None
    def __init__(self, editwin: PyShellEditorWindow | None = ...) -> None: ...
    def close(self) -> None: ...
    def remove_calltip_window(
        self,
        event: Event[Any] | None = ...,
    ) -> None: ...
    def force_open_calltip_event(self, event: Event[Any] | None) -> str: ...
    def try_open_calltip_event(self, event: Event[Any] | None) -> None: ...
    def refresh_calltip_event(self, event: Event[Any] | None) -> None: ...
    def open_calltip(self, evalfuncs: bool) -> None: ...
    def fetch_tip(self, expression: str) -> str: ...

def get_entity(expression: str | None) -> object | None: ...
def get_argspec(ob: object) -> str: ...
from idlelib import pyparse as pyparse
from idlelib.pyshell import PyShellEditorWindow
from tkinter import Text

class HyperParser:
    editwin: PyShellEditorWindow
    text: Text
    rawtext: str
    stopatindex: str
    bracketing: tuple[tuple[int, int], ...]
    isopener: list[bool]
    def __init__(self, editwin: PyShellEditorWindow, index: str) -> None: ...
    indexinrawtext: int
    indexbracket: int
    def set_index(self, index: str) -> None: ...
    def is_in_string(self) -> bool: ...
    def is_in_code(self) -> bool: ...
    def get_surrounding_brackets(
        self,
        openers: str = ...,
        mustclose: bool = ...,
    ) -> tuple[str, str] | None: ...
    def get_expression(self) -> str: ...

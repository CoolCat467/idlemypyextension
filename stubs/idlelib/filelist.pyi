from idlelib.editor import EditorWindow as EditorWindow
from idlelib.pyshell import PyShellEditorWindow
from tkinter import Misc, Variable
from typing import Any

class FileList:
    root: Misc
    inversedict: dict[EditorWindow | PyShellEditorWindow, str | None]
    vars: dict[str, Variable]
    dict: dict[str, EditorWindow | PyShellEditorWindow]
    def __init__(self, root: Misc) -> None: ...
    def open(
        self,
        filename: str,
        action: bool | None = ...,
    ) -> EditorWindow | None: ...
    def gotofileline(
        self,
        filename: str,
        lineno: int | None = ...,
    ) -> None: ...
    def new(self, filename: str | None = ...) -> EditorWindow: ...
    def close_all_callback(self, *args: Any, **kwds: Any) -> str: ...
    def unregister_maybe_terminate(
        self,
        edit: EditorWindow | PyShellEditorWindow,
    ) -> None: ...
    def filename_changed_edit(
        self,
        edit: EditorWindow | PyShellEditorWindow,
    ) -> None: ...
    def canonize(self, filename: str) -> str: ...

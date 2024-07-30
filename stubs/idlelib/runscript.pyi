from idlelib import macosx as macosx, outwin as outwin, pyshell as pyshell
from idlelib.config import idleConf as idleConf
from idlelib.filelist import FileList
from idlelib.pyshell import PyShell, PyShellEditorWindow
from idlelib.query import CustomRun as CustomRun
from tkinter import Event, Misc
from types import CodeType
from typing import Any

indent_message: str

class ScriptBinding:
    editwin: PyShellEditorWindow
    flist: FileList
    root: Misc
    cli_args: list[str]
    perf: float
    def __init__(self, editwin: PyShellEditorWindow) -> None: ...
    def check_module_event(self, event: Event[Any]) -> str: ...
    def tabnanny(self, filename: str) -> bool: ...
    shell: PyShell
    def checksyntax(self, filename: str) -> CodeType | bool: ...
    def run_custom_event(self, event: Event[Any]) -> str: ...
    def run_module_event(
        self,
        event: Event[Any],
        *,
        customize: bool = ...,
    ) -> str: ...
    def getfilename(self) -> str | None: ...
    def ask_save_dialog(self) -> bool: ...
    def errorbox(self, title: str, message: str) -> None: ...

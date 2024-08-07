from _sitebuiltins import _Printer
from idlelib import textview as textview
from tkinter import Button, Event, Misc, PhotoImage, Toplevel
from typing import Any

version: str

def build_bits() -> str: ...

class AboutDialog(Toplevel):
    bg: str
    fg: str
    parent: Misc
    def __init__(
        self,
        parent: Misc,
        title: str | None = ...,
        *,
        _htest: bool = ...,
        _utest: bool = ...,
    ) -> None: ...
    button_ok: Button
    icon_image: PhotoImage
    py_license: Button
    py_copyright: Button
    py_credits: Button
    readme: Button
    idle_news: Button
    idle_credits: Button
    def create_widgets(self) -> None: ...
    def show_py_license(self) -> None: ...
    def show_py_copyright(self) -> None: ...
    def show_py_credits(self) -> None: ...
    def show_idle_credits(self) -> None: ...
    def show_readme(self) -> None: ...
    def show_idle_news(self) -> None: ...
    def display_printer_text(self, title: str, printer: _Printer) -> None: ...
    def display_file_text(
        self,
        title: str,
        filename: str,
        encoding: str | None = ...,
    ) -> None: ...
    def ok(self, event: Event[Any] | None = ...) -> None: ...

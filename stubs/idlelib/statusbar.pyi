from tkinter import Misc
from tkinter.ttk import Frame, Label
from typing import Any

class MultiStatusBar(Frame):
    labels: dict[str, Label]
    def __init__(self, master: Misc, **kw: Any) -> None: ...
    def set_label(
        self,
        name: str,
        text: str = ...,
        side: str = ...,
        width: int = ...,
    ) -> None: ...

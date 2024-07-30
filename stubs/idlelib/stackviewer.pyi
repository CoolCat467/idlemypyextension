from idlelib.debugobj import (
    ObjectTreeItem as ObjectTreeItem,
    make_objecttreeitem as make_objecttreeitem,
)
from idlelib.pyshell import PyShellFileList
from idlelib.tree import (
    ScrolledCanvas as ScrolledCanvas,
    TreeItem as TreeItem,
    TreeNode as TreeNode,
)
from tkinter import Misc, Toplevel
from types import FrameType, TracebackType

def StackBrowser(
    root: Misc,
    flist: PyShellFileList | None = ...,
    tb: TracebackType | None = ...,
    top: Toplevel | None = ...,
) -> None: ...

class StackTreeItem(TreeItem):
    flist: PyShellFileList
    stack: list[tuple[FrameType, int]]
    text: str
    def __init__(
        self,
        flist: PyShellFileList | None = ...,
        tb: TracebackType | None = ...,
    ) -> None: ...
    def get_stack(self, tb: TracebackType) -> list[tuple[FrameType, int]]: ...
    def get_exception(self) -> str: ...
    def GetText(self) -> str: ...  # type: ignore[override]
    def GetSubList(self) -> list[TreeItem]: ...  # type: ignore[override]

class FrameTreeItem(TreeItem):
    info: tuple[FrameType, int]
    flist: None
    def __init__(
        self,
        info: tuple[FrameType, int],
        flist: PyShellFileList | None,
    ) -> None: ...
    def GetText(self) -> str: ...  # type: ignore[override]
    def GetSubList(self) -> list[TreeItem]: ...  # type: ignore[override]
    def OnDoubleClick(self) -> None: ...

class VariablesTreeItem(ObjectTreeItem):
    def GetText(self) -> str: ...  # type: ignore[override]
    def GetLabelText(self) -> None: ...
    def IsExpandable(self) -> bool: ...
    def GetSubList(self) -> list[TreeItem]: ...  # type: ignore[override]

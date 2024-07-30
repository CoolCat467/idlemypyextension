from collections.abc import Iterable
from idlelib.browser import (
    ModuleBrowser as ModuleBrowser,
    ModuleBrowserTreeItem as ModuleBrowserTreeItem,
)
from idlelib.tree import TreeItem as TreeItem
from tkinter import Misc

class PathBrowser(ModuleBrowser):
    master: Misc
    def __init__(
        self,
        master: Misc,
        *,
        _htest: bool = ...,
        _utest: bool = ...,
    ) -> None: ...
    def settitle(self) -> None: ...
    def rootnode(self) -> PathBrowserTreeItem: ...

class PathBrowserTreeItem(TreeItem):
    def GetText(self) -> str: ...
    def GetSubList(self) -> list[DirBrowserTreeItem]: ...

class DirBrowserTreeItem(TreeItem):
    dir: str
    packages: list[str]
    def __init__(self, dir: str, packages: list[str] = ...) -> None: ...
    def GetText(self) -> str: ...
    def GetSubList(self) -> list[ModuleBrowserTreeItem]: ...
    def ispackagedir(self, file: str) -> bool: ...
    def listmodules(
        self,
        allnames: Iterable[str],
    ) -> list[tuple[str, str]]: ...

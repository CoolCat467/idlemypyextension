from collections.abc import Callable, Hashable, Iterable
from idlelib.tree import (
    ScrolledCanvas as ScrolledCanvas,
    TreeItem as TreeItem,
    TreeNode as TreeNode,
)
from reprlib import Repr

myrepr: Repr

class ObjectTreeItem(TreeItem):
    labeltext: str
    object: object
    setfunction: Callable[[str], None]
    def __init__(
        self,
        labeltext: str,
        object: int,
        setfunction: Callable[[str], None] | None = ...,
    ) -> None: ...
    def GetLabelText(self) -> str | None: ...  # type: ignore[override]
    def GetText(self) -> str: ...  # type: ignore[override]
    def GetIconName(self) -> str | None: ...  # type: ignore[override]
    def IsEditable(self) -> bool: ...  # type: ignore[override]
    def SetText(self, text: str) -> None: ...
    def IsExpandable(self) -> bool: ...
    def GetSubList(self) -> list[TreeItem]: ...  # type: ignore[override]

class ClassTreeItem(ObjectTreeItem):
    def IsExpandable(self) -> bool: ...
    def GetSubList(self) -> list[TreeItem]: ...  # type: ignore[override]

class AtomicObjectTreeItem(ObjectTreeItem):
    def IsExpandable(self) -> bool: ...

class SequenceTreeItem(ObjectTreeItem):
    def IsExpandable(self) -> bool: ...
    def keys(self) -> Iterable[int]: ...
    def GetSubList(self) -> list[TreeItem]: ...  # type: ignore[override]

class DictTreeItem(SequenceTreeItem):
    def keys(self) -> list[Hashable]: ...  # type: ignore[override]

dispatch: dict[type, ObjectTreeItem]

def make_objecttreeitem(
    labeltext: str,
    object: object,
    setfunction: Callable[[str], None] | None = ...,
) -> ObjectTreeItem: ...

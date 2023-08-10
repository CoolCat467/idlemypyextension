"""Tests for annotate."""

from __future__ import annotations

from collections.abc import Collection, Sequence

import pytest
from idlemypyextension import annotate


@pytest.mark.parametrize(
    ("text", "expect"),
    [("  waf", 2), ("cat", 0), ("     fish", 5), ("   ", 3)],
)
def test_get_line_indent(text: str, expect: int) -> None:
    assert annotate.get_line_indent(text, " ") == expect


@pytest.mark.parametrize(
    ("name", "result"),
    [
        ("typing.Set", "set"),
        ("typing.TypedDict", "TypedDict"),
        ("mypy_extensions.KwArg", "KwArg"),
        ("builtins.list", "builtins.list"),
    ],
)
def test_get_type_repr(name: str, result: str) -> None:
    assert annotate.get_type_repr(name) == result


@pytest.mark.parametrize(
    ("typevalue", "result"),
    [
        (annotate.TypeValue("typing.Set"), "set"),
        (annotate.TypeValue("typing.TypedDict"), "TypedDict"),
        (annotate.TypeValue("mypy_extensions.KwArg"), "KwArg"),
        (annotate.TypeValue("builtins.list"), "builtins.list"),
        (annotate.TypeValue("List"), "list"),
        (
            annotate.TypeValue(
                "List",
                (annotate.TypeValue("list", (annotate.TypeValue("int"),)),),
            ),
            "list[list[int]]",
        ),
        (
            annotate.TypeValue(
                "Union",
                (annotate.TypeValue("str"), annotate.TypeValue("None")),
            ),
            "str | None",
        ),
        (
            annotate.TypeValue(
                "Union",
                (
                    annotate.TypeValue("set", (annotate.TypeValue("int"),)),
                    annotate.TypeValue("None"),
                ),
            ),
            "set[int] | None",
        ),
    ],
)
def test_get_typevalue_repr(
    typevalue: annotate.TypeValue,
    result: str,
) -> None:
    assert annotate.get_typevalue_repr(typevalue) == result


@pytest.mark.parametrize(
    ("items", "result"),
    [
        (("waffles",), "waffles"),
        (("waffles", "pancakes"), "waffles or pancakes"),
        (
            ("waffles", "pancakes", "a muffin"),
            "waffles, pancakes, or a muffin",
        ),
        (
            ("waffles", "pancakes", "cereal", "a muffin"),
            "waffles, pancakes, cereal, or a muffin",
        ),
    ],
)
def test_list_or(items: Collection[str], result: str) -> None:
    assert annotate.list_or(items) == result


@pytest.mark.parametrize(
    ("function_text", "arg_types", "return_type", "result"),
    [
        (
            """def format_id():""",
            [],
            "str",
            """def format_id() -> str:""",
        ),
        (
            """def format_id(user):""",
            ["int"],
            "str",
            """def format_id(user: int) -> str:""",
        ),
        (
            """def foo(x: int, longer_name: str) -> None:""",
            ["int", "str"],
            "None",
            """def foo(x: int, longer_name: str) -> None:""",
        ),
        (
            """def waffle_magic(
    self, obj: wafflemodule.Waffle, action: str
) -> None:""",
            ["wafflemodule.Waffle", "str"],
            "None",
            """def waffle_magic(
    self, obj: wafflemodule.Waffle, action: str
) -> None:""",
        ),
        (
            """def waffle_magic(
    self, obj, action, sand
):""",
            ["Union[int, float, complex, wafflemodule.Waffle]", "str", "int"],
            "None",
            """def waffle_magic(
    self, obj: int | float | complex | wafflemodule.Waffle, action: str, sand: int
) -> None:""",
        ),
        (
            """def get_annotation(
    annotation,
    get_line
):""",
            ["dict[str, Any]", "Callable[[int], str]"],
            "tuple[str, int]",
            """def get_annotation(
    annotation: dict[str, Any],
    get_line: Callable[[int], str]
) -> tuple[str, int]:""",
        ),
        (
            """def potatoe(
    get_line = lambda lno: GLOBAL_LINES[lno]
):""",
            ["Callable[[int], str]"],
            "bool",
            """def potatoe(
    get_line: Callable[[int], str] = lambda lno: GLOBAL_LINES[lno]
) -> bool:""",
        ),
        (
            """def potatoe(
    get_line = ...
):""",
            ["Callable[[int], str]"],
            "bool",
            """def potatoe(
    get_line: Callable[[int], str] = ...
) -> bool:""",
        ),
        (
            """def get_timezone_or_utc(
    zone = None
):""",
            ["Union[int, None]"],
            "Union[pytz.tzfile.America/Los_Angeles, int]",
            """def get_timezone_or_utc(
    zone: int | None = None
) -> datetime.tzinfo | int:""",
        ),
        ("def meep(x: T):", ["T`1"], "T`1", "def meep(x: T) -> T:"),
        ("def meep(x: T):", ["T`1"], "T-1", "def meep(x: T) -> Any:"),
        (
            "async def pop_obj(obj_id: int):",
            ["float"],
            "object",
            "async def pop_obj(obj_id: int) -> object:",
        ),
        (
            "async def pop_obj(self, obj_id: int, /, **kwargs):",
            ["float", "str"],
            "object",
            "async def pop_obj(self, obj_id: int, /, **kwargs: str) -> object:",
        ),
        (
            "def apply(self, funcname, /, *args, **kwargs):",
            ["str", "Any", "Any"],
            "Any",
            "def apply(self, funcname: str, /, *args: Any, **kwargs: Any) -> Any:",
        ),
        (
            "def apply(self, function, /, *args, **kwargs):",
            ["Callable[ArgsT, RetT]", "ArgsT.args", "ArgsT.kwargs"],
            "RetT",
            "def apply(self, function: Callable[ArgsT, RetT], /, *args: ArgsT.args, **kwargs: ArgsT.kwargs) -> RetT:",
        ),
        (
            "def __repr__(self):",
            [],
            "str",
            "def __repr__(self) -> str:",
        ),
        (
            "def __repr__(self,):",
            [],
            "str",
            "def __repr__(self, ) -> str:",
        ),
        (
            "def get(valuetype = int):",
            ["type"],
            "object",
            "def get(valuetype: type = int) -> object:",
        ),
        (
            "def get(valuetype = int,):",
            ["type"],
            "object",
            "def get(valuetype: type = int, ) -> object:",
        ),
        (
            "def bitfield(self, bits: int = ~ALL_BITS):",
            ["int"],
            "int",
            "def bitfield(self, bits: int = ~ALL_BITS) -> int:",
        ),
        (
            "def bitfield(self, bits = ~ALL_BITS):",
            ["int"],
            "int",
            "def bitfield(self, bits: int = ~ALL_BITS) -> int:",
        ),
        (
            "def meep(x: T | None):",
            ["Union[T, None]"],
            "T`1",
            "def meep(x: T | None) -> T:",
        ),
        (
            "def meep(x):",
            ["Callable[..., Any]"],
            "Any",
            "def meep(x: Callable[..., Any]) -> Any:",
        ),
        (
            "def read_global(self, length = GLOBALSTART+GLOBALREAD):",
            ["int"],
            "int",
            "def read_global(self, length: int = GLOBALSTART + GLOBALREAD) -> int:",
        ),
        (
            "def meep(x = A @ B):",
            ["Matrix"],
            "Vector",
            "def meep(x: Matrix = A @ B) -> Vector:",
        ),
        (
            """def line_len(
    get_line = ...
):""",
            ["Callable[[], str]"],
            "int",
            """def line_len(
    get_line: Callable[[], str] = ...
) -> int:""",
        ),
        (
            """def line_len(
    get_line = ...
) -> int | None:""",
            ["Callable[[], str]"],
            "Union[int, None]",
            """def line_len(
    get_line: Callable[[], str] = ...
) -> int | None:""",
        ),
    ],
)
def test_get_annotation(
    function_text: str,
    arg_types: Sequence[str],
    return_type: str,
    result: str,
) -> None:
    annotation_dict = {
        "line": 0,
        "signature": {"arg_types": arg_types, "return_type": return_type},
    }

    lines = function_text.splitlines(True)

    def get_line(line_no: int) -> str:
        return lines[line_no]

    returned, _ = annotate.get_annotation(annotation_dict, get_line)
    if returned != result:
        print(f"{returned}\n!=\n{result}")
    assert returned == result

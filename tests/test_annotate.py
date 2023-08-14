"""Tests for annotate."""

from __future__ import annotations

from collections.abc import Collection, Sequence

import pytest
from idlemypyextension import annotate


def test_parse_error() -> None:
    with pytest.raises(annotate.ParseError, match=""):
        raise annotate.ParseError()


@pytest.mark.parametrize(
    ("text", "expect"),
    [("  waf", 2), ("cat", 0), ("     fish", 5), ("   ", 3), ("", 0)],
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


def test_typevalue_repr() -> None:
    assert (
        repr(
            annotate.TypeValue(
                "Union",
                (
                    annotate.TypeValue("set", (annotate.TypeValue("int"),)),
                    annotate.TypeValue("None"),
                ),
            ),
        )
        == "TypeValue('Union', (TypeValue('set', (TypeValue('int'),)), TypeValue('None')))"
    )


def test_typevalue_eq() -> None:
    assert annotate.TypeValue(
        "Union",
        (
            annotate.TypeValue("set", (annotate.TypeValue("int"),)),
            annotate.TypeValue("None"),
        ),
    ) == annotate.TypeValue(
        "Union",
        (
            annotate.TypeValue("set", (annotate.TypeValue("int"),)),
            annotate.TypeValue("None"),
        ),
    )


def test_typevalue_super_eq() -> None:
    assert (
        annotate.TypeValue(
            "Union",
            (
                annotate.TypeValue("set", (annotate.TypeValue("int"),)),
                annotate.TypeValue("None"),
            ),
        )
        != "potatoe"
    )


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
    ("text", "tokens"),
    [
        (
            "(int, float) -> str",
            [
                annotate.Separator("("),
                annotate.DottedName("int"),
                annotate.Separator(","),
                annotate.DottedName("float"),
                annotate.Separator(")"),
                annotate.Separator("->"),
                annotate.DottedName("str"),
                annotate.End(),
            ],
        ),
        (
            "pytz.tzfile.America/Los_Angeles",
            [
                annotate.DottedName("datetime.tzinfo"),
                annotate.End(),
            ],
        ),
    ],
)
def test_tokenize(text: str, tokens: list[annotate.Token]) -> None:
    result = annotate.tokenize(text)
    if result != tokens:
        print(f"{tokens}\n!=\n{result}")
    assert result == tokens


def test_invalid_tokenize() -> None:
    with pytest.raises(
        annotate.ParseError,
        match="Could not parse '\\$HOME' from 'path.\\$HOME'",
    ):
        annotate.tokenize("path.$HOME")


@pytest.mark.parametrize(
    ("text", "tokens"),
    [
        (
            "def test(value: int = -~ALL_BITS):",
            [
                annotate.Definition("def"),
                annotate.FunctionName("test"),
                annotate.EndSeparator("("),
                annotate.ArgumentName("value"),
                annotate.TypeDef(":"),
                annotate.DottedName("int"),
                annotate.DefaultDef("="),
                annotate.ArgumentDefault("-~ALL_BITS"),
                annotate.EndSeparator(")"),
                annotate.EndDefinition(":"),
                annotate.End(),
            ],
        ),
    ],
)
def test_tokenize_definition(text: str, tokens: list[annotate.Token]) -> None:
    lines = text.splitlines(True)

    def get_line(line_no: int) -> str:
        return lines[line_no]

    result, _ = annotate.tokenize_definition(0, get_line)

    if result != tokens:
        print(f"{tokens}\n!=\n{result}")
    assert result == tokens


def test_invalid_tokenize_definition() -> None:
    lines = "def def".splitlines(True)

    def get_line(line_no: int) -> str:
        return lines[line_no]

    with pytest.raises(
        annotate.ParseError,
        match="Did not expect second definition keyword",
    ):
        annotate.tokenize_definition(0, get_line)


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
            """def format_name(name = "TEMP"):""",
            ["str"],
            "str",
            """def format_name(name: str = "TEMP") -> str:""",
        ),
        (
            """def sleep(time = 1 / 3):""",
            ["float"],
            "None",
            """def sleep(time: float = 1 / 3) -> None:""",
        ),
        (
            """def format_id(
    user# format function inline comment
):""",
            ["int"],
            "str",
            """def format_id(
    user: int  # format function inline comment
) -> str:""",
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
        (
            """def test(value: int = -~ALL_BITS):""",
            ["int"],
            "None",
            """def test(value: int = -~ALL_BITS) -> None:""",
        ),
        (
            """def potatoe(
    get_line = lambda lno: "",
    lines = 0,
):""",
            ["Callable[[int], str]", "int"],
            "bool",
            """def potatoe(
    get_line: Callable[[int], str] = lambda lno: "",
    lines: int = 0,
) -> bool:""",
        ),
        (
            """def potatoe(
    get_line = lambda lno, default: (default),
    lines = 0,
):""",
            ["Callable[[int, str], str]", "int"],
            "bool",
            """def potatoe(
    get_line: Callable[[int, str], str] = lambda lno, default: (default),
    lines: int = 0,
) -> bool:""",
        ),
        (
            """def potatoe(
    get_line: Callable[[int, str], str] = lambda lno, default: (default),
    lines: int = 0,
) -> bool:""",
            ["Callable[[int, str], str]", "int"],
            "bool",
            """def potatoe(
    get_line: Callable[[int, str], str] = lambda lno, default: (default),
    lines: int = 0,
) -> bool:""",
        ),
        (
            """def wrapper(**kwargs) -> Any:""",
            ["Any"],
            "Any",
            """def wrapper(**kwargs: Any) -> Any:""",
        ),
        (
            """def frog(numbers = (2, 3)) -> int:""",
            ["Tuple[int, int]"],
            "int",
            """def frog(numbers: tuple[int, int] = (2, 3)) -> int:""",
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


def test_get_annotation_tokenization_falure() -> None:
    annotation_dict = {
        "line": 0,
    }

    lines = "def def".splitlines(True)

    def get_line(line_no: int) -> str:
        return lines[line_no]

    with pytest.raises(
        annotate.ParseError,
        match="Did not expect second definition keyword",
    ):
        annotate.get_annotation(annotation_dict, get_line)


def test_get_annotation_tokenization_eof_falure() -> None:
    annotation_dict = {
        "line": 0,
    }

    lines = "def waffle() -> str".splitlines(True)

    def get_line(line_no: int) -> str:
        if line_no > 0:
            return ""
        return lines[line_no]

    with pytest.raises(
        annotate.ParseError,
        match="Reached End of File, expected end of definition",
    ):
        annotate.get_annotation(annotation_dict, get_line)


def test_parse_type_list_no_close_failure() -> None:
    parser = annotate.Parser(
        [annotate.DottedName("int"), annotate.DottedName("notend")],
    )
    with pytest.raises(
        annotate.ParseError,
        match="Expected \\) or \\], got 'notend'",
    ):
        parser.parse_type_list()


def test_parse_union_list() -> None:
    parser = annotate.Parser(
        [
            annotate.DottedName("int"),
            annotate.Separator("|"),
            annotate.DottedName("str"),
            annotate.End(),
        ],
    )
    parser.parse_union_list()


def test_parse_single_no_empty_union_failure() -> None:
    parser = annotate.Parser(
        [
            annotate.DottedName("Union"),
            annotate.Separator("["),
            annotate.Separator("]"),
        ],
    )
    with pytest.raises(annotate.ParseError, match="No items in Union"):
        parser.parse_single()


def test_parse_single_no_null_collection_failure() -> None:
    parser = annotate.Parser(
        [
            annotate.DottedName(),
        ],
    )
    with pytest.raises(
        annotate.ParseError,
        match="Expected token text to be string, got None",
    ):
        parser.parse_single()


def test_peek_out_of_tokens_failure() -> None:
    parser = annotate.Parser([])
    with pytest.raises(
        annotate.ParseError,
        match="Ran out of tokens",
    ):
        parser.peek()


def test_expect_failure() -> None:
    parser = annotate.Parser([annotate.DottedName("waffle")])
    with pytest.raises(
        annotate.ParseError,
        match="Expected 'def', got 'waffle'",
    ):
        parser.expect("def")


def test_expect_type_failure() -> None:
    parser = annotate.Parser([annotate.DottedName("waffle")])
    with pytest.raises(
        annotate.ParseError,
        match="Expected 'ReturnTypeDef', got DottedName\\(text='waffle'\\)",
    ):
        parser.expect_type(annotate.ReturnTypeDef)


def test_expect_type_multi_failure() -> None:
    parser = annotate.Parser([annotate.DottedName("waffle")])
    with pytest.raises(
        annotate.ParseError,
        match="Expected 'ReturnTypeDef' or 'Separator', got DottedName\\(text='waffle'\\)",
    ):
        parser.expect_type((annotate.ReturnTypeDef, annotate.Separator))


@pytest.mark.parametrize(
    ("tokens", "value"),
    [
        (
            [
                annotate.DottedName("mypy_extensions.NoReturn"),
            ],
            annotate.TypeValue("NoReturn"),
        ),
        (
            [
                annotate.DottedName("typing.NoReturn"),
            ],
            annotate.TypeValue("NoReturn"),
        ),
        (
            [
                annotate.DottedName("Tuple"),
                annotate.Separator("["),
                annotate.DottedName("int"),
                annotate.Separator(","),
                annotate.DottedName("str"),
                annotate.Separator("]"),
            ],
            annotate.TypeValue(
                "Tuple",
                (
                    annotate.TypeValue("int"),
                    annotate.TypeValue("str"),
                ),
            ),
        ),
        (
            [
                annotate.DottedName("Union"),
                annotate.Separator("["),
                annotate.DottedName("int"),
                annotate.Separator("]"),
            ],
            annotate.TypeValue("int"),
        ),
        (
            [
                annotate.DottedName("Optional"),
                annotate.Separator("["),
                annotate.DottedName("int"),
                annotate.Separator("]"),
            ],
            annotate.TypeValue(
                "Union",
                (annotate.TypeValue("int"), annotate.TypeValue("None")),
            ),
        ),
        (
            [
                annotate.DottedName("Callable"),
                annotate.Separator("["),
                annotate.Separator("["),
                annotate.Separator("]"),
                annotate.Separator(","),
                annotate.DottedName("int"),
                annotate.Separator("]"),
            ],
            annotate.TypeValue(
                "Callable",
                (annotate.TypeValue("[]"), annotate.TypeValue("int")),
            ),
        ),
    ],
)
def test_parse_single(
    tokens: list[annotate.Token],
    value: annotate.TypeValue,
) -> None:
    parser = annotate.Parser(tokens)

    result = parser.parse_single()

    if value != result:
        print(f"{value}\n!=\n{result}")
    assert result == result

"""Annotate - Annotate functions given signature."""

# Extensively modified by CoolCat467

# Extensively modified from https://github.com/dropbox/pyannotate/blob/master/pyannotate_tools/annotations/parse.py

# Pyannotate is licensed under the terms of the Apache License, Version 2.0,
# reproduced below.
#   Copyright (c) 2017 Dropbox, Inc.
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

from __future__ import annotations

__title__ = "Annotate"
__author__ = "CoolCat467"
__license__ = "Apache License, Version 2.0"


import ast
import re
import tokenize
from typing import TYPE_CHECKING, Any, Final, NamedTuple, NoReturn

if TYPE_CHECKING:
    from collections.abc import Callable, Collection, Sequence

TYPING_LOWER: Final = {"List", "Set", "Type", "Dict", "Tuple", "Overload"}


class ParseError(Exception):
    """Raised on any type comment parse error.

    The 'comment' attribute contains the comment that produced the error.
    """

    def __init__(self, comment: str | None = None) -> None:
        """Initialize with comment."""
        if comment is None:
            comment = ""
        elif hasattr(self, "add_note"):  # New in Python 3.11
            self.add_note(comment)
        super().__init__(comment)


class Token(NamedTuple):
    """Base token."""

    text: str | None = None


class DottedName(Token):
    """An identifier token, such as 'List', 'int' or 'package.name'."""

    __slots__ = ()


class Separator(Token):
    """A separator or punctuator token such as '(', '[' or '->'."""

    __slots__ = ()


class End(Token):
    """A token representing the end of a type comment."""

    __slots__ = ()

    def __init__(self) -> None:
        """Initialize superclass with no arguments."""
        super().__init__()


def tokenize_annotation(txt: str) -> list[Token]:
    """Translate a type comment into a list of tokens."""
    original = txt
    txt = txt.replace("?", "")
    tokens: list[Token] = []
    while True:
        if not txt:
            tokens.append(End())
            return tokens
        if txt[0] in {" ", "\n"}:
            txt = txt[1:]
        elif txt[0] in "()[],*":
            tokens.append(Separator(txt[0]))
            txt = txt[1:]
        elif txt[:2] == "->":
            tokens.append(Separator("->"))
            txt = txt[2:]
        elif txt[:3] == "...":
            tokens.append(DottedName("..."))
            txt = txt[3:]
        else:
            match_ = re.match(r"[-\w`]+(\s*(\.|:)\s*[-/\w]*)*", txt)
            if not match_:
                raise ParseError(f"Could not parse {txt!r} from {original!r}")
            fullname = match_.group(0)
            size = len(fullname)
            fullname = fullname.replace(" ", "")
            if "`" in fullname:
                fullname = fullname.split("`")[0]
            # pytz creates classes with the name of the timezone being used:
            # https://github.com/stub42/pytz/blob/f55399cddbef67c56db1b83e0939ecc1e276cf42/src/pytz/tzfile.py#L120-L123
            # This causes pyannotate to crash as it's invalid to have a class
            # name with a `/` in it (e.g. "pytz.tzfile.America/Los_Angeles")
            if fullname.startswith("pytz.tzfile."):
                fullname = "datetime.tzinfo"
            if "-" in fullname or "/" in fullname:
                print(f"{__file__}: {fullname} -> Any")
                # Not a valid Python name; there are many places that
                # generate these, so we just substitute Any rather
                # than crashing.
                fullname = "Any"
            tokens.append(DottedName(fullname))
            txt = txt[size:]


def get_line_indent(text: str, char: str = " ") -> int:
    """Return line indent."""
    index = -1
    for index, cur_char in enumerate(text):
        if cur_char != char:
            return index
    return index + 1


def deindent(level: int, text: str) -> str:
    """Undo indent on text by level of characters."""
    prefix = " " * level
    return "\n".join(line.removeprefix(prefix) for line in text.splitlines())


def tokenize_definition(
    start_line: int,
    get_line: Callable[[int], str],
) -> tuple[ast.FunctionDef, int]:
    """Return Function Definition AST and number of lines after start."""
    current_line_no = start_line
    definition_lines = []

    def read_line() -> str:
        """Incremental wrapper for get_line."""
        nonlocal current_line_no
        value = get_line(current_line_no)
        definition_lines.append(value)
        current_line_no += 1
        return value

    hasdef = False  # Do we have a definition token?
    defstart = False  # Has definition started?
    brackets = 0  # Current number of brackets in use
    typedef = 0  # Brackets in type definition (truthy if in type definition)
    default_arg = 0  # Brackets in default argument value

    # For each token tokenizer module finds
    for token in tokenize.generate_tokens(read_line):
        string = token.string
        token_name = tokenize.tok_name[token.type]
        if token_name == "NAME":  # noqa: S105
            if string == "def":  # Error if more than one in case invalid start
                if hasdef:
                    raise ParseError(
                        "Did not expect second definition keyword",
                    )
                hasdef = True  # Have definition now
        elif token_name == "OP":  # noqa: S105
            if string in "([{":
                # We have traveled in an bracket level
                brackets += 1
                # If we have a definition and this is open parenthesis,
                # we are starting definition
                if not defstart and hasdef and string == "(":
                    defstart = True
                # If doing a type definition, we have typedef level
                if typedef:
                    typedef += 1
                if default_arg:
                    default_arg += 1
            elif string in ")]}":
                # Left a bracket level
                brackets -= 1
                if typedef:  # Maybe left a type def level too
                    typedef -= 1
                if default_arg:
                    default_arg -= 1
            elif string == ",":
                # If exactly one level, leaving type definition land
                if typedef == 1:
                    typedef = 0
                if default_arg == 1:
                    default_arg = 0
            elif string == "->":
                # We are defining a return type
                typedef = 1
            elif string == ":":
                if defstart and not brackets:
                    # Ran out of brackets so done defining function
                    typedef = 0
                    break
                typedef = 1
            elif string == "=":  # Defining a default definition
                typedef = 0  # shouldn't be defining type but make sure
                default_arg = 1
    definition = "".join(definition_lines).rstrip() + " ..."
    indent_level = get_line_indent(definition)
    definition = deindent(indent_level, definition)
    print(f"[{__title__}] DEBUG: {definition = }")

    code = ast.parse(definition, type_comments=True)
    ast_def = code.body[0]
    if not isinstance(ast_def, ast.FunctionDef):
        raise ParseError(f"Expected FunctionDef, got {type(ast_def)}")
    # print(f"{ast.unparse(ast_def)}")
    return ast_def, current_line_no - start_line


def get_type_repr(name: str) -> str:
    """Return representation of name."""
    for separator in (".", ":"):
        if separator in name:
            module, text = name.split(separator, 1)
            if module in ("typing", "mypy_extensions"):
                if text in TYPING_LOWER:
                    return text.lower()
                return text
    return name


def get_typevalue_repr(typevalue: TypeValue) -> str:
    """Return representation of ClassType."""
    name = get_type_repr(typevalue.name)
    if name in TYPING_LOWER:
        name = name.lower()
    args = []
    for arg in typevalue.args:
        args.append(get_typevalue_repr(arg))
    if not args:
        if name:
            return name
        return "[]"
    if name == "Union":
        return " | ".join(args)
    values = ", ".join(args)
    return f"{name}[{values}]"


def typevalue_as_ast(typevalue: TypeValue) -> ast.Name | ast.Subscript:
    """Convert TypeValue into AST Name or Subscript."""
    name = get_type_repr(typevalue.name)
    if not typevalue.args:
        return ast.Name(name, ast.Load())
    slice_: ast.Tuple | ast.Name | ast.Subscript
    if len(typevalue.args) > 1:
        type_args = [typevalue_as_ast(v) for v in typevalue.args]
        slice_ = ast.Tuple(type_args, ast.Load())
    else:
        slice_ = typevalue_as_ast(typevalue.args[0])

    return ast.Subscript(ast.Name(name, ast.Load()), slice_, ast.Load())


class TypeValue:
    """A type value, potentially collection of multiple."""

    __slots__ = ("name", "args")

    def __init__(
        self,
        name: str,
        args: Sequence[TypeValue] | None = None,
    ) -> None:
        """Set up name and arguments."""
        self.name = name
        if args:
            self.args = tuple(args)
        else:
            self.args = ()

    def __repr__(self) -> str:
        """Return representation of self."""
        args = f", {self.args!r}" if self.args else ""
        return f"TypeValue({self.name!r}{args})"

    def __str__(self) -> str:
        """Return type value representation of self."""
        return get_typevalue_repr(self)

    def __eq__(self, rhs: object) -> bool:
        """Return if rhs is equal to self."""
        if isinstance(rhs, self.__class__):
            return self.name == rhs.name and self.args == rhs.args
        return super().__eq__(rhs)


def list_or(values: Collection[str]) -> str:
    """Return comma separated listing of values joined with ` or `."""
    if len(values) <= 2:
        return " or ".join(values)
    copy = list(values)
    copy[-1] = f"or {copy[-1]}"
    return ", ".join(copy)


class Parser:
    """Implementation of the type comment parser."""

    __slots__ = ("tokens", "i")

    def __init__(self, tokens: list[Token]) -> None:
        """Initialize with tokens list."""
        self.tokens = tokens
        self.i = 0

    def parse_type_list(self) -> list[TypeValue]:
        """Parse comma separated type list."""
        types = []
        while self.lookup() not in (")", "]"):
            typ = self.parse_type()
            types.append(typ)
            string = self.lookup()
            if string == ",":
                self.expect(",")
            elif string not in {")", "]"}:
                self.fail(f"Expected ) or ], got {string!r}")
        return types

    def parse_union_list(self) -> list[TypeValue]:
        """Parse | separated union list."""
        types = []
        while True:
            typ = self.parse_type()
            types.append(typ)
            if self.lookup() != "|":
                return types
            self.expect("|")

    def parse_single(self) -> TypeValue:
        """Parse single, does not look for | unions. Do not use directly."""
        if self.lookup() == "[":
            # Callable[[...], ...]
            #          ^^^^^
            self.expect("[")
            args = self.parse_type_list()
            self.expect("]")
            return TypeValue("", args)
        token = self.expect_type(DottedName)
        if token.text == "Any":
            return TypeValue("Any")
        if token.text == "mypy_extensions.NoReturn":
            return TypeValue("NoReturn")
        if token.text == "typing.NoReturn":
            return TypeValue("NoReturn")
        if token.text == "Tuple":
            self.expect("[")
            args = self.parse_type_list()
            self.expect("]")
            return TypeValue(token.text, args)
        if token.text == "Union":
            self.expect("[")
            items = self.parse_type_list()
            self.expect("]")
            if len(items) == 1:
                return items[0]
            if len(items) == 0:
                self.fail("No items in Union")
            return TypeValue(token.text, items)
        if token.text == "lambda":
            lambda_data = self.parse_lambda()
            return TypeValue(f"{token.text} {lambda_data}")
        if self.lookup() == "[":
            self.expect("[")
            args = self.parse_type_list()
            self.expect("]")
            if token.text == "Optional" and len(args) == 1:
                return TypeValue("Union", [args[0], TypeValue("None")])
            return TypeValue(token.text or "None", args)
        return TypeValue(token.text or "None")

    def parse_lambda_arguments(self) -> list[str]:
        """Parse lambda arguments."""
        arguments = []
        while self.lookup() != ":":
            typ = self.expect_type(DottedName)
            assert typ.text is not None
            arguments.append(typ.text)
            string = self.lookup()
            if string == ",":
                self.expect(",")
            elif string not in {",", ":"}:
                self.fail(f"Expected , or :, got {string!r}")
        return arguments

    def parse_lambda(self) -> str:
        """Parse lambda expression."""
        arguments = ", ".join(self.parse_lambda_arguments())
        self.expect(":")
        value = f"{arguments}: "

        brackets = 0
        while not isinstance(self.peek(), End):
            if self.lookup() == "," and not brackets:
                break
            token = self.next()

            assert token.text is not None
            value += token.text

            if not isinstance(token, DottedName | Separator):
                value += " "

            if token.text in {"(", "[", "{"}:
                brackets += 1
            elif token.text in {")", "]", "}"}:
                brackets -= 1
                if not brackets:
                    break
        return value

    def parse_type(self) -> TypeValue:
        """Parse type including | unions."""
        type_value = self.parse_single()
        if self.lookup() == "|":
            self.expect("|")
            args = [type_value, *self.parse_union_list()]
            return TypeValue("Union", args)
        return type_value

    def fail(self, error: str | None) -> NoReturn:
        """Raise parse error."""
        raise ParseError(error)

    def peek(self) -> Token:
        """Peek at next token."""
        if self.i >= len(self.tokens):
            self.fail("Ran out of tokens")
        return self.tokens[self.i]

    def next(self) -> Token:
        """Get next token."""
        token = self.peek()
        self.i += 1
        return token

    def expect(self, text: str) -> None:
        """Expect next token text to be text."""
        got = self.next().text
        if got != text:
            self.fail(f"Expected {text!r}, got {got!r}")

    def expect_type(
        self,
        token_type: type[Token] | tuple[type[Token], ...],
    ) -> Token:
        """Expect next token to be instance of token_type. Return token."""
        token = self.next()
        if not isinstance(token, token_type):
            if isinstance(token_type, tuple):
                expect_str = list_or(
                    [f"{cls.__name__!r}" for cls in token_type],
                )
            else:
                expect_str = f"{token_type.__name__!r}"
            self.fail(f"Expected {expect_str}, got {token!r}")
        return token

    def lookup(self) -> str:
        """Peek at next token and return it's text."""
        value = self.peek().text
        if value is None:
            return "None"
        return value

    def back(self) -> None:
        """Go back one token."""
        self.i -= 1

    def rest_tokens(self) -> list[Token]:
        """Return all tokens not processed."""
        return self.tokens[self.i :]


def get_annotation(
    annotation: dict[str, Any],
    get_line: Callable[[int], str],
) -> tuple[str, int]:
    """Return annotation and end line."""
    # print(f"[DEBUG] Annotate: {annotation = }\n")

    # Get definition tokens
    try:
        func_ast, line_count = tokenize_definition(
            annotation["line"],
            get_line,
        )
    except ParseError:
        print(f"Could not tokenize definition\n{annotation = }")
        raise
    except EOFError as exc:
        raise ParseError(
            "Reached End of File, expected end of definition",
        ) from exc

    # Get the argument and return tokens from signature
    signature = annotation["signature"]
    arg_tokens = [tokenize_annotation(arg) for arg in signature["arg_types"]]
    return_tokens = tokenize_annotation(signature["return_type"])

    arg_idx = 0
    for attr in ("posonlyargs", "args", "vararg", "kwonlyargs", "kwarg"):
        arg_list = getattr(func_ast.args, attr, [])
        if not arg_list:
            continue
        for argument in arg_list:
            if argument.annotation is not None:
                arg_idx += 1
                continue
            parser = Parser(arg_tokens[arg_idx])
            type_value = parser.parse_type()
            argument.annotation = typevalue_as_ast(type_value)
            arg_idx += 1
    if func_ast.returns is None:
        parser = Parser(return_tokens)
        type_value = parser.parse_type()
        func_ast.returns = typevalue_as_ast(type_value)

    new_lines = "\n".join(ast.unparse(func_ast).splitlines()[:-1])

    return new_lines, line_count


def run(annotation: dict[str, str]) -> None:
    """Run test of module."""

    def get_line(line: int) -> str:
        path = annotation["path"]
        assert isinstance(path, str), "Path must be string"
        with open(path, encoding="utf-8") as files:
            for line_no, line_text in enumerate(files):
                if line_no == line - 1:
                    return line_text
            raise EOFError

    print(f"{get_annotation(annotation, get_line)[0]!r}")


if __name__ == "__main__":
    print(f"{__title__}\nProgrammed by {__author__}.\n")
    # annotation = {
    #
    # }
    # run(annotation)

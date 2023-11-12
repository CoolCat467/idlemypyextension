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


import re
from collections.abc import Callable, Collection, Generator, Sequence
from tokenize import TokenInfo, generate_tokens, tok_name
from typing import Any, Final, NamedTuple, NoReturn

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
            self.add_note(comment)  # pragma: nocover
        super().__init__(comment)


class Token(NamedTuple):
    """Base token."""

    text: str | None = None


class LambdaBody(Token):
    """Lambda Body Text Token."""

    __slots__ = ()


class Name(Token):
    """Name Token."""

    __slots__ = ()


class FunctionName(Token):
    """Function name."""

    __slots__ = ()


class ArgumentName(Name):
    """Argument name."""

    __slots__ = ()


class Operator(Token):
    """Operator Token."""

    __slots__ = ()


class DottedName(Name):
    """An identifier token, such as 'List', 'int' or 'package.name'."""

    __slots__ = ()


class ArgumentDefault(DottedName):
    """Argument value."""

    __slots__ = ()


class Separator(Operator):
    """A separator or punctuator token such as '(', '[' or '->'."""

    __slots__ = ()


class EndSeparator(Separator):

    """End separator that does not need extra space."""


class Colin(Separator):
    """Colin ':'."""

    __slots__ = ()


class TypeDef(Colin):
    """Type Definition Start ':'."""

    __slots__ = ()


class DefaultDef(Separator):
    """Argument Default Definition Start '='."""

    __slots__ = ()


class Keyword(Name):
    """Keyword such as 'async', 'def'."""

    __slots__ = ()


class ReturnTypeDef(Separator):
    """Return type definition '->'."""

    __slots__ = ()


class Definition(Keyword):
    """Definition keyword."""

    __slots__ = ()


class EndDefinition(Colin):
    """End Definition Colin."""

    __slots__ = ()


class End(Token):
    """A token representing the end of a type comment."""

    __slots__ = ()

    def __init__(self) -> None:
        """Initialize superclass with no arguments."""
        super().__init__()


def tokenize(txt: str) -> list[Token]:
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
                print(f"{__file__}: {fullname!r} -> Any")
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


def read_lambda(generator: Generator[TokenInfo, None, None]) -> str:
    """Return lambda body text."""
    text = []

    brackets = 0  # Current number of brackets in use
    has_args = False

    for token in generator:
        string = token.string
        type_ = tok_name[token.type]
        # print(f'{string = }')
        if type_ == "OP":
            if string in "([{":
                # We have traveled in an bracket level
                brackets += 1
            elif string in ")]}":
                # Left a bracket level
                brackets -= 1
            elif string == ":":
                has_args = True
                string += " "
            elif string == ",":
                string += " "
        text.append(string)
        if (
            token.end[1] < len(token.line)
            and token.line[token.end[1]] in {",", "\n"}
            and has_args
            and not brackets
        ):
            return "".join(text)
    raise ParseError("Reading lambda failed")  # pragma: nocover


def read_fstring(
    starting_token: TokenInfo,
    generator: Generator[TokenInfo, None, None],
) -> str:
    """Return f-string text."""
    text = [starting_token.string]

    for token in generator:
        string = token.string
        type_ = tok_name[token.type]
        # print(f'{string = }')
        if type_ == "FSTRING_START":
            string = read_fstring(token, generator)
        text.append(string)
        if type_ == "FSTRING_END":
            return "".join(text)
    raise ParseError("Reading f-string failed")  # pragma: nocover


def tokenize_definition(
    start_line: int,
    get_line: Callable[[int], str],
) -> tuple[list[Token], int]:
    """Return list of Tokens and number of lines after start."""
    current_line_no = start_line

    def read_line() -> str:
        """Return next line."""
        nonlocal current_line_no
        value = get_line(current_line_no)
        # print(f'read_line: {value!r}')
        current_line_no += 1
        return value

    hasdef = False  # Do we have a definition token?
    defstart = False  # Has definition started?
    brackets = 0  # Current number of brackets in use
    typedef = 0  # Brackets in type definition (truthy if in type definition)
    default_arg = 0  # Brackets in default argument value
    indent = 0  # Current indent
    tokens: list[Token] = []

    # For each token tokenizer module finds
    token_generator = generate_tokens(read_line)
    for token in token_generator:
        # print(f'{tok_name[token.type]} {token.string!r}', end=' -> ')
        string = token.string
        if tok_name[token.type] == "NAME":
            if string == "async":  # Remember async
                tokens.append(Keyword(string))
            elif (
                string == "def"
            ):  # Error if more than one in case invalid start
                if hasdef:
                    raise ParseError(
                        "Did not expect second definition keyword",
                    )
                tokens.append(Definition(string))
                hasdef = True  # Have definition now
            elif not defstart:  # If not started definition, only function name
                tokens.append(FunctionName(string))
            elif typedef:  # If we are doing type definition, add DottedName
                # If last was also a DottedName and it ended with a dot,
                # instead add name text to previous
                if (
                    tokens
                    and isinstance(tokens[-1], DottedName)
                    and tokens[-1].text is not None
                    and tokens[-1].text.endswith(".")
                ):
                    previous = tokens.pop().text
                    assert previous is not None
                    tokens.append(DottedName(previous + string))
                else:
                    tokens.append(DottedName(string))
            elif default_arg and string == "lambda":
                tokens.append(ArgumentDefault(string))
                tokens.append(LambdaBody(read_lambda(token_generator)))
            elif default_arg:
                # If defining argument default, add ArgumetDefault
                if tokens and isinstance(tokens[-1], ArgumentDefault):
                    assert tokens[-1].text is not None
                    last = tokens[-1].text.rstrip()[-1]
                    if last in {"+", "-"}:
                        previous = tokens.pop().text
                        assert previous is not None
                        tokens.append(ArgumentDefault(f"{previous} {string}"))
                    else:
                        previous = tokens.pop().text
                        assert previous is not None
                        tokens.append(ArgumentDefault(previous + string))
                else:
                    tokens.append(ArgumentDefault(string))
            else:  # Otherwise is an argument name
                tokens.append(ArgumentName(string))
        elif tok_name[token.type] == "OP":
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
                # if default_arg:
                #     default_arg += 1
                tokens.append(EndSeparator(string))  # No spaces
            elif string in ")]}":
                # Left a bracket level
                brackets -= 1
                if typedef:  # Maybe left a type def level too
                    typedef -= 1
                if default_arg:
                    default_arg -= 1
                tokens.append(EndSeparator(string))
            elif string in {"*", "**", "/"} and not default_arg:
                tokens.append(EndSeparator(string))
            elif string == "|":
                tokens.append(Separator(string))
            elif string == ",":
                # If exactly one level, leaving type definition land
                if typedef == 1:
                    typedef = 0
                if default_arg == 1:
                    default_arg = 0
                tokens.append(Separator(string))  # Space on end
            elif string == "->":
                # We are defining a return type
                tokens.append(ReturnTypeDef(string))
                typedef = 1
            elif string == ":":
                if defstart and not brackets:
                    # Ran out of brackets so done defining function
                    tokens.append(EndDefinition(string))
                    typedef = 0
                    break
                tokens.append(TypeDef(string))
                typedef = 1
            elif string == "=":  # Defining a default definition
                tokens.append(DefaultDef(string))
                typedef = 0  # shouldn't be defining type but make sure
                default_arg = 1
            elif string in {"-", "+", "~"}:  # Unary operators
                # Add on to previous ArgumentDefault if it exists
                if tokens and isinstance(tokens[-1], ArgumentDefault):
                    previous = tokens.pop().text
                    assert previous is not None
                    if string in {"-", "+"}:
                        tokens.append(ArgumentDefault(f"{previous} {string}"))
                    else:
                        tokens.append(ArgumentDefault(previous + string))
                else:
                    tokens.append(ArgumentDefault(string))
            elif (
                string
                in {
                    "/",
                    "//",
                    "*",
                    "^",
                    "@",
                    "%",
                    "**",
                    ">>",
                    "<<",
                    "&",
                    "|",
                }
                and tokens
                and isinstance(tokens[-1], ArgumentDefault)
            ):  # All other math operators
                prev = tokens.pop().text
                assert prev is not None
                tokens.append(ArgumentDefault(f"{prev} {string} "))
            elif string == "." and (
                tokens and isinstance(tokens[-1], DottedName)
            ):
                previous = tokens.pop().text
                assert previous is not None
                tokens.append(DottedName(previous + string))
            elif string == "...":  # Ellipsis constant
                tokens.append(DottedName(string))
            else:  # pragma: no cover
                raise ParseError(f"Exhaustive list of OP failed: {string!r}")
        elif tok_name[token.type] in {"NL", "NEWLINE"}:
            # replace separator ends with end separators
            if tokens and isinstance(tokens[-1], Separator):
                tokens.append(EndSeparator(tokens.pop().text))
            tokens.append(EndSeparator(string))
            # we have a new indent level
            indent = get_line_indent(get_line(current_line_no))
            tokens.append(EndSeparator(" " * indent))
        elif tok_name[token.type] == "COMMENT":
            # Remember comments as separators
            tokens.append(EndSeparator(f"  {string}"))
        elif tok_name[token.type] in {"STRING", "NUMBER"}:
            # Only argument default, so add on to previous if exists
            if tokens and isinstance(tokens[-1], ArgumentDefault):
                previous = tokens.pop().text
                assert previous is not None
                tokens.append(ArgumentDefault(previous + string))
            else:
                tokens.append(ArgumentDefault(string))
        elif tok_name[token.type] == "INDENT":  # pragma: nocover
            tokens.append(EndSeparator(string))
        elif tok_name[token.type] == "FSTRING_START":
            tokens.append(
                ArgumentDefault(read_fstring(token, token_generator)),
            )
        elif tok_name[token.type] == "ENDMARKER":
            raise EOFError(
                "Found ENDMARKER token while reading function definition",
            )
        else:  # pragma: nocover
            print(f"[DEBUG] {token = }")
            raise ParseError(
                f"Unrecognized token type {tok_name[token.type]!r}",
            )
        # print(tokens[-1])
    # print(tokens[-1])
    # print()
    tokens.append(End())
    return tokens, current_line_no - start_line


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
            typ = self.parse_single()
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
        if token.text is None:
            self.fail("Expected token text to be string, got None")
        if token.text == "Any":
            return TypeValue("Any")
        if token.text in {"mypy_extensions.NoReturn", "typing.NoReturn"}:
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
        if token.text == "Overload":
            self.expect("(")
            args = self.parse_type_list()
            self.expect(")")
            return TypeValue(token.text, args)
        if self.lookup() == "[":
            self.expect("[")
            args = self.parse_type_list()
            self.expect("]")
            if token.text == "Optional" and len(args) == 1:
                return TypeValue("Union", [args[0], TypeValue("None")])
            return TypeValue(token.text, args)
        return TypeValue(token.text)

    def parse_lambda(self) -> str:
        """Parse lambda expression."""
        body = self.expect_type(LambdaBody)
        assert body.text is not None
        return body.text

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

    def next(self) -> Token:  # noqa: A003
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
        return self.tokens[self.i : len(self.tokens)]


def get_annotation(
    annotation: dict[str, Any],
    get_line: Callable[[int], str],
) -> tuple[str, int]:
    """Return annotation and end line."""
    # print(f"[DEBUG] Annotate: {annotation = }\n")

    # Get definition tokens
    try:
        def_tokens, line_count = tokenize_definition(
            annotation["line"],
            get_line,
        )
    except ParseError:
        print(f"Could not tokenize definition\n{annotation = }")
        raise
    except EOFError as exc:
        print(f"[ERROR] Annotate: {annotation = }\n")
        raise ParseError(
            "Reached End of File, expected end of definition",
        ) from exc

    # Get the argument and return tokens from signature
    signature = annotation["signature"]
    arg_tokens = [tokenize(arg) for arg in signature["arg_types"]]
    return_tokens = tokenize(signature["return_type"])

    # Find start of argument definition
    new_lines = ""
    parser = Parser(def_tokens)
    while True:
        token = parser.next()
        if isinstance(token, ArgumentName):
            parser.back()
            break
        if token.text == ")":
            parser.back()
            break
        assert (
            token.text is not None
        ), "Unreachable, End token is the only null text token"
        new_lines += token.text
        if isinstance(token, Keyword):
            new_lines += " "

    # Find out which arguments we have to skip (*, **, /)
    skip_args: set[int] = set()
    # print(f'{parser.rest_tokens() = }\n')
    argument = 0
    argparser = Parser(parser.rest_tokens())
    while True:
        if isinstance(argparser.peek(), ReturnTypeDef | EndDefinition):
            break

        token = argparser.next()
        if isinstance(token, Separator):
            if token.text in {"/", "*"}:
                skip_args.add(argument)
                argument += 1
                # if argparser.lookup() == "*":
                #     argparser.expect("*")

        elif isinstance(token, ArgumentName):
            argument += 1
        elif isinstance(token, End):  # pragma: nocover
            raise ParseError(
                "Found End token during argument location handling",
            )
    # print(f"{skip_args = } {len(arg_tokens) = } {argument = }")

    arg_place = len(arg_tokens) - argument
    if arg_place < 0:
        # Self or class argument does not require type so annotations are
        # not given
        skip_args.add(0)
        arg_place = -1
    # print(f"{skip_args = }")

    # Handle arguments
    argument = 0
    while True:
        token = parser.next()
        # print(f"{token = } ({argument = })")
        if isinstance(token, Separator):
            if isinstance(token, EndSeparator):
                assert token.text is not None
                new_lines += token.text
            else:
                new_lines += f"{token.text} "
            if token.text in {"*", "/"}:
                argument += 1
            if token.text == ")":
                break
        elif isinstance(token, ArgumentName):
            name = token.text
            type_text = ""
            if isinstance(parser.peek(), TypeDef):
                parser.expect(":")
                type_value = parser.parse_type()
                type_text = ": " + str(type_value)
            elif argument not in skip_args:
                type_value = Parser(arg_tokens[arg_place]).parse_type()
                type_text = ": " + str(type_value)
            if isinstance(parser.peek(), DefaultDef):
                parser.expect("=")
                type_text += " = "
                if isinstance(parser.peek(), EndSeparator):
                    type_text += f"{parser.next().text}"
                    type_text += ", ".join(map(str, parser.parse_type_list()))
                    type_text += f"{parser.next().text}"
                else:
                    type_text += str(parser.parse_type())
            # print(f"{name}{type_text}")
            new_lines += f"{name}{type_text}"
            argument += 1
            arg_place += 1
        elif isinstance(token, End):  # pragma: no cover
            print("Found End token during argument parsing")
            parser.back()
            break
    # print(f'{type_text = }')

    # Handle the end
    if isinstance(parser.peek(), EndDefinition | End):
        parser.tokens = (
            [ReturnTypeDef("->")] + return_tokens[:-1] + parser.rest_tokens()
        )
        parser.i = 0
    # print(f'{parser.rest_tokens() = }')
    parser.expect("->")
    new_lines += " -> "
    ret_type = str(parser.parse_type())
    new_lines += ret_type
    while True:
        token = parser.next()
        if isinstance(token, End):
            break
        assert token.text is not None
        new_lines += token.text

    return new_lines, line_count


def run(annotation: dict[str, str]) -> None:  # pragma: nocover
    """Run test of module."""

    def get_line(line: int) -> str:
        path = annotation["path"]
        assert isinstance(path, str), "Path must be string"
        with open(path, encoding="utf-8") as files:
            for line_no, line_text in enumerate(files):
                if line_no == line - 1:
                    return line_text
            raise EOFError

    print(f"{get_annotation(annotation, get_line)!r}")


if __name__ == "__main__":  # pragma: nocover
    print(f"{__title__}\nProgrammed by {__author__}.\n")
    # run()

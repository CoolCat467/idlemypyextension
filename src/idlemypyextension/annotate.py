#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Annotate - Annotate functions given signature

"Annotate functions given signature"

# Extensively modified by CoolCat467

# Extensively modified from https://github.com/dropbox/pyannotate/blob/master/pyannotate_tools/annotations/parse.py

## Pyannotate is licensed under the terms of the Apache License, Version 2.0,
## reproduced below.
##   Copyright (c) 2017 Dropbox, Inc.
##
##   Licensed under the Apache License, Version 2.0 (the "License");
##   you may not use this file except in compliance with the License.
##   You may obtain a copy of the License at
##
##       http://www.apache.org/licenses/LICENSE-2.0
##
##   Unless required by applicable law or agreed to in writing, software
##   distributed under the License is distributed on an "AS IS" BASIS,
##   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
##   See the License for the specific language governing permissions and
##   limitations under the License.

from __future__ import annotations

__title__ = 'Annotate'
__license__ = 'Apache License, Version 2.0'

from typing import Any, NoReturn, Final, Sequence
from collections.abc import Callable
import re
from tokenize import generate_tokens, tok_name

BUILTINS: Final = {'List', 'Set', 'Type', 'Dict', 'Tuple'}

class ParseError(Exception):
    """Raised on any type comment parse error.
    The 'comment' attribute contains the comment that produced the error.
    """

    def __init__(self, comment: str | None = None) -> None:
        if comment is None:
            comment = ''
        elif hasattr(self, 'add_note'):  # New in Python 3.11
            self.add_note(comment)
        super(ParseError, self).__init__(comment)

class Token:
    "Base token"
    __slots__ = ('text')
    def __init__(self, text: str | None = None) -> None:
        self.text = text

    def __repr__(self) -> str:
        value = '' if self.text is None else f'{self.text!r}'
        return f'{self.__class__.__name__}({value})'

class Name(Token):
    """Name Token"""

class FunctionName(Token):
    """Function name"""

class ArgumentName(Name):
    """Argument name"""

class Operator(Token):
    """Operator Token"""

class DottedName(Name):
    """An identifier token, such as 'List', 'int' or 'package.name'"""

class ArgumentDefault(DottedName):
    """Argument value"""

class Separator(Operator):
    """A separator or punctuator token such as '(', '[' or '->'"""

class EndSeparator(Separator):
    """End seprator that does not need extra space"""

class Colin(Separator):
    """Colin ':'"""

class TypeDef(Colin):
    """Type Definition Start ':'"""

class DefaultDef(Separator):
    """Argumen Default Definiition Start '='"""

class Keyword(Name):
    """Keyword such as 'async', 'def'"""

class ReturnTypeDef(Separator):
    """Return type definition '->'"""

class Definition(Keyword):
    """Definition keyword"""

class EndDefinition(Colin):
    """End Definition Colin"""

class End(Token):
    """A token representing the end of a type comment"""
    def __init__(self) -> None:
        super().__init__()

def tokenize(s: str) -> list[Token]:
    """Translate a type comment into a list of tokens."""
    original = s
    s = s.replace('?', '')
    tokens: list[Token] = []
    while True:
        if not s:
            tokens.append(End())
            return tokens
        elif s[0] in {' ', '\n'}:
            s = s[1:]
        elif s[0] in '()[],*':
            tokens.append(Separator(s[0]))
            s = s[1:]
        elif s[:2] == '->':
            tokens.append(Separator('->'))
            s = s[2:]
        elif s[:3] == '...':
            tokens.append(DottedName('...'))
            s = s[3:]
        else:
            m = re.match(r'[-\w`]+(\s*(\.|:)\s*[-/\w]*)*', s)
            if not m:
                raise ParseError(f'Could not parse {s!r} from {original!r}')
            fullname = m.group(0)
            fullname = fullname.replace(' ', '')
            if '`' in fullname:
                fullname = fullname.split('`')[0]
            # pytz creates classes with the name of the timezone being used:
            # https://github.com/stub42/pytz/blob/f55399cddbef67c56db1b83e0939ecc1e276cf42/src/pytz/tzfile.py#L120-L123
            # This causes pyannotates to crash as it's invalid to have a class
            # name with a `/` in it (e.g. "pytz.tzfile.America/Los_Angeles")
            if fullname.startswith('pytz.tzfile.'):
                fullname = 'datetime.tzinfo'
            if '-' in fullname or '/' in fullname:
                print(f'{__file__}: {fullname} -> Any')
                # Not a valid Python name; there are many places that
                # generate these, so we just substitute Any rather
                # than crashing.
                fullname = 'Any'
            tokens.append(DottedName(fullname))
            s = s[len(m.group(0)):]


def get_line_indent(text: str, char: str = ' ') -> int:
    "Return line indent"
    for idx, cur in enumerate(text.split(char)):
        if cur != '':
            return idx
    return 0


def tokenize_definition(line: int,
                        get_line: Callable[[int], str]) -> list[Token]:
    "Tokenize function definition"
    def read_line() -> str:
        "Incremental wrapper for get_line"
        nonlocal line
        value = get_line(line)
##        print(f'{value!r}')
        line += 1
        return value

    hasdef = False  # Do we have a definition token?
    defstart = False  # Has definition started?
    brackets = 0  # Current number of brackets in use
    typedef = 0  # Brackets in type definition (truthy if in type definition)
    indent = 0  # Current indent
    tokens: list[Token] = []

    # For each token tokenizer module finds
    for token in generate_tokens(read_line):
##        print(f'{tok_name[token.type]} {token.string!r}', end=' -> ')
        string = token.string
        if tok_name[token.type] == 'NAME':
            if string == 'async':  # Remember async
                tokens.append(Keyword(string))
            elif string == 'def':  # Error if more than one incase invalid start
                if hasdef:
                    raise ParseError('Did not expect second definition keyword')
                tokens.append(Definition(string))
                hasdef = True  # Have definition now
            elif not defstart:  # If not started definition, only function name
                tokens.append(FunctionName(string))
            elif typedef:  # If we are doing type definition, add DottedName
                # If last was also a DottedName and it ended with a dot,
                # instead add name text to previous
                if (tokens and isinstance(tokens[-1], DottedName)
                    and tokens[-1].text.endswith('.')):
                    tokens.append(DottedName(tokens.pop().text + string))
                else:
                    tokens.append(DottedName(string))
            elif tokens and isinstance(tokens[-1], DefaultDef):
                # If previous was a DefaultDef, must be ArgumentDefault
                tokens.append(ArgumentDefault(string))
            else:  # Otherwise is an argument name
                tokens.append(ArgumentName(string))
        elif tok_name[token.type] == 'OP':
            if string in '([{':
                # We have traveled in an bracket level
                brackets += 1
                # If we have a definition and this is open parenthisis,
                # we are starting definition
                if not defstart and hasdef and string == '(':
                    defstart = True
                # If doing a type definition, we have typedef level
                if typedef:
                    typedef += 1
                tokens.append(EndSeparator(string))  # No spaces
            elif string in ')]}':
                # Left a bracket level
                brackets -= 1
                if typedef:  # Maybe left a type def level too
                    typedef -= 1
                tokens.append(EndSeparator(string))
            elif string in {'*', '**'}:
                tokens.append(EndSeparator(string))
            elif string == '|':
                tokens.append(Separator(string))
            elif string == ',':
                # If exactly one level, leaving type definition land
                if typedef == 1:
                    typedef = 0
                tokens.append(Separator(string))  # Space on end
            elif string == '->':
                # We are defining a return type
                tokens.append(ReturnTypeDef(string))
                typedef = 1
            elif string == ':':
                if defstart and not brackets:
                    # Ran out of brackets so done defining function
                    tokens.append(EndDefinition(string))
                    typedef = 0
                    break
                tokens.append(TypeDef(string))
                typedef = 1
            elif string == '=':  # Defining a default definition
                tokens.append(DefaultDef(string))
                typedef = 0  # shouldn't be defining type but make sure
            elif string in {'-', '+', '~'}:  # Unary operators
                # Add on to previous ArgumentDefault if it exists
                if tokens and isinstance(tokens[-1], ArgumentDefault):
                    tokens.append(ArgumentDefault(tokens.pop().text + string))
                else:
                    tokens.append(ArgumentDefault(string))
            elif string in {'/', '//', '*', '^', '@', '%', '**',
                            '>>', '<<', '&', '|'}:  # All other math operators
                if tokens and isinstance(tokens[-1], ArgumentDefault):
                    # In-place mathmatics for default argument, add
                    # on to previous if exists
                    tokens.append(ArgumentDefault(tokens.pop().text
                                                  + ' ' + string + ' '))
                elif string == '@' and not hasdef:
                    # Not matrix mult, decorator
                    tokens.append(EndSeparator(string))
                else:
                    tokens.append(ArgumentDefault(string))
            elif string == '.' and (tokens
                                    and isinstance(tokens[-1], DottedName)):
                tokens.append(DottedName(tokens.pop().text + string))
            elif string == '...':  # Elipsis constant
                tokens.append(DottedName(string))
            else:
                raise ParseError(f'Exaustive list of OP failed: {string}')
        elif tok_name[token.type] == 'INDENT':
            tokens.append(EndSeparator(string))
            indent = len(string)
        elif tok_name[token.type] in {'NL', 'NEWLINE'}:
            # replace seperator ends with end seperators
            if tokens and isinstance(tokens[-1], Separator):
                tokens.append(EndSeparator(tokens.pop().text))
            tokens.append(EndSeparator(string))
            # we have a new indent level
            indent = get_line_indent(get_line(line))
            tokens.append(EndSeparator(' '*indent))
        elif tok_name[token.type] == 'COMMENT':
            # Remember comments as seperators
            tokens.append(EndSeparator(string))
        elif tok_name[token.type] in {'STRING', 'NUMBER'}:
            # Only argument default, so add on to previous if exists
            if tokens and isinstance(tokens[-1], ArgumentDefault):
                tokens.append(ArgumentDefault(tokens.pop().text + string))
            else:
                tokens.append(ArgumentDefault(string))
        else:
            raise ParseError(f'Unrecognized token type {tok_name[token.type]}')
##        print(tokens[-1])
##    print(tokens[-1])
##    print()
    tokens.append(End())
    return tokens


def get_type_repr(name: str) -> str:
    "Get representation of name"
    if '.' in name:
        module, text = name.split('.', 1)
        if module == 'typing' and text in BUILTINS:
            return text.lower()
    if ':' in name:
        module, text = name.split(':', 1)
        if module == 'typing' and text in BUILTINS:
            return text.lower()
##        return text
    return name


def get_typevalue_repr(typevalue: 'TypeValue') -> str:
    "Get representation of ClassType"
    name = get_type_repr(typevalue.name)
    if name in BUILTINS:
        name = name.lower()
    args = []
    for arg in typevalue.args:
        args.append(get_typevalue_repr(arg))
    if not args:
        return name
    if name == 'Union':
        return ' | '.join(args)
    values = ', '.join(args)
    return f'{name}[{values}]'


class TypeValue:
    """A type value, potentially collection of multiple"""
    __slots__ = ('name', 'args')
    def __init__(self,
                 name: str,
                 args: Sequence['TypeValue'] | None = None) -> None:
        self.name = name
        if args:
            self.args = tuple(args)
        else:
            self.args = ()

    def __repr__(self) -> str:
        return f'TypeValue({self.name!r}, {self.args!r})'

    def __str__(self) -> str:
        return get_typevalue_repr(self)


class Parser:
    """Implementation of the type comment parser"""
    __slots__ = ('tokens', 'i')
    def __init__(self, tokens: list[Token]) -> None:
        self.tokens = tokens
        self.i = 0

    def parse_type_list(self) -> list[TypeValue]:
        "Parse comma seperated type list"
        types = []
        while self.lookup() not in (')', ']'):
            typ = self.parse_type()
            types.append(typ)
            string = self.lookup()
            if string == ',':
                self.expect(',')
            elif string not in {')', ']'}:
                self.fail(f'Expected ) or ], got {string!r}')
        return types

    def parse_union_list(self) -> list[TypeValue]:
        "Parse | seperated union list"
        types = []
        while True:
            typ = self.parse_type()
            types.append(typ)
            if self.lookup() != '|':
                return types
            else:
                self.expect('|')

    def parse_single(self) -> TypeValue:
        "Parse single, does not look for | unions. Do not use directly."
        if self.lookup() == '[':
            # Callable[[...], ...]
            #          ^^^^^
            self.expect('[')
            args = self.parse_type_list()
            self.expect(']')
            return TypeValue('', args)
        t = self.expect_type(DottedName)
        if t.text == 'Any':
            return TypeValue('Any')
        elif t.text == 'mypy_extensions.NoReturn':
            return TypeValue('NoReturn')
        elif t.text == 'typing.NoReturn':
            return TypeValue('NoReturn')
        elif t.text == 'Tuple':
            self.expect('[')
            args = self.parse_type_list()
            self.expect(']')
            return TypeValue(t.text, args)
        elif t.text == 'Union':
            self.expect('[')
            items = self.parse_type_list()
            self.expect(']')
            if len(items) == 1:
                return items[0]
            elif len(items) == 0:
                self.fail('No items in Union')
            else:
                return TypeValue(t.text, items)
        else:
            if self.lookup() == '[':
                self.expect('[')
                args = self.parse_type_list()
                self.expect(']')
                if t.text == 'Optional' and len(args) == 1:
                    return TypeValue('Union', [args[0], TypeValue('None')])
                if t.text is None:
                    t.text = 'None'
                return TypeValue(t.text, args)
            else:
                if t.text is None:
                    t.text = 'None'
                return TypeValue(t.text)

    def parse_type(self) -> TypeValue:
        "Parse type including | unions"
        type_value = self.parse_single()
        if self.lookup() == '|':
            self.expect('|')
            args = [type_value] + self.parse_union_list()
            return TypeValue('Union', args)
        return type_value

    def fail(self, error: str | None) -> NoReturn:
        "Raise parse error"
        raise ParseError(error)

    def peek(self) -> Token:
        "Peek at next token"
        if self.i >= len(self.tokens):
            self.fail('Ran out of tokens')
        return self.tokens[self.i]

    def next(self) -> Token:
        "Get next token"
        token = self.peek()
        self.i += 1
        return token

    def expect(self, text: str) -> None:
        "Expect next token text to be text"
        if self.next().text != text:
            self.fail(f'Expected {text}')

    def expect_type(self,
                    token_type: type[Token] | tuple[type[Token], ...]
                    ) -> Token:
        "Expect next token to be instance of token_type. Return token."
        token = self.next()
        if not isinstance(token, token_type):
            if hasattr(token_type, '__iter__'):
                expect_str = [cls.__name__ for cls in token_type]
            else:
                expect_str = token_type.__name__
            self.fail(f'Expected {expect_str!r}, got {token}')
        return token

    def lookup(self) -> str:
        "Peek at next token and return it's text"
        value = self.peek().text
        if value is None:
            return 'None'
        return value

    def back(self) -> None:
        "Go back one token"
        self.i -= 1

    def rest_tokens(self) -> list[Token]:
        "Return all tokens not processed"
        return self.tokens[self.i:]


def get_annotation(annotation: dict[str, Any],
                   get_line: Callable[[int], str]) -> str:
    "Get annotation"
##    print(f'{annotation = }\n')

    # Get definition tokens
    try:
        def_tokens = tokenize_definition(annotation['line'], get_line)
    except ParseError:
        print(f'Could tokenize definition\n{annotation = }')
        raise
    except EOFError:
        raise ParseError('Reached End of File, expected end of definition')
##    print(f'{def_tokens = }\n')

    # Get the argument and return tokens from signature
    signature = annotation['signature']
    arg_tokens = [tokenize(arg) for arg in signature['arg_types']]
    return_tokens = tokenize(signature['return_type'])

##    print(f'{arg_tokens = }\n')
##    print(f'{return_tokens = }\n')

    # Find start of argument definition
    new_lines = ''
    parser = Parser(def_tokens)
    while True:
        token = parser.next()
        if isinstance(token, ArgumentName):
            parser.back()
            break
        elif token.text == ')':
            parser.back()
            break
        assert token.text is not None, "Unreachable, End token is only null text token"
        new_lines += token.text
        if isinstance(token, Keyword):
            new_lines += ' '

    # Find out which arguments we have to skip (*, **, /)
    skip_args: set[int] = set()
##    print(f'{parser.rest_tokens() = }\n')
    argument = 0
    argparser = Parser(parser.rest_tokens())
    while True:
        token = argparser.next()
        if isinstance(token, Separator):
            if token.text == ')':
                break
            if token.text == '/':
                skip_args.add(argument)
                argument += 1
            elif token.text == '*':
                skip_args.add(argument)
                argument += 1
                if argparser.lookup() == '*':
                    argparser.expect('*')
        elif isinstance(token, ArgumentName):
            argument += 1
##        elif isinstance(token, End):
##            parser.back()
##            break

    arg_place = len(arg_tokens) - argument
##    print(f'{arg_tokens = }\n{len(arg_tokens) = }\n{argument = }')
    if arg_place < 0:
        # Self or class argument does not require type so annotations are
        # not given
        for skip in range(-arg_place):
            skip_args.add(skip)

##    print(f'{skip_args = }\n{arg_place = }\n')
##    print(f'{parser.rest_tokens() = }\n')

    # Handle arguments
    argument = 0
    while True:
        token = parser.next()
        if isinstance(token, Separator):
            if isinstance(token, EndSeparator):
                new_lines += token.text
            else:
                new_lines += f'{token.text} '
            if token.text == ')':
                break
            if token.text == '*':
                argument += 1
        elif isinstance(token, ArgumentName):
            name = token.text
            type_text = ''
##            print(f'{argument = }')
            if isinstance(parser.peek(), TypeDef):
                parser.expect(':')
                type_value = parser.parse_type()
##                print(f'{token} has TypeDef')
##                print(f'{type_value = }')
                type_text = ': '+str(type_value)
##                print(f'{type_text = }')
            elif argument not in skip_args:
                type_value = Parser(arg_tokens[arg_place]).parse_type()
##                print(f'{type_value = }')
                type_text = ': '+str(type_value)
            if isinstance(parser.peek(), DefaultDef):
                parser.expect('=')
                type_value = parser.parse_type()
                type_text += ' = ' + str(type_value)
            new_lines += f'{name}{type_text}'
            argument += 1
            arg_place += 1
        elif isinstance(token, End):
            print('Found End token during argument parsing')
            parser.back()
            break
##    print(f'{parser.rest_tokens() = }\n')
    # Handle the end
    if isinstance(parser.peek(), EndDefinition):
        parser.tokens = [ReturnTypeDef('->')] + return_tokens[:-1] + parser.rest_tokens()
        parser.i = 0
    elif isinstance(parser.peek(), End):
        parser.tokens = [ReturnTypeDef('->')] + return_tokens[:-1] + parser.rest_tokens()
        parser.i = 0
    parser.expect('->')
    new_lines += ' -> '
    ret_type = str(parser.parse_type())
    new_lines += ret_type
    while True:
        token = parser.next()
        if isinstance(token, End):
            break
        new_lines += token.text

    return new_lines





def run() -> None:
    "Run test of module"
    annotation = {'func_name': 'idlemypyextension.suggest', 'line': 516, 'path': '/home/samuel/Desktop/Python/Tests/Idle extention/idlemypyextension/src/idlemypyextension/__init__.py', 'samples': 0, 'signature': {'arg_types': ['str', 'int'], 'return_type': 'None'}}
##    annotation = {'func_name': 'idlemypyextension.get_msg_line', 'line': 319, 'path': '/home/samuel/Desktop/Python/Tests/Idle extention/idlemypyextension/src/idlemypyextension/__init__.py', 'samples': 0, 'signature': {'arg_types': ['int', 'str'], 'return_type': 'str'}}
##    annotation = {'func_name': 'tokenize', 'line': 108, 'path': '/home/samuel/Desktop/Python/Tests/Idle extention/idlemypyextension/src/idlemypyextension/annotate.py', 'samples': 0, 'signature': {'arg_types': ['str'], 'return_type': 'typing:List[idlemypyextension.annotate.Token]'}}
##    annotation = {'func_name': 'idlemypyextension.ensure_daemon_running', 'line': 492, 'path': '/home/samuel/Desktop/Python/Tests/Idle extention/idlemypyextension/src/idlemypyextension/__init__.py', 'samples': 0, 'signature': {'arg_types': ['bool'], 'return_type': 'bool'}}
##    annotation = {'func_name': 'get_required_config', 'line': 45, 'path': '/home/samuel/Desktop/Python/Tests/Idle extention/idlemypyextension/src/idlemypyextension/__init__.py', 'samples': 0, 'signature': {'arg_types': ['typing.Dict[str, str]', 'typing.Dict[str, str]'], 'return_type': 'str'}}
##    annotation = {'func_name': 'check_installed', 'line': 60, 'path': '/home/samuel/Desktop/Python/Tests/Idle extention/idlemypyextension/src/idlemypyextension/__init__.py', 'samples': 0, 'signature': {'arg_types': [], 'return_type': 'bool'}}
    annotation = {'func_name': 'idlemypyextension.initial', 'line': 663, 'path': '/home/samuel/Desktop/Python/Tests/Idle extention/idlemypyextension/src/idlemypyextension/__init__.py', 'samples': 0, 'signature': {'arg_types': [], 'return_type': 'Tuple[Optional[str], str, int]'}}
##    annotation = {'func_name': 'idlemypyextension.add_comments', 'line': 429, 'path': '/home/samuel/Desktop/Python/Tests/Idle extention/idlemypyextension/src/idlemypyextension/__init__.py', 'samples': 0, 'signature': {'arg_types': ['str', 'str'], 'return_type': 'typing.List[int]'}}
##    annotation = {'func_name': 'idlemypyextension.get_pointers', 'line': 401, 'path': '/home/samuel/Desktop/Python/Tests/Idle extention/idlemypyextension/src/idlemypyextension/__init__.py', 'samples': 0, 'signature': {'arg_types': ['typing:List[typing.Dict[str, Union[int, str]]]'], 'return_type': 'Optional[typing.Dict[str, Union[int, str]]]'}}
##    annotation = {'func_name': 'idlemypyextension.add_comment', 'line': 333, 'path': '/home/samuel/Desktop/Python/Tests/Idle extention/idlemypyextension/src/idlemypyextension/__init__.py', 'samples': 0, 'signature': {'arg_types': ['typing.Dict[str, Union[str, int]]', 'int'], 'return_type': 'bool'}}
##    annotation = {'func_name': 'translate_file_given_coro', 'line': 168, 'path': '/home/samuel/Desktop/Python/Projects/Localization Translation Utility/auto_trans.py', 'samples': 0, 'signature': {'arg_types': ['Callable[[typing.Dict[str, Any], str, str], auto_trans:Awaitable[typing.Dict[str, str]]]', 'Tuple[typing.Dict[Any, Any], typing.Dict[Any, Any]]', 'typing.List[Tuple[str, str]]', 'str'], 'return_type': 'typing:Coroutine[Any, Any, typing.Coroutine[Any, Any, int]]'}}
##    annotation = {'func_name': 'section_to_walk', 'line': 145, 'path': '/home/samuel/Desktop/Python/Projects/Localization Translation Utility/auto_trans.py', 'samples': 0, 'signature': {'arg_types': ['typing.List[str]'], 'return_type': 'typing:Tuple[Tuple[str, typing.List[str]], ...]'}}
##    annotation = {'func_name': 'read', 'line': 129, 'path': '/home/samuel/Desktop/Python/Ports/OpenComputers/MineOS/Libraries/Proxy.py', 'samples': 0, 'signature': {'arg_types': ['io.IOBase', 'int'], 'return_type': 'Tuple[bool, int]'}}
##    annotation = {'func_name': 'ClassType.__init__', 'line': 20, 'path': '/home/samuel/Desktop/Python/Tests/Idle extention/idlemypyextension/src/idlemypyextension/internal_types.py', 'samples': 0, 'signature': {'arg_types': ['str', 'Optional[idlemypyextension.internal_types:Sequence[idlemypyextension.internal_types.AbstractType]]'], 'return_type': 'None'}}
    def get_line(line: int) -> str:
        path = annotation['path']
        assert isinstance(path, str), "Path must be string"
        with open(path, 'r', encoding='utf-8') as files:
            for line_no, line_text in enumerate(files):
                if line_no == line-1:
                    return line_text
            raise EOFError
    print(f'{get_annotation(annotation, get_line)!r}')


if __name__ == '__main__':
    print(f'{__title__}\nProgrammed by {__author__}.\n')
    run()

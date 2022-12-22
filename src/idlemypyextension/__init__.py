#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Idle Type Check - Use mypy to type check open file, then add comments to file.

"Type Check IDLE Extension"

# Programmed by CoolCat467


__title__     = 'idlemypyextension'
__author__    = 'CoolCat467'
__license__   = 'GPLv3'
__version__   = '0.1.0'
__ver_major__ = 0
__ver_minor__ = 1
__ver_patch__ = 0

from typing import Any, TypeVar, cast, Final
from collections.abc import Callable

import os
import sys
import json
import math
import re
import traceback
from functools import wraps
from tkinter   import messagebox, Event, Tk

from idlelib         import search, searchengine
from idlelib.config  import idleConf
from idlelib.pyshell import PyShellEditorWindow

from idlemypyextension import annotate

DAEMON_TIMEOUT_MIN: Final = 5
ACTION_TIMEOUT_MIN: Final = 5

_HAS_MYPY = True
try:
    from idlemypyextension import client
except ImportError:
    print(f'{__file__}: Mypy not installed!')
    _HAS_MYPY = False

def get_required_config(values: dict[str, str], bind_defaults: dict[str, str]) -> str:
    "Get required configuration file data"
    config = ''
    # Get configuration defaults
    settings = '\n'.join(f'{key} = {default}' for key, default in values.items())
    if settings:
        config += f"\n[{__title__}]\n{settings}"
        if bind_defaults:
            config += '\n'
    # Get key bindings data
    settings = '\n'.join(f'{event} = {key}' for event, key in bind_defaults.items())
    if settings:
        config += f"\n[{__title__}_cfgBindings]\n{settings}"
    return config

def check_installed() -> bool:
    "Make sure extension installed."
    # Get list of system extensions
    extensions = list(idleConf.defaultCfg['extensions'])
    ex_defaults = idleConf.defaultCfg['extensions'].file

    # Import this extension (this file),
    module = __import__(__title__)

    # Get extension class
    if not hasattr(module, __title__):
        print(f'ERROR: Somehow, {__title__} was installed improperly, no {__title__} class '\
              'found in module. Please report this on github.', file=sys.stderr)
        sys.exit(1)

    cls = getattr(module, __title__)

    # Get extension class keybinding defaults
    required_config = get_required_config(
        getattr(cls, 'values', {}),
        getattr(cls, 'bind_defaults', {})
    )

    # If this extension not in there,
    if __title__ not in extensions:
        # Tell user how to add it to system list.
        print(f'{__title__} not in system registered extensions!')
        print(f'Please run the following command to add {__title__} to system extensions list.\n')
        # Make sure line-breaks will go properly in terminal
        add_data = required_config.replace('\n', '\\n')
        # Tell them command
        print(f"echo -e '{add_data}' | sudo tee -a {ex_defaults}")
        print()
    else:
        print(f'Configuration should be good! (v{__version__})')
        return True
    return False

def get_line_selection(line: int) -> tuple[str, str]:
    "Get selection strings for given line"
    return f'{line}.0', f'{line+1}.0'

# Stolen from idlelib.searchengine
def get_line_col(index: str) -> tuple[int, int]:
    "Return (line, col) tuple of integers from 'line.col' string."
    line, col = map(int, index.split('.', 1)) # Fails on invalid index
    return line, col

def get_line_indent(text: str, char: str = ' ') -> int:
    "Return line indent."
    for idx, cur in enumerate(text.split(char)):
        if cur != '':
            return idx
    return 0

def ensure_section_exists(section: str) -> bool:
    "Ensure section exists in user extensions configuration. Return True if created."
    if not section in idleConf.GetSectionList('user', 'extensions'):
        idleConf.userCfg['extensions'].AddSection(section)
        return True
    return False

F = TypeVar('F', bound=Callable[..., Any])

def undo_block(func: F) -> F:
    "Mark block of edits as a single undo block."
    @wraps(func)
    def undo_wrapper(self: 'idlemypyextension', *args: Any, **kwargs: Any) -> Any:
        "Wrap function in start and stop undo events."
        self.text.undo_block_start()
        try:
            return func(self, *args, **kwargs)
        finally:
            self.text.undo_block_stop()
    return cast(F, undo_wrapper)

def ensure_values_exist_in_section(section: str, values: dict[str, str]) -> bool:
    "For each key in values, make sure key exists. If not, create and set to value. "\
    "Return True if created any defaults."
    need_save = False
    for key, default in values.items():
        value = idleConf.GetOption('extensions', section, key,
                                   warn_on_default=False)
        if value is None:
            idleConf.SetOption('extensions', section, key, default)
            need_save = True
    return need_save

def get_search_engine_params(engine: searchengine.SearchEngine) -> dict[str, str | bool]:
    "Get current search engine parameters"
    return {
        name: getattr(engine, f'{name}var').get()
        for name in ('pat', 're', 'case', 'word', 'wrap', 'back')
    }

def set_search_engine_params(engine: searchengine.SearchEngine,
                             data: dict[str, str | bool]) -> None:
    "Get current search engine parameters"
    for name in ('pat', 're', 'case', 'word', 'wrap', 'back'):
        if name in data:
            getattr(engine, f'{name}var').set(data[name])

def get_fake_editwin() -> PyShellEditorWindow:
    "Get fake edit window for testing"
    from idlelib.pyshell import PyShellEditorWindow
    class FakeEditWindow(PyShellEditorWindow):
        "FakeEditWindow for testing"
        from tkinter import Text
        class _FakeText(Text):
            bind = lambda x, y: None
        text = _FakeText
        from idlelib.format import FormatRegion
        fregion = FormatRegion
        from idlelib.pyshell import PyShellFileList
        flist = PyShellFileList
        from idlelib.iomenu import IOBinding
        io = IOBinding
    return FakeEditWindow

# Important weird: If event handler function returns 'break',
# then it prevents other bindings of same event type from running.
# If returns None, normal and others are also run.

class idlemypyextension:# pylint: disable=invalid-name
    "Add comments from mypy to an open program."
    __slots__ = (
        'editwin',
        'text',
        'formatter',
        'files',
        'flist',
    )
    # Extend the file and format menus.
    menudefs = [
        ('edit', [
            None,
            ('_Type Check File', '<<type-check>>'),
            ('Find Next Type Comment', '<<find-next-type-comment>>')
        ] ),
        ('format', [
            ('Suggest Signature', '<<suggest-signature>>'),
            ('Remove Type Comments', '<<remove-type-comments>>')
        ] ),
        ('run', [
            ('Shutdown dmypy daemon', '<<shutdown-dmypy-daemon>>')
        ] )
    ]
    # Default values for configuration file
    values = {
        'enable'         : 'True',
        'enable_editor'  : 'True',
        'enable_shell'   : 'False',
        'daemon_flags'   : 'None',
        'search_wrap'    : 'True',
        'suggest_replace': 'False',
        'timeout_mins'   : '30',
        'action_max_sec' : '40',
    }
    # Default key binds for configuration file
    bind_defaults = {
        'type-check'            : '<Alt-Key-t>',
        'suggest-signature'     : '<Alt-Key-s>',
        'remove-type-comments'  : '<Alt-Shift-Key-T>',
        'find-next-type-comment': '<Alt-Key-g>'
    }
    comment = '# types: '

    # Overwritten in reload
    daemon_flags        = 'None'
    search_wrap         = 'True'
    suggest_replace     = 'False'
    timeout_mins = '30'
    action_max_sec      = '40'

    # Class attributes
    idlerc_folder = os.path.expanduser(idleConf.userdir)
    mypy_folder   = os.path.join(idlerc_folder, 'mypy')
    status_file   = os.path.join(mypy_folder, 'dmypy.json')
    log_file      = os.path.join(mypy_folder, 'log.txt')

    def __init__(self, editwin: PyShellEditorWindow) -> None:
        "Initialize the settings for this extension."
##        self.editwin  : idlelib.pyshell.PyShellEditorWindow = editwin
##        self.text     : idlelib.multicall.MultiCallCreator  = editwin.text
##        self.formatter: idlelib.format.FormatRegion         = editwin.fregion
##        self.flist    : idlelib.pyshell.PyShellFileList     = editwin.flist
##        self.files    : idlelib.iomenu.IOBinding            = editwin.io
        self.editwin   = editwin
        self.text      = editwin.text
        self.formatter = editwin.fregion
        self.flist     = editwin.flist
        self.files     = editwin.io

        if not os.path.exists(self.mypy_folder):
            os.mkdir(self.mypy_folder)

        for attr_name in (a for a in dir(self) if not a.startswith('_')):
            if attr_name.endswith('_event'):
                bind_name = '-'.join(attr_name.split('_')[:-1]).lower()
                self.text.bind(f'<<{bind_name}>>', getattr(self, attr_name))
##                print(f'{attr_name} -> {bind_name}')

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}({self.editwin!r})'

    @property
    def daemon_timeout(self) -> int:
        "Daemon timeout"
        if self.timeout_mins == 'None':
            return DAEMON_TIMEOUT_MIN * 60
        try:
            return max(DAEMON_TIMEOUT_MIN * 60,
                       math.ceil(float(self.timeout_mins) * 60))
        except ValueError:
            return DAEMON_TIMEOUT_MIN * 60

    @property
    def action_timeout(self) -> int | None:
        "Action timeout"
        if self.action_max_sec == 'None':
            return None
        try:
            return max(ACTION_TIMEOUT_MIN, int(self.action_max_sec))
        except ValueError:
            return max(ACTION_TIMEOUT_MIN, int(self.values['action_max_sec']))

    @property
    def flags(self) -> list[str]:
        "Daemon server flags"
        base = {
            f'--cache-dir={self.mypy_folder}',
##            '--cache-fine-grained',
            '--hide-error-context',
            '--no-color-output',
            '--show-absolute-path',
            '--no-error-summary',
        }
        if self.daemon_flags == 'None':
            return list(base)
        return list(base | {s.strip() for s in self.daemon_flags.split(' ')})

    @classmethod
    def ensure_bindings_exist(cls) -> bool:
        "Ensure key bindings exist in user extensions configuration. Return True if need to save."
        need_save = False
        section = f'{cls.__name__}_cfgBindings'
        if ensure_section_exists(section):
            need_save = True
        if ensure_values_exist_in_section(section, cls.bind_defaults):
            need_save = True
        return need_save

    @classmethod
    def ensure_config_exists(cls) -> bool:
        "Ensure required configuration exists for this extension. Return True if need to save."
        need_save = False
        if ensure_section_exists(cls.__name__):
            need_save = True
        if ensure_values_exist_in_section(cls.__name__, cls.values):
            need_save = True
        return need_save

    @classmethod
    def reload(cls) -> None:
        "Load class variables from configuration."
##        # Ensure file default values exist so they appear in settings menu
##        save = cls.ensure_config_exists()
##        if cls.ensure_bindings_exist() or save:
##            idleConf.SaveUserCfgFiles()

        # Reload configuration file
        idleConf.LoadCfgFiles()

        # For all possible configuration values
        for key, default in cls.values.items():
            # Set attribute of key name to key value from configuration file
            if not key in {'enable', 'enable_editor', 'enable_shell'}:
                value = idleConf.GetOption(
                    'extensions',
                    cls.__name__,
                    key,
                    default=default
                )
                setattr(cls, key, value)

    @classmethod
    def get_msg_line(cls, indent: int, msg: str) -> str:
        "Return message line given indent and message."
        strindent = ' '*indent
        return f'{strindent}{cls.comment}{msg}'

    def get_line(self, line: int) -> str:
        "Get the characters from the given line in the currently open file."
        chars: str = self.text.get(*get_line_selection(line))
        return chars

    def comment_exists(self, line: int, text: str) -> bool:
        "Return True if comment for message already exists on line."
        return self.get_msg_line(0, text) in self.get_line(line-1)

    def add_comment(self,
                    message: dict[str, str | int],
                    max_exist_up: int = 0) -> bool:
        "Return True if added new comment, False if already exists."
        # Get line and message from output
##        file = str(message['file'])
        line = int(message['line'])
        msg  = str(message['message'])

        # If there is already a comment from us there, ignore that line.
        # +1-1 is so at least up by 1 is checked, range(0) = []
        for i in range(max_exist_up+1):
            if self.comment_exists(line-(i-1), msg):
                return False

        # Get line checker is talking about
        chars = self.get_line(line)

        # Figure out line indent
        indent = get_line_indent(chars)

        # Add comment line
        chars = self.get_msg_line(indent, msg)+'\n'+chars

        # Save changes
        start, end = get_line_selection(line)
        self.text.delete(start, end)
        self.text.insert(start, chars, None)
        return True

    @staticmethod
    def parse_comments(comments: str,
                       default_file: str,
                       default_line: int
                       ) -> dict[str, list[dict[str, str | int]]]:
        "Get list of message dictionaries from mypy output."
        error_type = re.compile(r'  \[[a-z\-]+\]\s*$')

        files: dict[str, list[dict[str, str | int]]] = {}
        for comment in comments.splitlines():
            filename = default_file
            line     = default_line
            col      = 0
            mtype    = 'unrecognized'

            if comment.count(': ') < 2:
                text = comment
            else:
                where, mtype, text = comment.split(': ', 2)

                position = where.split(':')

                filename = position[0]
                if len(position) > 1:
                    line = int(position[1])
                if len(position) > 2:
                    col = int(position[2])
            comment_type = error_type.search(text)
            if comment_type is not None:
                text = text[:comment_type.start()]
                mtype = f'{comment_type.group(0)[3:-1]} {mtype}'

            message: dict[str, str | int] = {
                'file'   : filename,
                'line'   : line,
                'column' : col,
                'type'   : mtype,
                'message': f'{mtype}: {text}'
            }

            if not filename in files:
                files[filename] = []
            files[filename].append(message)
        return files

    def get_pointers(self,
                     messages: list[dict[str, int | str]]
                     ) -> dict[str, int | str] | None:
        "Return message pointing to message column position"
        line = int(messages[0]['line'])+1

        # Figure out line intent
        indent = get_line_indent(self.get_line(line))

        columns: list[int] = []
        for message in messages:
            columns.append(int(message['column']))

        lastcol = len(self.comment) + indent + 1
        new_line = ''
        for col in sorted(frozenset(columns)):
            if col < lastcol:
                continue
            spaces = col - lastcol
            new_line += ' '*spaces + '^'
            lastcol = col+1

        if not new_line.strip():
            return None

        return {
            'line'   : line,
            'message': new_line
        }

    def add_comments(self,
                     target_filename: str,
                     normal: str) -> list[int]:
        "Add comments for target filename, return list of comments added"
        start_line: int = self.editwin.getlineno()

        files = self.parse_comments(
            normal,
            os.path.abspath(self.files.filename),
            start_line
        )

        # Only handling messages for target filename
        line_data: dict[int, list[dict[str, Any]]] = {}
        if target_filename in files:
            for message in files[target_filename]:
                line = message['line']
                assert isinstance(line, int), "Line must be int"
                if not line in line_data:
                    line_data[line] = []
                line_data[line].append(message)

        line_order: list[int] = list(sorted(line_data, reverse=True))
        first: int = line_order[-1] if line_order else start_line

        if not first in line_data:# if used starting line
            line_data[first] = []
            line_order.append(first)

        for filename in {f for f in files if f != target_filename}:
            line_data[first].append({
                'file'   : target_filename,
                'line'   : first,
                'column' : 0,
                'type'   : 'note',
                'message': f'Another file has errors: {filename}'
            })

        comments = []
        for line in line_order:
            messages = line_data[line]
            if not messages:
                continue
            pointers = self.get_pointers(messages)
            if pointers is not None:
                messages.append(pointers)

            total = len(messages)
            for message in reversed(messages):
                if self.add_comment(message, total):
                    comments.append(line)
        return comments

    def ask_save_dialog(self) -> bool:
        "Ask to save dialog stolen from idlelib.runscript.ScriptBinding"
        msg = 'Source Must Be Saved\n' + 5*' ' + 'OK to Save?'
        confirm: bool = messagebox.askokcancel(
            title   = 'Save Before Run or Check',
            message = msg,
            default = messagebox.OK,
            parent  = self.text
        )
        return confirm

    def ensure_daemon_running(self) -> bool:
        "Make sure daemon is running. Return False if cannot continue"
        if not client.is_running(self.status_file):
            started = client.start(self.status_file,
                                   flags = self.flags,
                                   daemon_timeout = self.daemon_timeout,
                                   log_file = self.log_file)
            return started
        return True

    def shutdown_dmypy_daemon_event(self, event: 'Event[Any]') -> str:
        "Shutdown the dmypy daemon"
        # pylint: disable=unused-argument
        if not client.is_running(self.status_file):
            self.text.bell()
            return 'break'
        # Only stop if running
        response = client.stop(self.status_file)
        if any((v in response and response[v] for v in ('err', 'error'))):
            # Kill
            client.kill(self.status_file)
        return 'break'

    def check(self, file: str) -> dict[str, Any]:
        "Preform dmypy check"
        if not self.ensure_daemon_running():
            return {'out': '',
                    'err': 'Error: Could not start mypy daemon'}
        flags = self.flags
        flags += [file]
        return client.run(self.status_file,
                          flags          = flags,
                          timeout        = self.action_timeout,
                          daemon_timeout = self.daemon_timeout,
                          log_file       = self.log_file,
                          export_types   = True)

    def get_suggestion_text(self,
                            annotation: dict[str, Any]) -> str | None:
        """Get suggestion text from annotation.

        Return None on error or no difference, text if different"""
        while annotation['line'] >= 0 and not 'def' in self.get_line(annotation['line']):
            annotation['line'] -= 1
        line = annotation['line']

        try:
            text = annotate.get_annotation(annotation, self.get_line)
        except annotate.ParseError as ex:
            ex_text, ex_traceback = sys.exc_info()[1:]
            traceback.print_exception(
                None,  # Ignored since python 3.5
                value = ex_text,
                tb = ex_traceback,
                limit = None,
                chain = True
            )
            indent = get_line_indent(self.get_line(line))
            return self.get_msg_line(indent, f'Error generating suggestion: {ex}')

        select_start = f'{line}.0'
        line_end = line+len(text.splitlines())
        select_end = f'{line_end}.0'

        if text == self.text.get(select_start, select_end)[:-1]:
            return None
        return text

    def suggest(self, file: str, line: int) -> None:
        "Preform dmypy suggest"
        if not self.ensure_daemon_running():
            response = {'err': 'Error: Could not start mypy daemon'}
        else:
            function = f'{file}:{line}'
            response = client.suggest(self.status_file,
                                      function = function,
                                      do_json  = True,
                                      timeout  = self.action_timeout)
##        print(f'{response = }')

        errors = ''
        if 'error' in response:
            errors += response['error']
        if 'err' in response:
            errors += response['err']

        # Display errors
        if errors:
            lines = errors.splitlines()
            lines[0] = f'Error running mypy: {lines[0]}'
            for message in reversed(lines):
                self.add_comment({
                    'file': file,
                    'line': line,
                    'message': message,
                }, len(lines))

            self.text.bell()
            return

        annotations = json.loads(response['out'])

        line = annotations[0]['line']

        samples: dict[int, list[str]] = {}
        for annotation in annotations:
            count = annotation['samples']
            text = self.get_suggestion_text(annotation)
            if text is None:
                continue
            if not count in samples:
                samples[count] = []
            samples[count].append(text)

        order = sorted(samples, reverse=True)
        lines = []
        for count in order:
            for sample in samples[count]:
                if not sample in lines:
                    lines.append(sample)

        replace = self.suggest_replace == 'True'

        if len(lines) == 1:
            text = lines[0]
            if 'Error generating suggestion: ' in text:
                replace = False
        else:
            text = '\n'.join(lines)
            replace = False

        select_start = f'{line}.0'
        line_end = line+len(text.splitlines())
        select_end = f'{line_end}.0'

        if not text or text == self.text.get(select_start, select_end)[:-1]:
            # Bell to let user know happened, just nothing to do
            self.editwin.gotoline(line)
            self.text.bell()
            return

        if replace:
            self.text.delete(select_start, select_end)
        elif 'Error generating suggestion: ' not in text:
            text = '\n'.join(f'##{l}' for l in text.splitlines())
        text += '\n'

        self.text.insert(select_start, text, None)
        self.editwin.gotoline(line)
        self.text.bell()

    @undo_block
    def suggest_signature_event(self, event: 'Event[Any]') -> str:
        "Handle suggest signature event"
        # pylint: disable=unused-argument
        init_return, file, start_line_no = self.initial()
        if init_return is not None:
            return init_return

        self.suggest(file, start_line_no)

        return 'break'

    def initial(self) -> tuple[str | None, str, int]:
        """Do common initial setup. Return error or none, file, and start line

        Reload configuration, make sure file is saved,
        and make sure mypy is installed"""
        self.reload()

        # Get file we are checking
        file: str = os.path.abspath(self.files.filename)

        # Remember where we started
        start_line_no: int = self.editwin.getlineno()

        if not _HAS_MYPY:
            self.add_comment({
                'file': file,
                'line': start_line_no,
                'message': 'Could not import mypy. '\
                'Please install mypy and restart IDLE to use this extension.'
            }, start_line_no)

            # Make bell sound so user knows they need to pay attention
            self.text.bell()
            return 'break', file, start_line_no

        # Make sure file is saved.
        if not self.files.get_saved():
            if not self.ask_save_dialog():
                # If not ok to save, do not run. Would break file.
                self.text.bell()
                return 'break', file, start_line_no
            # Otherwise, we are clear to save
            self.files.save(None)
            self.files.set_saved(True)

        # Everything worked
        return None, file, start_line_no

    @undo_block
    def type_check_event(self, event: 'Event[Any]') -> str:
        "Preform a mypy check and add comments."
        # pylint: disable=unused-argument
        init_return, file, start_line_no = self.initial()
        if init_return is not None:
            return init_return

        # Run mypy on open file
        response = self.check(file)
        normal = ''
        if 'out' in response:
            normal = response['out']
        errors = ''
        if 'err' in response:
            errors = response['err']
        if 'error' in response:
            errors += response['error']
##        print(response)

        if errors:
            lines = errors.splitlines()
            lines[0] = f'Error running mypy: {lines[0]}'
            for message in reversed(lines):
                self.add_comment({
                    'file': file,
                    'line': start_line_no,
                    'message': message,
                }, len(lines))

            self.text.bell()
            return 'break'

        if normal:
            # Add code comments
            self.add_comments(file, normal)

        # Make bell sound so user knows we are done,
        # as it freezes a bit while mypy looks at the file
        self.text.bell()
        return 'break'

    def remove_type_comments_event(self, event: 'Event[Any]') -> str:
        "Remove selected mypy comments."
        # pylint: disable=unused-argument
        # Get selected region lines
        head, tail, chars, lines = self.formatter.get_region()
        if not self.comment in chars:
            # Make bell sound so user knows this ran even though
            # nothing happened.
            self.text.bell()
            return 'break'
        # Using dict so we can reverse and enumerate
        ldict = dict(enumerate(lines))
        for idx in sorted(ldict.keys(), reverse=True):
            line = ldict[idx]
            # If after indent there is mypy comment
            if line.lstrip().startswith(self.comment):
                # If so, remove line
                del lines[idx]
        # Apply changes
        self.formatter.set_region(head, tail, chars, lines)
        return 'break'

    @undo_block
    def remove_all_type_comments(self, event: 'Event[Any]') -> str:
        "Remove all mypy comments."
        # pylint: disable=unused-argument
        eof_idx = self.text.index('end')

        chars = self.text.get('0.0', eof_idx)

        lines = chars.splitlines()
        modified = False
        for idx in reversed(range(len(lines))):
            if lines[idx].lstrip().startswith(self.comment):
                del lines[idx]
                modified = True
        if not modified:
            return 'break'

        chars = '\n'.join(lines)

        # Apply changes
        self.text.delete('0.0', eof_idx)
        self.text.insert('0.0', chars, None)
        return 'break'

    @undo_block
    def find_next_type_comment_event(self, event: 'Event[Any]') -> str:
        "Find next comment by hacking the search dialog engine."
        # pylint: disable=unused-argument
        self.reload()

        root: Tk
        root = self.text._root()# pylint: disable=protected-access

        # Get search engine singleton from root
        engine: searchengine.SearchEngine = searchengine.get(root)

        # Get current search prams
        global_search_params = get_search_engine_params(engine)

        # Set search pattern to comment starter
        set_search_engine_params(engine, {
            'pat' : f'^\\s*{self.comment}',
            're'  : True,
            'case': True,
            'word': False,
            'wrap': self.search_wrap == 'True',
            'back': False
        })

        # Find current pattern
        search.find_again(self.text)

        # Re-apply previous search prams
        set_search_engine_params(engine, global_search_params)
        return 'break'

idlemypyextension.reload()

if __name__ == '__main__':
    print(f'{__title__} v{__version__}\nProgrammed by {__author__}.\n')
    check_installed()
##    self = idlemypyextension(get_fake_editwin())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Idle Type Check - Use mypy to type check and add comments to open file

"Type Check IDLE Extension"

# Programmed by CoolCat467

from __future__ import annotations

__title__ = "idlemypyextension"
__author__ = "CoolCat467"
__license__ = "GPLv3"
__version__ = "1.0.0"
__ver_major__ = 1
__ver_minor__ = 0
__ver_patch__ = 0

import json
import math
import os
import re
import sys
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial, wraps
from idlelib import search, searchengine
from idlelib.config import idleConf
from idlelib.format import FormatRegion
from idlelib.iomenu import IOBinding
from idlelib.pyshell import PyShellEditorWindow, PyShellFileList
from idlelib.undo import UndoDelegator
from tkinter import Event, Text, Tk, messagebox
from typing import Any, Final, TypeVar, cast

from idlemypyextension import annotate, tktrio

DAEMON_TIMEOUT_MIN: Final = 5
ACTION_TIMEOUT_MIN: Final = 5

_HAS_MYPY = True
try:
    from idlemypyextension import client
except ImportError:
    print(f"{__file__}: Mypy not installed!")
    _HAS_MYPY = False


def get_required_config(
    values: dict[str, str], bind_defaults: dict[str, str]
) -> str:
    "Get required configuration file data"
    config = ""
    # Get configuration defaults
    settings = "\n".join(
        f"{key} = {default}" for key, default in values.items()
    )
    if settings:
        config += f"\n[{__title__}]\n{settings}"
        if bind_defaults:
            config += "\n"
    # Get key bindings data
    settings = "\n".join(
        f"{event} = {key}" for event, key in bind_defaults.items()
    )
    if settings:
        config += f"\n[{__title__}_cfgBindings]\n{settings}"
    return config


def check_installed() -> bool:
    "Make sure extension installed."
    # Get list of system extensions
    extensions = list(idleConf.defaultCfg["extensions"])
    ex_defaults = idleConf.defaultCfg["extensions"].file

    # Import this extension (this file),
    module = __import__(__title__)

    # Get extension class
    if not hasattr(module, __title__):
        print(
            f"ERROR: Somehow, {__title__} was installed improperly, "
            f"no {__title__} class found in module. Please report "
            "this on github.",
            file=sys.stderr,
        )
        sys.exit(1)

    cls = getattr(module, __title__)

    # Get extension class keybinding defaults
    required_config = get_required_config(
        getattr(cls, "values", {}), getattr(cls, "bind_defaults", {})
    )

    # If this extension not in there,
    if __title__ not in extensions:
        # Tell user how to add it to system list.
        print(f"{__title__} not in system registered extensions!")
        print(
            f"Please run the following command to add {__title__} "
            + "to system extensions list.\n"
        )
        # Make sure line-breaks will go properly in terminal
        add_data = required_config.replace("\n", "\\n")
        # Tell them the command
        print(f"echo -e '{add_data}' | sudo tee -a {ex_defaults}")
        print()
    else:
        print(f"Configuration should be good! (v{__version__})")
        return True
    return False


def get_line_selection(line: int) -> tuple[str, str]:
    "Get selection strings for given line"
    return f"{line}.0", f"{line+1}.0"


# Stolen from idlelib.searchengine
def get_line_col(index: str) -> tuple[int, int]:
    "Return (line, col) tuple of integers from 'line.col' string."
    line, col = map(int, index.split(".", 1))  # Fails on invalid index
    return line, col


def get_line_indent(text: str, char: str = " ") -> int:
    "Return line indent."
    for idx, cur in enumerate(text.split(char)):
        if cur != "":
            return idx
    return 0


def ensure_section_exists(section: str) -> bool:
    "Ensure section exists in user extensions configuration, return if edited"
    if section not in idleConf.GetSectionList("user", "extensions"):
        idleConf.userCfg["extensions"].AddSection(section)
        return True
    return False


F = TypeVar("F", bound=Callable[..., Any])


def undo_block(func: F) -> F:
    "Mark block of edits as a single undo block."

    @wraps(func)
    def undo_wrapper(
        self: "idlemypyextension", *args: Any, **kwargs: Any
    ) -> Any:
        "Wrap function in start and stop undo events."
        self.undo.undo_block_start()
        try:
            return func(self, *args, **kwargs)
        finally:
            self.undo.undo_block_stop()

    return cast(F, undo_wrapper)


def ensure_values_exist_in_section(
    section: str, values: dict[str, str]
) -> bool:
    """For each key in values, make sure key exists. Return if edited

    If not, create and set to value."""
    need_save = False
    for key, default in values.items():
        value = idleConf.GetOption(
            "extensions", section, key, warn_on_default=False
        )
        if value is None:
            idleConf.SetOption("extensions", section, key, default)
            need_save = True
    return need_save


def get_search_engine_params(
    engine: searchengine.SearchEngine,
) -> dict[str, str | bool]:
    "Get current search engine parameters"
    return {
        name: getattr(engine, f"{name}var").get()
        for name in ("pat", "re", "case", "word", "wrap", "back")
    }


def set_search_engine_params(
    engine: searchengine.SearchEngine, data: dict[str, str | bool]
) -> None:
    "Get current search engine parameters"
    for name in ("pat", "re", "case", "word", "wrap", "back"):
        if name in data:
            getattr(engine, f"{name}var").set(data[name])


@dataclass(slots=True)
class Message:
    """Represents one message from mypy"""

    file: str
    line: int
    message: str
    line_end: int | None = None
    column: int = 0
    column_end: int | None = None
    msg_type: str = "unrecognized"


# Important weird: If event handler function returns 'break',
# then it prevents other bindings of same event type from running.
# If returns None, normal and others are also run.


class idlemypyextension:  # pylint: disable=invalid-name
    "Add comments from mypy to an open program."
    __slots__ = (
        "editwin",
        "text",
        "undo",
        "formatter",
        "files",
        "flist",
        "triorun",
    )
    # Extend the file and format menus.
    menudefs = [
        (
            "edit",
            [
                None,
                ("_Type Check File", "<<type-check>>"),
                ("Find Next Type Comment", "<<find-next-type-comment>>"),
            ],
        ),
        (
            "format",
            [
                ("Suggest Signature", "<<suggest-signature>>"),
                ("Remove Type Comments", "<<remove-type-comments>>"),
            ],
        ),
        ("run", [("Shutdown dmypy daemon", "<<shutdown-dmypy-daemon>>")]),
    ]
    # Default values for configuration file
    values = {
        "enable": "True",
        "enable_editor": "True",
        "enable_shell": "False",
        "daemon_flags": "None",
        "search_wrap": "True",
        "suggest_replace": "False",
        "timeout_mins": "30",
        "action_max_sec": "None",
    }
    # Default key binds for configuration file
    bind_defaults = {
        "type-check": "<Alt-Key-t>",
        "suggest-signature": "<Alt-Key-s>",
        "remove-type-comments": "<Alt-Shift-Key-T>",
        "find-next-type-comment": "<Alt-Key-g>",
    }
    comment = "# types: "

    # Overwritten in reload
    daemon_flags = "None"
    search_wrap = "True"
    suggest_replace = "False"
    timeout_mins = "30"
    action_max_sec = "None"

    # Class attributes
    idlerc_folder = os.path.expanduser(idleConf.userdir)
    mypy_folder = os.path.join(idlerc_folder, "mypy")
    status_file = os.path.join(mypy_folder, "dmypy.json")
    log_file = os.path.join(mypy_folder, "log.txt")

    def __init__(self, editwin: PyShellEditorWindow) -> None:
        """Initialize the settings for this extension."""
        self.editwin: PyShellEditorWindow = editwin
        self.text: Text = editwin.text
        self.undo: UndoDelegator = editwin.undo
        self.formatter: FormatRegion = editwin.fregion
        self.flist: PyShellFileList = editwin.flist
        self.files: IOBinding = editwin.io

        if not os.path.exists(self.mypy_folder):
            os.mkdir(self.mypy_folder)

        self.triorun = tktrio.TkTrioRunner(
            self.editwin.top,
            self.editwin.close,
        )

        for attr_name in dir(self):
            if attr_name.startswith("_"):
                continue
            if attr_name.endswith("_event_async"):
                bind_name = "-".join(attr_name.split("_")[:-2]).lower()
                self.text.bind(f"<<{bind_name}>>", self.get_async(attr_name))
                # print(f'{attr_name} -> {bind_name}')

    def get_async(
        self,
        name: str,
    ) -> Callable[["Event[Any]"], str]:
        """Get sync callable to run async function"""
        async_function = getattr(self, name)

        @wraps(async_function)
        def call_trio(event: "Event[Any]") -> str:
            self.triorun(partial(async_function, event))
            return "break"

        return call_trio

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.editwin!r})"

    @property
    def daemon_timeout(self) -> int:
        "Daemon timeout"
        if self.timeout_mins == "None":
            return DAEMON_TIMEOUT_MIN * 60
        try:
            return max(
                DAEMON_TIMEOUT_MIN * 60,
                math.ceil(float(self.timeout_mins) * 60),
            )
        except ValueError:
            return DAEMON_TIMEOUT_MIN * 60

    @property
    def action_timeout(self) -> int | None:
        "Action timeout"
        if self.action_max_sec == "None":
            return None
        try:
            return max(ACTION_TIMEOUT_MIN, int(self.action_max_sec))
        except ValueError:
            return max(ACTION_TIMEOUT_MIN, int(self.values["action_max_sec"]))

    @property
    def flags(self) -> list[str]:
        "Mypy Daemon flags"
        base = {
            "--hide-error-context",
            "--no-color-output",
            "--show-absolute-path",
            "--no-error-summary",
            "--soft-error-limit=-1",
            "--show-traceback",
            f"--cache-dir={self.mypy_folder}",
            # "--cache-fine-grained",
        }
        if self.daemon_flags == "None":
            return list(base)
        extra = set()
        for arg in self.daemon_flags.split(" "):
            value = arg.strip()
            if value:
                extra.add(value)
        return list(base | extra)

    @classmethod
    def ensure_bindings_exist(cls) -> bool:
        """Ensure key bindings exist in user extensions configuration.

        Return True if need to save."""
        need_save = False
        section = f"{cls.__name__}_cfgBindings"
        if ensure_section_exists(section):
            need_save = True
        if ensure_values_exist_in_section(section, cls.bind_defaults):
            need_save = True
        return need_save

    @classmethod
    def ensure_config_exists(cls) -> bool:
        """Ensure required configuration exists for this extension.

        Return True if need to save."""
        need_save = False
        if ensure_section_exists(cls.__name__):
            need_save = True
        if ensure_values_exist_in_section(cls.__name__, cls.values):
            need_save = True
        return need_save

    @classmethod
    def reload(cls) -> None:
        "Load class variables from configuration."
        # # Ensure file default values exist so they appear in settings menu
        # save = cls.ensure_configuration_exists()
        # if cls.ensure_bindings_exist() or save:
        #     idleConf.SaveUserCfgFiles()

        # Reload configuration file
        idleConf.LoadCfgFiles()

        # For all possible configuration values
        for key, default in cls.values.items():
            # Set attribute of key name to key value from configuration file
            if key not in {"enable", "enable_editor", "enable_shell"}:
                value = idleConf.GetOption(
                    "extensions", cls.__name__, key, default=default
                )
                setattr(cls, key, value)

    @classmethod
    def get_msg_line(cls, indent: int, msg: str) -> str:
        "Return message line given indent and message."
        strindent = " " * indent
        return f"{strindent}{cls.comment}{msg}"

    def get_line(self, line: int) -> str:
        "Get the characters from the given line in the currently open file."
        chars: str = self.text.get(*get_line_selection(line))
        return chars

    def comment_exists(self, line: int, text: str) -> bool:
        "Return True if comment for message already exists on line."
        return self.get_msg_line(0, text) in self.get_line(line - 1)

    def add_comment(self, message: Message, max_exist_up: int = 0) -> bool:
        "Return True if added new comment, False if already exists."
        # Get line and message from output
        # file = message.file
        line = message.line
        msg = message.message

        # If there is already a comment from us there, ignore that line.
        # +1-1 is so at least up by 1 is checked, range(0) = []
        for i in range(max_exist_up + 1):
            if self.comment_exists(line - (i - 1), msg):
                return False

        # Get line checker is talking about
        chars = self.get_line(line)

        # Figure out line indent
        indent = get_line_indent(chars)

        # Add comment line
        chars = self.get_msg_line(indent, msg) + "\n" + chars

        # Save changes
        start, end = get_line_selection(line)
        self.text.delete(start, end)
        self.text.insert(start, chars, ())
        return True

    @staticmethod
    def parse_comments(
        comments: str, default_file: str, default_line: int
    ) -> dict[str, list[Message]]:
        """Get list of message dictionaries from mypy output."""
        error_type = re.compile(r"  \[[a-z\-]+\]\s*$")

        files: dict[str, list[Message]] = {}
        for comment in comments.splitlines():
            if not comment.strip():
                continue
            filename = default_file
            line = default_line
            line_end = default_line
            col = 0
            col_end = 0
            msg_type = "unrecognized"

            if comment.count(": ") < 2:
                text = comment
            else:
                where, msg_type, text = comment.split(": ", 2)

                position = where.split(":")

                filename = position[0]
                if len(position) > 1:
                    line = int(position[1])
                    line_end = line
                if len(position) > 2:
                    col = int(position[2])
                    col_end = col
                if len(position) > 4:
                    line_end = int(position[3])
                    if line_end == line:
                        col_end = int(position[4])
                    else:
                        line_end = line
            comment_type = error_type.search(text)
            if comment_type is not None:
                text = text[: comment_type.start()]
                msg_type = f"{comment_type.group(0)[3:-1]} {msg_type}"

            message = Message(
                file=filename,
                line=line,
                message=f"{msg_type}: {text}",
                column=col,
                line_end=line_end,
                column_end=col_end,
                msg_type=msg_type,
            )

            if filename not in files:
                files[filename] = []
            files[filename].append(message)
        return files

    def get_pointers(self, messages: list[Message]) -> Message | None:
        """Return message pointing to multiple messages all on the same line

        Messages must all be on the same line and be in the same file"""
        line = messages[0].line
        file = messages[0].file

        # Figure out line intent
        line_text = self.get_line(line)
        indent = get_line_indent(line_text)
        line_len = len(line_text)

        columns: set[int] = set()
        lastcol = len(self.comment) + indent + 1

        for message in messages:
            if message.line != line:
                raise ValueError(f"Message `{message}` not on line `{line}`")
            if message.file != file:
                raise ValueError(f"Message `{message}` not in file `{file}`")
            if message.column_end is None:
                end = message.column
            else:
                end = message.column_end - lastcol
            for col in range(message.column, end + 1):
                columns.add(col)

        new_line = ""
        for col in sorted(columns):
            if col > line_len:
                break
            spaces = col - lastcol - 1
            new_line += " " * spaces + "^"
            lastcol = col

        if not new_line.strip():
            return None

        return Message(file=file, line=line + 1, message=new_line)

    @undo_block
    def add_comments(
        self, target_filename: str, start_line: int, normal: str
    ) -> list[int]:
        """Add comments for target filename, return list of comments added"""
        assert self.files.filename is not None
        files = self.parse_comments(
            normal, os.path.abspath(self.files.filename), start_line
        )

        # Only handling messages for target filename
        line_data: dict[int, list[Message]] = {}
        if target_filename in files:
            for message in files[target_filename]:
                if message.line not in line_data:
                    line_data[message.line] = []
                line_data[message.line].append(message)

        line_order: list[int] = list(sorted(line_data, reverse=True))
        first: int = line_order[-1] if line_order else start_line

        if first not in line_data:  # if used starting line
            line_data[first] = []
            line_order.append(first)

        for filename in {f for f in files if f != target_filename}:
            line_data[first].append(
                Message(
                    file=target_filename,
                    line=first,
                    message=f"note: Another file has errors: {filename}",
                    column_end=0,
                    msg_type="note",
                )
            )

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

    @undo_block
    def add_errors(self, file: str, start_line: int, errors: str) -> None:
        """Add errors to file"""
        lines = errors.splitlines()
        lines[0] = f"Error running mypy: {lines[0]}"
        for message in reversed(lines):
            self.add_comment(
                Message(
                    file=file,
                    line=start_line,
                    message=message,
                ),
                len(lines),
            )

    def ask_save_dialog(self) -> bool:
        "Ask to save dialog stolen from idlelib.runscript.ScriptBinding"
        msg = "Source Must Be Saved\n" + 5 * " " + "OK to Save?"
        confirm: bool = messagebox.askokcancel(
            title="Save Before Run or Check",
            message=msg,
            default=messagebox.OK,
            parent=self.text,
        )
        return confirm

    async def ensure_daemon_running(self) -> bool:
        "Make sure daemon is running. Return False if cannot continue"
        if not client.is_running(self.status_file):
            started = await client.start(
                self.status_file,
                flags=self.flags,
                daemon_timeout=self.daemon_timeout,
                log_file=self.log_file,
            )
            return started
        return True

    async def shutdown_dmypy_daemon_event_async(
        self, event: "Event[Any]"
    ) -> str:
        "Shutdown dmypy daemon event handler"
        # pylint: disable=unused-argument
        if not client.is_running(self.status_file):
            self.text.bell()
            return "break"

        # Only stop if running
        response = await client.stop(self.status_file)
        if any((v in response and response[v] for v in ("err", "error"))):
            # Kill
            client.kill(self.status_file)

        return "break"

    async def check(self, file: str) -> dict[str, Any]:
        "Preform dmypy check"
        if not await self.ensure_daemon_running():
            return {"out": "", "err": "Error: Could not start mypy daemon"}
        flags = self.flags
        flags += [file]
        # print(f"\n{__title__} DEBUG: check {flags = }\n")
        command = " ".join(
            [
                "dmypy",
                f"--status-file={self.status_file}",
                "run",
                f"--log-file={self.log_file}",
                file,
                "--",
            ]
            + self.flags
        )
        print(f"\n[{__title__}] DEBUG: {command = }")
        return await client.run(
            self.status_file,
            flags=flags,
            timeout=self.action_timeout,
            daemon_timeout=self.daemon_timeout,
            log_file=self.log_file,
            export_types=True,
        )

    def get_suggestion_text(
        self, annotation: dict[str, Any]
    ) -> tuple[str | None, int]:
        """Get suggestion text from annotation.

        Return None on error or no difference, text if different"""
        while annotation["line"] >= 0 and "def" not in self.get_line(
            annotation["line"]
        ):
            annotation["line"] -= 1
        line = annotation["line"]

        try:
            text, line_count = annotate.get_annotation(
                annotation, self.get_line
            )
        except annotate.ParseError as ex:
            ex_text, ex_traceback = sys.exc_info()[1:]
            traceback.print_exception(
                None,  # Ignored since python 3.5
                value=ex_text,
                tb=ex_traceback,
                limit=None,
                chain=True,
            )
            indent = get_line_indent(self.get_line(line))
            return (
                self.get_msg_line(
                    indent, f"Error generating suggestion: {ex}"
                ),
                1,
            )

        select_start = f"{line}.0"
        line_end = line + line_count
        select_end = f"{line_end}.0"

        if text == self.text.get(select_start, select_end)[:-1]:
            return None, line_count
        return text, line_count

    async def suggest(self, file: str, line: int) -> None:
        "Preform dmypy suggest"
        if not await self.ensure_daemon_running():
            response = {"err": "Error: Could not start mypy daemon"}
        else:
            function = f"{file}:{line}"
            response = await client.suggest(
                self.status_file,
                function=function,
                do_json=True,
                timeout=self.action_timeout,
            )
        # print(f'{__title__} DEBUG: suggest {response = }')

        normal = ""
        errors = ""
        if "error" in response:
            errors += response["error"]
        if "err" in response:
            if errors:
                errors += "\n"
            errors += response["err"]
        if "stderr" in response:
            if normal:
                normal += "\n"
            normal += response["stderr"]

        # Display errors
        if errors:
            # Add mypy errors
            self.add_errors(file, self.editwin.getlineno(), errors)

            self.text.bell()
            return

        annotations = json.loads(response["out"])

        line = annotations[0]["line"]

        samples: dict[int, list[str]] = {}
        line_count = 0
        for annotation in annotations:
            count = annotation["samples"]
            text, suggest_lines = self.get_suggestion_text(annotation)
            if text is None:
                continue
            if count not in samples:
                samples[count] = []
            samples[count].append(text)
            line_count += suggest_lines

        order = sorted(samples, reverse=True)
        lines = []
        for count in order:
            for sample in samples[count]:
                if sample not in lines:
                    lines.append(sample)

        replace = self.suggest_replace == "True"

        if len(lines) == 1:
            text = lines[0]
            if "Error generating suggestion: " in text:
                replace = False
        else:
            text = "\n".join(lines)
            replace = False

        select_start = f"{line}.0"
        line_end = line + line_count
        select_end = f"{line_end}.0"

        if not text or text == self.text.get(select_start, select_end)[:-1]:
            # Bell to let user know happened, just nothing to do
            self.editwin.gotoline(line)
            self.text.bell()
            return

        if not replace and "Error generating suggestion: " not in text:
            text = "\n".join(f"##{line}" for line in text.splitlines())
        text += "\n"

        self.undo.undo_block_start()
        try:
            if replace:
                self.text.delete(select_start, select_end)

            self.text.insert(select_start, text, ())
        finally:
            self.undo.undo_block_stop()

        self.editwin.gotoline(line)
        self.text.bell()

    def initial(self) -> tuple[str | None, str | None]:
        """Do common initial setup. Return error or none, file, and start line

        Reload configuration, make sure file is saved,
        and make sure mypy is installed"""
        self.reload()

        # Get file we are checking
        raw_filename: str | None = self.files.filename
        if raw_filename is None:
            return "break", None
        file: str = os.path.abspath(raw_filename)

        # Remember where we started
        start_line_no: int = self.editwin.getlineno()

        if not _HAS_MYPY:
            self.add_comment(
                Message(
                    file=file,
                    line=start_line_no,
                    message="Could not import mypy. "
                    "Please install mypy and restart IDLE "
                    + "to use this extension.",
                ),
                start_line_no,
            )

            # Make bell sound so user knows they need to pay attention
            self.text.bell()
            return "break", file

        # Make sure file is saved.
        if not self.files.get_saved():
            if not self.ask_save_dialog():
                # If not ok to save, do not run. Would break file.
                self.text.bell()
                return "break", file
            # Otherwise, we are clear to save
            self.files.save(None)
            self.files.set_saved(True)

        # Everything worked
        return None, file

    async def suggest_signature_event_async(self, event: "Event[Any]") -> str:
        "Handle suggest signature event"
        # pylint: disable=unused-argument
        init_return, file = self.initial()

        if init_return is not None:
            return init_return
        if file is None:
            return "break"

        await self.suggest(file, self.editwin.getlineno())

        return "break"

    async def type_check_event_async(self, event: "Event[Any]") -> str:
        "Preform a mypy check and add comments."
        init_return, file = self.initial()

        if init_return is not None:
            return init_return
        if file is None:
            return "break"

        # Run mypy on open file
        response = await self.check(file)

        print(f"\n[{__title__}] DEBUG: type check {response = }\n")

        normal = ""
        errors = ""
        if "out" in response:
            normal = response["out"]
        if "error" in response:
            errors += response["error"]
        if "err" in response:
            if errors:
                errors += "\n"
            errors += response["err"]
        if "stdout" in response:
            if normal:
                normal += "\n"
            normal += response["stdout"]
        if "stderr" in response:
            if normal:
                normal += "\n"
            normal += response["stderr"]

        if normal:
            # Add code comments
            self.add_comments(file, self.editwin.getlineno(), normal)

        if errors:
            # Add mypy errors
            self.add_errors(file, self.editwin.getlineno(), errors)

        # Make bell sound so user knows we are done,
        # as it freezes a bit while mypy looks at the file
        self.text.bell()
        return "break"

    @undo_block
    def remove_type_comments_event(self, event: "Event[Any]") -> str:
        "Remove selected mypy comments."
        # pylint: disable=unused-argument
        # Get selected region lines
        head, tail, chars, lines = self.formatter.get_region()
        if self.comment not in chars:
            # Make bell sound so user knows this ran even though
            # nothing happened.
            self.text.bell()
            return "break"
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
        return "break"

    @undo_block
    def remove_all_type_comments(self, event: "Event[Any]") -> str:
        "Remove all mypy comments."
        # pylint: disable=unused-argument
        eof_idx = self.text.index("end")

        chars = self.text.get("0.0", eof_idx)

        lines = chars.splitlines()
        modified = False
        for idx in reversed(range(len(lines))):
            if lines[idx].lstrip().startswith(self.comment):
                del lines[idx]
                modified = True
        if not modified:
            return "break"

        chars = "\n".join(lines)

        # Apply changes
        self.text.delete("0.0", eof_idx)
        self.text.insert("0.0", chars, ())
        return "break"

    @undo_block
    def find_next_type_comment_event(self, event: "Event[Any]") -> str:
        "Find next comment by hacking the search dialog engine."
        # pylint: disable=unused-argument
        self.reload()

        root: Tk = self.editwin.root

        # Get search engine singleton from root
        engine: searchengine.SearchEngine = searchengine.get(root)

        # Get current search prams
        global_search_params = get_search_engine_params(engine)

        # Set search pattern to comment starter
        set_search_engine_params(
            engine,
            {
                "pat": f"^\\s*{self.comment}",
                "re": True,
                "case": True,
                "word": False,
                "wrap": self.search_wrap == "True",
                "back": False,
            },
        )

        # Find current pattern
        search.find_again(self.text)

        # Re-apply previous search prams
        set_search_engine_params(engine, global_search_params)
        return "break"

    # def close(self) -> None:
    #    """Called when any idle editor window closes"""


idlemypyextension.reload()


def get_fake_editwin(root_tk: Tk) -> PyShellEditorWindow:
    "Get fake edit window for testing"
    from idlelib.pyshell import PyShellEditorWindow

    class FakeEditWindow(PyShellEditorWindow):  # type: ignore[misc]
        "FakeEditWindow for testing"

        def __init__(self) -> None:
            return

        from tkinter import Text

        class _FakeText(Text):
            "Make bind do nothing"

            def __init__(self) -> None:
                return

            bind = lambda x, y: None  # type: ignore[assignment]  # noqa
            root = root_tk
            close = None

        text = _FakeText()
        fregion = FormatRegion
        flist = PyShellFileList
        io = IOBinding

    return FakeEditWindow()


if __name__ == "__main__":
    print(f"{__title__} v{__version__}\nProgrammed by {__author__}.\n")
    check_installed()
    # self = idlemypyextension(get_fake_editwin())

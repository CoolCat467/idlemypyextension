"""IDLE Extension Utilities."""

# Programmed by CoolCat467

from __future__ import annotations

# IDLE Extension Utilities
# Copyright (C) 2023-2025  CoolCat467
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

__title__ = "extension-utils"
__author__ = "CoolCat467"
__license__ = "GNU General Public License Version 3"

import importlib
import sys
import time
import traceback
from contextlib import contextmanager
from functools import wraps
from idlelib import search, searchengine
from idlelib.config import idleConf
from os.path import abspath
from pathlib import Path
from tkinter import TclError, Text, Tk, messagebox
from typing import TYPE_CHECKING, ClassVar, Literal, NamedTuple, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Iterable, Sequence
    from idlelib.editor import EditorWindow
    from idlelib.format import FormatRegion
    from idlelib.iomenu import IOBinding
    from idlelib.pyshell import PyShellEditorWindow, PyShellFileList
    from idlelib.undo import UndoDelegator

    from typing_extensions import ParamSpec, Self

    PS = ParamSpec("PS")

T = TypeVar("T")

LOGS_PATH = Path(idleConf.userdir) / "logs"
TITLE: str = __title__


def set_title(title: str) -> None:
    """Set program title."""
    global TITLE
    TITLE = title


def get_required_config(
    values: dict[str, str],
    bind_defaults: dict[str, str | None],
    extension_title: str,
) -> str:
    """Get required configuration file data."""
    if __title__ == TITLE:
        set_title(extension_title)
    config = ""
    # Get configuration defaults
    settings = "\n".join(
        f"{key} = {default}" for key, default in values.items()
    )
    if settings:
        config += f"\n[{extension_title}]\n{settings}"
        if bind_defaults:
            config += "\n"
    # Get key bindings data
    settings = "\n".join(
        f"{event} = {key}"
        for event, key in bind_defaults.items()
        if key is not None
    )
    if settings:
        config += f"\n[{extension_title}_cfgBindings]\n{settings}"
    return config


def check_installed(
    extension: str,
    version: str,
    cls: type[BaseExtension] | None = None,
) -> bool:
    """Make sure extension installed. Return True if installed correctly."""
    # Get list of system extensions
    extensions = set(idleConf.defaultCfg["extensions"])

    # Do we have the user extend extension?
    has_user = "idleuserextend" in idleConf.GetExtensions(active_only=True)

    # If we don't, things get messy and we need to change the root config file
    ex_defaults = idleConf.defaultCfg["extensions"].file
    if has_user:
        # Otherwise, idleuserextend patches IDLE and we only need to modify
        # the user config file
        ex_defaults = idleConf.userCfg["extensions"].file
        extensions |= set(idleConf.userCfg["extensions"])

    if cls is None:
        # Import extension
        module = importlib.import_module(extension)

        # Get extension class
        if not hasattr(module, extension):
            print(
                f"ERROR: Somehow, {extension} was installed improperly, "
                f"no {extension} class found in module. Please report "
                "this on github.",
                file=sys.stderr,
            )
            return False

        cls = getattr(module, extension)
    # if not issubclass(cls, BaseExtension):
    #     raise ValueError(f"Expected BaseExtension subclass, got {cls!r}")

    # If this extension not in there,
    if extension not in extensions:
        # Get extension class keybinding defaults
        required_config = get_required_config(
            getattr(cls, "values", {}),
            getattr(cls, "bind_defaults", {}),
            extension,
        )

        # Tell user how to add it to system list.
        print(f"{extension} not in system registered extensions!")
        print(
            f"Please run the following command to add {extension} "
            + "to system extensions list.\n",
        )
        # Make sure line-breaks will go properly in terminal
        add_data = required_config.replace("\n", "\\n")
        # Tell them the command
        append = "| sudo tee -a"
        if has_user:
            append = ">>"
        print(f"echo -e '{add_data}' {append} {ex_defaults}\n")
    else:
        print(f"Configuration should be good! (v{version})")
        return True
    return False


def get_line_selection(line: int, length: int = 1) -> tuple[str, str]:
    """Get selection strings for given line(s)."""
    return f"{line}.0", f"{line + length}.0"


# Stolen from idlelib.searchengine
def get_line_col(index: str) -> tuple[int, int]:
    """Return (line, col) tuple of integers from {line}.{col} string."""
    line, col = map(int, index.split(".", 1))  # Fails on invalid index
    return line, col


# Stolen from idlelib.searchengine
def get_selected_text_indexes(text: Text) -> tuple[str, str]:
    """Return tuple of {line}.{col} indexes from selection or insert mark."""
    try:
        first = text.index("sel.first")
    except TclError:
        first = None
    try:
        last = text.index("sel.last")
    except TclError:
        last = None
    first = first or text.index("insert")
    last = last or first
    return first, last


def hide_hit(text: Text) -> None:
    """Remove `hit` tag from entire file."""
    text.tag_remove("hit", "1.0", "end")
    # text.update_idletasks()


def set_insert_and_move(text: Text, index: str) -> None:
    """Bring area into view.

    Moves `insert` mark and moves to insert mark.
    """
    text.mark_set("insert", index)
    text.see("insert")

    # Force update
    text.update_idletasks()


def highlight_region(text: Text, tag: str, first: str, last: str) -> None:
    """Add a given tag to the region of text between first and last indices."""
    if first == last:
        text.tag_add(tag, first)
    else:
        text.tag_add(tag, first, last)


def show_hit(text: Text, first: str, last: str, tag: str = "hit") -> None:
    """Highlight text between first and last indices.

    Indexes are formatted as `{line}.{col}` strings.

    Text is highlighted via the 'hit' tag and the marked
    section is brought into view.

    Does not clear previously set hit tags implicitly.

    Note that because of how IDLE works, selection tag ("sel")
    will override "hit" tag, so this function removes selection
    tags from the entire file. If you need this information,
    please use `get_selected_text_indexes` or something equivalent
    beforehand.
    """
    text.tag_remove("sel", "1.0", "end")
    highlight_region(text, tag, first, last)

    set_insert_and_move(text, first)


def get_whole_line(index: str, offset: int = 0) -> str:
    """Return index line plus offset at column zero."""
    line = get_line_col(index)[0]
    return f"{line + offset}.0"


def get_line_indent(text: str, char: str = " ") -> int:
    """Return line indent."""
    index = -1
    for index, cur_char in enumerate(text):
        if cur_char != char:
            return index
    return index + 1


def get_line_indent_handle_tabs(text: str) -> tuple[bool, int]:
    """Return if uses tabs and associated indentation level."""
    uses_tabs = text.startswith("\t")
    if uses_tabs:
        indent = get_line_indent(text, "\t")
    else:
        indent = get_line_indent(text)
    return uses_tabs, indent


def ensure_section_exists(section: str) -> bool:
    """Ensure section exists in user extensions configuration.

    Returns True if edited.
    """
    if section not in idleConf.GetSectionList("user", "extensions"):
        idleConf.userCfg["extensions"].AddSection(section)
        return True
    return False


def ensure_values_exist_in_section(
    section: str,
    values: dict[str, str | None] | dict[str, str],
) -> bool:
    """For each key in values, make sure key exists. Return if edited.

    If key does not exist and default value is not None, create and set
    to value.
    """
    need_save = False
    for key, default in values.items():
        value = idleConf.GetOption(
            "extensions",
            section,
            key,
            warn_on_default=False,
        )
        if value is None and default is not None:
            idleConf.SetOption("extensions", section, key, default)
            need_save = True
    return need_save


def ask_save_dialog(parent: Text) -> bool:
    """Ask to save dialog. Return if ok to save.

    Stolen from idlelib.runscript.ScriptBinding.
    """
    msg = "Source Must Be Saved\n" + 5 * " " + "OK to Save?"
    confirm: bool = messagebox.askokcancel(
        title="Save Before Run or Check",
        message=msg,
        default=messagebox.OK,
        parent=parent,
    )
    return confirm


def get_search_engine_params(
    engine: searchengine.SearchEngine,
) -> dict[str, str | bool]:
    """Get current search engine parameters."""
    return {
        name: getattr(engine, f"{name}var").get()
        for name in ("pat", "re", "case", "word", "wrap", "back")
    }


def set_search_engine_params(
    engine: searchengine.SearchEngine,
    data: dict[str, str | bool],
) -> None:
    """Get current search engine parameters."""
    for name in ("pat", "re", "case", "word", "wrap", "back"):
        if name in data:
            getattr(engine, f"{name}var").set(data[name])


@contextmanager
def search_engine_block(
    engine: searchengine.SearchEngine,
) -> Generator[None, None, None]:
    """Search engine modification context manager."""
    global_search_params = get_search_engine_params(engine)
    try:
        yield None
    finally:
        set_search_engine_params(engine, global_search_params)


@contextmanager
def undo_block(undo: UndoDelegator) -> Generator[None, None, None]:
    """Undo block context manager."""
    undo.undo_block_start()
    try:
        yield None
    finally:
        undo.undo_block_stop()


@contextmanager
def temporary_overwrite(
    object_: object,
    attribute: str,
    value: object,
) -> Generator[None, None, None]:
    """Temporarily overwrite object_.attribute with value, restore on exit."""
    if not hasattr(object_, attribute):
        yield None
    else:
        original = getattr(object_, attribute)
        setattr(object_, attribute, value)
        try:
            yield None
        finally:
            setattr(object_, attribute, original)


def extension_log(content: str) -> None:
    """Log content to extension log file."""
    if not LOGS_PATH.exists():
        LOGS_PATH.mkdir(exist_ok=True)
    log_file = LOGS_PATH / f"{TITLE}.log"
    with log_file.open("a", encoding="utf-8") as fp:
        format_time = time.strftime("[%Y-%m-%d %H:%M:%S] ")
        for line in content.splitlines(keepends=True):
            fp.write(f"{format_time}{line}")
        if not line.endswith("\n"):
            fp.write("\n")


def extension_log_exception(exc: BaseException, print_: bool = True) -> None:
    """Log exception to extension log."""
    exception_text = "".join(traceback.format_exception(exc))
    extension_log(exception_text)
    if print_:
        print(exception_text, file=sys.stderr)


def log_exceptions(function: Callable[PS, T]) -> Callable[PS, T]:
    """Log any exceptions raised."""

    @wraps(function)
    def wrapper(*args: PS.args, **kwargs: PS.kwargs) -> T:
        """Catch Exceptions, log them to log file, and re-raise."""
        try:
            return function(*args, **kwargs)
        except Exception as exc:
            extension_log_exception(exc)
            raise

    return wrapper


class Comment(NamedTuple):
    """Represents one comment."""

    file: str
    line: int
    contents: str
    line_end: int | None = None
    column: int = 0
    column_end: int | None = None

    def get_full_span(self) -> tuple[int, int, int, int]:
        """Return full span as tuple of (line, col, end_line, end_col)."""
        return (
            self.line,
            self.column,
            self.line_end if self.line_end is not None else self.line,
            self.column_end if self.column_end is not None else self.column,
        )

    def replace_content(self, contents: str) -> Self:
        """Return comment with same data except contents."""
        return self._replace(contents=contents)


def int_default(text: str, default: int = 0) -> int:
    """Return text as int or default if there is a ValueError."""
    try:
        return int(text)
    except ValueError:
        return default


class FilePosition(NamedTuple):
    """File Position."""

    path: str
    line: int
    col: int
    line_end: int
    col_end: int

    def is_range(self) -> bool:
        """Return True if file position covers a range."""
        return self.line != self.line_end or self.col != self.col_end

    def as_select(self) -> tuple[str, str]:
        """Return text selection region index strings."""
        return f"{self.line}.{self.col}", f"{self.line_end}.{self.col_end}"

    def delta_column(self, delta: int = -1) -> Self:
        """Return position but with delta added to column."""
        return self._replace(col=self.col + delta)

    @classmethod
    def parse(cls, file_position: str) -> Self:
        """Parse file position string."""
        line = 0
        line_end = 0
        col = 0
        col_end = 0

        windows_drive_letter = ""
        if sys.platform == "win32":
            windows_drive_letter, file_position = file_position.split(":", 1)
            windows_drive_letter += ":"
        position = file_position.split(":", 5)

        filename = position[0]
        if len(position) > 1:
            line = int_default(position[1])
            line_end = line
        if len(position) > 2:
            col = int_default(position[2])
            col_end = col
        if len(position) > 4:
            line_end = int_default(position[3], line_end)
            col_end = int_default(position[4], col_end)

        # If line end is before beginning, swap.
        if line_end < line:
            line, line_end = line_end, line
            col, col_end = col_end, col

        return cls(
            path=f"{windows_drive_letter}{filename}",
            line=line,
            col=col,
            line_end=line_end,
            col_end=col_end,
        )


class BaseExtension:
    """Base extension class."""

    __slots__ = (
        "comment_prefix",
        "editwin",
        "files",
        "flist",
        "formatter",
        "text",
        "undo",
    )

    # Extend the file and format menus.
    menudefs: ClassVar[
        Sequence[tuple[str, Sequence[tuple[str, str] | None]]]
    ] = ()

    # Default values for configuration file
    values: ClassVar[dict[str, str]] = {
        "enable": "True",
        "enable_editor": "True",
        "enable_shell": "False",
    }

    # Default key binds for configuration file
    bind_defaults: ClassVar[dict[str, str | None]] = {}

    def __init__(
        self,
        editwin: PyShellEditorWindow,
        *,
        comment_prefix: str | None = None,
    ) -> None:
        """Initialize this extension."""
        self.editwin: PyShellEditorWindow = editwin
        self.text: Text = editwin.text
        self.undo: UndoDelegator = editwin.undo
        self.formatter: FormatRegion = editwin.fregion
        self.files: IOBinding = editwin.io
        self.flist: PyShellFileList = editwin.flist

        if comment_prefix is None:
            comment_prefix = f"{self.__class__.__name__}"
        self.comment_prefix = f"# {comment_prefix}: "

        self.bind_non_keyboard(self.bind_defaults)

    def __repr__(self) -> str:
        """Return representation of self."""
        return f"{self.__class__.__name__}({self.editwin!r})"

    def bind_non_keyboard(self, bind_defaults: dict[str, str | None]) -> None:
        """Bind non-keyboard triggered events.

        IDLE only binds keyboard events automatically.
        """
        for bind_name, key in bind_defaults.items():
            if key is not None:
                continue
            bind_func_name = bind_name.replace("-", "_") + "_event"
            if not hasattr(self, bind_func_name):
                raise ValueError(f"Missing function {bind_func_name}")
            bind_func = getattr(self, bind_func_name)
            if not callable(bind_func):
                raise ValueError(f"{bind_func_name} should be callable")
            self.text.bind(f"<<{bind_name}>>", bind_func)

    def get_rightclick_menu_labels(self) -> list[str | None]:
        """Return rightclick menu labels."""
        return [entry[0] for entry in self.editwin.rmenu_specs]

    def register_rightclick_menu_entry(
        self,
        label: str,
        event_name: str,
        verify_function: Callable[[], bool] | None = None,
    ) -> None:
        """Register a rightclick menu entry.

        Arguments:
        label: str
            Text to display.
        event_name: str
            Event to raise when entry is selected.
        verify_function: Callable[[], bool] | None
            Optional function to determine if this entry should
            be enabled or not. Returns True if should be enabled.

        Skips adding if label already in right click menu labels.

        """
        if label in self.get_rightclick_menu_labels():
            return

        entry: tuple[str, str, str | None]
        if verify_function is None:
            entry = (label, event_name, None)
        else:
            # Technically can be "normal", "disabled", or "active",
            # where "active" sets it to like it's being hovered
            # but we will say no.
            # Normal is standard unlit, disabled is disabled.
            @wraps(verify_function)
            def verify_state_return_wrap() -> Literal["normal" | "disabled"]:
                return "normal" if verify_function() else "disabled"

            # wacky thing, idlelib.editor.right_menu_event does
            # `state = getattr(self, verify_state)()`
            # so needs to be an attribute on editor object.
            attr_name = f"_rmenu_verify_function_{label.lower()}"
            setattr(self.editwin, attr_name, verify_state_return_wrap)

            entry = (label, event_name, attr_name)
        self.editwin.rmenu_specs.append(entry)

    def register_rightclick_menu_entries(
        self,
        entries: Iterable[tuple[str, str, Callable[[], bool] | None]],
    ) -> None:
        """Register multiple rightclick menu entries.

        Entries are a series of (label, event_name, verify_function) tuples.

        See register_rightclick_menu_entry for more information.
        """
        for label, event_name, verify_function in entries:
            self.register_rightclick_menu_entry(
                label,
                event_name,
                verify_function,
            )

    @classmethod
    def ensure_bindings_exist(cls) -> bool:
        """Ensure key bindings exist in user extensions configuration.

        Return True if need to save.
        """
        if not cls.bind_defaults:
            return False

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

        Return True if need to save.
        """
        need_save = False
        if ensure_section_exists(cls.__name__):
            need_save = True
        if ensure_values_exist_in_section(cls.__name__, cls.values):
            need_save = True
        return need_save

    @classmethod
    def reload(cls) -> None:
        """Load class variables from configuration."""
        # Ensure file default values exist so they appear in settings menu
        save = cls.ensure_config_exists()
        if cls.ensure_bindings_exist() or save:
            idleConf.SaveUserCfgFiles()

        # Reload configuration file
        idleConf.LoadCfgFiles()

        # For all possible configuration values
        for key, default in cls.values.items():
            # Set attribute of key name to key value from configuration file
            if key not in {"enable", "enable_editor", "enable_shell"}:
                value = idleConf.GetOption(
                    "extensions",
                    cls.__name__,
                    key,
                    default=default,
                )
                setattr(cls, key, value)

    def get_tabwidth_indent_spaces(self) -> str:
        """Return tabwidth indent as spaces."""
        return " " * self.editwin.get_tk_tabwidth()

    def get_line(
        self,
        line: int,
        text_win: Text | None = None,
    ) -> str:
        """Get the characters from the given line in currently open file."""
        if text_win is None:
            text_win = self.text
        chars: str = text_win.get(*get_line_selection(line))
        return chars

    def get_line_replace_tabs(
        self,
        line: int,
        text_win: Text | None = None,
    ) -> tuple[bool, str]:
        """Return if line uses tabs and line using spaces."""
        chars = self.get_line(line, text_win)
        if chars.startswith("\t"):
            return True, chars.replace("\t", self.get_tabwidth_indent_spaces())
        return False, chars

    def reinstate_line_tabs(self, line: str) -> str:
        """Return line with leading indent replaced with tabs."""
        indent = get_line_indent(line)
        indent_text = line[:indent]
        post_indent = line[indent:]
        return (
            indent_text.replace(self.get_tabwidth_indent_spaces(), "\t")
            + post_indent
        )

    def reinstate_char_tabs(self, chars: str) -> str:
        """Return potentially multiline string with indentation replaced with tabs."""
        lines = chars.splitlines(keepends=True)
        return "".join(map(self.reinstate_line_tabs, lines))

    def get_comment_line(self, indent: int, content: str) -> str:
        """Return comment line given indent and content."""
        strindent = " " * indent
        return f"{strindent}{self.comment_prefix}{content}"

    def comment_exists(
        self,
        line: int,
        comment: str,
        text_win: Text | None = None,
    ) -> bool:
        """Return True if comment for message already exists on line."""
        return self.get_comment_line(0, comment) in self.get_line(
            line - 1,
            text_win=text_win,
        )

    def add_comment(
        self,
        comment: Comment,
        max_exist_up: int = 0,
    ) -> bool:
        """Return True if added new comment, False if already exists.

        Arguments:
        ---------
            max_exist_up: Max distance upwards to look for comment to already exist.

        Does not use an undo block, please use one yourself.

        """
        # Get line and message from output
        file = comment.file
        line = comment.line
        msg = comment.contents

        editwin: EditorWindow = self.editwin

        open_file: str | None = self.files.filename
        if open_file is None or abspath(open_file) != file:
            opened = self.flist.open(file)
            if opened is None:
                return False
            editwin = opened

        # If there is already a comment from us there, ignore that line.
        # +1-1 is so at least up by 1 is checked, range(0) = []
        for i in range(max_exist_up + 1):
            if self.comment_exists(line - (i - 1), msg, editwin.text):
                return False

        # Get line checker is talking about
        uses_tabs, chars = self.get_line_replace_tabs(line, editwin.text)

        # Figure out line indent
        indent = get_line_indent(chars)

        # Add comment line
        chars = self.get_comment_line(indent, msg) + "\n" + chars
        if uses_tabs:
            chars = self.reinstate_char_tabs(chars)

        # Save changes
        start, end = get_line_selection(line)
        editwin.text.delete(start, end)
        editwin.text.insert(start, chars, ())
        return True

    def get_pointers(self, comments: list[Comment]) -> Comment | None:
        """Return comment pointing to multiple comments all on the same line.

        If none of the comment pointers are going to be visible
        with the comment prefix, returns None.

        Does not handle comments that span multiple lines, assumes
        comments are all comment.line

        Messages must all be on the same line and be in the same file,
        otherwise ValueError is raised.
        """
        line = comments[0].line
        file = comments[0].file

        # Figure out next line intent
        next_line_text = self.get_line(line + 1)
        _uses_tabs, indent = get_line_indent_handle_tabs(next_line_text)

        lastcol = len(self.get_comment_line(indent, ""))

        columns: set[int] = set()

        for comment in comments:
            if comment.line != line:
                raise ValueError(f"Comment `{comment}` not on line `{line}`")
            if comment.file != file:
                raise ValueError(f"Comment `{comment}` not in file `{file}`")
            if comment.column_end is None:
                end = comment.column
            else:
                end = comment.column_end
            for col in range(comment.column, end + 1):
                columns.add(col)

        new_line = ""
        for col in sorted(columns):
            spaces = (col - lastcol) - 1
            if spaces < 0:
                continue
            new_line += " " * spaces + "^"
            lastcol = col

        if not new_line.strip():
            return None

        return Comment(file=file, line=line + 1, contents=new_line)

    def add_comments(
        self,
        comments: Sequence[Comment],
    ) -> dict[str, list[int]]:
        """Add comments to file(s). Ignores comments that already exist.

        Return dict of per file a list of lines were a comment was added.

        Changes are wrapped in an undo block.
        """
        file_comments: dict[str, list[int]] = {}

        with undo_block(self.undo):
            total = len(comments)
            for comment in reversed(comments):
                if self.add_comment(comment, total):
                    file_comments.setdefault(comment.file, [])
                    file_comments[comment.file].append(comment.line)
        return file_comments

    def add_comment_block(
        self,
        file: str,
        start_line: int,
        lines: Sequence[str],
    ) -> list[int]:
        """Add lines to file, in order as they appear top to bottom.

        Returns list of lines were a comment was added.

        Changes are wrapped in an undo block.
        """
        if not lines:
            return []
        file_comments = self.add_comments(
            [
                Comment(
                    file=file,
                    line=start_line,
                    contents=line,
                )
                for line in lines
            ],
        )
        return file_comments.get(file, [])

    def remove_selected_extension_comments(self) -> bool:
        """Remove selected extension comments. Return if removed any comments.

        Changes are wrapped in an undo block.
        """
        # Get selected region lines
        head, _tail, chars, lines = self.formatter.get_region()
        region_start, _col = get_line_col(head)

        edited = False
        with undo_block(self.undo):
            for index, line_text in reversed(tuple(enumerate(lines))):
                # If after indent there is mypy comment
                if line_text.lstrip().startswith(self.comment_prefix):
                    # If so, remove line
                    self.text.delete(
                        *get_line_selection(index + region_start),
                    )
                    edited = True
        if not edited:
            # Make bell sound so user knows this ran even though
            # nothing happened.
            self.text.bell()
        return edited

    def remove_all_extension_comments(self) -> str:
        """Remove all extension comments.

        Changes are wrapped in an undo block.
        """
        eof_idx = self.text.index("end")
        chars = self.text.get("0.0", eof_idx)

        lines = chars.splitlines()

        edited = False
        with undo_block(self.undo):
            for index, line_text in reversed(tuple(enumerate(lines))):
                # If after indent there is mypy comment
                if line_text.lstrip().startswith(self.comment_prefix):
                    # If so, remove line
                    self.text.delete(*get_line_selection(index))
                    edited = True
        if not edited:
            # Make bell sound so user knows this ran even though
            # nothing happened.
            self.text.bell()
        return "break"

    def find_next_extension_comment(self, search_wrap: bool = True) -> bool:
        """Find next extension comment by hacking the search dialog engine.

        Return True if the search was successful and False otherwise.
        """
        root: Tk = self.editwin.root

        # Get search engine singleton from root
        engine: searchengine.SearchEngine = searchengine.get(root)

        # With search engine parameter restore block
        with search_engine_block(engine):
            # Set search pattern to comment starter
            set_search_engine_params(
                engine,
                {
                    "pat": f"^\\s*{self.comment_prefix}",
                    "re": True,
                    "case": True,
                    "word": False,
                    "wrap": search_wrap,
                    "back": False,
                },
            )

            # Find current pattern
            found = search.find_again(self.text)
            assert isinstance(found, bool)
            return found

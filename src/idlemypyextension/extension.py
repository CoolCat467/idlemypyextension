"""Type Check IDLE Extension."""

# Programmed by CoolCat467

from __future__ import annotations

# IDLE Mypy daemon integration extension
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

__title__ = "extension"
__author__ = "CoolCat467"
__license__ = "GNU General Public License Version 3"

import contextlib
import json
import math
import os
import re
import sys
import traceback
from functools import partial, wraps
from idlelib.config import idleConf
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, Final, Literal

from idlemypyextension import annotate, client, tktrio, utils

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from idlelib.pyshell import PyShellEditorWindow
    from tkinter import Event, Misc

DAEMON_TIMEOUT_MIN: Final = 5
ACTION_TIMEOUT_MIN: Final = 5
UNKNOWN_FILE: Final = "<unknown file>"
COULD_NOT_START_ERROR = client.Response(
    {"out": "", "err": "Error: Could not start mypy daemon"},
)


def debug(message: object) -> None:
    """Print debug message."""
    # Censor username/user files
    as_str = str(message)

    ##username = os.getlogin()
    ##home_directory = os.path.expanduser("~")
    ##
    ##as_str = as_str.replace(home_directory, "~")
    ##as_str = as_str.replace(username, "<username>")

    print(f"\n[{__title__}] DEBUG: {as_str}")


MYPY_ERROR_TYPE: Final = re.compile(r"  \[([a-z\-]+)\]\s*$")


def parse_comments(
    mypy_output: str,
    default_file: str = "<unknown file>",
    default_line: int = 0,
) -> dict[str, list[utils.Comment]]:
    """Parse mypy output, return mapping of filenames to lists of comments."""
    files: dict[str, list[utils.Comment]] = {}
    for output_line in mypy_output.splitlines():
        if not output_line.strip():
            continue
        filename = default_file
        line = default_line
        line_end = default_line
        col = 0
        col_end = 0
        msg_type = "unrecognized"

        if output_line.count(": ") < 2:
            text = output_line
        else:
            where, msg_type, text = output_line.split(": ", 2)

            windows_drive_letter = ""
            if sys.platform == "win32":
                windows_drive_letter, where = where.split(":", 1)
                windows_drive_letter += ":"
            position = where.rsplit(":", 4)

            filename = f"{windows_drive_letter}{position[0]}"
            colon_count = len(position)
            if colon_count > 1:
                line = int(position[1])
                line_end = line
            if colon_count > 2:
                col = int(position[2])
                col_end = col
            if colon_count > 4:
                line_end = int(position[3])
                # if line_end == line:
                col_end = int(position[4])
                # else:
                #    line_end = line
        comment_type = MYPY_ERROR_TYPE.search(text)
        if comment_type is not None:
            text = text[: comment_type.start()]
            msg_type = f"{comment_type.group(1)} {msg_type}"

        comment = utils.Comment(
            file=filename,
            line=line,
            contents=f"{msg_type}: {text}",
            column=col,
            line_end=line_end,
            column_end=col_end,
        )

        files.setdefault(filename, [])
        files[filename].append(comment)
    return files


def parse_type_inspect(
    mypy_output: str,
    file: str,
    default_line: int = 0,
) -> list[utils.Comment]:
    """Parse mypy inspect output as a list of comments."""
    comments = []
    for output_line in mypy_output.splitlines():
        if " -> " not in output_line:
            comments.append(utils.Comment(file, default_line, output_line))
            continue
        span, content = output_line.split(" -> ", 1)
        line, column, line_end, column_end = map(int, span.split(":", 3))
        content = content.removeprefix('"').removesuffix('"')
        comments.append(
            utils.Comment(file, line, content, line_end, column, column_end),
        )
    return comments


# Important weird: If event handler function returns 'break',
# then it prevents other bindings of same event type from running.
# If returns None, normal and others are also run.


class idlemypyextension(utils.BaseExtension):  # noqa: N801
    """Add comments from mypy to an open program."""

    __slots__ = ("triorun",)
    # Extend the file and format menus.
    menudefs: ClassVar[
        Sequence[tuple[str, Sequence[tuple[str, str] | None]]]
    ] = (
        (
            "edit",
            (
                None,
                ("_Type Check File", "<<type-check>>"),
                ("Find Next Type Comment", "<<find-next-type-comment>>"),
            ),
        ),
        (
            "format",
            (
                ("Suggest Signature", "<<suggest-signature>>"),
                ("Remove Type Comments", "<<remove-type-comments>>"),
            ),
        ),
        (
            "run",
            (("Shutdown dmypy daemon", "<<shutdown-dmypy-daemon>>"),),
        ),
    )
    # Default values for configuration file
    values: ClassVar[dict[str, str]] = {
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
    bind_defaults: ClassVar[dict[str, str | None]] = {
        "type-check": "<Alt-Key-t>",
        "suggest-signature": "<Alt-Key-s>",
        "remove-type-comments": "<Alt-Shift-Key-T>",
        "find-next-type-comment": "<Alt-Key-g>",
        "shutdown-dmypy-daemon": None,
        "dmypy-inspect-type": None,
        "dmypy-goto-definition": None,
    }

    # Overwritten in reload
    daemon_flags = "None"
    search_wrap = "True"
    suggest_replace = "False"
    timeout_mins = "30"
    action_max_sec = "None"

    # Class attributes
    idlerc_folder = Path(idleConf.userdir).expanduser().absolute()
    mypy_folder = idlerc_folder / "mypy"
    status_file = mypy_folder / "dmypy.json"
    log_file = mypy_folder / "log.txt"

    def __init__(self, editwin: PyShellEditorWindow) -> None:
        """Initialize the settings for this extension."""
        super().__init__(editwin, comment_prefix="types")

        if not self.mypy_folder.exists():
            self.mypy_folder.mkdir(parents=True)

        self.triorun = tktrio.TkTrioRunner(
            self.editwin.top,
            self.flist,
            restore_close=self.editwin.close,
        )

        self.text.after_idle(self.register_rightclick_items)

    def register_rightclick_items(self) -> None:
        """Register right click menu entries."""
        self.register_rightclick_menu_entry(
            "Inspect Type",
            "<<dmypy-inspect-type>>",
        )
        self.register_rightclick_menu_entry(
            "Goto Definition",
            "<<dmypy-goto-definition>>",
        )

    def __getattr__(self, attr_name: str) -> object:
        """Transform event async sync calls to sync wrappers."""
        if attr_name.endswith("_event"):
            as_async = f"{attr_name}_async"
            if hasattr(self, as_async):
                return self.get_async(as_async)
        return super().__getattribute__(attr_name)

    def update_task_status(self, ignore: set[str] | None = None) -> None:
        """Update async task statusbar entry."""
        display = ""
        if hasattr(self.triorun, "nursery"):
            child_tasks = self.triorun.nursery.child_tasks
            task_names = {task.name.rsplit(".", 1)[-1] for task in child_tasks}
            if ignore:
                task_names -= ignore
            if task_names:
                tasks = (
                    name.removesuffix("_async").removesuffix("_event")
                    for name in sorted(task_names)
                )
                tasks = (" ".join(name.split("_")).title() for name in tasks)
                plural = "s" if len(task_names) > 1 else ""
                display = f"Async task{plural}: {', '.join(tasks)}"
        self.editwin.status_bar.set_label("asyncstatus", display, side="right")

    def get_async(
        self,
        name: str,
    ) -> Callable[[Event[Misc]], str]:
        """Get sync callable to run async function."""
        async_function = getattr(self, name)

        # Type of decorated function contains type `Any`
        @wraps(async_function)
        async def task_status_wrap(event: Event[Misc]) -> None:  # type: ignore[misc]
            self.update_task_status()
            try:
                await async_function(event)
            finally:
                self.update_task_status({name})

        # Type of decorated function contains type `Any`
        @wraps(async_function)
        @utils.log_exceptions
        def call_trio(event: Event[Misc]) -> str:  # type: ignore[misc]
            self.triorun(partial(task_status_wrap, event))
            return "break"

        return call_trio

    @property
    def daemon_timeout(self) -> int:
        """Daemon timeout."""
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
        """Action timeout."""
        if self.action_max_sec == "None":
            return None
        try:
            return max(ACTION_TIMEOUT_MIN, int(self.action_max_sec))
        except ValueError:
            return None

    @property
    def flags(self) -> list[str]:
        """Mypy Daemon flags."""
        base = {
            "--hide-error-context",
            "--no-color-output",
            "--show-absolute-path",
            "--no-error-summary",
            "--soft-error-limit=-1",
            "--show-traceback",
            f'--cache-dir="{self.mypy_folder}"',
            # f'--log-file="{self.log_file}"',
            # "--cache-fine-grained",
        }
        if self.daemon_flags == "None":
            return list(base)
        extra = set()
        for arg in self.daemon_flags.split():
            value = arg.strip()
            if value:
                extra.add(value)
        return list(base | extra)

    @property
    def typecomment_only_current_file(self) -> bool:
        """Should only add type comments for currently open file?."""
        return True

    def add_type_comments_for_file(
        self,
        comments: list[utils.Comment],
    ) -> dict[str, list[int]]:
        """Add type comments for target files.

        Return list of lines were a comment was added.

        Changes are wrapped in an undo block.
        """
        # Split up comments by line in order
        line_data: dict[int, list[utils.Comment]] = {}
        for comment in comments:
            line_data.setdefault(comment.line, [])
            line_data[comment.line].append(comment)

        all_messages = []
        for line in sorted(line_data):
            messages = line_data[line]
            if not messages:
                continue
            all_messages.extend(messages)
            pointers = self.get_pointers(messages)
            if pointers is not None:
                all_messages.append(pointers)

        return self.add_comments(all_messages)

    def add_mypy_messages(
        self,
        start_line: int,
        mypy_output: str,
        only_filename: str | None = None,
        add_all_override: bool = False,
    ) -> dict[str, list[int]]:
        """Add mypy comments for target filename.

        Return list of lines where comments were added.

        Changes are wrapped in an undo block.
        """
        default_file = UNKNOWN_FILE
        if self.files.filename is not None:
            default_file = os.path.abspath(self.files.filename)

        if only_filename is not None:
            only_filename = os.path.abspath(only_filename)

        file_comments = parse_comments(
            mypy_output,
            default_file,
            start_line,
        )

        file_commented_lines: dict[str, list[int]] = {}

        to_comment = set(file_comments)

        if self.typecomment_only_current_file and not add_all_override:
            assert only_filename is not None
            to_comment = {only_filename}

            # Find first line in target file or use start_line
            if not file_comments.get(only_filename):
                other_files_comment_line = start_line
            else:
                other_files_comment_line = min(
                    comment.line for comment in file_comments[only_filename]
                )

            # Add comments about how other files have errors
            file_comments.setdefault(only_filename, [])
            for filename in file_comments:
                if filename == only_filename:
                    continue
                file_comments[only_filename].append(
                    utils.Comment(
                        file=only_filename,
                        line=other_files_comment_line,
                        contents=f"Another file has errors: {filename!r}",
                        column_end=0,
                    ),
                )

        for target_filename in to_comment:
            if target_filename not in file_comments:
                continue
            if target_filename == UNKNOWN_FILE:
                continue
            file_comment_lines = self.add_type_comments_for_file(
                file_comments[target_filename],
            )
            file_commented_lines.update(file_comment_lines)
        return file_commented_lines

    def add_extra_data(
        self,
        file: str,
        start_line: int,
        data: str,
        prefix: str = "",
    ) -> tuple[int, list[int]]:
        """Add extra data to file as a big block of comments.

        Returns
        -------
        Tuple of:
        - Number of lines attempted to add
        - List of line numbers added that were not already there
        otherwise empty because no content.

        Changes are wrapped in an undo block.

        """
        if not data:
            return 0, []
        lines = data.splitlines()
        if not lines:
            return 0, []
        lines[0] = f"{prefix}{lines[0]}"
        added = self.add_comment_block(file, start_line, lines)
        return len(lines), added

    def add_errors(
        self,
        file: str,
        start_line: int,
        errors: str,
    ) -> tuple[int, list[int]]:
        """Add error lines to file as a block of comments.

        Returns
        -------
        Tuple of:
        - Number of lines attempted to add
        - List of line numbers added that were not already there
        otherwise None because no content.

        """
        return self.add_extra_data(
            file,
            start_line,
            errors,
            prefix="Error running mypy: ",
        )

    async def ensure_daemon_running(self) -> bool:
        """Make sure daemon is running. Return False if cannot continue."""
        if await client.is_running(self.status_file):
            return True
        command = " ".join(
            x
            for x in [
                "dmypy",
                f'--status-file="{self.status_file}"',
                "start",
                f'--log-file="{self.log_file}"',
                (
                    f"--timeout={self.daemon_timeout}"
                    if self.daemon_timeout
                    else ""
                ),
                "--",
                *self.flags,
            ]
            if x
        )
        debug(f"{command = }")
        return await client.start(
            self.status_file,
            flags=self.flags,
            daemon_timeout=self.daemon_timeout,
            log_file=self.log_file,
        )

    async def shutdown_dmypy_daemon_event_async(
        self,
        event: Event[Misc],
    ) -> str:
        """Shutdown dmypy daemon event handler."""
        # pylint: disable=unused-argument
        if not await client.is_running(self.status_file):
            self.text.bell()
            return "break"

        # Only stop if running
        command = f'dmypy --status-file="{self.status_file}" stop'
        debug(f"{command = }")
        response = await client.stop(self.status_file)
        debug(f"{response = }")
        if response.get("err") or response.get("error"):
            # Kill
            await client.kill(self.status_file)

        return "break"

    async def check(self, file: str) -> client.Response:
        """Perform dmypy check."""
        if not await self.ensure_daemon_running():
            return COULD_NOT_START_ERROR
        ##flags = self.flags
        ##flags += [file]
        ### debug(f"check {flags = }")
        ##command = " ".join(
        ##    x
        ##    for x in [
        ##        "dmypy",
        ##        f'--status-file="{self.status_file}"',
        ##        "run",
        ##        (
        ##            f"--timeout={self.action_timeout}"
        ##            if self.action_timeout
        ##            else ""
        ##        ),
        ##        f'--log-file="{self.log_file}"',
        ##        "--export-types",
        ##        f'"{file}"',
        ##        "--",
        ##        *self.flags,
        ##    ]
        ##    if x
        ##)
        ##debug(f"{command = }")
        ##return await client.run(
        ##    self.status_file,
        ##    flags=flags,
        ##    timeout=self.action_timeout,
        ##    daemon_timeout=self.daemon_timeout,
        ##    log_file=self.log_file,
        ##    export_types=True,
        ##)
        command = f"dmypy --status-file='{self.status_file}' check --export-types {file!r}"
        debug(f"{command = }")
        return await client.check(
            self.status_file,
            files=[file],
            timeout=self.action_timeout,
            export_types=True,
        )

    def get_suggestion_text(
        self,
        annotation: dict[str, object],
    ) -> tuple[str | None, int]:
        """Get suggestion text from annotation.

        Return None on error or no difference, text if different
        """
        # while annotation["line"] >= 0 and "def" not in self.get_line(
        #     annotation["line"],
        # ):
        #     annotation["line"] -= 1
        line = annotation["line"]
        assert isinstance(line, int)

        try:
            text, line_count = annotate.get_annotation(
                annotation,
                self.get_line,
            )
        except Exception as ex:
            ex_text, ex_traceback = sys.exc_info()[1:]
            traceback.print_exception(
                None,  # Ignored since python 3.5
                value=ex_text,
                tb=ex_traceback,
                limit=None,
                chain=True,
            )
            indent = utils.get_line_indent(self.get_line(line))
            return (
                self.get_comment_line(
                    indent,
                    f"Error generating suggestion: {ex}",
                ),
                1,
            )

        select_start = f"{line}.0"
        line_end = line + line_count
        select_end = f"{line_end}.0"

        if text == self.text.get(select_start, select_end)[:-1]:
            return None, line_count
        return text, line_count

    def get_response_errors(self, response: client.Response) -> str | None:
        """Return errors from response if they exist else None."""
        errors = ""
        if response.get("error"):
            errors += response["error"]
        if response.get("err"):
            if errors:
                errors += "\n\n"
            errors += response["err"]
        if response.get("stderr"):
            if errors:
                errors += "\n\n"
            errors += f"stderr:\n{response['stderr']}"
        if "out" not in response and not errors:
            errors += "No response from dmypy daemon."

        return errors if errors else None

    async def suggest(self, file: str, line: int) -> None:
        """Perform dmypy suggest."""
        if await self.ensure_daemon_running():
            function = f"{file}:{line}"

            command = " ".join(
                (
                    "dmypy",
                    f'--status-file="{self.status_file}"',
                    "suggest",
                    f'"{function}"',
                ),
            )
            debug(f"{command = }")

            response = await client.suggest(
                self.status_file,
                function=function,
                do_json=True,
                timeout=self.action_timeout,
            )
        else:
            response = COULD_NOT_START_ERROR
        debug(f"suggest {response = }")

        if errors := self.get_response_errors(response):
            # Display errors
            # self.editwin.getlineno()
            self.add_errors(file, line, errors)
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

        with utils.undo_block(self.undo):
            if replace:
                self.text.delete(select_start, select_end)

            self.text.insert(select_start, text, ())

        self.editwin.gotoline(line)
        self.text.bell()

    def initial(self) -> tuple[str | None, str | None]:
        """Do common initial setup. Return error or none, file.

        Reload configuration, make sure file is saved,
        and make sure mypy is installed
        """
        # Reload configuration
        self.reload()

        # Get file we are checking
        raw_filename: str | None = self.files.filename
        if raw_filename is None:
            return "break", None
        file: str = os.path.abspath(raw_filename)

        # Make sure file is saved.
        if not self.files.get_saved():
            if not utils.ask_save_dialog(self.text):
                # If not ok to save, do not run. Would break file.
                self.text.bell()
                return "break", file
            # Otherwise, we are clear to save
            self.files.save(None)
            if not self.files.get_saved():
                return "break", file

        # Everything worked
        return None, file

    async def suggest_signature_event_async(self, event: Event[Misc]) -> str:
        """Handle suggest signature event."""
        # pylint: disable=unused-argument
        init_return, file = self.initial()

        if init_return is not None:
            return init_return

        if file is None:
            return "break"

        # if client.REQUEST_LOCK.locked():
        #     # If already requesting something from daemon,
        #     # do not send any other requests.
        #     debug(client.REQUEST_LOCK.statistics())
        #     # Make bell sound so user knows this ran even though
        #     # nothing happened.
        #     self.text.bell()
        #     return "break"

        await self.suggest(file, self.editwin.getlineno())

        return "break"

    async def dmypy_inspect(
        self,
        location: str,
        show: Literal["type", "attrs", "definition"],
        include_span: bool,
    ) -> client.Response:
        """Return result from dmypy inspect."""
        if await self.ensure_daemon_running():
            command = " ".join(
                x
                for x in (
                    "dmypy",
                    f"--status-file='{self.status_file}'",
                    "inspect",
                    f"--show={show!r}",
                    ("--include-span" if include_span else ""),
                    "--force-reload",
                    f"{location!r}",
                )
                if x
            )
            debug(f"{command = }")

            return await client.inspect(
                self.status_file,
                location=location,
                show=show,
                include_span=include_span,
                force_reload=True,  # needed_save,
            )
        return COULD_NOT_START_ERROR

    async def dmypy_inspect_shared(
        self,
        show: Literal["type", "attrs", "definition"],
        include_span: bool,
    ) -> (
        tuple[Literal[False], str] | tuple[Literal[True], tuple[str, str, int]]
    ):
        """Shared dmypy inspect code, return either fail string or success (output, file, line_no)."""
        # needed_save = not self.files.get_saved()
        init_return, file = self.initial()

        if init_return is not None:
            return False, init_return

        if file is None:
            return False, "break"

        sel_start, sel_end = utils.get_selected_text_indexes(self.text)

        start_line, start_col = utils.get_line_col(sel_start)
        end_line, end_col = utils.get_line_col(sel_end)

        location = f"{file}:{start_line}:{start_col + 1}"
        if sel_start != sel_end:
            location += f":{end_line}:{end_col}"

        result = await self.dmypy_inspect(location, show, include_span)

        if errors := self.get_response_errors(result):
            # Display errors
            # self.editwin.getlineno()
            with utils.undo_block(self.undo):
                self.add_errors(file, start_line, errors)
            self.text.bell()
            return False, "break"

        output = result["out"]
        if result.get("status"):
            with utils.undo_block(self.undo):
                self.add_errors(file, start_line, output)
            return False, "break"

        return True, (output, file, start_line)

    async def dmypy_inspect_type_event_async(self, event: Event[Misc]) -> str:
        """Perform dmypy inspect type from right click menu."""
        success, maybe_response = await self.dmypy_inspect_shared(
            show="type",
            include_span=True,
        )
        if not success:
            value = maybe_response
            assert not isinstance(value, tuple)
            # Failed somehow
            return value

        response_tuple = maybe_response
        assert isinstance(response_tuple, tuple)
        response, file, start_line = response_tuple

        comments = parse_type_inspect(response, file, start_line)

        for index, comment in enumerate(tuple(comments)):
            pointer = self.get_pointers([comment])
            if not pointer:
                continue
            comments[index] = pointer.replace_content(
                f"{pointer.contents} - {comment.contents}",
            )
        with utils.undo_block(self.undo):
            self.add_comments(comments)

        return "break"

    async def dmypy_goto_definition_event_async(
        self,
        event: Event[Misc],
    ) -> str:
        """Perform dmypy inspect definition from right click menu."""
        success, maybe_response = await self.dmypy_inspect_shared(
            show="definition",
            include_span=False,
        )
        if not success:
            value = maybe_response
            assert not isinstance(value, tuple)
            # Failed somehow
            return value

        response_tuple = maybe_response
        assert isinstance(response_tuple, tuple)
        raw_locations, file, start_line = response_tuple

        # Just read first one
        raw_location = raw_locations.splitlines()[0]

        debug(f"goto definition {raw_location = }")
        location, _function = raw_location.rsplit(":", 1)

        position = utils.FilePosition.parse(location)
        position = position.delta_column()

        # Try to get editor window of file path
        editor_window = self.flist.open(position.path)

        # On failure do a bell
        if editor_window is None:
            self.text.bell()
            return "break"

        # Show selection in file
        utils.show_hit(editor_window.text, *position.as_select(), tag="sel")

        return "break"

    def type_check_add_response_comments(
        self,
        response: client.Response,
        file: str,
    ) -> None:
        """Add all the comments (error and regular) from dmypy response."""
        debug(f"type check {response = }")

        if response.get("out"):
            # Add code comments
            self.add_mypy_messages(
                self.editwin.getlineno(),
                response["out"],
                file,
            )
        if response.get("error"):
            self.add_errors(file, self.editwin.getlineno(), response["error"])
        if response.get("err"):
            # Add mypy run errors
            self.add_errors(file, self.editwin.getlineno(), response["err"])
        if response.get("stdout"):
            self.add_extra_data(
                file,
                self.editwin.getlineno(),
                response["stdout"],
                prefix="dmypy run stdout: ",
            )
        if response.get("stderr"):
            self.add_extra_data(
                file,
                self.editwin.getlineno(),
                response["stderr"],
                prefix="dmypy run stderr: ",
            )

        # Make bell sound so user knows we are done,
        # as it freezes a bit while mypy looks at the file
        self.text.bell()

    async def type_check_event_async(self, event: Event[Misc]) -> str:
        """Perform a mypy check and add comments."""
        init_return, file = self.initial()

        if init_return is not None:
            return init_return

        if file is None:
            return "break"

        if client.REQUEST_LOCK.locked():
            # If already requesting something from daemon,
            # do not send any other requests.
            debug(client.REQUEST_LOCK.statistics())
            # Make bell sound so user knows this ran even though
            # nothing happened.
            self.text.bell()
            return "break"

        # Run mypy on open file
        response = await self.check(file)

        self.type_check_add_response_comments(response, file)
        return "break"

    @utils.log_exceptions
    def remove_type_comments_event(self, _event: Event[Misc]) -> str:
        """Remove selected extension comments."""
        self.remove_selected_extension_comments()
        return "break"

    @utils.log_exceptions
    def remove_all_type_comments(self, _event: Event[Misc]) -> str:
        """Remove all extension comments."""
        self.remove_all_extension_comments()
        return "break"

    @utils.log_exceptions
    def find_next_type_comment_event(self, _event: Event[Misc]) -> str:
        """Find next extension comment by hacking the search dialog engine."""
        # Reload configuration
        self.reload()

        # Find comment
        self.find_next_extension_comment(self.search_wrap == "True")

        return "break"

    def unregister_async_events(self) -> None:
        """Unregister asynchronous event handlers."""
        for bind_name in self.bind_defaults:
            attr_name = bind_name.replace("-", "_") + "_event_async"
            if hasattr(self, attr_name):
                self.text.event_delete(f"<<{bind_name}>>")

    @utils.log_exceptions
    def on_reload(self) -> None:
        """Extension cleanup before IDLE window closes."""
        # Wrapped in try except so failure doesn't cause zombie windows.
        with contextlib.suppress(AttributeError):
            del self.triorun
        try:
            self.unregister_async_events()
        except Exception as exc:
            utils.extension_log_exception(exc)

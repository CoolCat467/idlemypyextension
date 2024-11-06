"""Type Check IDLE Extension."""

# Programmed by CoolCat467

from __future__ import annotations

# IDLE Mypy daemon integration extension
# Copyright (C) 2023-2024  CoolCat467
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

import json
import math
import os
import re
import sys
import traceback
from functools import partial, wraps
from idlelib.config import idleConf
from typing import TYPE_CHECKING, Any, ClassVar, Final

from idlemypyextension import annotate, client, mttkinter, tktrio, utils

if TYPE_CHECKING:
    from collections.abc import Callable
    from idlelib.pyshell import PyShellEditorWindow
    from tkinter import Event

DAEMON_TIMEOUT_MIN: Final = 5
ACTION_TIMEOUT_MIN: Final = 5
UNKNOWN_FILE: Final = "<unknown file>"


def debug(message: object) -> None:
    """Print debug message."""
    # TODO: Censor username/user files
    print(f"\n[{__title__}] DEBUG: {message}")


def parse_comments(
    mypy_output: str,
    default_file: str = "<unknown file>",
    default_line: int = 0,
) -> dict[str, list[utils.Comment]]:
    """Parse mypy output, return mapping of filenames to lists of comments."""
    error_type = re.compile(r"  \[[a-z\-]+\]\s*$")

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

            position = where.split(":", 4)

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


# Important weird: If event handler function returns 'break',
# then it prevents other bindings of same event type from running.
# If returns None, normal and others are also run.


class idlemypyextension(utils.BaseExtension):  # noqa: N801
    """Add comments from mypy to an open program."""

    __slots__ = ("triorun",)
    # Extend the file and format menus.
    menudefs: ClassVar = [
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
    values: ClassVar = {
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
    bind_defaults: ClassVar = {
        "type-check": "<Alt-Key-t>",
        "suggest-signature": "<Alt-Key-s>",
        "remove-type-comments": "<Alt-Shift-Key-T>",
        "find-next-type-comment": "<Alt-Key-g>",
    }

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
        super().__init__(editwin, comment_prefix="types")

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
    ) -> Callable[[Event[Any]], str]:
        """Get sync callable to run async function."""
        async_function = getattr(self, name)

        @wraps(async_function)
        @utils.log_exceptions
        def call_trio(event: Event[Any]) -> str:
            self.triorun(partial(async_function, event))
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
            return max(ACTION_TIMEOUT_MIN, int(self.values["action_max_sec"]))

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
        for arg in self.daemon_flags.split(" "):
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
        target_filename: str,
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

        files = parse_comments(
            mypy_output,
            default_file,
            start_line,
        )

        file_commented_lines: dict[str, list[int]] = {}

        to_comment = list(files)

        if self.typecomment_only_current_file and not add_all_override:
            assert only_filename is not None
            to_comment = [only_filename]

            # Find first line in target file or use start_line
            if not files.get(only_filename):
                other_files_comment_line = start_line
            else:
                other_files_comment_line = min(
                    comment.line for comment in files[only_filename]
                )

            # Add comments about how other files have errors
            files.setdefault(only_filename, [])
            for filename in files:
                if filename == only_filename:
                    continue
                files[only_filename].append(
                    utils.Comment(
                        file=only_filename,
                        line=other_files_comment_line,
                        contents=f"Another file has errors: {filename!r}",
                        column_end=0,
                    ),
                )

        for target_filename in to_comment:
            if target_filename not in files:
                continue
            if target_filename == UNKNOWN_FILE:
                continue
            file_comments = self.add_type_comments_for_file(
                target_filename,
                files[target_filename],
            )
            file_commented_lines.update(file_comments)
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
        if not client.is_running(self.status_file):
            return await client.start(
                self.status_file,
                flags=self.flags,
                daemon_timeout=self.daemon_timeout,
                log_file=self.log_file,
            )
        return True

    async def shutdown_dmypy_daemon_event_async(
        self,
        event: Event[Any],
    ) -> str:
        """Shutdown dmypy daemon event handler."""
        # pylint: disable=unused-argument
        if not client.is_running(self.status_file):
            self.text.bell()
            return "break"

        # Only stop if running
        response = await client.stop(self.status_file)
        if response.get("err") or response.get("error"):
            # Kill
            client.kill(self.status_file)

        return "break"

    async def check(self, file: str) -> client.Response:
        """Perform dmypy check."""
        if not await self.ensure_daemon_running():
            return client.Response(
                {"out": "", "err": "Error: Could not start mypy daemon"},
            )
        flags = self.flags
        flags += [file]
        # debug(f"check {flags = }")
        command = " ".join(
            x
            for x in [
                "dmypy",
                f'--status-file="{self.status_file}"',
                "run",
                (
                    f"--timeout={self.action_timeout}"
                    if self.action_timeout
                    else ""
                ),
                f'--log-file="{self.log_file}"',
                "--export-types",
                f'"{file}"',
                "--",
                *self.flags,
            ]
            if x
        )
        debug(f"{command = }")
        return await client.run(
            self.status_file,
            flags=flags,
            timeout=self.action_timeout,
            daemon_timeout=self.daemon_timeout,
            log_file=self.log_file,
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

    async def suggest(self, file: str, line: int) -> None:
        """Perform dmypy suggest."""
        if not await self.ensure_daemon_running():
            response = client.Response(
                {"err": "Error: Could not start mypy daemon"},
            )
        else:
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
        debug(f"suggest {response = }")

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
            errors += f'stderr:\n{response["stderr"]}'
        if "out" not in response and not errors:
            errors += "No response from dmypy daemon."

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

    async def suggest_signature_event_async(self, event: Event[Any]) -> str:
        """Handle suggest signature event."""
        # pylint: disable=unused-argument
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

        await self.suggest(file, self.editwin.getlineno())

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

    async def type_check_event_async(self, event: Event[Any]) -> str:
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
    def remove_type_comments_event(self, _event: Event[Any]) -> str:
        """Remove selected extension comments."""
        self.remove_selected_extension_comments()
        return "break"

    @utils.log_exceptions
    def remove_all_type_comments(self, _event: Event[Any]) -> str:
        """Remove all extension comments."""
        self.remove_all_extension_comments()
        return "break"

    @utils.log_exceptions
    def find_next_type_comment_event(self, _event: Event[Any]) -> str:
        """Find next extension comment by hacking the search dialog engine."""
        # Reload configuration
        self.reload()

        # Find comment
        self.find_next_extension_comment(self.search_wrap == "True")

        return "break"

    def unregister_async_events(self) -> None:
        """Unregister asynchronous event handlers."""
        for attr_name in dir(self):
            if attr_name.startswith("_"):
                continue
            if attr_name.endswith("_event_async"):
                bind_name = "-".join(attr_name.split("_")[:-2]).lower()
                self.text.event_delete(f"<<{bind_name}>>")

    @utils.log_exceptions
    def close(self) -> None:
        """Extension cleanup before IDLE window closes."""
        # Wrapped in try except so failure doesn't cause zombie windows.
        del self.triorun
        try:
            mttkinter.restore()
            self.unregister_async_events()
        except Exception as exc:
            traceback.print_exception(exc)

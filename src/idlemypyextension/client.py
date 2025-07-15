"""Client for mypy daemon mode - Modified version of mypy.dmypy.client.

This manages a daemon process which keeps useful state in memory
rather than having to read it back from disk on each run.
"""

# Modified by CoolCat467
# Original at https://github.com/python/mypy/blob/master/mypy/dmypy/client.py
# Original retrieved November 24th 2022
# Last updated to match original on March 11th 2023

# Mypy (and mypyc) are licensed under the terms of the MIT license,
# reproduced below.
#
#    The MIT License
#
#    Copyright (c) 2012-2022 Jukka Lehtosalo and contributors
#    Copyright (c) 2015-2022 Dropbox, Inc.
#
#    Permission is hereby granted, free of charge, to any person obtaining a
#    copy of this software and associated documentation files (the "Software"),
#    to deal in the Software without restriction, including without limitation
#    the rights to use, copy, modify, merge, publish, distribute, sublicense,
#    and/or sell copies of the Software, and to permit persons to whom the
#    Software is furnished to do so, subject to the following conditions:
#
#    The above copyright notice and this permission notice shall be included in
#    all copies or substantial portions of the Software.
#
#    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
#    THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#    LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
#    FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
#    DEALINGS IN THE SOFTWARE.

from __future__ import annotations

__title__ = "Mypy Daemon Client"
__license__ = "MIT"

import base64
import contextlib
import sys
from collections import ChainMap
from typing import TYPE_CHECKING, Literal, TypedDict, cast

import orjson

from idlemypyextension.moduleguard import guard_imports
from idlemypyextension.utils import extension_log, extension_log_exception

with guard_imports({"trio", "mypy"}):
    import trio
    from mypy.dmypy_os import alive as _alive, kill as _kill
    from mypy.dmypy_server import (
        Server as _Server,
        daemonize as _daemonize,
        process_start_options as _process_start_options,
    )
    from mypy.ipc import IPCClient as _IPCClient, IPCException as _IPCException
    from mypy.version import __version__

if TYPE_CHECKING:
    import io
    import os
    from collections.abc import Sequence

    from typing_extensions import NotRequired


# If should force to use base request system mypy implements
# If False and not on windows, will manually read unix sockets asynchronously.
FORCE_BASE_REQUEST: bool = False


def debug(message: str) -> None:
    """Print debug message."""
    # TODO: Censor username/user files
    content = f"[{__title__}] DEBUG: {message}"
    print(f"\n{content}")
    extension_log(content)


class Stats(TypedDict):
    """Statistics dictionary from dmypy response."""

    validate_meta_time: float
    files_parsed: int
    modules_parsed: int
    stubs_parsed: int
    parse_time: float
    find_module_time: float
    find_module_calls: int
    graph_size: int
    stubs_found: int
    graph_load_time: float
    fm_cache_size: int
    load_fg_deps_time: float
    sccs_left: int
    nodes_left: int
    cache_commit_time: float


class Response(TypedDict):
    """Response dictionary from dmypy."""

    platform: NotRequired[str]
    python_version: NotRequired[str]
    out: NotRequired[str]
    err: NotRequired[str]
    stdout: NotRequired[str]
    stderr: NotRequired[str]
    error: NotRequired[str]
    memory_psutil_missing: NotRequired[str]
    memory_rss_mib: NotRequired[float]
    memory_vms_mib: NotRequired[float]
    memory_maxrss_mib: NotRequired[float]
    restart: NotRequired[str]
    status: NotRequired[int]
    stats: NotRequired[Stats]
    final: NotRequired[bool]


class BadStatusError(Exception):
    """Exception raised when there is something wrong with the status file.

    For example:
    - No status file found
    - Status file malformed
    - Process whose process id is in the status file does not exist
    """


# Client-side infrastructure.


def str_maintain_none(obj: str | object | None) -> str | None:
    """Return string or None, maintaining None."""
    if obj is None:
        return None
    return str(obj)


async def _read_status(
    status_file: str | os.PathLike[str],
) -> dict[str, object]:
    """Read status file.

    Raise BadStatusError if the status file doesn't exist or contains
    invalid JSON or the JSON is not a dict.
    """
    path = trio.Path(status_file)
    if not await path.is_file():
        raise BadStatusError("No status file found")

    contents = await path.read_text(encoding="utf-8")
    try:
        data = orjson.loads(contents)
    except Exception as exc:
        extension_log_exception(exc)
        raise BadStatusError("Malformed status file (not JSON)") from exc
    if not isinstance(data, dict):
        raise BadStatusError("Invalid status file (not a dict)")
    return data


def _check_status(data: dict[str, object]) -> tuple[int, str]:
    """Check if the process is alive.

    Return (process id, connection_name) on success.

    Raise BadStatusError if something's wrong.
    """
    if "pid" not in data:
        raise BadStatusError("Invalid status file (no pid field)")
    pid = data["pid"]
    if not isinstance(pid, int):
        raise BadStatusError("pid field is not an int")
    if not _alive(pid):
        raise BadStatusError("Daemon has died")
    if "connection_name" not in data:
        raise BadStatusError("Invalid status file (no connection_name field)")
    connection_name = data["connection_name"]
    if not isinstance(connection_name, str):
        raise BadStatusError("connection_name field is not a string")
    return pid, connection_name


async def get_status(status_file: str | os.PathLike[str]) -> tuple[int, str]:
    """Read status file and check if the process is alive.

    Return (process id, connection_name) on success.

    Raise BadStatusError if something's wrong.
    """
    data = await _read_status(status_file)
    return _check_status(data)


def _read_request_response_json(request_response: str | bytes) -> Response:
    """Read request response json."""
    # debug(f'{request_response = }')
    try:
        data = orjson.loads(request_response)
    except Exception as exc:
        extension_log_exception(exc)
        return {"error": "Data received is not valid JSON"}
    if not isinstance(data, dict):
        return {"error": f"Data received is not a dict (got {type(data)})"}
    return cast("Response", data)


async def _request_win32(
    name: str,
    request_arguments: bytes,
    timeout: int | None = None,  # noqa: ASYNC109
) -> Response:
    """Request from daemon on windows."""

    async def _receive(
        async_connection: trio._file_io.AsyncIOWrapper[io.StringIO],
    ) -> Response:
        """Receive JSON data from a connection until EOF.

        Raise OSError if the data received is not valid JSON or if it is
        not a dict.
        """
        bdata: str = await async_connection.read()
        if not bdata:
            return {"error": "No data received, IPC socket connection closed."}
        return _read_request_response_json(bdata)

    try:
        all_responses: list[Response] = []
        with _IPCClient(name, timeout) as client:
            async_client = trio.wrap_file(cast("io.StringIO", client))
            await async_client.write(request_arguments.decode("utf-8"))

            final = False
            while not final:
                response = await _receive(async_client)
                final = bool(response.pop("final", False))
                all_responses.append(response)
                debug(f"{response = }")
        # if len(all_responses) > 1:
        #    debug(f"request win32 {all_responses = }")
        return cast("Response", dict(ChainMap(*all_responses).items()))  # type: ignore[arg-type]
    except (OSError, _IPCException, ValueError) as err:
        return {"error": str(err)}


def find_frame_in_buffer(
    buffer: bytearray,
) -> tuple[bytearray, bytearray | None]:
    """Return a full frame from the bytes we have in the buffer.

    Returns (next frame keep data, complete frame | None)
    """
    space_pos = buffer.find(b" ")
    if space_pos == -1:
        # Incomplete frame
        return buffer, None
    # We have a full frame
    return buffer[space_pos + 1 :], buffer[:space_pos]


async def _request_linux(
    filename: str,
    request_arguments: bytes,
    timeout: float | None = None,  # noqa: ASYNC109
) -> Response:
    """Request from daemon on linux/unix."""
    buffer = bytearray()
    frame: bytearray | None = None
    all_responses: list[Response] = []
    async with await trio.open_unix_socket(filename) as connection:
        # Frame the data by urlencoding it and separating by space.
        request_frame = base64.encodebytes(request_arguments) + b" "
        await connection.send_all(request_frame)

        is_not_done = True
        while is_not_done:
            # Receive more data into the buffer.
            try:
                if timeout is None:
                    more = await connection.receive_some()
                else:
                    with trio.fail_after(timeout):
                        more = await connection.receive_some()
            except trio.TooSlowError:
                return {"error": "IPC socket connection timed out"}
            if not more:
                # Connection closed
                # Socket was empty and we didn't get any frame.
                return {
                    "error": "No data received, IPC socket connection closed.",
                }
            buffer.extend(more)

            buffer, frame = find_frame_in_buffer(buffer)
            if frame is None:
                continue
            # Frame is not None, we read a full frame
            response_text = base64.decodebytes(frame)
            response = _read_request_response_json(response_text)

            is_not_done = not bool(response.pop("final", False))
            all_responses.append(response)
            debug(f"{response = }")
    # if len(all_responses) > 1:
    #    debug(f"request linux {all_responses = }")
    return cast("Response", dict(ChainMap(*all_responses).items()))  # type: ignore[arg-type]


REQUEST_LOCK = trio.Lock()


async def request(
    status_file: str | os.PathLike[str],
    command: str,
    *,
    timeout: int | None = None,  # noqa: ASYNC109
    **kwds: object,
) -> Response:
    """Send a request to the daemon.

    Return the JSON dict with the response.

    Raise BadStatusError if there is something wrong with the status file
    or if the process whose process id is in the status file has died.

    Return {'error': <message>} if an IPC operation or receive()
    raised OSError.  This covers cases such as connection refused or
    closed prematurely as well as invalid JSON received.

    `stdout` and `stderr` fields are apparently debug data.
    """
    args = dict(kwds)
    args["command"] = command
    # Tell the server whether this request was NOT initiated from a
    # human-facing terminal, so that it can format the type checking
    # output accordingly.
    args["is_tty"] = False
    args["terminal_width"] = 80
    request_arguments = orjson.dumps(args)
    _pid, name = await get_status(status_file)

    async with REQUEST_LOCK:
        if sys.platform == "win32" or FORCE_BASE_REQUEST:
            return await _request_win32(name, request_arguments, timeout)
        # Windows run thinks unreachable, everything else knows it is not
        return await _request_linux(  # type: ignore[unreachable,unused-ignore]
            name,
            request_arguments,
            timeout,
        )


async def is_running(status_file: str | os.PathLike[str]) -> bool:
    """Check if the server is running cleanly."""
    try:
        await get_status(status_file)
    except BadStatusError:
        return False
    return True


async def stop(status_file: str | os.PathLike[str]) -> Response:
    """Stop daemon via a 'stop' request."""
    return await request(status_file, "stop", timeout=5)


async def _wait_for_server(
    status_file: str | os.PathLike[str],
    timeout: float = 5.0,  # noqa: ASYNC109
) -> bool:
    """Wait until the server is up. Return False if timed out."""
    try:
        with trio.fail_after(timeout):
            while True:
                try:
                    data = await _read_status(status_file)
                except BadStatusError:
                    # If the file isn't there yet, retry later.
                    await trio.sleep(0.1)
                    continue
                break
    except trio.TooSlowError:
        return False
    # If the file's content is bogus or the process is dead, fail.
    try:
        _check_status(data)
    except BadStatusError:
        return False
    return True


async def _start_server(
    status_file: str | os.PathLike[str],
    *,
    flags: list[str],
    daemon_timeout: int | None = None,
    allow_sources: bool = False,
    log_file: str | os.PathLike[str] | None = None,
) -> bool:
    """Start the server and wait for it. Return False if error starting.

    daemon_timeout:
        Server shutdown timeout (in seconds)
    """
    start_options = _process_start_options(flags, allow_sources)
    if (
        _daemonize(
            start_options,
            str(status_file),
            timeout=daemon_timeout,
            log_file=str_maintain_none(log_file),
        )
        != 0
    ):
        return False
    return await _wait_for_server(status_file)


async def restart(
    status_file: str | os.PathLike[str],
    *,
    flags: list[str],
    daemon_timeout: int | None = 0,
    allow_sources: bool = False,
    log_file: str | os.PathLike[str] | None = None,
) -> bool:
    """Restart daemon (it may or may not be running; but not hanging).

    Returns False if error starting.

    daemon_timeout:
        Server shutdown timeout (in seconds)
    """
    # Bad or missing status file or dead process; good to start.
    with contextlib.suppress(BadStatusError):
        await stop(status_file)
    return await _start_server(
        status_file,
        flags=flags,
        daemon_timeout=daemon_timeout,
        allow_sources=allow_sources,
        log_file=log_file,
    )


# Action functions


async def start(
    status_file: str | os.PathLike[str],
    *,
    flags: list[str],
    daemon_timeout: int = 0,
    allow_sources: bool = False,
    log_file: str | os.PathLike[str] | None = None,
) -> bool:
    """Start daemon if not already running.

    Returns False if error starting / already running.

    daemon_timeout:
        Server shutdown timeout (in seconds)
    """
    if not await is_running(status_file):
        # Bad or missing status file or dead process; good to start.
        return await _start_server(
            status_file,
            flags=flags,
            daemon_timeout=daemon_timeout,
            allow_sources=allow_sources,
            log_file=log_file,
        )
    return False


async def status(
    status_file: str | os.PathLike[str],
    *,
    timeout: int = 5,  # noqa: ASYNC109
    fswatcher_dump_file: str | None = None,
) -> Response:
    """Ask daemon to return status."""
    return await request(
        status_file,
        "status",
        timeout=timeout,
        fswatcher_dump_file=fswatcher_dump_file,
    )


async def run(
    status_file: str | os.PathLike[str],
    *,
    flags: list[str],
    timeout: int | None = None,  # noqa: ASYNC109
    daemon_timeout: int = 0,
    log_file: str | os.PathLike[str] | None = None,
    export_types: bool = False,
) -> Response:
    """Do a check, starting (or restarting) the daemon as necessary.

    Restarts the daemon if the running daemon reports that it is
    required (due to a configuration change, for example).

    daemon_timeout:
        Server shutdown timeout (in seconds)
    """
    # Start if missing status file or dead process
    await start(
        status_file=status_file,
        flags=flags,
        daemon_timeout=daemon_timeout,
        allow_sources=True,
        log_file=log_file,
    )
    response = await request(
        status_file,
        "run",
        timeout=timeout,
        version=__version__,
        args=flags,
        export_types=export_types,
    )
    # If the daemon signals that a restart is necessary, do it
    if "restart" in response:
        debug(f'Restarting: "{response["restart"]}"')
        await restart(
            status_file,
            flags=flags,
            daemon_timeout=timeout,
            allow_sources=True,
            log_file=log_file,
        )
        return await request(
            status_file,
            "run",
            timeout=timeout,
            version=__version__,
            args=flags,
            export_types=export_types,
        )
    return response


async def kill(status_file: str | os.PathLike[str]) -> bool:
    """Kill daemon process with SIGKILL. Return True if killed."""
    pid = (await get_status(status_file))[0]
    try:
        _kill(pid)
    except OSError as ex:
        debug(f"Kill exception: {ex}")
        return False
    return True


async def check(
    status_file: str | os.PathLike[str],
    files: Sequence[str],
    *,
    timeout: int | None = None,  # noqa: ASYNC109
    export_types: bool = False,
) -> Response:
    """Ask the daemon to check a list of files."""
    return await request(
        status_file,
        "check",
        timeout=timeout,
        files=files,
        export_types=export_types,
    )


async def recheck(
    status_file: str | os.PathLike[str],
    export_types: bool,
    *,
    timeout: int | None = None,  # noqa: ASYNC109
    remove: list[str] | None = None,
    update: list[str] | None = None,
) -> Response:
    """Ask the daemon to recheck the previous list of files.

    If at least one of --remove or --update is given, the server will
    update the list of files to check accordingly and assume that any other
    files are unchanged.  If none of these flags are given, the server will
    call stat() on each file last checked to determine its status.

    Files given in --update ought to exist.  Files given in --remove need not
    exist; if they don't they will be ignored.
    The lists may be empty but oughtn't contain duplicates or overlap.

    NOTE: The list of files is lost when the daemon is restarted.
    """
    # if remove is not None or update is not None:
    return await request(
        status_file,
        "recheck",
        timeout=timeout,
        export_types=export_types,
        remove=remove,
        update=update,
    )
    # return await request(
    #     status_file,
    #     "recheck",
    #     timeout=timeout,
    #     export_types=export_types,
    # )


async def inspect(
    status_file: str | os.PathLike[str],
    location: str,  # line:col
    show: Literal["type", "attrs", "definition"] = "type",
    *,
    timeout: int | None = None,  # noqa: ASYNC109
    verbosity: int = 0,
    limit: int = 0,
    include_span: bool = False,
    include_kind: bool = False,
    include_object_attrs: bool = False,
    union_attrs: bool = False,
    force_reload: bool = False,
) -> Response:
    """Ask daemon to print the type of an expression.

    Locate and statically inspect expression(s)

    Location specified as
    path/to/file.py:line:column[:end_line:end_column]. If position is
    given (i.e. only line and column), this will return all enclosing
    expressions

    show:
        What kind of inspection to run, can be one of the following:
        [type, attrs, definition]

    verbosity:
        Increase verbosity of the type string representation

    limit:
        Return at most NUM innermost expressions (if position is given);
        0 means no limit

    include_span:
        Prepend each inspection result with the span of corresponding
        expression (e.g. 1:2:3:4:"int")

    include_kind:
        Prepend each inspection result with the kind of corresponding
        expression (e.g. NameExpr:"int")

    include_object_attrs:
        Include attributes of "object" in "attrs" inspection

    union_attrs:
        Include attributes valid for some of possible expression types
        (by default an intersection is returned)

    force_reload:
        Re-parse and re-type-check file before inspection (may be slow)
    """
    return await request(
        status_file,
        "inspect",
        timeout=timeout,
        show=show,
        location=location,
        verbosity=verbosity,
        limit=limit,
        include_span=include_span,
        include_kind=include_kind,
        include_object_attrs=include_object_attrs,
        union_attrs=union_attrs,
        force_reload=force_reload,
    )


async def suggest(
    status_file: str | os.PathLike[str],
    function: str,
    do_json: bool,
    *,
    timeout: int | None = None,  # noqa: ASYNC109
    callsites: bool = False,
    no_errors: bool = False,
    no_any: bool = False,
    flex_any: float | None = None,
    use_fixme: str | None = None,
    max_guesses: int | None = 64,
) -> Response:
    """Ask the daemon for a suggested signature.

    Suggest a signature or show call sites for a specific function

    function:
        Function specified as '[package.]module.[class.]function' or
        absolute path with line number at the end

    do_json:
        Produce json that pyannotate can use to apply a suggestion

    callsites:
        Find callsites instead of suggesting a type

    no_errors:
        Only produce suggestions that cause no errors

    no_any:
        Only produce suggestions that don't contain Any

    flex_any:
        Allow anys in types if they go above a certain score (scores are from 0-1)

    use_fixme:
        A dummy name to use instead of Any for types that can't be inferred

    max_guesses:
        Set the maximum number of types to try for a function (default 64)
    """
    return await request(
        status_file,
        "suggest",
        timeout=timeout,
        function=function,
        json=do_json,
        callsites=callsites,
        no_errors=no_errors,
        no_any=no_any,
        flex_any=flex_any,
        use_fixme=use_fixme,
        max_guesses=max_guesses,
    )


async def hang(
    status_file: str | os.PathLike[str],
    *,
    timeout: int = 1,  # noqa: ASYNC109
) -> Response:
    """Hang for 100 seconds, as a debug hack."""
    if not isinstance(timeout, int):
        raise ValueError("Timeout must be an integer!")
    return await request(status_file, "hang", timeout=timeout)


def do_daemon(
    status_file: str | os.PathLike[str],
    flags: list[str],
    daemon_timeout: int | None = None,
) -> None:
    """Serve requests in the foreground.

    daemon_timeout:
        Server shutdown timeout (in seconds)
    """
    options = _process_start_options(flags, allow_sources=False)
    _Server(options, str(status_file), timeout=daemon_timeout).serve()

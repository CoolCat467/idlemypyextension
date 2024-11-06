"""Type Check IDLE Extension."""

# Programmed by CoolCat467

from __future__ import annotations

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

__title__ = "idlemypyextension"
__author__ = "CoolCat467"
__license__ = "GNU General Public License Version 3"
__version__ = "1.1.0"


import argparse
import idlelib.pyshell as pyshell
import sys
import tkinter

from idlemypyextension import utils
from idlemypyextension.extension import idlemypyextension as idlemypyextension


def check_installed() -> bool:
    """Make sure extension installed. Return True if installed correctly."""
    return utils.check_installed(__title__, __version__, idlemypyextension)


def run(args: list[str]) -> int:
    """Entry point."""
    parser = argparse.ArgumentParser(
        prog=__title__,
        description="Mypy Daemon IDLE Integration Extension.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"{__title__} v{__version__}",
    )
    parser.add_argument(
        "infile",
        nargs="?",
        type=argparse.FileType("r"),
        default=sys.stdin,
    )

    namespace = parser.parse_args(args)

    if not args:
        if check_installed():
            return 0
        return 1

    original_capture_warnings = pyshell.capture_warnings

    def capture_warnings(enable: bool) -> None:
        """Only enable capturing warnings."""
        if enable:
            original_capture_warnings(True)

    # Start IDLE but make sure mainloop does not start so we can use it
    # ourselves
    class ExitException(BaseException):
        """Exit Exception."""

    def fake_mainloop(tk_root: tkinter.Tk) -> None:
        """Fake Tkinter main loop. Crash instantly."""
        raise ExitException()

    try:
        with utils.temporary_overwrite(tkinter.Tk, "mainloop", fake_mainloop):
            with utils.temporary_overwrite(
                sys,
                "argv",
                [pyshell.__file__, "-e"],  # open in editor mode
            ):
                pyshell.main()
    except ExitException:
        pass  # expected to happen
    else:
        # Something went wrong, did not get exit exception
        pyshell.root.destroy()
        pyshell.capture_warnings(False)
        return 1

    # Get file list and Tk Root from pyshell globals
    flist = pyshell.flist

    pyshell_window = {v: k for k, v in flist.inversedict.items()}.get(None)

    if pyshell_window is None:
        # Pyshell not created properly, exit.
        pyshell.root.destroy()
        pyshell.capture_warnings(False)
        return 1
    assert isinstance(pyshell_window, pyshell.PyShellEditorWindow)

    if not pyshell_window.extensions:
        # No extensions loadex, close.
        pyshell.root.destroy()
        pyshell.capture_warnings(False)
        return 1

    extension = pyshell_window.extensions.get(__title__)

    if extension is None:
        # Extension failed to load somehow, close
        pyshell.root.destroy()
        pyshell.capture_warnings(False)
        return 1
    assert isinstance(extension, idlemypyextension)

    # Add all comments to all files.
    with namespace.infile as fp:
        extension.add_mypy_messages(0, fp.read(), add_all_override=True)
    # Close original blank window
    del extension
    pyshell_window.close()

    # Run IDLE's main loop
    while flist.inversedict:  # keep IDLE running while files are open.
        pyshell.root.mainloop()
    pyshell.root.destroy()
    pyshell.capture_warnings(False)

    return 0


def cli_run() -> None:
    """Command line interface entry point."""
    sys.exit(run(sys.argv[1:]))


utils.set_title(__title__)
idlemypyextension.reload()


if __name__ == "__main__":
    print(f"{__title__} v{__version__}\nProgrammed by {__author__}.\n")
    cli_run()

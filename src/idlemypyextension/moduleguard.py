"""moduleguard - Guard import(s) from IDLE interfering with system path."""

# Programmed by CoolCat467

from __future__ import annotations

# moduleguard - Guard import(s) from IDLE interfering with system path.
# Copyright (C) 2023  CoolCat467
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

__title__ = "moduleguard"
__author__ = "CoolCat467"
__license__ = "GNU General Public License Version 3"
__version__ = "0.0.0"

import json
import os
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable
    from types import TracebackType

    from typing_extensions import Self


def does_path_interfere(
    path: str,
    modules: set[str],
    *,
    ignorepaths: set[str] | None = None,
) -> bool:
    """Return True if path contains something that could interfere.

    Arguments:
    ---------
      path: Path to check.
      modules: Set of module names we want to make sure won't interfere.
      ignorepaths: Set of paths already checked and known won't interfere.

    This is a recursive function that mutates ignorepaths in each iteration.
    It is advised against passing the ignorepaths argument.

    """
    # Setup ignorepaths set when user calls this
    if ignorepaths is None:
        ignorepaths = set()

    # Don't read root
    if len(path.split(os.sep)) <= 2:
        return False

    for dirpath, dirnames, filenames in os.walk(path, topdown=True):
        # Remove directories we have already visited
        for dirname in tuple(dirnames):
            if os.path.join(dirpath, dirname) in ignorepaths:
                dirnames.remove(dirname)

        for filename in filenames:
            # Skip filenames with no extension
            if os.path.extsep not in filename:
                continue
            # If filename is module name, that's bad
            if filename.split(os.path.extsep, 1)[0] in modules:
                return True

        # If this is a module internal directory
        if "__init__.py" in filenames:
            # Get the next level up's name and the module name
            level_up, dir_module_name = os.path.split(path)
            # If module name matches, bad
            if dir_module_name in modules:
                return True
            # Otherwise, everything is fine and we have checked this folder.
            # No need for next iteration to do so again
            ignorepaths.add(path)
            # Need to check level up now
            return does_path_interfere(
                level_up,
                modules,
                ignorepaths=ignorepaths,
            )
    # If nothing matched we should be fine
    return False


class ImportGuardContextManager:
    """Guard imports against user packages from idle's sys.path manipulation."""

    __slots__ = ("modules", "original")

    def __init__(self, modules: set[str]) -> None:
        """Initialize modules set."""
        self.modules = modules
        self.original: list[str] = []

        bad_modules = ", ".join(modules & set(sys.builtin_module_names))
        if bad_modules:
            raise ValueError(
                f"Cannot guard following builtin modules: {bad_modules}",
            )

    def __repr__(self) -> str:
        """Return representation of self."""
        return f"{self.__class__.__name__}({self.modules!r})"

    def __enter__(self) -> Self:
        """Modify sys.path to remove interference."""
        # Get deep copy
        self.original = json.loads(json.dumps(sys.path))

        # Remove blanks
        index = 0
        while index < len(sys.path):
            if not sys.path[index]:
                path = sys.path.pop(index)
                # print(f"[DEBUG] popped sys.{path = }")
                continue
            index += 1
        # print(f"[DEBUG] {sys.path = }")

        if "idlelib" not in sys.modules:
            # We are in before IDLE, we should be safe
            return self

        # Remove conflict(s)
        # First, find where the end of idle's manipulation is
        max_read = 0
        for max_read, path in enumerate(sys.path):  # noqa: B007
            if path.startswith(sys.exec_prefix):
                break
        max_read = min(max_read, 2)

        index = 0
        while index < max_read:
            if does_path_interfere(sys.path[index], self.modules):
                path = sys.path.pop(index)
                # print(f"[DEBUG] popped sys.{path = }")
                max_read -= 1
                continue
            index += 1

        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Restore sys.path to what it was before we changed it."""
        sys.path.clear()
        for item in self.original:
            sys.path.append(item)


def guard_import(module_name: str) -> ImportGuardContextManager:
    """Guard an import against user packages from idle's sys.path manipulation."""
    return ImportGuardContextManager({module_name})


def guard_imports(module_names: Iterable[str]) -> ImportGuardContextManager:
    """Guard specified imports against user packages from idle's sys.path manipulation."""
    return ImportGuardContextManager(set(module_names))


if __name__ == "__main__":
    print(f"{__title__}\nProgrammed by {__author__}.\n")

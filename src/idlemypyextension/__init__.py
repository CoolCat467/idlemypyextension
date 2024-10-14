"""Type Check IDLE Extension."""

# Programmed by CoolCat467

from __future__ import annotations

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

__title__ = "idlemypyextension"
__author__ = "CoolCat467"
__license__ = "GNU General Public License Version 3"
__version__ = "1.0.4"


from idlemypyextension import utils
from idlemypyextension.extension import idlemypyextension as idlemypyextension


def check_installed() -> bool:
    """Make sure extension installed."""
    return utils.check_installed(__title__, __version__, idlemypyextension)


utils.set_title(__title__)
idlemypyextension.reload()


if __name__ == "__main__":
    print(f"{__title__} v{__version__}\nProgrammed by {__author__}.\n")
    check_installed()

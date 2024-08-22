from __future__ import annotations

import pytest

from idlemypyextension import utils


def test_get_required_config() -> None:
    assert (
        utils.get_required_config(
            {
                "fish_enabled": "True",
                "waffle_mode": "False",
                "user_settings": "1, 2, 3",
            },
            {
                "check_fishes": "Ctrl+Alt+f",
                "reboot": "Ctrl+Alt+Del",
            },
            "fish_extend",
        )
        == """
[fish_extend]
fish_enabled = True
waffle_mode = False
user_settings = 1, 2, 3

[fish_extend_cfgBindings]
check_fishes = Ctrl+Alt+f
reboot = Ctrl+Alt+Del"""
    )


def test_get_line_selection() -> None:
    assert utils.get_line_selection(3) == ("3.0", "4.0")
    assert utils.get_line_selection(3, 3) == ("3.0", "6.0")


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("0.0", (0, 0)),
        ("1.0", (1, 0)),
        ("0.1", (0, 1)),
        ("29120.314817317", (29120, 314817317)),
        ("-231.-234327", (-231, -234327)),
    ],
)
def test_get_line_col_success(line: str, expected: tuple[int, int]) -> None:
    assert utils.get_line_col(line) == expected


@pytest.mark.parametrize(
    "line",
    [
        "",
        "93732",
        "0x7f",
        "0x74.0xff",
    ],
)
def test_get_line_col_failure(line: str) -> None:
    with pytest.raises(
        ValueError,
        match=r"(not enough values to unpack)|(invalid literal for int\(\) with base 10:)",
    ):
        utils.get_line_col(line)


@pytest.mark.parametrize(
    ("index", "offset", "expect"),
    [("3.14", 0, "3.0"), ("3.14", 1, "4.0"), ("2981.23", -1, "2980.0")],
)
def test_get_whole_line(index: str, offset: int, expect: str) -> None:
    assert utils.get_whole_line(index, offset) == expect


@pytest.mark.parametrize(
    ("text", "expect"),
    [("  waf", 2), ("cat", 0), ("     fish", 5), ("   ", 3), ("", 0)],
)
def test_get_line_indent(text: str, expect: int) -> None:
    assert utils.get_line_indent(text, " ") == expect

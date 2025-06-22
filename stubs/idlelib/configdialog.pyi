from collections.abc import Callable
from idlelib import macosx as macosx
from idlelib.autocomplete import AutoComplete as AutoComplete
from idlelib.codecontext import CodeContext as CodeContext
from idlelib.config import (
    ConfigChanges as ConfigChanges,
    IdleConfParser,
    IdleUserConfParser,
    idleConf as idleConf,
)
from idlelib.config_key import GetKeysDialog as GetKeysDialog
from idlelib.dynoption import DynOptionMenu as DynOptionMenu
from idlelib.format import FormatParagraph as FormatParagraph
from idlelib.parenmatch import ParenMatch as ParenMatch
from idlelib.query import HelpSource as HelpSource, SectionName as SectionName
from idlelib.squeezer import Squeezer as Squeezer
from idlelib.textview import (
    ScrollableTextFrame as ScrollableTextFrame,
    view_text as view_text,
)
from tkinter import (
    BooleanVar,
    Button,
    Event,
    IntVar,
    Listbox,
    Misc,
    StringVar,
    Toplevel,
    Variable,
)
from tkinter.ttk import (
    Checkbutton,
    Combobox,
    Entry,
    Frame,
    Label,
    LabelFrame,
    Notebook,
    OptionMenu,
    Radiobutton,
    Spinbox,
    Style,
)
from typing import Any, TypeVar

from mypy_extensions import VarArg

changes: ConfigChanges
reloadables: tuple[
    AutoComplete,
    CodeContext,
    ParenMatch,
    FormatParagraph,
    Squeezer,
]

class ConfigDialog(Toplevel):
    parent: Misc
    def __init__(
        self,
        parent: Misc,
        title: str = ...,
        *,
        _htest: bool = ...,
        _utest: bool = ...,
    ) -> None: ...
    frame: Frame  # type: ignore[assignment]
    note: Notebook
    extpage: ExtPage
    highpage: HighPage
    fontpage: FontPage
    keyspage: KeysPage
    winpage: WinPage
    shedpage: ShedPage
    def create_widgets(self) -> None: ...
    buttons: dict[str, Button]
    def create_action_buttons(self) -> Frame: ...
    def ok(self) -> None: ...
    def apply(self) -> None: ...
    def cancel(self) -> None: ...
    def destroy(self) -> None: ...
    def help(self) -> None: ...
    def deactivate_current_config(self) -> None: ...
    def activate_config_changes(self) -> None: ...

font_sample_text: str

class FontPage(Frame):
    highlight_sample: str
    def __init__(self, master: Misc | None, highpage: HighPage) -> None: ...
    font_name: str
    font_size: int
    font_bold: bool
    fontlist: Listbox
    sizelist: DynOptionMenu
    bold_toggle: Checkbutton
    font_sample: ScrollableTextFrame
    def create_page_font(self) -> None: ...
    def load_font_cfg(self) -> None: ...
    def var_changed_font(self, *params: Any) -> None: ...
    def on_fontlist_select(self, event: Event[Any] | None) -> None: ...
    def set_samples(self, event: Event[Any] | None = ...) -> None: ...

class HighPage(Frame):
    extpage: ExtPage
    cd: Toplevel
    style: Style
    def __init__(self, master: Misc | None, extpage: ExtPage) -> None: ...
    theme_elements: dict[str, tuple[str, str]]
    builtin_name: StringVar
    custom_name: StringVar
    fg_bg_toggle: BooleanVar
    color: StringVar
    theme_source: BooleanVar
    highlight_target: StringVar
    frame_color_set: Frame
    button_set_color: Button
    targetlist: DynOptionMenu
    fg_on: Radiobutton
    bg_on: Radiobutton
    button_save_custom: Button
    builtin_theme_on: Radiobutton
    custom_theme_on: Radiobutton
    builtinlist: DynOptionMenu
    customlist: DynOptionMenu
    button_delete_custom: Button
    theme_message: Label
    def create_page_highlight(self) -> None: ...
    def load_theme_cfg(self) -> None: ...
    def var_changed_builtin_name(self, *params: Any) -> None: ...
    def var_changed_custom_name(self, *params: Any) -> None: ...
    def var_changed_theme_source(self, *params: Any) -> None: ...
    def var_changed_color(self, *params: Any) -> None: ...
    def var_changed_highlight_target(self, *params: Any) -> None: ...
    def set_theme_type(self) -> None: ...
    def get_color(self) -> None: ...
    def on_new_color_set(self) -> None: ...
    def get_new_theme_name(self, message: str) -> SectionName: ...
    def save_as_new_theme(self) -> None: ...
    def create_new(self, new_theme_name: str) -> None: ...
    def set_highlight_target(self) -> None: ...
    def set_color_sample_binding(self, *args: Any) -> None: ...
    def set_color_sample(self) -> None: ...
    def paint_theme_sample(self) -> None: ...
    def save_new(self, theme_name: str, theme: dict[str, str]) -> None: ...
    def askyesno(self, *args: str | None, **kwargs: Any) -> bool: ...
    def delete_custom(self) -> None: ...

class KeysPage(Frame):
    extpage: ExtPage
    cd: Toplevel
    def __init__(self, master: Misc | None, extpage: ExtPage) -> None: ...
    builtin_name: StringVar
    custom_name: StringVar
    keyset_source: BooleanVar
    keybinding: StringVar
    bindingslist: Listbox
    button_new_keys: Button
    builtin_keyset_on: Radiobutton
    custom_keyset_on: Radiobutton
    builtinlist: DynOptionMenu
    customlist: DynOptionMenu
    button_delete_custom_keys: Button
    button_save_custom_keys: Button
    keys_message: Label
    def create_page_keys(self) -> None: ...
    def load_key_cfg(self) -> None: ...
    def var_changed_builtin_name(self, *params: Any) -> None: ...
    def var_changed_custom_name(self, *params: Any) -> None: ...
    def var_changed_keyset_source(self, *params: Any) -> None: ...
    def var_changed_keybinding(self, *params: Any) -> None: ...
    def set_keys_type(self) -> None: ...
    def get_new_keys(self) -> None: ...
    def get_new_keys_name(self, message: str) -> SectionName: ...
    def save_as_new_key_set(self) -> None: ...
    def on_bindingslist_select(self, event: Event[Any] | None) -> None: ...
    def create_new_key_set(self, new_key_set_name: str) -> None: ...
    def load_keys_list(self, keyset_name: str) -> None: ...
    @staticmethod
    def save_new_key_set(keyset_name: str, keyset: dict[str, str]) -> None: ...
    def askyesno(self, *args: str | None, **kwargs: Any) -> bool: ...
    def delete_custom_keys(self) -> None: ...

class WinPage(Frame):
    def __init__(self, master: Misc | None) -> None: ...
    digits_only: tuple[str, ...]
    def init_validators(self) -> None: ...
    startup_edit: IntVar
    win_width: StringVar
    win_height: StringVar
    indent_spaces: StringVar
    cursor_blink: BooleanVar
    autocomplete_wait: StringVar
    paren_style: StringVar
    flash_delay: StringVar
    paren_bell: BooleanVar
    format_width: StringVar
    startup_editor_on: Radiobutton
    startup_shell_on: Radiobutton
    win_width_int: Entry
    win_height_int: Entry
    indent_chooser: Spinbox | Combobox
    cursor_blink_bool: Checkbutton
    auto_wait_int: Entry
    paren_style_type: OptionMenu
    paren_flash_time: Entry
    bell_on: Checkbutton
    format_width_int: Entry
    def create_page_windows(self) -> None: ...
    def load_windows_cfg(self) -> None: ...

class ShedPage(Frame):
    def __init__(self, master: Misc | None) -> None: ...
    digits_only: tuple[str, ...]
    def init_validators(self) -> None: ...
    auto_squeeze_min_lines: StringVar
    autosave: IntVar
    line_numbers_default: BooleanVar
    context_lines: StringVar
    auto_squeeze_min_lines_int: Entry
    save_ask_on: Radiobutton
    save_auto_on: Radiobutton
    line_numbers_default_bool: Checkbutton
    context_int: Entry
    def create_page_shed(self) -> None: ...
    def load_shelled_cfg(self) -> None: ...

class ExtPage(Frame):
    ext_defaultCfg: IdleConfParser
    ext_userCfg: IdleUserConfParser
    is_int: Callable[[int], bool]
    def __init__(self, master: Misc | None) -> None: ...
    extension_names: StringVar
    frame_help: HelpFrame
    extension_list: Listbox
    details_frame: LabelFrame
    config_frame: dict[str, VerticalScrolledFrame]
    current_extension: str | None
    outerframe: ExtPage
    tabbed_page_set: Listbox
    def create_page_extensions(self) -> None: ...
    extensions: dict[str, list[dict[str, str | int | StringVar | None]]]
    def load_extensions(self) -> None: ...
    def extension_selected(self, event: Event[Any] | None) -> None: ...
    def create_extension_frame(self, ext_name: str) -> None: ...
    def set_extension_value(
        self,
        section: str,
        opt: dict[str, str | int | StringVar | None],
    ) -> bool: ...
    def save_all_changed_extensions(self) -> None: ...

class HelpFrame(LabelFrame):
    def __init__(self, master: Misc | None, **cfg: Any) -> None: ...
    helplist: Listbox
    button_helplist_edit: Button
    button_helplist_add: Button
    button_helplist_remove: Button
    def create_frame_help(self) -> None: ...
    def help_source_selected(self, event: Event[Any] | None) -> None: ...
    def set_add_delete_state(self) -> None: ...
    def helplist_item_add(self) -> None: ...
    def helplist_item_edit(self) -> None: ...
    def helplist_item_remove(self) -> None: ...
    def update_help_changes(self) -> None: ...
    user_helplist: list[tuple[str, str, str]]
    def load_helplist(self) -> None: ...

_Variable = TypeVar("_Variable", StringVar, IntVar, BooleanVar)

class VarTrace:
    untraced: list[
        tuple[StringVar | IntVar | BooleanVar, str | tuple[str, str, str]]
    ]
    traced: list[
        tuple[StringVar | IntVar | BooleanVar, str | tuple[str, str, str]]
    ]
    def __init__(self) -> None: ...
    def clear(self) -> None: ...
    def add(
        self,
        var: _Variable,
        callback: str | tuple[str, str, str],
    ) -> _Variable: ...
    @staticmethod
    def make_callback(
        var: Variable,
        config: str | tuple[str, str, str],
    ) -> Callable[[VarArg(Any)], None]: ...
    def attach(self) -> None: ...
    def detach(self) -> None: ...

tracers: VarTrace
help_common: str
help_pages: dict[str, str]

def is_int(s: str) -> bool: ...

class VerticalScrolledFrame(Frame):
    interior: Frame
    def __init__(
        self,
        parent: Misc | None,
        *args: dict[str, Any] | None,
        **kw: Any,
    ) -> None: ...

"""Theme and styling configuration for the GUI."""

import dearpygui.dearpygui as dpg


class Colors:
    """Color constants for the GUI theme."""

    # Background colors
    BG_PRIMARY = (20, 20, 25)
    BG_SECONDARY = (30, 30, 35)
    BG_TERTIARY = (40, 40, 45)

    # Text colors
    TEXT_PRIMARY = (220, 220, 220)
    TEXT_SECONDARY = (160, 160, 160)
    TEXT_DISABLED = (100, 100, 100)

    # Accent colors
    ACCENT_PRIMARY = (0, 119, 200)  # Blue
    ACCENT_SECONDARY = (100, 149, 237)  # Cornflower blue

    # Status colors
    SUCCESS = (46, 204, 113)  # Green
    WARNING = (241, 196, 15)  # Yellow
    ERROR = (231, 76, 60)  # Red
    INFO = (52, 152, 219)  # Blue

    # Trading colors
    BUY_GREEN = (46, 204, 113)
    SELL_RED = (231, 76, 60)
    PROFIT_GREEN = (39, 174, 96)
    LOSS_RED = (192, 57, 43)

    # Border colors
    BORDER_LIGHT = (60, 60, 65)
    BORDER_DARK = (15, 15, 20)

    # Chart colors
    CANDLE_UP = (46, 204, 113)
    CANDLE_DOWN = (231, 76, 60)
    VOLUME_BAR = (100, 149, 237, 128)


class Fonts:
    """Font configuration."""

    DEFAULT_SIZE = 15
    SMALL_SIZE = 13
    LARGE_SIZE = 18
    TITLE_SIZE = 20


def setup_theme():
    """
    Set up the dark theme for the GUI.

    Returns:
        Theme tag
    """
    with dpg.theme() as theme_tag:
        with dpg.theme_component(dpg.mvAll):
            # Window styling
            dpg.add_theme_color(dpg.mvThemeCol_WindowBg, Colors.BG_PRIMARY, category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(
                dpg.mvThemeCol_ChildBg, Colors.BG_SECONDARY, category=dpg.mvThemeCat_Core
            )
            dpg.add_theme_color(
                dpg.mvThemeCol_PopupBg, Colors.BG_SECONDARY, category=dpg.mvThemeCat_Core
            )

            # Frame styling
            dpg.add_theme_color(
                dpg.mvThemeCol_FrameBg, Colors.BG_TERTIARY, category=dpg.mvThemeCat_Core
            )
            dpg.add_theme_color(
                dpg.mvThemeCol_FrameBgHovered, Colors.ACCENT_SECONDARY, category=dpg.mvThemeCat_Core
            )
            dpg.add_theme_color(
                dpg.mvThemeCol_FrameBgActive, Colors.ACCENT_PRIMARY, category=dpg.mvThemeCat_Core
            )

            # Text styling
            dpg.add_theme_color(dpg.mvThemeCol_Text, Colors.TEXT_PRIMARY, category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(
                dpg.mvThemeCol_TextDisabled, Colors.TEXT_DISABLED, category=dpg.mvThemeCat_Core
            )

            # Border styling
            dpg.add_theme_color(
                dpg.mvThemeCol_Border, Colors.BORDER_LIGHT, category=dpg.mvThemeCat_Core
            )
            dpg.add_theme_color(
                dpg.mvThemeCol_BorderShadow, Colors.BORDER_DARK, category=dpg.mvThemeCat_Core
            )

            # Button styling
            dpg.add_theme_color(
                dpg.mvThemeCol_Button, Colors.ACCENT_PRIMARY, category=dpg.mvThemeCat_Core
            )
            dpg.add_theme_color(
                dpg.mvThemeCol_ButtonHovered, Colors.ACCENT_SECONDARY, category=dpg.mvThemeCat_Core
            )
            dpg.add_theme_color(
                dpg.mvThemeCol_ButtonActive, Colors.ACCENT_PRIMARY, category=dpg.mvThemeCat_Core
            )

            # Header styling
            dpg.add_theme_color(
                dpg.mvThemeCol_Header, Colors.BG_TERTIARY, category=dpg.mvThemeCat_Core
            )
            dpg.add_theme_color(
                dpg.mvThemeCol_HeaderHovered, Colors.ACCENT_SECONDARY, category=dpg.mvThemeCat_Core
            )
            dpg.add_theme_color(
                dpg.mvThemeCol_HeaderActive, Colors.ACCENT_PRIMARY, category=dpg.mvThemeCat_Core
            )

            # Tab styling
            dpg.add_theme_color(dpg.mvThemeCol_Tab, Colors.BG_TERTIARY, category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(
                dpg.mvThemeCol_TabHovered, Colors.ACCENT_SECONDARY, category=dpg.mvThemeCat_Core
            )
            dpg.add_theme_color(
                dpg.mvThemeCol_TabActive, Colors.ACCENT_PRIMARY, category=dpg.mvThemeCat_Core
            )

            # Spacing and rounding
            dpg.add_theme_style(
                dpg.mvStyleVar_FrameRounding, 4, category=dpg.mvThemeCat_Core
            )
            dpg.add_theme_style(
                dpg.mvStyleVar_WindowRounding, 6, category=dpg.mvThemeCat_Core
            )
            dpg.add_theme_style(dpg.mvStyleVar_FramePadding, 8, 4, category=dpg.mvThemeCat_Core)
            dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 8, 4, category=dpg.mvThemeCat_Core)

    return theme_tag


def create_button_theme(bg_color, hover_color=None, active_color=None):
    """
    Create a custom button theme.

    Args:
        bg_color: Background color tuple (R, G, B)
        hover_color: Hover color (defaults to lighter version)
        active_color: Active color (defaults to bg_color)

    Returns:
        Theme tag
    """
    if hover_color is None:
        hover_color = tuple(min(c + 30, 255) for c in bg_color)
    if active_color is None:
        active_color = bg_color

    with dpg.theme() as theme_tag:
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Button, bg_color, category=dpg.mvThemeCat_Core)
            dpg.add_theme_color(
                dpg.mvThemeCol_ButtonHovered, hover_color, category=dpg.mvThemeCat_Core
            )
            dpg.add_theme_color(
                dpg.mvThemeCol_ButtonActive, active_color, category=dpg.mvThemeCat_Core
            )

    return theme_tag


def create_text_theme(color):
    """
    Create a custom text theme.

    Args:
        color: Text color tuple (R, G, B)

    Returns:
        Theme tag
    """
    with dpg.theme() as theme_tag:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(dpg.mvThemeCol_Text, color, category=dpg.mvThemeCat_Core)

    return theme_tag


# Pre-create common themes
BUY_BUTTON_THEME = None
SELL_BUTTON_THEME = None
PROFIT_TEXT_THEME = None
LOSS_TEXT_THEME = None
SUCCESS_TEXT_THEME = None
WARNING_TEXT_THEME = None
ERROR_TEXT_THEME = None


def initialize_common_themes():
    """Initialize commonly used themes."""
    global BUY_BUTTON_THEME, SELL_BUTTON_THEME
    global PROFIT_TEXT_THEME, LOSS_TEXT_THEME
    global SUCCESS_TEXT_THEME, WARNING_TEXT_THEME, ERROR_TEXT_THEME

    BUY_BUTTON_THEME = create_button_theme(Colors.BUY_GREEN)
    SELL_BUTTON_THEME = create_button_theme(Colors.SELL_RED)

    PROFIT_TEXT_THEME = create_text_theme(Colors.PROFIT_GREEN)
    LOSS_TEXT_THEME = create_text_theme(Colors.LOSS_RED)

    SUCCESS_TEXT_THEME = create_text_theme(Colors.SUCCESS)
    WARNING_TEXT_THEME = create_text_theme(Colors.WARNING)
    ERROR_TEXT_THEME = create_text_theme(Colors.ERROR)

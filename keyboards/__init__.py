"""
Keyboards package
"""
from .main_menu import get_main_menu_keyboard
from .tariff_selection import get_tariff_selection_keyboard

__all__ = [
    "get_main_menu_keyboard",
    "get_tariff_selection_keyboard",
]

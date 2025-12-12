"""
Клавиатура выбора тарифа
"""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database.models import Tariff
from typing import List


def get_tariff_selection_keyboard(tariffs: List[Tariff]) -> InlineKeyboardMarkup:
    """Клавиатура для выбора тарифа"""
    buttons = []
    for tariff in tariffs:
        button_text = f"{tariff.name} — {int(tariff.price)} ₽"
        buttons.append([
            InlineKeyboardButton(
                text=button_text,
                callback_data=f"select_tariff_{tariff.id}"
            )
        ])
    
    # Кнопка отмены
    buttons.append([
        InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

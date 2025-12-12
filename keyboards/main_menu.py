"""
Главное меню бота
"""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def get_main_menu_keyboard(has_active_subscription: bool = False) -> InlineKeyboardMarkup:
    """Главное меню с основными разделами"""
    buttons = [
        [
            InlineKeyboardButton(text="📦 Мой тариф", callback_data="my_subscription"),
        ],
    ]
    
    # Разные кнопки для пользователей с подпиской и без
    if has_active_subscription:
        buttons.append([
            InlineKeyboardButton(text="🔄 Продлить подписку", callback_data="renew_subscription"),
        ])
        buttons.append([
            InlineKeyboardButton(text="📞 Заказать парфюм", callback_data="order_perfume"),
        ])
    else:
        buttons.append([
            InlineKeyboardButton(text="💳 Купить подписку", callback_data="renew_subscription"),
        ])
    
    buttons.append([
        InlineKeyboardButton(text="🎁 Реферальная программа", callback_data="referral_program"),
    ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    return keyboard

"""
Обработчики главного меню
"""
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from database.base import get_session
from services.user_service import UserService
from services.subscription_service import SubscriptionService
from services.referral_service import ReferralService
from services.tariff_service import TariffService
from keyboards.main_menu import get_main_menu_keyboard
from keyboards.tariff_selection import get_tariff_selection_keyboard
from states.subscription_states import SubscriptionStates
from datetime import datetime
from config import settings

router = Router()


@router.callback_query(F.data == "my_subscription")
async def show_my_subscription(callback: CallbackQuery):
    """Показать информацию о текущей подписке"""
    async for session in get_session():
        user = await UserService.get_user_by_telegram_id(
            session=session,
            telegram_id=callback.from_user.id,
        )
        
        if not user:
            await callback.answer("Пользователь не найден", show_alert=True)
            return
        
        subscription = await SubscriptionService.get_active_subscription(
            session=session,
            user_id=user.id,
        )
        
        if not subscription:
            text = (
                "❌ У вас нет активной подписки.\n\n"
                "Оформите подписку, чтобы получить доступ к парфюмерии по закупочным ценам."
            )
        else:
            # Загружаем тариф
            tariff = await TariffService.get_tariff_by_id(
                session=session,
                tariff_id=subscription.tariff_id,
            )
            tariff_name = tariff.name if tariff else "Неизвестный тариф"
            
            start_date = subscription.start_date.strftime("%d.%m.%Y") if subscription.start_date else "—"
            end_date = subscription.end_date.strftime("%d.%m.%Y") if subscription.end_date else "—"
            
            text = (
                f"📦 Ваша подписка\n\n"
                f"Тариф: {tariff_name}\n"
                f"Дата начала: {start_date}\n"
                f"Дата окончания: {end_date}\n"
                f"Статус: {'✅ Активна' if subscription.status.value == 'active' else '❌ Истекла'}"
            )
        
        # Проверяем наличие активной подписки для меню
        has_active = subscription is not None and subscription.status.value == 'active'
        await callback.message.edit_text(
            text,
            reply_markup=get_main_menu_keyboard(has_active_subscription=has_active)
        )
        await callback.answer()
        break


@router.callback_query(F.data == "renew_subscription")
async def renew_subscription(callback: CallbackQuery):
    """Продлить подписку"""
    async for session in get_session():
        user = await UserService.get_user_by_telegram_id(
            session=session,
            telegram_id=callback.from_user.id,
        )
        
        if not user:
            await callback.answer("Пользователь не найден", show_alert=True)
            return
        
        # Получаем все активные тарифы
        tariffs = await TariffService.get_all_active_tariffs(session=session)
        
        if not tariffs:
            await callback.answer("Тарифы временно недоступны", show_alert=True)
            return
        
        text = "Выберите тариф для продления подписки:"
        await callback.message.edit_text(
            text,
            reply_markup=get_tariff_selection_keyboard(tariffs)
        )
        await callback.answer()
        break


@router.callback_query(F.data == "referral_program")
async def show_referral_program(callback: CallbackQuery):
    """Показать информацию о реферальной программе"""
    async for session in get_session():
        user = await UserService.get_user_by_telegram_id(
            session=session,
            telegram_id=callback.from_user.id,
        )
        
        if not user:
            await callback.answer("Пользователь не найден", show_alert=True)
            return
        
        stats = await ReferralService.get_referral_stats(session=session, user_id=user.id)
        
        referral_link = f"https://t.me/{settings.BOT_USERNAME}?start={stats['referral_code']}"
        
        text = (
            f"🎁 Реферальная программа\n\n"
            f"Ваша реферальная ссылка:\n"
            f"`{referral_link}`\n\n"
            f"📊 Статистика:\n"
            f"• Всего приглашено: {stats['total_referrals']}\n"
            f"• Оплатили подписку: {stats['paid_referrals']}\n"
            f"• Активных рефералов: {stats['active_paid_referrals']}\n\n"
        )
        
        if stats['bonus_issued']:
            text += "✅ Вы уже получили подарок за приглашение 3 активных рефералов!"
        elif stats['bonus_available']:
            text += "🎉 Поздравляем! Вы достигли 3 активных рефералов и получили подарок!"
        else:
            remaining = stats['remaining_for_bonus']
            text += f"🎯 До подарка осталось: {remaining} активных рефералов\n\n"
            text += "💡 Условия:\n"
            text += "• Пригласите 3 друзей по вашей реферальной ссылке\n"
            text += "• Они должны оформить и оплатить подписку\n"
            text += "• Вы получите подарок — парфюм!"
        
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")],
        ])
        
        await callback.message.edit_text(
            text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        await callback.answer()
        break


@router.callback_query(F.data == "get_catalog")
async def get_catalog(callback: CallbackQuery):
    """Показать два варианта каталога — кнопки открывают ссылки на Яндекс.Диск"""
    text = (
        "📂 <b>Каталог</b>\n\n"
        "Выберите каталог — откроется ссылка на Яндекс.Диск:"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=settings.CATALOG_NAME_1, url=settings.CATALOG_LINK_1)],
        [InlineKeyboardButton(text=settings.CATALOG_NAME_2, url=settings.CATALOG_LINK_2)],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")],
    ])
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "order_perfume")
async def order_perfume(callback: CallbackQuery):
    """Показать WhatsApp-номер менеджера"""
    wa_link = f"https://wa.me/{settings.MANAGER_WHATSAPP.lstrip('+').replace('-', '')}"
    text = (
        f"📞 Заказ парфюма\n\n"
        f"Для заказа парфюма свяжитесь с нашим менеджером в WhatsApp:\n\n"
        f"📱 <a href=\"{wa_link}\">Написать в WhatsApp</a> ({settings.MANAGER_WHATSAPP})\n\n"
        f"Менеджер поможет вам с выбором и оформлением заказа."
    )
    
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")],
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery):
    """Вернуться в главное меню"""
    async for session in get_session():
        user = await UserService.get_user_by_telegram_id(
            session=session,
            telegram_id=callback.from_user.id,
        )
        
        has_active = False
        if user:
            subscription = await SubscriptionService.get_active_subscription(
                session=session,
                user_id=user.id,
            )
            has_active = subscription is not None
        
        text = "Главное меню:"
        await callback.message.edit_text(text, reply_markup=get_main_menu_keyboard(has_active_subscription=has_active))
        await callback.answer()
        break

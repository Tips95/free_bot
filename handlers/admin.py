"""
Админ панель для управления ботом
"""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from sqlalchemy.ext.asyncio import AsyncSession
from database.base import get_session
from services.user_service import UserService
from services.subscription_service import SubscriptionService
from services.payment_service import PaymentService
from services.referral_service import ReferralService
from database.models import SubscriptionStatus, PaymentStatus
from sqlalchemy import select, func
from database.models import User, Subscription, Payment, Referral
from config import settings
import logging
from datetime import datetime

logger = logging.getLogger(__name__)
router = Router()


def is_admin(user_id: int) -> bool:
    """Проверка, является ли пользователь администратором"""
    if not settings.ADMIN_TELEGRAM_IDS:
        return False
    try:
        admin_ids = [int(id_str.strip()) for id_str in settings.ADMIN_TELEGRAM_IDS.split(',')]
        return user_id in admin_ids
    except (ValueError, TypeError):
        return False


@router.message(Command("admin"))
async def admin_menu(message: Message):
    """Главное меню админ панели"""
    if not is_admin(message.from_user.id):
        await message.answer("❌ У вас нет доступа к админ панели")
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users")],
        [InlineKeyboardButton(text="💳 Платежи", callback_data="admin_payments")],
        [InlineKeyboardButton(text="📦 Подписки", callback_data="admin_subscriptions")],
        [InlineKeyboardButton(text="🎁 Рефералы", callback_data="admin_referrals")],
        [InlineKeyboardButton(text="📋 Список подписчиков", callback_data="admin_subscribers_list")],
    ])
    
    await message.answer(
        "🔐 <b>Админ панель</b>\n\n"
        "Выберите раздел:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


@router.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):
    """Общая статистика"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    async for session in get_session():
        # Общее количество пользователей
        stmt = select(func.count(User.id))
        result = await session.execute(stmt)
        total_users = result.scalar() or 0
        
        # Активные подписки
        now = datetime.utcnow()
        stmt = select(func.count(Subscription.id)).where(
            Subscription.status == SubscriptionStatus.ACTIVE,
            Subscription.end_date > now
        )
        result = await session.execute(stmt)
        active_subscriptions = result.scalar() or 0
        
        # Всего подписок
        stmt = select(func.count(Subscription.id))
        result = await session.execute(stmt)
        total_subscriptions = result.scalar() or 0
        
        # Успешные платежи
        stmt = select(func.count(Payment.id)).where(
            Payment.status == PaymentStatus.SUCCEEDED
        )
        result = await session.execute(stmt)
        successful_payments = result.scalar() or 0
        
        # Общая сумма платежей
        stmt = select(func.sum(Payment.amount)).where(
            Payment.status == PaymentStatus.SUCCEEDED
        )
        result = await session.execute(stmt)
        total_revenue = result.scalar() or 0.0
        total_revenue = float(total_revenue) if total_revenue else 0.0
        
        # Всего рефералов
        stmt = select(func.count(Referral.id))
        result = await session.execute(stmt)
        total_referrals = result.scalar() or 0
        
        # Оплаченные рефералы
        stmt = select(func.count(Referral.id)).where(
            Referral.has_paid_subscription == True
        )
        result = await session.execute(stmt)
        paid_referrals = result.scalar() or 0
        
        # Уникальных пользователей, которые когда-либо покупали подписку
        stmt = select(func.count(func.distinct(Subscription.user_id))).where(
            Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.EXPIRED])
        )
        result = await session.execute(stmt)
        unique_subscribers = result.scalar() or 0
        
        text = (
            f"📊 <b>Общая статистика</b>\n\n"
            f"👥 <b>Пользователи:</b>\n"
            f"• Всего зарегистрировано: {total_users}\n"
            f"• Приобрели подписку: {unique_subscribers}\n"
            f"• С активной подпиской: {active_subscriptions}\n\n"
            f"📦 <b>Подписки:</b>\n"
            f"• Всего оформлено: {total_subscriptions}\n"
            f"• Активных: {active_subscriptions}\n\n"
            f"💳 <b>Платежи:</b>\n"
            f"• Успешных: {successful_payments}\n"
            f"• Общая сумма: {total_revenue:.2f} ₽\n\n"
            f"🎁 <b>Рефералы:</b>\n"
            f"• Всего приглашено: {total_referrals}\n"
            f"• Оплатили подписку: {paid_referrals}\n"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")],
        ])
        
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        await callback.answer()
        break


@router.callback_query(F.data == "admin_users")
async def admin_users(callback: CallbackQuery):
    """Статистика по пользователям"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    async for session in get_session():
        # Новые пользователи за последние 7 дней
        week_ago = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        stmt = select(func.count(User.id)).where(
            User.created_at >= week_ago
        )
        result = await session.execute(stmt)
        new_users_week = result.scalar() or 0
        
        # Новые пользователи за последние 30 дней
        month_ago = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        stmt = select(func.count(User.id)).where(
            User.created_at >= month_ago
        )
        result = await session.execute(stmt)
        new_users_month = result.scalar() or 0
        
        # Пользователи с заполненным профилем
        stmt = select(func.count(User.id)).where(
            User.surname.isnot(None),
            User.name.isnot(None),
            User.phone.isnot(None)
        )
        result = await session.execute(stmt)
        users_with_profile = result.scalar() or 0
        
        text = (
            f"👥 <b>Статистика пользователей</b>\n\n"
            f"📈 <b>Новые пользователи:</b>\n"
            f"• За последние 7 дней: {new_users_week}\n"
            f"• За текущий месяц: {new_users_month}\n\n"
            f"📝 <b>Профили:</b>\n"
            f"• С заполненным профилем: {users_with_profile}\n"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")],
        ])
        
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        await callback.answer()
        break


@router.callback_query(F.data == "admin_payments")
async def admin_payments(callback: CallbackQuery):
    """Статистика по платежам"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    async for session in get_session():
        # Платежи по статусам
        stmt = select(func.count(Payment.id)).where(
            Payment.status == PaymentStatus.PENDING
        )
        result = await session.execute(stmt)
        pending_payments = result.scalar() or 0
        
        stmt = select(func.count(Payment.id)).where(
            Payment.status == PaymentStatus.SUCCEEDED
        )
        result = await session.execute(stmt)
        succeeded_payments = result.scalar() or 0
        
        stmt = select(func.count(Payment.id)).where(
            Payment.status == PaymentStatus.CANCELED
        )
        result = await session.execute(stmt)
        canceled_payments = result.scalar() or 0
        
        # Платежи за сегодня
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        stmt = select(func.count(Payment.id)).where(
            Payment.status == PaymentStatus.SUCCEEDED,
            Payment.created_at >= today
        )
        result = await session.execute(stmt)
        payments_today = result.scalar() or 0
        
        stmt = select(func.sum(Payment.amount)).where(
            Payment.status == PaymentStatus.SUCCEEDED,
            Payment.created_at >= today
        )
        result = await session.execute(stmt)
        revenue_today = result.scalar() or 0.0
        revenue_today = float(revenue_today) if revenue_today else 0.0
        
        # Платежи за месяц
        month_ago = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        stmt = select(func.count(Payment.id)).where(
            Payment.status == PaymentStatus.SUCCEEDED,
            Payment.created_at >= month_ago
        )
        result = await session.execute(stmt)
        payments_month = result.scalar() or 0
        
        stmt = select(func.sum(Payment.amount)).where(
            Payment.status == PaymentStatus.SUCCEEDED,
            Payment.created_at >= month_ago
        )
        result = await session.execute(stmt)
        revenue_month = result.scalar() or 0.0
        revenue_month = float(revenue_month) if revenue_month else 0.0
        
        text = (
            f"💳 <b>Статистика платежей</b>\n\n"
            f"📊 <b>По статусам:</b>\n"
            f"• Ожидают оплаты: {pending_payments}\n"
            f"• Успешных: {succeeded_payments}\n"
            f"• Отменено: {canceled_payments}\n\n"
            f"📅 <b>За сегодня:</b>\n"
            f"• Платежей: {payments_today}\n"
            f"• Сумма: {revenue_today:.2f} ₽\n\n"
            f"📆 <b>За текущий месяц:</b>\n"
            f"• Платежей: {payments_month}\n"
            f"• Сумма: {revenue_month:.2f} ₽\n"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")],
        ])
        
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        await callback.answer()
        break


@router.callback_query(F.data == "admin_subscriptions")
async def admin_subscriptions(callback: CallbackQuery):
    """Статистика по подпискам"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    async for session in get_session():
        now = datetime.utcnow()
        
        # Подписки по статусам
        stmt = select(func.count(Subscription.id)).where(
            Subscription.status == SubscriptionStatus.ACTIVE,
            Subscription.end_date > now
        )
        result = await session.execute(stmt)
        active = result.scalar() or 0
        
        stmt = select(func.count(Subscription.id)).where(
            Subscription.status == SubscriptionStatus.EXPIRED
        )
        result = await session.execute(stmt)
        expired = result.scalar() or 0
        
        stmt = select(func.count(Subscription.id)).where(
            Subscription.status == SubscriptionStatus.PENDING
        )
        result = await session.execute(stmt)
        pending = result.scalar() or 0
        
        # Подписки, истекающие в ближайшие 7 дней
        week_later = now.replace(hour=23, minute=59, second=59, microsecond=999999) + \
                     __import__('datetime').timedelta(days=7)
        stmt = select(func.count(Subscription.id)).where(
            Subscription.status == SubscriptionStatus.ACTIVE,
            Subscription.end_date >= now,
            Subscription.end_date <= week_later
        )
        result = await session.execute(stmt)
        expiring_soon = result.scalar() or 0
        
        text = (
            f"📦 <b>Статистика подписок</b>\n\n"
            f"📊 <b>По статусам:</b>\n"
            f"• Активных: {active}\n"
            f"• Истекших: {expired}\n"
            f"• Ожидают оплаты: {pending}\n\n"
            f"⏰ <b>Истекают в ближайшие 7 дней:</b> {expiring_soon}\n"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")],
        ])
        
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        await callback.answer()
        break


@router.callback_query(F.data == "admin_referrals")
async def admin_referrals(callback: CallbackQuery):
    """Статистика по рефералам"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    async for session in get_session():
        # Всего реферальных связей
        stmt = select(func.count(Referral.id))
        result = await session.execute(stmt)
        total = result.scalar() or 0
        
        # Оплатившие подписку
        stmt = select(func.count(Referral.id)).where(
            Referral.has_paid_subscription == True
        )
        result = await session.execute(stmt)
        paid = result.scalar() or 0
        
        # Конверсия
        conversion = (paid / total * 100) if total > 0 else 0
        
        text = (
            f"🎁 <b>Статистика рефералов</b>\n\n"
            f"📊 <b>Общая информация:</b>\n"
            f"• Всего приглашено: {total}\n"
            f"• Оплатили подписку: {paid}\n"
            f"• Конверсия: {conversion:.1f}%\n"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")],
        ])
        
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        await callback.answer()
        break


@router.callback_query(F.data == "admin_back")
async def admin_back(callback: CallbackQuery):
    """Вернуться в главное меню админ панели"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users")],
        [InlineKeyboardButton(text="💳 Платежи", callback_data="admin_payments")],
        [InlineKeyboardButton(text="📦 Подписки", callback_data="admin_subscriptions")],
        [InlineKeyboardButton(text="🎁 Рефералы", callback_data="admin_referrals")],
        [InlineKeyboardButton(text="📋 Список подписчиков", callback_data="admin_subscribers_list")],
    ])
    
    await callback.message.edit_text(
        "🔐 <b>Админ панель</b>\n\n"
        "Выберите раздел:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "admin_subscribers_list")
async def admin_subscribers_list(callback: CallbackQuery):
    """Список всех подписчиков с их карточками"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    async for session in get_session():
        now = datetime.utcnow()
        
        # Получаем уникальных пользователей с активными подписками (берем самую свежую подписку для каждого)
        stmt = select(
            User,
            Subscription
        ).join(Subscription).where(
            Subscription.status == SubscriptionStatus.ACTIVE,
            Subscription.end_date > now
        ).order_by(Subscription.end_date.desc())
        result = await session.execute(stmt)
        all_subscriptions = result.all()
        
        # Группируем по user_id, оставляя только самую свежую подписку для каждого пользователя
        unique_users = {}
        for user, subscription in all_subscriptions:
            if user.id not in unique_users:
                unique_users[user.id] = (user, subscription)
        
        if not unique_users:
            text = "📋 <b>Список подписчиков</b>\n\n❌ Нет активных подписчиков"
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")],
            ])
            await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
            await callback.answer()
            break
        
        # Формируем список подписчиков
        from services.tariff_service import TariffService
        
        subscribers_text = f"📋 <b>Список подписчиков</b>\n\n"
        subscribers_text += f"Всего активных подписчиков: <b>{len(unique_users)}</b>\n\n"
        subscribers_text += "━━━━━━━━━━━━━━━━━━━━\n\n"
        
        # Сортируем по дате окончания подписки (самые свежие первыми)
        sorted_users = sorted(unique_users.values(), key=lambda x: x[1].end_date, reverse=True)
        
        for user, subscription in sorted_users:
            # Загружаем тариф
            tariff = await TariffService.get_tariff_by_id(
                session=session,
                tariff_id=subscription.tariff_id,
            )
            tariff_name = tariff.name if tariff else "Неизвестный тариф"
            
            # Формируем карточку
            fio = f"{user.surname or ''} {user.name or ''} {user.patronymic or ''}".strip()
            if not fio:
                fio = f"{user.first_name or ''} {user.last_name or ''}".strip() or f"ID: {user.telegram_id}"
            
            start_date = subscription.start_date.strftime("%d.%m.%Y") if subscription.start_date else "—"
            end_date = subscription.end_date.strftime("%d.%m.%Y") if subscription.end_date else "—"
            
            subscribers_text += (
                f"👤 <b>{fio}</b>\n"
                f"📱 Телефон: {user.phone or '—'}\n"
                f"🆔 Telegram ID: {user.telegram_id}\n"
                f"📦 Тариф: {tariff_name}\n"
                f"📅 Активация: {start_date}\n"
                f"📅 Окончание: {end_date}\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
            )
        
        # Разбиваем на части, если текст слишком длинный (лимит Telegram ~4096 символов)
        if len(subscribers_text) > 4000:
            # Отправляем первую часть
            first_part = subscribers_text[:4000]
            last_newline = first_part.rfind('\n')
            if last_newline > 0:
                first_part = first_part[:last_newline]
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")],
            ])
            await callback.message.edit_text(first_part, reply_markup=keyboard, parse_mode="HTML")
            
            # Отправляем остальное отдельным сообщением
            remaining = subscribers_text[last_newline+1:]
            await callback.message.answer(remaining, parse_mode="HTML")
        else:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")],
            ])
            await callback.message.edit_text(subscribers_text, reply_markup=keyboard, parse_mode="HTML")
        
        await callback.answer()
        break


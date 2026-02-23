"""
Фоновые задачи
"""
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.ext.asyncio import AsyncSession
from database.base import get_session
from services.subscription_service import SubscriptionService
from services.referral_service import ReferralService
from services.user_service import UserService
from services.payment_service import PaymentService
from database.models import ReferralBonusStatus, PaymentStatus, SubscriptionStatus
from config import settings
from aiogram import Bot
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


async def check_subscriptions_task(bot: Bot):
    """Проверка подписок и отправка напоминаний"""
    try:
        async for session in get_session():
            # Переводим истёкшие подписки в expired
            expired_count = await SubscriptionService.expire_subscriptions(session=session)
            if expired_count > 0:
                logger.info(f"Expired {expired_count} subscriptions")
            
            # Получаем подписки для напоминания
            subscriptions = await SubscriptionService.get_subscriptions_for_reminder(session=session)
            
            for subscription in subscriptions:
                try:
                    # Получаем пользователя по id
                    from sqlalchemy import select
                    from database.models import User
                    stmt = select(User).where(User.id == subscription.user_id)
                    result = await session.execute(stmt)
                    user = result.scalar_one_or_none()
                    
                    if not user:
                        continue
                    
                    end_date = subscription.end_date.strftime("%d.%m.%Y")
                    text = (
                        f"⏰ Напоминание о подписке\n\n"
                        f"Ваша подписка истечёт через 3 дня.\n"
                        f"Дата окончания: {end_date}\n\n"
                        f"Продлите подписку, чтобы не потерять доступ к парфюмерии по закупочным ценам!"
                    )
                    
                    from keyboards.main_menu import get_main_menu_keyboard
                    # Подписка активна (иначе не было бы напоминания)
                    await bot.send_message(
                        chat_id=user.telegram_id,
                        text=text,
                        reply_markup=get_main_menu_keyboard(has_active_subscription=True),
                    )
                    
                    # Отмечаем, что напоминание отправлено
                    await SubscriptionService.mark_reminder_sent(
                        session=session,
                        subscription_id=subscription.id,
                    )
                    
                    logger.info(f"Sent reminder to user {user.telegram_id} for subscription {subscription.id}")
                    
                except Exception as e:
                    logger.error(f"Error sending reminder for subscription {subscription.id}: {e}")
            
            break
    except Exception as e:
        logger.error(f"Error in check_subscriptions_task: {e}")


async def check_pending_payments_task(bot: Bot):
    """Проверка статуса pending платежей и активация подписок"""
    try:
        async for session in get_session():
            from sqlalchemy import select
            from database.models import Payment, Subscription
            
            # Получаем все pending платежи
            stmt = select(Payment).where(
                Payment.status == PaymentStatus.PENDING
            ).order_by(Payment.created_at.desc())
            result = await session.execute(stmt)
            pending_payments = list(result.scalars().all())
            
            for payment in pending_payments:
                try:
                    # Проверяем статус в YooKassa
                    if payment.yookassa_payment_id:
                        new_status = await PaymentService.check_payment_status(
                            session=session,
                            payment_id=payment.id,
                        )
                        
                        # Если платеж успешен, активируем подписку
                        if new_status == PaymentStatus.SUCCEEDED and payment.subscription_id:
                            # Проверяем, не активирована ли уже подписка
                            stmt = select(Subscription).where(Subscription.id == payment.subscription_id)
                            result = await session.execute(stmt)
                            subscription = result.scalar_one_or_none()
                            
                            if subscription and subscription.status != SubscriptionStatus.ACTIVE:
                                # Активируем подписку
                                subscription = await SubscriptionService.activate_subscription(
                                    session=session,
                                    subscription_id=payment.subscription_id,
                                )
                                
                                # Отмечаем реферала как оплатившего
                                await ReferralService.mark_referral_as_paid(
                                    session=session,
                                    referred_user_id=payment.user_id,
                                )
                                
                                # Уведомляем пользователя
                                from sqlalchemy import select
                                from database.models import User
                                stmt = select(User).where(User.id == payment.user_id)
                                result = await session.execute(stmt)
                                user = result.scalar_one_or_none()
                                
                                if user:
                                    from services.tariff_service import TariffService
                                    tariff = await TariffService.get_tariff_by_id(
                                        session=session,
                                        tariff_id=subscription.tariff_id,
                                    )
                                    
                                    tariff_name = tariff.name if tariff else "Неизвестный тариф"
                                    start_date = subscription.start_date.strftime("%d.%m.%Y") if subscription.start_date else "—"
                                    end_date = subscription.end_date.strftime("%d.%m.%Y") if subscription.end_date else "—"
                                    
                                    wa_link = f"https://wa.me/{settings.MANAGER_WHATSAPP.lstrip('+').replace('-', '')}"
                                    text = (
                                        f"✅ Платёж успешно выполнен!\n\n"
                                        f"📋 Ваша подписка активирована:\n"
                                        f"Тариф: {tariff_name}\n"
                                        f"Дата начала: {start_date}\n"
                                        f"Дата окончания: {end_date}\n\n"
                                        f"📞 Для заказа парфюма свяжитесь с менеджером:\n"
                                        f"📱 <a href=\"{wa_link}\">Написать в WhatsApp</a> ({settings.MANAGER_WHATSAPP})"
                                    )
                                    
                                    from keyboards.main_menu import get_main_menu_keyboard
                                    await bot.send_message(
                                        chat_id=user.telegram_id,
                                        text=text,
                                        reply_markup=get_main_menu_keyboard(has_active_subscription=True),
                                    )
                                    
                                    logger.info(f"Activated subscription {subscription.id} for payment {payment.id}")
                                    
                except Exception as e:
                    logger.error(f"Error checking payment {payment.id}: {e}")
            
            break
    except Exception as e:
        logger.error(f"Error in check_pending_payments_task: {e}")


async def daily_active_subscribers_report_task(bot: Bot):
    """Ежедневная рассылка админам списка всех пользователей с активной подпиской"""
    if not settings.ADMIN_TELEGRAM_IDS:
        return
    try:
        admin_ids = [int(id_str.strip()) for id_str in settings.ADMIN_TELEGRAM_IDS.split(",")]
    except (ValueError, TypeError):
        logger.warning("Invalid ADMIN_TELEGRAM_IDS for daily report")
        return
    try:
        async for session in get_session():
            from sqlalchemy import select
            from database.models import User, Tariff

            subscriptions = await SubscriptionService.get_all_active_subscriptions(session=session)
            lines = []
            for i, sub in enumerate(subscriptions, 1):
                stmt = select(User).where(User.id == sub.user_id)
                result = await session.execute(stmt)
                user = result.scalar_one_or_none()
                stmt = select(Tariff).where(Tariff.id == sub.tariff_id)
                result = await session.execute(stmt)
                tariff = result.scalar_one_or_none()
                tariff_name = tariff.name if tariff else "—"
                end_str = sub.end_date.strftime("%d.%m.%Y") if sub.end_date else "—"
                fio = " ".join(filter(None, [user.surname, user.name, user.patronymic])).strip() if user else "—"
                phone = user.phone or "—"
                username = f"@{user.username}" if user and user.username else "—"
                tg_id = user.telegram_id if user else "—"
                lines.append(
                    f"{i}. {fio} | {phone} | {username} | ID: {tg_id} | {tariff_name} | до {end_str}"
                )
            date_str = datetime.utcnow().strftime("%d.%m.%Y %H:%M")
            header = (
                f"📋 <b>Отчёт: подписчики с активной подпиской</b>\n"
                f"Дата: {date_str}\n"
                f"Всего: {len(subscriptions)}\n\n"
            )
            body = "\n".join(lines) if lines else "Нет активных подписок."
            full_text = header + body
            max_len = 4096
            if len(full_text) > max_len:
                parts = [header]
                current = []
                current_len = len(header)
                for line in lines:
                    line_ = line + "\n"
                    if current_len + len(line_) > max_len and current:
                        parts.append("\n".join(current))
                        current = []
                        current_len = 0
                    current.append(line)
                    current_len += len(line_)
                if current:
                    parts.append("\n".join(current))
            else:
                parts = [full_text]
            for admin_id in admin_ids:
                try:
                    for part in parts:
                        await bot.send_message(
                            chat_id=admin_id,
                            text=part,
                            parse_mode="HTML",
                        )
                except Exception as e:
                    logger.warning(f"Failed to send daily report to admin {admin_id}: {e}")
            break
    except Exception as e:
        logger.error(f"Error in daily_active_subscribers_report_task: {e}")


async def check_referral_bonuses_task(bot: Bot):
    """Проверка и уведомление о реферальных бонусах"""
    try:
        async for session in get_session():
            # Получаем все ожидающие бонусы
            bonuses = await ReferralService.get_pending_bonuses(session=session)
            
            for bonus in bonuses:
                try:
                    # Получаем пользователя по id
                    from sqlalchemy import select
                    from database.models import User
                    stmt = select(User).where(User.id == bonus.user_id)
                    result = await session.execute(stmt)
                    user = result.scalar_one_or_none()
                    
                    if not user:
                        continue
                    
                    # Уведомляем пользователя
                    wa_link = f"https://wa.me/{settings.MANAGER_WHATSAPP.lstrip('+').replace('-', '')}"
                    text = (
                        f"🎉 Поздравляем!\n\n"
                        f"Вы пригласили {bonus.active_referrals_count} активных рефералов!\n"
                        f"Вы получили подарок — парфюм!\n\n"
                        f"Свяжитесь с менеджером для получения подарка:\n"
                        f"📱 <a href=\"{wa_link}\">Написать в WhatsApp</a> ({settings.MANAGER_WHATSAPP})"
                    )
                    
                    from keyboards.main_menu import get_main_menu_keyboard
                    # Проверяем наличие активной подписки
                    active_sub = await SubscriptionService.get_active_subscription(
                        session=session,
                        user_id=user.id,
                    )
                    has_active = active_sub is not None
                    
                    await bot.send_message(
                        chat_id=user.telegram_id,
                        text=text,
                        reply_markup=get_main_menu_keyboard(has_active_subscription=has_active),
                    )
                    
                    # Уведомляем администраторов (если указаны)
                    if settings.ADMIN_TELEGRAM_IDS:
                        try:
                            admin_ids = [int(id_str.strip()) for id_str in settings.ADMIN_TELEGRAM_IDS.split(',')]
                            admin_text = (
                                f"🎁 Новый реферальный бонус!\n\n"
                                f"Пользователь: @{user.username or 'N/A'} (ID: {user.telegram_id})\n"
                                f"Активных рефералов: {bonus.active_referrals_count}\n"
                                f"Нужно выдать подарок — парфюм."
                            )
                            for admin_id in admin_ids:
                                try:
                                    await bot.send_message(
                                        chat_id=admin_id,
                                        text=admin_text,
                                    )
                                except Exception as e:
                                    logger.warning(f"Failed to send message to admin {admin_id}: {e}")
                        except (ValueError, TypeError) as e:
                            logger.warning(f"Invalid ADMIN_TELEGRAM_IDS: {e}")
                    
                    # Отмечаем бонус как уведомлённый
                    await ReferralService.mark_bonus_notified(
                        session=session,
                        bonus_id=bonus.id,
                    )
                    
                    logger.info(f"Notified user {user.telegram_id} about bonus {bonus.id}")
                    
                except Exception as e:
                    logger.error(f"Error processing bonus {bonus.id}: {e}")
            
            break
    except Exception as e:
        logger.error(f"Error in check_referral_bonuses_task: {e}")


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    """Настройка планировщика задач"""
    scheduler = AsyncIOScheduler()
    
    # Ежедневный отчёт админам: список подписчиков с активной подпиской (09:00)
    scheduler.add_job(
        daily_active_subscribers_report_task,
        trigger=CronTrigger(hour=9, minute=0),
        args=[bot],
        id="daily_active_subscribers_report",
        replace_existing=True,
    )
    # Проверка подписок каждый день в 10:00
    scheduler.add_job(
        check_subscriptions_task,
        trigger=CronTrigger(hour=10, minute=0),
        args=[bot],
        id="check_subscriptions",
        replace_existing=True,
    )
    
    # Проверка бонусов каждый день в 11:00
    scheduler.add_job(
        check_referral_bonuses_task,
        trigger=CronTrigger(hour=11, minute=0),
        args=[bot],
        id="check_referral_bonuses",
        replace_existing=True,
    )
    
    # Проверка pending платежей каждые 5 минут
    scheduler.add_job(
        check_pending_payments_task,
        trigger=CronTrigger(minute="*/5"),  # Каждые 5 минут
        args=[bot],
        id="check_pending_payments",
        replace_existing=True,
    )
    
    return scheduler

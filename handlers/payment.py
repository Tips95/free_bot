"""
Обработчики платежей и webhook от YooKassa
"""
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, PreCheckoutQuery, SuccessfulPayment
from sqlalchemy.ext.asyncio import AsyncSession
from database.base import get_session
from services.payment_service import PaymentService
from services.subscription_service import SubscriptionService
from services.referral_service import ReferralService
from services.user_service import UserService
from database.models import PaymentStatus
from keyboards.main_menu import get_main_menu_keyboard
from config import settings
import json

router = Router()


@router.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery):
    """Обработка pre-checkout запроса"""
    await pre_checkout_query.answer(ok=True)


@router.callback_query(F.data.startswith("test_payment_"))
async def process_test_payment(callback: CallbackQuery):
    """Обработка тестового платежа (симуляция успешной оплаты)"""
    from config import settings
    
    if not settings.is_test_mode:
        await callback.answer("Тестовый режим отключен", show_alert=True)
        return
    
    payment_id = int(callback.data.split("_")[-1])
    
    async for session in get_session():
        # Получаем платёж
        from sqlalchemy import select
        from database.models import Payment
        
        stmt = select(Payment).where(Payment.id == payment_id)
        result = await session.execute(stmt)
        payment = result.scalar_one_or_none()
        
        if not payment:
            await callback.answer("Платёж не найден", show_alert=True)
            return
        
        if payment.status == PaymentStatus.SUCCEEDED:
            await callback.answer("Платёж уже обработан", show_alert=True)
            return
        
        # Обновляем статус платежа
        payment = await PaymentService.update_payment_status(
            session=session,
            payment_id=payment.id,
            status=PaymentStatus.SUCCEEDED,
        )
        
        # Активируем подписку
        if payment.subscription_id:
            subscription = await SubscriptionService.activate_subscription(
                session=session,
                subscription_id=payment.subscription_id,
            )
            
            # Загружаем тариф для карточки
            from services.tariff_service import TariffService
            tariff = await TariffService.get_tariff_by_id(
                session=session,
                tariff_id=subscription.tariff_id,
            )
            if tariff:
                subscription.tariff = tariff
            
            # Отмечаем реферала как оплатившего (если есть)
            await ReferralService.mark_referral_as_paid(
                session=session,
                referred_user_id=payment.user_id,
            )
            
            # Формируем карточку клиента
            user = await UserService.get_user_by_telegram_id(
                session=session,
                telegram_id=callback.from_user.id,
            )
            
            if user:
                card_text = _generate_client_card(user, subscription)
                
                wa_link = f"https://wa.me/{settings.MANAGER_WHATSAPP.lstrip('+').replace('-', '')}"
                # Отправляем карточку и WhatsApp-номер
                text = (
                    f"✅ Платёж успешно выполнен! (Тестовый режим)\n\n"
                    f"{card_text}\n\n"
                    f"📞 Для заказа парфюма свяжитесь с менеджером:\n"
                    f"📱 <a href=\"{wa_link}\">Написать в WhatsApp</a> ({settings.MANAGER_WHATSAPP})"
                )
                
                # После оплаты подписка активна, показываем кнопку заказа
                await callback.message.edit_text(text, reply_markup=get_main_menu_keyboard(has_active_subscription=True))
                await callback.answer("✅ Оплата успешно симулирована!")
        break


@router.message(F.successful_payment)
async def process_successful_payment(message: Message):
    """Обработка успешной оплаты"""
    payment_info = message.successful_payment
    
    async for session in get_session():
        # Ищем платёж по invoice_payload или другим данным
        # YooKassa может не отправлять invoice_payload, поэтому ищем по другим признакам
        
        # Получаем пользователя
        user = await UserService.get_user_by_telegram_id(
            session=session,
            telegram_id=message.from_user.id,
        )
        
        if not user:
            await message.answer("Ошибка: пользователь не найден")
            return
        
        # Ищем последний pending платёж пользователя
        from sqlalchemy import select
        from database.models import Payment
        
        stmt = select(Payment).where(
            Payment.user_id == user.id,
            Payment.status == PaymentStatus.PENDING,
        ).order_by(Payment.created_at.desc())
        result = await session.execute(stmt)
        payment = result.scalar_one_or_none()
        
        if not payment:
            await message.answer("Платёж не найден. Обратитесь в поддержку.")
            return
        
        # Обновляем статус платежа
        payment = await PaymentService.update_payment_status(
            session=session,
            payment_id=payment.id,
            status=PaymentStatus.SUCCEEDED,
        )
        
        # Активируем подписку
        if payment.subscription_id:
            subscription = await SubscriptionService.activate_subscription(
                session=session,
                subscription_id=payment.subscription_id,
            )
            
            # Загружаем тариф для карточки
            from services.tariff_service import TariffService
            tariff = await TariffService.get_tariff_by_id(
                session=session,
                tariff_id=subscription.tariff_id,
            )
            if tariff:
                subscription.tariff = tariff  # Присваиваем для использования в функции
            
            # Отмечаем реферала как оплатившего (если есть)
            await ReferralService.mark_referral_as_paid(
                session=session,
                referred_user_id=user.id,
            )
            
            # Формируем карточку клиента
            card_text = _generate_client_card(user, subscription)
            
        wa_link = f"https://wa.me/{settings.MANAGER_WHATSAPP.lstrip('+').replace('-', '')}"
        # Отправляем карточку и WhatsApp-номер
        text = (
            f"✅ Платёж успешно выполнен!\n\n"
            f"{card_text}\n\n"
            f"📞 Для заказа парфюма свяжитесь с менеджером:\n"
            f"📱 <a href=\"{wa_link}\">Написать в WhatsApp</a> ({settings.MANAGER_WHATSAPP})"
        )
        
        # После оплаты подписка активна, показываем кнопку заказа
        await message.answer(text, reply_markup=get_main_menu_keyboard(has_active_subscription=True))
        break


def _generate_client_card(user, subscription) -> str:
    """Генерация карточки клиента"""
    fio = f"{user.surname or ''} {user.name or ''} {user.patronymic or ''}".strip()
    client_id = user.telegram_id  # Можно использовать публичный ID
    
    start_date = subscription.start_date.strftime("%d.%m.%Y") if subscription.start_date else "—"
    end_date = subscription.end_date.strftime("%d.%m.%Y") if subscription.end_date else "—"
    
    # Безопасное получение названия тарифа
    tariff_name = subscription.tariff.name if hasattr(subscription, 'tariff') and subscription.tariff else "Неизвестный тариф"
    
    card = (
        f"📋 Карточка клиента\n\n"
        f"ФИО: {fio}\n"
        f"Телефон: {user.phone or '—'}\n"
        f"ID клиента: {client_id}\n"
        f"Тариф: {tariff_name}\n"
        f"Дата активации: {start_date}\n"
        f"Дата окончания: {end_date}"
    )
    
    return card


# Webhook handler для YooKassa (если используется webhook)
@router.message(F.web_app_data)
async def handle_webhook(message: Message):
    """Обработка webhook от YooKassa (если используется)"""
    # YooKassa webhook обычно обрабатывается через отдельный endpoint
    # Здесь можно добавить обработку, если нужно
    pass

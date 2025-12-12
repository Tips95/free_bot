"""
Обработчики оформления подписки
"""
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from database.base import get_session
from services.user_service import UserService
from services.tariff_service import TariffService
from services.subscription_service import SubscriptionService
from services.payment_service import PaymentService
from services.referral_service import ReferralService
from keyboards.main_menu import get_main_menu_keyboard
from states.subscription_states import SubscriptionStates
from config import settings
import re

router = Router()


@router.callback_query(F.data.startswith("select_tariff_"))
async def select_tariff(callback: CallbackQuery, state: FSMContext):
    """Выбор тарифа и начало анкетирования"""
    tariff_id = int(callback.data.split("_")[-1])
    
    async for session in get_session():
        tariff = await TariffService.get_tariff_by_id(session=session, tariff_id=tariff_id)
        
        if not tariff:
            await callback.answer("Тариф не найден", show_alert=True)
            return
        
        # Сохраняем выбранный тариф в состояние
        await state.update_data(tariff_id=tariff_id)
        await state.set_state(SubscriptionStates.waiting_for_surname)
        
        text = (
            f"Выбран тариф: {tariff.name} — {int(tariff.price)} ₽\n\n"
            f"Для оформления подписки необходимо заполнить анкету.\n\n"
            f"Введите вашу фамилию:"
        )
        
        await callback.message.edit_text(text)
        await callback.answer()
        break


@router.message(SubscriptionStates.waiting_for_surname)
async def process_surname(message: Message, state: FSMContext):
    """Обработка фамилии"""
    surname = message.text.strip()
    
    if not surname or len(surname) < 2:
        await message.answer("Пожалуйста, введите корректную фамилию (минимум 2 символа):")
        return
    
    await state.update_data(surname=surname)
    await state.set_state(SubscriptionStates.waiting_for_name)
    
    await message.answer("Введите ваше имя:")


@router.message(SubscriptionStates.waiting_for_name)
async def process_name(message: Message, state: FSMContext):
    """Обработка имени"""
    name = message.text.strip()
    
    if not name or len(name) < 2:
        await message.answer("Пожалуйста, введите корректное имя (минимум 2 символа):")
        return
    
    await state.update_data(name=name)
    await state.set_state(SubscriptionStates.waiting_for_patronymic)
    
    await message.answer("Введите ваше отчество:")


@router.message(SubscriptionStates.waiting_for_patronymic)
async def process_patronymic(message: Message, state: FSMContext):
    """Обработка отчества"""
    patronymic = message.text.strip()
    
    if not patronymic or len(patronymic) < 2:
        await message.answer("Пожалуйста, введите корректное отчество (минимум 2 символа):")
        return
    
    await state.update_data(patronymic=patronymic)
    await state.set_state(SubscriptionStates.waiting_for_phone)
    
    await message.answer(
        "Введите ваш номер телефона в формате +7XXXXXXXXXX или 8XXXXXXXXXX:"
    )


@router.message(SubscriptionStates.waiting_for_phone)
async def process_phone(message: Message, state: FSMContext):
    """Обработка телефона и создание подписки"""
    phone = message.text.strip()
    
    # Валидация телефона
    phone = re.sub(r'[^\d+]', '', phone)
    if phone.startswith('8'):
        phone = '+7' + phone[1:]
    elif not phone.startswith('+7'):
        phone = '+7' + phone
    
    if not re.match(r'^\+7\d{10}$', phone):
        await message.answer(
            "Пожалуйста, введите корректный номер телефона в формате +7XXXXXXXXXX:"
        )
        return
    
    # Получаем данные из состояния
    data = await state.get_data()
    tariff_id = data.get("tariff_id")
    surname = data.get("surname")
    name = data.get("name")
    patronymic = data.get("patronymic")
    
    async for session in get_session():
        # Получаем пользователя
        user = await UserService.get_user_by_telegram_id(
            session=session,
            telegram_id=message.from_user.id,
        )
        
        if not user:
            await message.answer("Ошибка: пользователь не найден")
            await state.clear()
            return
        
        # Обновляем профиль пользователя
        user = await UserService.update_user_profile(
            session=session,
            user_id=user.id,
            surname=surname,
            name=name,
            patronymic=patronymic,
            phone=phone,
        )
        
        # Получаем тариф
        tariff = await TariffService.get_tariff_by_id(session=session, tariff_id=tariff_id)
        
        if not tariff:
            await message.answer("Ошибка: тариф не найден")
            await state.clear()
            return
        
        # Создаём подписку
        subscription = await SubscriptionService.create_subscription(
            session=session,
            user_id=user.id,
            tariff_id=tariff_id,
        )
        
        # Создаём платёж
        payment, payment_url = await PaymentService.create_payment(
            session=session,
            user_id=user.id,
            subscription_id=subscription.id,
            amount=float(tariff.price),
        )
        
        await state.clear()
        
        # Отправляем ссылку на оплату
        from config import settings
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        
        if settings.is_test_mode:
            # Тестовый режим - добавляем кнопку для симуляции оплаты
            text = (
                f"✅ Анкета заполнена!\n\n"
                f"Тариф: {tariff.name}\n"
                f"Сумма: {int(tariff.price)} ₽\n\n"
                f"🧪 ТЕСТОВЫЙ РЕЖИМ\n"
                f"Нажмите кнопку ниже для симуляции успешной оплаты:"
            )
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Симулировать оплату", callback_data=f"test_payment_{payment.id}")],
                [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_menu")],
            ])
        else:
            # Реальный режим - обычная ссылка на оплату
            text = (
                f"✅ Анкета заполнена!\n\n"
                f"Тариф: {tariff.name}\n"
                f"Сумма: {int(tariff.price)} ₽\n\n"
                f"Перейдите по ссылке для оплаты:"
            )
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💳 Оплатить", url=payment_url)],
                [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_menu")],
            ])
        
        await message.answer(text, reply_markup=keyboard)
        break


@router.callback_query(F.data == "cancel")
async def cancel_subscription(callback: CallbackQuery, state: FSMContext):
    """Отмена оформления подписки"""
    await state.clear()
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
        
        await callback.message.edit_text(
            "Оформление подписки отменено.",
            reply_markup=get_main_menu_keyboard(has_active_subscription=has_active)
        )
        await callback.answer()
        break

"""
Обработчик команды /start
"""
from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from database.base import get_session
from services.user_service import UserService
from services.subscription_service import SubscriptionService
from services.tariff_service import TariffService
from keyboards.main_menu import get_main_menu_keyboard
import logging

logger = logging.getLogger(__name__)
router = Router()


# Обработчик команды /start
@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    """Обработка команды /start"""
    logger.info(f"Received /start from user {message.from_user.id}")
    
    await state.clear()
    
    # Извлекаем реферальный код из команды
    referrer_code = None
    if message.text and len(message.text.split()) > 1:
        referrer_code = message.text.split()[1]
        logger.info(f"Referral code: {referrer_code}")
    
    try:
        # Получаем сессию БД
        async for session in get_session():
            # Создаём или получаем пользователя
            user, is_new = await UserService.get_or_create_user(
                session=session,
                telegram_id=message.from_user.id,
                username=message.from_user.username,
                first_name=message.from_user.first_name,
                last_name=message.from_user.last_name,
                referrer_code=referrer_code,
            )
            logger.info(f"User {'created' if is_new else 'found'}: {user.id}")
            
            # Обрабатываем реферальный код
            if referrer_code:
                from services.referral_service import ReferralService
                from sqlalchemy import select
                from database.models import User
                
                # Если пользователь новый и referrer_id уже определён — создаём запись
                if is_new and user.referrer_id:
                    await ReferralService.create_referral(
                        session=session,
                        referrer_id=user.referrer_id,
                        referred_id=user.id,
                    )
                    await session.commit()
                    logger.info(f"Referral created for new user {user.id}")
                # Если пользователь уже существует, но ещё не привязан к рефереру — привязываем
                elif not is_new and not user.referrer_id:
                    stmt = select(User).where(User.referral_code == referrer_code)
                    result = await session.execute(stmt)
                    referrer = result.scalar_one_or_none()
                    
                    # Запрещаем самоприглашение и дубликаты
                    if referrer and referrer.id != user.id:
                        user.referrer_id = referrer.id
                        await session.commit()
                        await ReferralService.create_referral(
                            session=session,
                            referrer_id=referrer.id,
                            referred_id=user.id,
                        )
                        await session.commit()
                        logger.info(f"Referral attached for existing user {user.id} -> referrer {referrer.id}")
            
            # Получаем тарифы для отображения
            tariffs = await TariffService.get_all_active_tariffs(session=session)
            
            # Проверяем наличие активной подписки
            subscription = await SubscriptionService.get_active_subscription(
                session=session,
                user_id=user.id,
            )
            has_active_subscription = subscription is not None
            
            # Формируем текст приветствия
            welcome_text = (
                "👋 Добро пожаловать в бот подписки на парфюмерию!\n\n"
                "✨ <b>Что мы предлагаем:</b>\n"
                "• Доступ к парфюмерии по закупочным ценам\n"
                "• Реферальная программа с подарками\n"
                "• Заказ парфюма через WhatsApp-менеджера\n\n"
                "🎁 <b>Реферальная программа:</b>\n"
                "Пригласите 3 друзей по вашей реферальной ссылке.\n"
                "Когда они оплатят подписку, вы получите подарок — парфюм!\n\n"
                "💡 <b>Как это работает:</b>\n"
                "1. Оформите подписку на любой тариф\n"
                "2. Получите доступ к парфюмерии по закупочным ценам\n"
                "3. Заказывайте парфюм через WhatsApp-менеджера\n"
                "4. Приглашайте друзей и получайте подарки!\n\n"
                "Выберите действие:"
            )
            
            # Используем функцию главного меню для единообразия
            keyboard = get_main_menu_keyboard(has_active_subscription=has_active_subscription)
            
            await message.answer(
                welcome_text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            logger.info(f"Welcome message sent to user {message.from_user.id}")
            break
    except Exception as e:
        logger.error(f"Error in cmd_start: {e}", exc_info=True)
        import traceback
        error_details = traceback.format_exc()
        logger.error(f"Full traceback: {error_details}")
        await message.answer("Произошла ошибка. Попробуйте позже.")

"""
Сервис для работы с пользователями
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database.models import User
from typing import Optional
import secrets
import string


class UserService:
    """Сервис для работы с пользователями"""
    
    @staticmethod
    def _generate_referral_code() -> str:
        """Генерация уникального реферального кода"""
        alphabet = string.ascii_uppercase + string.digits
        return ''.join(secrets.choice(alphabet) for _ in range(8))
    
    @staticmethod
    async def get_or_create_user(
        session: AsyncSession,
        telegram_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        referrer_code: Optional[str] = None,
    ) -> tuple[User, bool]:
        """
        Получить или создать пользователя
        Returns: (user, is_new)
        """
        # Проверяем существование пользователя
        stmt = select(User).where(User.telegram_id == telegram_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        
        if user:
            # Обновляем данные, если изменились
            if username and user.username != username:
                user.username = username
            if first_name and user.first_name != first_name:
                user.first_name = first_name
            if last_name and user.last_name != last_name:
                user.last_name = last_name
            await session.commit()
            return user, False
        
        # Создаём нового пользователя
        referral_code = UserService._generate_referral_code()
        
        # Проверяем уникальность кода
        while True:
            stmt = select(User).where(User.referral_code == referral_code)
            result = await session.execute(stmt)
            if result.scalar_one_or_none() is None:
                break
            referral_code = UserService._generate_referral_code()
        
        # Ищем реферера, если указан код
        referrer_id = None
        if referrer_code:
            stmt = select(User).where(User.referral_code == referrer_code)
            result = await session.execute(stmt)
            referrer = result.scalar_one_or_none()
            if referrer and referrer.telegram_id != telegram_id:  # Защита от самоприглашения
                referrer_id = referrer.id
        
        user = User(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            referral_code=referral_code,
            referrer_id=referrer_id,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        
        return user, True
    
    @staticmethod
    async def get_user_by_telegram_id(
        session: AsyncSession,
        telegram_id: int,
    ) -> Optional[User]:
        """Получить пользователя по telegram_id"""
        stmt = select(User).where(User.telegram_id == telegram_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
    
    @staticmethod
    async def update_user_profile(
        session: AsyncSession,
        user_id: int,
        surname: str,
        name: str,
        patronymic: str,
        phone: str,
    ) -> User:
        """Обновить профиль пользователя"""
        stmt = select(User).where(User.id == user_id)
        result = await session.execute(stmt)
        user = result.scalar_one()
        
        user.surname = surname
        user.name = name
        user.patronymic = patronymic
        user.phone = phone
        
        await session.commit()
        await session.refresh(user)
        return user

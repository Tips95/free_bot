"""
Сервис для работы с подписками
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from database.models import Subscription, SubscriptionStatus, User, Tariff
from datetime import datetime, timedelta
from typing import Optional, List
from dateutil.relativedelta import relativedelta


class SubscriptionService:
    """Сервис для работы с подписками"""
    
    @staticmethod
    async def create_subscription(
        session: AsyncSession,
        user_id: int,
        tariff_id: int,
    ) -> Subscription:
        """Создать подписку (статус PENDING до оплаты)"""
        subscription = Subscription(
            user_id=user_id,
            tariff_id=tariff_id,
            status=SubscriptionStatus.PENDING,
        )
        session.add(subscription)
        await session.commit()
        await session.refresh(subscription)
        return subscription
    
    @staticmethod
    async def activate_subscription(
        session: AsyncSession,
        subscription_id: int,
    ) -> Subscription:
        """Активировать подписку после успешной оплаты"""
        stmt = select(Subscription).where(Subscription.id == subscription_id)
        result = await session.execute(stmt)
        subscription = result.scalar_one()
        
        # Получаем тариф для расчёта дат
        stmt = select(Tariff).where(Tariff.id == subscription.tariff_id)
        result = await session.execute(stmt)
        tariff = result.scalar_one()
        
        # Если есть активная подписка, продлеваем от даты окончания
        # Иначе начинаем с текущей даты
        now = datetime.utcnow()
        
        # Проверяем, есть ли активная подписка
        stmt = select(Subscription).where(
            and_(
                Subscription.user_id == subscription.user_id,
                Subscription.status == SubscriptionStatus.ACTIVE,
                Subscription.end_date > now,
            )
        ).order_by(Subscription.end_date.desc())
        result = await session.execute(stmt)
        active_sub = result.scalar_one_or_none()
        
        if active_sub and active_sub.end_date > now:
            # Продление от даты окончания текущей подписки
            start_date = active_sub.end_date
        else:
            # Новая подписка
            start_date = now
        
        end_date = start_date + relativedelta(months=tariff.duration_months)
        
        subscription.status = SubscriptionStatus.ACTIVE
        subscription.start_date = start_date
        subscription.end_date = end_date
        subscription.reminder_sent = False
        
        await session.commit()
        await session.refresh(subscription)
        return subscription
    
    @staticmethod
    async def get_active_subscription(
        session: AsyncSession,
        user_id: int,
    ) -> Optional[Subscription]:
        """Получить активную подписку пользователя"""
        now = datetime.utcnow()
        stmt = select(Subscription).where(
            and_(
                Subscription.user_id == user_id,
                Subscription.status == SubscriptionStatus.ACTIVE,
                Subscription.end_date > now,
            )
        ).order_by(Subscription.end_date.desc())
        result = await session.execute(stmt)
        # Берём последнюю (с максимальной датой окончания), даже если их несколько
        return result.scalars().first()
    
    @staticmethod
    async def get_user_subscriptions(
        session: AsyncSession,
        user_id: int,
    ) -> List[Subscription]:
        """Получить все подписки пользователя"""
        stmt = select(Subscription).where(
            Subscription.user_id == user_id
        ).order_by(Subscription.created_at.desc())
        result = await session.execute(stmt)
        return list(result.scalars().all())
    
    @staticmethod
    async def expire_subscriptions(session: AsyncSession) -> int:
        """
        Перевести истёкшие подписки в статус EXPIRED
        Returns: количество обновлённых подписок
        """
        now = datetime.utcnow()
        stmt = select(Subscription).where(
            and_(
                Subscription.status == SubscriptionStatus.ACTIVE,
                Subscription.end_date <= now,
            )
        )
        result = await session.execute(stmt)
        subscriptions = list(result.scalars().all())
        
        for sub in subscriptions:
            sub.status = SubscriptionStatus.EXPIRED
        
        await session.commit()
        return len(subscriptions)
    
    @staticmethod
    async def get_subscriptions_for_reminder(session: AsyncSession) -> List[Subscription]:
        """
        Получить подписки, которым нужно отправить напоминание
        (за 3 дня до окончания, напоминание ещё не отправлено)
        """
        now = datetime.utcnow()
        reminder_date = now + timedelta(days=3)
        
        stmt = select(Subscription).where(
            and_(
                Subscription.status == SubscriptionStatus.ACTIVE,
                Subscription.reminder_sent == False,
                Subscription.end_date <= reminder_date,
                Subscription.end_date > now,
            )
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())
    
    @staticmethod
    async def mark_reminder_sent(
        session: AsyncSession,
        subscription_id: int,
    ):
        """Отметить, что напоминание отправлено"""
        stmt = select(Subscription).where(Subscription.id == subscription_id)
        result = await session.execute(stmt)
        subscription = result.scalar_one()
        subscription.reminder_sent = True
        await session.commit()

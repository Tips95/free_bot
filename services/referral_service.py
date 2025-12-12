"""
Сервис для работы с реферальной системой
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from database.models import User, Referral, ReferralBonus, ReferralBonusStatus, Subscription, SubscriptionStatus
from datetime import datetime
from typing import Optional, List
from services.subscription_service import SubscriptionService


class ReferralService:
    """Сервис для работы с реферальной системой"""
    
    # Количество рефералов для получения бонуса
    BONUS_THRESHOLD = 3
    
    @staticmethod
    async def create_referral(
        session: AsyncSession,
        referrer_id: int,
        referred_id: int,
    ) -> Referral:
        """Создать запись о реферале"""
        # Проверяем, не существует ли уже такая запись
        stmt = select(Referral).where(
            and_(
                Referral.referrer_id == referrer_id,
                Referral.referred_id == referred_id,
            )
        )
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()
        
        if existing:
            return existing
        
        referral = Referral(
            referrer_id=referrer_id,
            referred_id=referred_id,
            has_paid_subscription=False,
        )
        session.add(referral)
        await session.commit()
        await session.refresh(referral)
        return referral
    
    @staticmethod
    async def mark_referral_as_paid(
        session: AsyncSession,
        referred_user_id: int,
    ):
        """
        Отметить реферала как оплатившего подписку
        Вызывается после успешной оплаты подписки
        """
        # Находим реферальную запись
        stmt = select(Referral).where(Referral.referred_id == referred_user_id)
        result = await session.execute(stmt)
        referral = result.scalar_one_or_none()
        
        if not referral or referral.has_paid_subscription:
            return  # Уже отмечен или не найден
        
        referral.has_paid_subscription = True
        await session.commit()
        
        # Проверяем, нужно ли выдать бонус рефереру
        await ReferralService._check_and_issue_bonus(session, referral.referrer_id)
    
    @staticmethod
    async def _check_and_issue_bonus(
        session: AsyncSession,
        referrer_id: int,
    ):
        """
        Проверить и выдать бонус, если реферер достиг порога
        """
        # Проверяем, не получал ли уже бонус
        stmt = select(ReferralBonus).where(
            and_(
                ReferralBonus.user_id == referrer_id,
                ReferralBonus.status != ReferralBonusStatus.PENDING,
            )
        )
        result = await session.execute(stmt)
        existing_bonus = result.scalar_one_or_none()
        
        if existing_bonus:
            return  # Бонус уже был выдан
        
        # Считаем активных оплаченных рефералов
        active_count = await ReferralService.count_active_paid_referrals(session, referrer_id)
        
        if active_count >= ReferralService.BONUS_THRESHOLD:
            # Создаём запись о бонусе
            bonus = ReferralBonus(
                user_id=referrer_id,
                status=ReferralBonusStatus.PENDING,
                active_referrals_count=active_count,
            )
            session.add(bonus)
            await session.commit()
            await session.refresh(bonus)
    
    @staticmethod
    async def count_active_paid_referrals(
        session: AsyncSession,
        referrer_id: int,
    ) -> int:
        """
        Подсчитать количество активных оплаченных рефералов
        """
        # Получаем всех рефералов с оплаченными подписками
        stmt = select(Referral).where(
            and_(
                Referral.referrer_id == referrer_id,
                Referral.has_paid_subscription == True,
            )
        )
        result = await session.execute(stmt)
        referrals = list(result.scalars().all())
        
        if not referrals:
            return 0
        
        # Проверяем, что у рефералов есть активная подписка
        now = datetime.utcnow()
        active_count = 0
        
        for referral in referrals:
            # Проверяем наличие активной подписки
            active_sub = await SubscriptionService.get_active_subscription(
                session,
                referral.referred_id,
            )
            if active_sub:
                active_count += 1
        
        return active_count
    
    @staticmethod
    async def get_referral_stats(
        session: AsyncSession,
        user_id: int,
    ) -> dict:
        """
        Получить статистику по рефералам пользователя
        Returns: {
            "total_referrals": int,
            "paid_referrals": int,
            "active_paid_referrals": int,
            "bonus_available": bool,
            "bonus_issued": bool,
            "referral_code": str,
        }
        """
        # Получаем пользователя
        stmt = select(User).where(User.id == user_id)
        result = await session.execute(stmt)
        user = result.scalar_one()
        
        # Общее количество рефералов
        stmt = select(func.count(Referral.id)).where(Referral.referrer_id == user_id)
        result = await session.execute(stmt)
        total_referrals = result.scalar_one() or 0
        
        # Количество оплаченных рефералов
        stmt = select(func.count(Referral.id)).where(
            and_(
                Referral.referrer_id == user_id,
                Referral.has_paid_subscription == True,
            )
        )
        result = await session.execute(stmt)
        paid_referrals = result.scalar_one() or 0
        
        # Количество активных оплаченных рефералов
        active_paid_referrals = await ReferralService.count_active_paid_referrals(session, user_id)
        
        # Проверяем бонус
        stmt = select(ReferralBonus).where(User.id == user_id)
        result = await session.execute(stmt)
        bonuses = list(result.scalars().all())
        bonus_issued = any(b.status != ReferralBonusStatus.PENDING for b in bonuses)
        bonus_available = active_paid_referrals >= ReferralService.BONUS_THRESHOLD and not bonus_issued
        
        return {
            "total_referrals": total_referrals,
            "paid_referrals": paid_referrals,
            "active_paid_referrals": active_paid_referrals,
            "bonus_available": bonus_available,
            "bonus_issued": bonus_issued,
            "referral_code": user.referral_code,
            "remaining_for_bonus": max(0, ReferralService.BONUS_THRESHOLD - active_paid_referrals),
        }
    
    @staticmethod
    async def get_pending_bonuses(session: AsyncSession) -> List[ReferralBonus]:
        """Получить все ожидающие бонусы (для уведомлений)"""
        stmt = select(ReferralBonus).where(
            ReferralBonus.status == ReferralBonusStatus.PENDING
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())
    
    @staticmethod
    async def mark_bonus_notified(
        session: AsyncSession,
        bonus_id: int,
    ):
        """Отметить бонус как уведомлённый"""
        stmt = select(ReferralBonus).where(ReferralBonus.id == bonus_id)
        result = await session.execute(stmt)
        bonus = result.scalar_one()
        bonus.status = ReferralBonusStatus.NOTIFIED
        await session.commit()

"""
Сервис для работы с тарифами
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database.models import Tariff
from typing import List, Optional


class TariffService:
    """Сервис для работы с тарифами"""
    
    @staticmethod
    async def get_all_active_tariffs(session: AsyncSession) -> List[Tariff]:
        """Получить все активные тарифы"""
        stmt = select(Tariff).where(Tariff.is_active == True).order_by(Tariff.duration_months)
        result = await session.execute(stmt)
        return list(result.scalars().all())
    
    @staticmethod
    async def get_tariff_by_code(session: AsyncSession, code: str) -> Optional[Tariff]:
        """Получить тариф по коду"""
        stmt = select(Tariff).where(Tariff.code == code, Tariff.is_active == True)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_tariff_by_id(session: AsyncSession, tariff_id: int) -> Optional[Tariff]:
        """Получить тариф по ID"""
        stmt = select(Tariff).where(Tariff.id == tariff_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_tariff_by_name(session: AsyncSession, name: str) -> Optional[Tariff]:
        """Получить тариф по названию (Месячный, Полгода, Годовой)"""
        stmt = select(Tariff).where(Tariff.name == name)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
    
    @staticmethod
    async def init_default_tariffs(session: AsyncSession):
        """Инициализация дефолтных тарифов"""
        default_tariffs = [
            {"code": "monthly", "name": "Месячный", "duration_months": 1, "price": 249.00},
            {"code": "half_year", "name": "Полгода", "duration_months": 6, "price": 1499.00},
            {"code": "yearly", "name": "Годовой", "duration_months": 12, "price": 1999.00},
        ]
        
        for tariff_data in default_tariffs:
            stmt = select(Tariff).where(Tariff.code == tariff_data["code"])
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()
            
            if not existing:
                tariff = Tariff(**tariff_data)
                session.add(tariff)
        
        await session.commit()

"""
Сервис для работы с платежами
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database.models import Payment, PaymentStatus, Subscription
from typing import Optional
import aiohttp
import json
from config import settings


class PaymentService:
    """Сервис для работы с платежами"""
    
    @staticmethod
    async def create_payment(
        session: AsyncSession,
        user_id: int,
        subscription_id: int,
        amount: float,
    ) -> tuple[Payment, str]:
        """
        Создать платёж через YooKassa
        Returns: (payment, payment_url)
        """
        # Проверяем, нет ли уже активного платежа для этой подписки
        stmt = select(Payment).where(
            Payment.subscription_id == subscription_id,
            Payment.status == PaymentStatus.PENDING,
        )
        result = await session.execute(stmt)
        existing_payment = result.scalar_one_or_none()
        
        if existing_payment:
            # Возвращаем существующий платёж
            payment_url = await PaymentService._get_payment_url(existing_payment.yookassa_payment_id)
            return existing_payment, payment_url
        
        # Создаём платёж в YooKassa
        payment_data = {
            "amount": {
                "value": f"{amount:.2f}",
                "currency": "RUB"
            },
            "confirmation": {
                "type": "redirect",
                "return_url": f"https://t.me/{settings.BOT_USERNAME}"
            },
            "description": f"Подписка на парфюмерию",
            "metadata": {
                "user_id": user_id,
                "subscription_id": subscription_id,
            },
            "capture": True,
        }
        
        yookassa_payment_id, payment_url = await PaymentService._create_yookassa_payment(payment_data)
        
        # Создаём запись в БД
        payment = Payment(
            user_id=user_id,
            subscription_id=subscription_id,
            yookassa_payment_id=yookassa_payment_id,
            amount=amount,
            currency="RUB",
            status=PaymentStatus.PENDING,
            payment_metadata=json.dumps(payment_data.get("metadata", {})),
        )
        session.add(payment)
        await session.commit()
        await session.refresh(payment)
        
        return payment, payment_url
    
    @staticmethod
    async def _create_yookassa_payment(payment_data: dict) -> tuple[str, str]:
        """Создать платёж в YooKassa API"""
        # Определяем URL API в зависимости от режима
        if settings.is_test_mode:
            # Тестовый API для тестовых ключей
            url = "https://api.yookassa.ru/v3/payments"
        else:
            # Продакшн API для реальных ключей
            url = "https://api.yookassa.ru/v3/payments"
        
        # Базовая аутентификация: Shop ID и Secret Key
        auth = aiohttp.BasicAuth(settings.YOOKASSA_SHOP_ID, settings.YOOKASSA_SECRET_KEY)
        
        # Idempotence-Key для предотвращения дублирования платежей
        import uuid
        idempotence_key = str(uuid.uuid4())
        headers = {
            "Content-Type": "application/json",
            "Idempotence-Key": idempotence_key
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payment_data, auth=auth, headers=headers) as response:
                if response.status not in (200, 201):
                    error_text = await response.text()
                    raise Exception(f"YooKassa API error: {response.status} - {error_text}")
                
                data = await response.json()
                payment_id = data["id"]
                payment_url = data["confirmation"]["confirmation_url"]
                return payment_id, payment_url
    
    @staticmethod
    async def _get_payment_url(payment_id: str) -> str:
        """Получить URL платежа по ID"""
        url = f"https://api.yookassa.ru/v3/payments/{payment_id}"
        auth = aiohttp.BasicAuth(settings.YOOKASSA_SHOP_ID, settings.YOOKASSA_SECRET_KEY)
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, auth=auth) as response:
                if response.status != 200:
                    raise Exception(f"Failed to get payment: {response.status}")
                data = await response.json()
                return data["confirmation"]["confirmation_url"]
    
    @staticmethod
    async def get_payment_by_yookassa_id(
        session: AsyncSession,
        yookassa_payment_id: str,
    ) -> Optional[Payment]:
        """Получить платёж по ID YooKassa"""
        stmt = select(Payment).where(Payment.yookassa_payment_id == yookassa_payment_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
    
    @staticmethod
    async def update_payment_status(
        session: AsyncSession,
        payment_id: int,
        status: PaymentStatus,
    ) -> Payment:
        """Обновить статус платежа"""
        stmt = select(Payment).where(Payment.id == payment_id)
        result = await session.execute(stmt)
        payment = result.scalar_one()
        payment.status = status
        await session.commit()
        await session.refresh(payment)
        return payment
    
    @staticmethod
    async def check_payment_status(
        session: AsyncSession,
        payment_id: int,
    ) -> PaymentStatus:
        """Проверить статус платежа в YooKassa"""
        stmt = select(Payment).where(Payment.id == payment_id)
        result = await session.execute(stmt)
        payment = result.scalar_one()
        
        if not payment.yookassa_payment_id:
            return payment.status
        
        url = f"https://api.yookassa.ru/v3/payments/{payment.yookassa_payment_id}"
        auth = aiohttp.BasicAuth(settings.YOOKASSA_SHOP_ID, settings.YOOKASSA_SECRET_KEY)
        
        async with aiohttp.ClientSession() as session_http:
            async with session_http.get(url, auth=auth) as response:
                if response.status != 200:
                    return payment.status
                
                data = await response.json()
                yookassa_status = data.get("status")
                
                if yookassa_status == "succeeded":
                    new_status = PaymentStatus.SUCCEEDED
                elif yookassa_status == "canceled":
                    new_status = PaymentStatus.CANCELED
                else:
                    new_status = PaymentStatus.PENDING
                
                if new_status != payment.status:
                    payment.status = new_status
                    await session.commit()
                
                return payment.status

"""
Модели БД
"""
from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Boolean,
    ForeignKey,
    Numeric,
    Enum as SQLEnum,
    Text,
    Index,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
import enum
from database.base import Base


class SubscriptionStatus(str, enum.Enum):
    """Статусы подписки"""
    ACTIVE = "active"
    EXPIRED = "expired"
    PENDING = "pending"  # Ожидает оплаты


class PaymentStatus(str, enum.Enum):
    """Статусы платежа"""
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    CANCELED = "canceled"


class ReferralBonusStatus(str, enum.Enum):
    """Статусы реферального бонуса"""
    PENDING = "pending"  # Ожидает выдачи
    ISSUED = "issued"  # Выдан
    NOTIFIED = "notified"  # Уведомлён пользователь и админ


class User(Base):
    """Пользователь"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(Integer, unique=True, nullable=False, index=True)
    username = Column(String(255), nullable=True)
    first_name = Column(String(255), nullable=True)
    last_name = Column(String(255), nullable=True)
    
    # Данные анкеты
    surname = Column(String(255), nullable=True)  # Фамилия
    name = Column(String(255), nullable=True)  # Имя
    patronymic = Column(String(255), nullable=True)  # Отчество
    phone = Column(String(20), nullable=True)
    
    # Реферальная система
    referral_code = Column(String(50), unique=True, nullable=False, index=True)
    referrer_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    subscriptions = relationship("Subscription", back_populates="user", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="user", cascade="all, delete-orphan")
    referrals = relationship("Referral", foreign_keys="Referral.referrer_id", back_populates="referrer")
    referral_bonuses = relationship("ReferralBonus", back_populates="user")
    
    __table_args__ = (
        Index("idx_user_telegram_id", "telegram_id"),
        Index("idx_user_referral_code", "referral_code"),
    )


class Tariff(Base):
    """Тариф подписки"""
    __tablename__ = "tariffs"
    
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, nullable=False)  # monthly, half_year, yearly
    name = Column(String(255), nullable=False)  # Название для отображения
    duration_months = Column(Integer, nullable=False)  # Длительность в месяцах
    price = Column(Numeric(10, 2), nullable=False)  # Цена в рублях
    is_active = Column(Boolean, default=True, nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    subscriptions = relationship("Subscription", back_populates="tariff")
    
    __table_args__ = (
        Index("idx_tariff_code", "code"),
    )


class Subscription(Base):
    """Подписка пользователя"""
    __tablename__ = "subscriptions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    tariff_id = Column(Integer, ForeignKey("tariffs.id"), nullable=False)
    
    status = Column(SQLEnum(SubscriptionStatus), default=SubscriptionStatus.PENDING, nullable=False)
    start_date = Column(DateTime(timezone=True), nullable=True)
    end_date = Column(DateTime(timezone=True), nullable=True)
    
    # Флаг для отслеживания отправки напоминания
    reminder_sent = Column(Boolean, default=False, nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    user = relationship("User", back_populates="subscriptions")
    tariff = relationship("Tariff", back_populates="subscriptions")
    payment = relationship("Payment", back_populates="subscription", uselist=False)
    
    __table_args__ = (
        Index("idx_subscription_user_id", "user_id"),
        Index("idx_subscription_status", "status"),
        Index("idx_subscription_end_date", "end_date"),
    )


class Payment(Base):
    """Платёж"""
    __tablename__ = "payments"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    subscription_id = Column(Integer, ForeignKey("subscriptions.id"), nullable=True, unique=True)
    
    yookassa_payment_id = Column(String(255), unique=True, nullable=True, index=True)
    amount = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(3), default="RUB", nullable=False)
    status = Column(SQLEnum(PaymentStatus), default=PaymentStatus.PENDING, nullable=False)
    
    # Дополнительные данные от YooKassa
    payment_metadata = Column(Text, nullable=True)  # JSON (переименовано из metadata, т.к. metadata зарезервировано в SQLAlchemy)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    user = relationship("User", back_populates="payments")
    subscription = relationship("Subscription", back_populates="payment")
    
    __table_args__ = (
        Index("idx_payment_user_id", "user_id"),
        Index("idx_payment_yookassa_id", "yookassa_payment_id"),
        Index("idx_payment_status", "status"),
    )


class Referral(Base):
    """Реферал"""
    __tablename__ = "referrals"
    
    id = Column(Integer, primary_key=True, index=True)
    referrer_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    referred_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True, index=True)
    
    # Флаг, что реферал оплатил подписку
    has_paid_subscription = Column(Boolean, default=False, nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    referrer = relationship("User", foreign_keys=[referrer_id], back_populates="referrals")
    referred = relationship("User", foreign_keys=[referred_id])
    
    __table_args__ = (
        Index("idx_referral_referrer_id", "referrer_id"),
        Index("idx_referral_referred_id", "referred_id"),
        Index("idx_referral_paid", "has_paid_subscription"),
    )


class ReferralBonus(Base):
    """Реферальный бонус (подарок)"""
    __tablename__ = "referral_bonuses"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    status = Column(SQLEnum(ReferralBonusStatus), default=ReferralBonusStatus.PENDING, nullable=False)
    
    # Количество активных рефералов на момент выдачи
    active_referrals_count = Column(Integer, nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    user = relationship("User", back_populates="referral_bonuses")
    
    __table_args__ = (
        Index("idx_bonus_user_id", "user_id"),
        Index("idx_bonus_status", "status"),
    )

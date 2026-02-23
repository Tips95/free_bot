"""
Конфигурация приложения
"""
import os
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Настройки приложения"""
    
    # Telegram Bot
    BOT_TOKEN: str
    BOT_USERNAME: Optional[str] = None
    
    # Database: по умолчанию — постоянное хранилище /data (данные не теряются при пересборке).
    # Для локальной разработки задайте в .env: DATABASE_URL=sqlite+aiosqlite:///./bot.db
    DATA_DIR: Optional[str] = None
    DATABASE_URL: str = "sqlite+aiosqlite:////data/bot.db"
    
    # YooKassa
    YOOKASSA_SHOP_ID: str
    YOOKASSA_SECRET_KEY: str
    YOOKASSA_WEBHOOK_URL: Optional[str] = None
    
    # Test Mode (автоматически определяется по префиксу ключа)
    TEST_MODE: Optional[bool] = None  # Если None, определяется автоматически
    
    # WhatsApp
    MANAGER_WHATSAPP: str = "+7999-399-57-95"
    
    # Admin (можно указать несколько через запятую)
    ADMIN_TELEGRAM_IDS: Optional[str] = None  # Например: "95714127,6172571059"
    
    # Ссылки на каталоги (Яндекс.Диск) — показываются подписчикам
    CATALOG_LINK_1: str = "https://disk.yandex.ru/i/32sab_Y5hmPQHA"  # масляные духи
    CATALOG_LINK_2: str = "https://disk.yandex.ru/i/uWosSxMs_S2TMw"  # дубайские оригиналы
    CATALOG_NAME_1: str = "Масляные духи"
    CATALOG_NAME_2: str = "Дубайские оригиналы"
    
    # Базовые значения статистики (добавляются к данным из БД после восстановления/миграции)
    STATS_BASELINE_TOTAL_USERS: int = 892
    STATS_BASELINE_USERS_WITH_SUBSCRIPTION: int = 103  # приобрели подписку
    STATS_BASELINE_ACTIVE_SUBSCRIPTIONS: int = 62
    STATS_BASELINE_TOTAL_SUBSCRIPTIONS: int = 185
    STATS_BASELINE_SUCCESSFUL_PAYMENTS: int = 107
    STATS_BASELINE_REVENUE: float = 33143.0  # ₽
    STATS_BASELINE_REFERRALS: int = 7
    STATS_BASELINE_PAID_REFERRALS: int = 0
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
    
    @property
    def database_url(self) -> str:
        """URL БД: если задан DATA_DIR (напр. /data), используем его для сохранения bot.db"""
        if self.DATA_DIR:
            path = self.DATA_DIR.rstrip("/") + "/bot.db"
            # Абсолютный путь: sqlite+aiosqlite:////data/bot.db
            return f"sqlite+aiosqlite://{path}" if path.startswith("/") else f"sqlite+aiosqlite:///{path}"
        return self.DATABASE_URL

    @property
    def is_test_mode(self) -> bool:
        """Автоматически определяем тестовый режим по префиксу ключа"""
        if self.TEST_MODE is not None:
            return self.TEST_MODE
        # Тестовый режим если ключ начинается с "test_", продакшн если с "live_"
        return self.YOOKASSA_SECRET_KEY.startswith('test_')


settings = Settings()

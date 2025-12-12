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
    
    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./bot.db"
    
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
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
    
    @property
    def is_test_mode(self) -> bool:
        """Автоматически определяем тестовый режим по префиксу ключа"""
        if self.TEST_MODE is not None:
            return self.TEST_MODE
        # Тестовый режим если ключ начинается с "test_", продакшн если с "live_"
        return self.YOOKASSA_SECRET_KEY.startswith('test_')


settings = Settings()

"""
Однократная загрузка подписчиков в БД (восстановление списка).
Запуск из корня проекта: python scripts/seed_subscribers.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.base import get_session, init_db
from services.seed_restore import run_seed


async def main():
    await init_db()
    async for session in get_session():
        result = await run_seed(session)
        print(f"Добавлено подписок: {result['added']}, пропущено: {result['skipped']}")
        for err in result["errors"]:
            print(f"  Ошибка: {err}")
        break
    print("Готово.")


if __name__ == "__main__":
    asyncio.run(main())

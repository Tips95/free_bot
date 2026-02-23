"""
Однократная загрузка подписчиков в БД (восстановление списка).
Запуск из корня проекта: python scripts/seed_subscribers.py
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime

# Корень проекта в path для импортов
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.base import get_session, init_db
from database.models import User, Subscription, SubscriptionStatus
from services.user_service import UserService
from services.tariff_service import TariffService
from sqlalchemy import select

# Список подписчиков: ФИО, телефон, Telegram ID, тариф, дата активации, дата окончания
SUBSCRIBERS = [
    ("Абдулаева Мадина Турпал Алиевна", "+79380000089", 6416879137, "Годовой", "17.02.2026", "17.02.2027"),
    ("Хакимова Селима Сулейманова", "+79640629137", 7625874543, "Годовой", "02.02.2026", "02.02.2027"),
    ("Ахмадов Хусейн Зоврбекович", "+79940840530", 7861445606, "Годовой", "01.02.2026", "01.02.2027"),
    ("Мамакаева Танзила Танзила Муслимовна", "+79640685214", 965385761, "Полгода", "27.01.2026", "27.07.2026"),
    ("Цухаев Ахмед Эльбертович", "+79659474962", 1972017291, "Месячный", "23.02.2026", "23.03.2026"),
    ("Астамиров Ясин анзорович", "+79635883900", 6058701320, "Месячный", "22.02.2026", "22.03.2026"),
    ("Тарамов Турпал Хавашевич", "+79189938858", 1465522910, "Месячный", "22.02.2026", "22.03.2026"),
    ("Ибрагимов Турпал Ирагаевич", "+79635976251", 948989612, "Месячный", "22.02.2026", "22.03.2026"),
    ("Идуев Ислам Русланович", "+79647555575", 8322541800, "Месячный", "21.02.2026", "21.03.2026"),
    ("Дабачхаджиев Анзор Рамзанович", "+79286417177", 781351437, "Месячный", "21.02.2026", "21.03.2026"),
    ("Даудов Адам Ахмедович", "+79899293904", 5140000395, "Месячный", "21.02.2026", "21.03.2026"),
    ("Буцугов Ширван Шамханович", "+79380034404", 6485259727, "Месячный", "21.02.2026", "21.03.2026"),
    ("Каталог Макка Мусаевна", "+79995474141", 7313702704, "Месячный", "19.02.2026", "19.03.2026"),
    ("Магомадов Булат Булат Вахаевич", "+79639830500", 5771786131, "Месячный", "18.02.2026", "18.03.2026"),
    ("Муцуев Имран Русланович", "+79889043360", 7646911735, "Месячный", "18.02.2026", "18.03.2026"),
    ("Юнусов Магомед Шамильевич", "+79286444575", 95714127, "Месячный", "17.02.2026", "17.03.2026"),
    ("Мачаева Раяна Магомедовна", "+79388940934", 5092079195, "Месячный", "16.02.2026", "16.03.2026"),
    ("Закаев Магомед-Арби Вахидович", "+79688388848", 6257792458, "Месячный", "16.02.2026", "16.03.2026"),
    ("Борзиев Дауд Дауд Асланбекович", "+79389999457", 7675704322, "Месячный", "16.02.2026", "16.03.2026"),
    ("Самбуралиев Аюб Зайналбекович", "+79281212828", 8555775394, "Месячный", "16.02.2026", "16.03.2026"),
    ("Давлетбиев Асхаб Юсупович", "+79635895102", 6498101854, "Месячный", "15.02.2026", "15.03.2026"),
    ("Хасаев Мажид Магомедович", "+79339996101", 1375457238, "Месячный", "15.02.2026", "15.03.2026"),
    # Баштаров Мухьаммад Сулейманович +79289009119 — Telegram ID не был указан; добавьте строку с его ID при необходимости
]


def parse_fio(fio: str) -> tuple[str, str, str]:
    """ФИО строка -> (surname, name, patronymic)."""
    parts = fio.strip().split()
    if not parts:
        return "", "", ""
    if len(parts) == 1:
        return parts[0], "", ""
    surname = parts[0]
    patronymic = parts[-1]
    name = " ".join(parts[1:-1]) if len(parts) > 2 else parts[1]
    return surname, name, patronymic


def parse_date(s: str) -> datetime:
    """DD.MM.YYYY -> datetime (naive UTC)."""
    return datetime.strptime(s.strip(), "%d.%m.%Y")


async def run():
    await init_db()
    async for session in get_session():
        for fio, phone, telegram_id, tariff_name, act_str, end_str in SUBSCRIBERS:
            if telegram_id is None:
                print(f"Пропуск (нет Telegram ID): {fio}")
                continue
            try:
                user, _ = await UserService.get_or_create_user(
                    session=session,
                    telegram_id=telegram_id,
                    first_name=fio,
                )
                surname, name, patronymic = parse_fio(fio)
                user.surname = surname or user.surname
                user.name = name or user.name
                user.patronymic = patronymic or user.patronymic
                user.phone = phone or user.phone

                tariff = await TariffService.get_tariff_by_name(session=session, name=tariff_name)
                if not tariff:
                    print(f"Тариф не найден: {tariff_name}, пропуск {fio}")
                    continue

                # Проверяем, нет ли уже активной подписки на эту дату
                stmt = select(Subscription).where(
                    Subscription.user_id == user.id,
                    Subscription.status == SubscriptionStatus.ACTIVE,
                )
                result = await session.execute(stmt)
                existing = result.scalars().first()
                if existing:
                    print(f"Уже есть активная подписка: {fio}, пропуск")
                    continue

                start_dt = parse_date(act_str)
                end_dt = parse_date(end_str)
                sub = Subscription(
                    user_id=user.id,
                    tariff_id=tariff.id,
                    status=SubscriptionStatus.ACTIVE,
                    start_date=start_dt,
                    end_date=end_dt,
                    reminder_sent=False,
                )
                session.add(sub)
                print(f"OK: {fio} | {tariff_name} | до {end_str}")
            except Exception as e:
                print(f"Ошибка для {fio}: {e}")
        await session.commit()
        break
    print("Готово.")


if __name__ == "__main__":
    asyncio.run(run())

"""
Восстановление списка подписчиков в БД (общая логика для скрипта и админ-команды).
"""
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database.models import User, Subscription, SubscriptionStatus
from services.user_service import UserService
from services.tariff_service import TariffService

# Список подписчиков: ФИО, телефон, Telegram ID, тариф, дата активации, дата окончания
SEED_SUBSCRIBERS = [
    ("Абдулаева Мадина Турпал Алиевна", "+79380000089", 6416879137, "Годовой", "17.02.2026", "17.02.2027"),
    ("Хакимова Селима Сулейманова", "+79640629137", 7625874543, "Годовой", "02.02.2026", "02.02.2027"),
    ("Ахмадов Хусейн Зоврбекович", "+79940840530", 7861445606, "Годовой", "01.02.2026", "01.02.2027"),
    ("Мамакаева Танзила Танзила Муслимовна", "+79640685214", 965385761, "Полгода", "27.01.2026", "27.07.2026"),
    ("Дагаев Беслан Лемаевич", "+79280866669", 5150564504, "Месячный", "24.02.2026", "24.03.2026"),
    ("Некдаров Мухаммед Олазырович", "+79606668595", 521269332, "Месячный", "23.02.2026", "23.03.2026"),
    ("Гаджиева Мархет Ахмедовна", "+79285598701", 889889681, "Месячный", "23.02.2026", "23.03.2026"),
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
]


def _parse_fio(fio: str) -> tuple[str, str, str]:
    parts = fio.strip().split()
    if not parts:
        return "", "", ""
    if len(parts) == 1:
        return parts[0], "", ""
    surname, patronymic = parts[0], parts[-1]
    name = " ".join(parts[1:-1]) if len(parts) > 2 else parts[1]
    return surname, name, patronymic


def _parse_date(s: str) -> datetime:
    return datetime.strptime(s.strip(), "%d.%m.%Y")


async def run_seed(session: AsyncSession) -> dict:
    """
    Загружает подписчиков в БД. Пропускает записи без telegram_id и уже с активной подпиской.
    Returns: {"added": int, "skipped": int, "errors": list[str]}
    """
    result = {"added": 0, "skipped": 0, "errors": []}
    for fio, phone, telegram_id, tariff_name, act_str, end_str in SEED_SUBSCRIBERS:
        if telegram_id is None:
            result["skipped"] += 1
            continue
        try:
            user, _ = await UserService.get_or_create_user(
                session=session,
                telegram_id=telegram_id,
                first_name=fio,
            )
            surname, name, patronymic = _parse_fio(fio)
            user.surname = surname or user.surname
            user.name = name or user.name
            user.patronymic = patronymic or user.patronymic
            user.phone = phone or user.phone

            tariff = await TariffService.get_tariff_by_name(session=session, name=tariff_name)
            if not tariff:
                result["errors"].append(f"Тариф «{tariff_name}» не найден: {fio}")
                continue

            stmt = select(Subscription).where(
                Subscription.user_id == user.id,
                Subscription.status == SubscriptionStatus.ACTIVE,
            )
            r = await session.execute(stmt)
            if r.scalars().first():
                result["skipped"] += 1
                continue

            start_dt = _parse_date(act_str)
            end_dt = _parse_date(end_str)
            sub = Subscription(
                user_id=user.id,
                tariff_id=tariff.id,
                status=SubscriptionStatus.ACTIVE,
                start_date=start_dt,
                end_date=end_dt,
                reminder_sent=False,
            )
            session.add(sub)
            result["added"] += 1
        except Exception as e:
            result["errors"].append(f"{fio}: {e}")
    await session.commit()
    return result

"""
Состояния FSM для оформления подписки
"""
from aiogram.fsm.state import State, StatesGroup


class SubscriptionStates(StatesGroup):
    """Состояния для процесса оформления подписки"""
    waiting_for_surname = State()  # Ожидание фамилии
    waiting_for_name = State()  # Ожидание имени
    waiting_for_patronymic = State()  # Ожидание отчества
    waiting_for_phone = State()  # Ожидание телефона

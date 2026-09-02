from datetime import datetime

from constants import ARRIVAL_OPTIONS
from database import db


# ==========================================
# ВЫЧИСЛИТЕЛЬНАЯ МАТЕМАТИКА И ЗАРПЛАТА
# ==========================================
def calculate_salary_and_premium(year, month, hour_rate):
    current_data = db.get_month_data(year, month)

    total_hours = 0.0
    real_work_smen_count = 0

    for date_str, shift in current_data.items():
        if shift["status"] == "Рабочая смена":
            total_hours += shift["hours"] or 0
            real_work_smen_count += 1
        # "Выходной для премии" сознательно НЕ учитывается ни в часах, ни в
        # счётчике смен — это просто информационная отметка в календаре.

    premium_hours = 0
    if 17 <= real_work_smen_count <= 18:
        premium_hours = 9
    elif 19 <= real_work_smen_count <= 20:
        premium_hours = 12
    elif 21 <= real_work_smen_count <= 22:
        premium_hours = 16
    elif real_work_smen_count == 23:
        premium_hours = 18
    elif real_work_smen_count == 24:
        premium_hours = 20
    elif real_work_smen_count >= 25:
        premium_hours = 21

    base_salary = total_hours * hour_rate
    premium_money = premium_hours * hour_rate
    total_salary = base_salary + premium_money

    return {
        "hours_money": base_salary,
        "premium_money": premium_money,
        "total_salary": total_salary,
        "effective_smen": real_work_smen_count,
        "total_hours": total_hours,
    }


def get_operator_for_date(date_obj, op_names):
    base_date = datetime(2026, 9, 1).date()
    delta_days = (date_obj - base_date).days
    operator_index = delta_days % 4
    if operator_index < 0:
        operator_index += 4
    return op_names[operator_index]


def hours_for_arrival(arrival_value):
    """До 20:00 и Буфер -> 11ч без штрафа. Опоздание -> 10ч (минус 1 час)."""
    if arrival_value == ARRIVAL_OPTIONS[2]:
        return 10.0
    return 11.0

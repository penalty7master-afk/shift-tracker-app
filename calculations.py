import calendar
from datetime import date, datetime, timedelta

from constants import (ARRIVAL_OPTIONS, DEFAULT_CYCLE_START, EVENT_BREAK, EVENT_WORK,
                       FULL_SHIFT_HOURS, LATE_SHIFT_HOURS, PREMIUM_LADDER,
                       STATUS_WORK, WEIGHT_NORM)


# ==========================================
# ФОРМАТИРОВАНИЕ
# ==========================================
def format_money(value):
    return f"{int(round(value or 0)):,}".replace(",", " ") + " ₽"


def format_hours(value):
    v = float(value or 0.0)
    return f"{v:.0f}" if abs(v - round(v)) < 0.01 else f"{v:.1f}"


def format_weight(value):
    v = float(value or 0.0)
    return f"{v:.0f}" if abs(v - round(v)) < 0.01 else f"{v:.1f}"


# ==========================================
# ГРАФИК СМЕН
# ==========================================
def parse_cycle_start(value):
    try:
        return datetime.strptime(value or DEFAULT_CYCLE_START, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return datetime.strptime(DEFAULT_CYCLE_START, "%Y-%m-%d").date()


def get_operator_for_date(date_obj, op_names, cycle_start=None):
    """Оператор по ротации 4/4 от настраиваемой даты старта цикла."""
    base = parse_cycle_start(cycle_start)
    # Остаток от деления на положительное число в Python неотрицательный,
    # поэтому даты до base обрабатываются корректно.
    return op_names[(date_obj - base).days % 4]


def hours_for_arrival(arrival_value):
    """До 20:00 и Буфер -> полная смена. Опоздание -> минус один час."""
    return LATE_SHIFT_HOURS if arrival_value == ARRIVAL_OPTIONS[2] else FULL_SHIFT_HOURS


def month_dates(year, month):
    days = calendar.monthrange(year, month)[1]
    return [date(year, month, d) for d in range(1, days + 1)]


def planned_dates_for_operator(year, month, op_names, operator, cycle_start=None):
    """Все дни месяца, которые по графику достаются указанному оператору."""
    if not operator or operator not in op_names:
        return []
    return [d for d in month_dates(year, month)
            if get_operator_for_date(d, op_names, cycle_start) == operator]


# ==========================================
# ПРЕМИЯ
# ==========================================
def premium_hours_for(shifts):
    result = 0
    for threshold, hours in PREMIUM_LADDER:
        if shifts >= threshold:
            result = hours
    return result


def next_premium_step(shifts):
    """(порог, часов_премии, сколько_смен_осталось) или None, если потолок взят."""
    for threshold, hours in PREMIUM_LADDER:
        if shifts < threshold:
            return threshold, hours, threshold - shifts
    return None


def premium_progress(shifts):
    """Доля 0..1 до следующей ступени — для полосы прогресса."""
    step = next_premium_step(shifts)
    if step is None:
        return 1.0
    threshold = step[0]
    previous = 0
    for t, _h in PREMIUM_LADDER:
        if t < threshold:
            previous = t
    span = threshold - previous
    if span <= 0:
        return 1.0
    return max(0.0, min(1.0, (shifts - previous) / span))


# ==========================================
# ИТОГИ ЗА МЕСЯЦ
# ==========================================
def month_summary(month_data, config):
    """
    Считает всё по уже загруженному словарю месяца.
    month_data: {"YYYY-MM-DD": {...}} — результат db.get_month_data().
    """
    hour_rate = float(config.get("hour_rate") or 0.0)
    tax_rate = float(config.get("tax_rate") or 0.0)
    holiday_mult = float(config.get("holiday_mult") or 1.0)

    total_hours = 0.0      # фактически отработанные часы
    paid_hours = 0.0       # часы с учётом праздничного коэффициента
    shifts = 0
    late = 0
    buffer_count = 0
    on_time = 0
    holidays = 0
    norm_ok = 0
    norm_fail = 0
    total_weight = 0.0

    norms = config.get("product_norms") or {}

    for shift in month_data.values():
        if shift.get("status") != STATUS_WORK:
            # "Выходной для премии" — только информационная отметка,
            # в часы и в счётчик смен он сознательно не идёт.
            continue

        shifts += 1
        hours = float(shift.get("hours") or 0.0)
        total_hours += hours
        mult = holiday_mult if shift.get("holiday") else 1.0
        if shift.get("holiday"):
            holidays += 1
        paid_hours += hours * mult

        arrival = shift.get("arrival_status") or ARRIVAL_OPTIONS[0]
        if arrival == ARRIVAL_OPTIONS[2]:
            late += 1
        elif arrival == ARRIVAL_OPTIONS[1]:
            buffer_count += 1
        else:
            on_time += 1

        weight = float(shift.get("weight") or 0.0)
        total_weight += weight
        norm = float(norms.get(shift.get("product"), WEIGHT_NORM) or WEIGHT_NORM)
        if weight >= norm:
            norm_ok += 1
        else:
            norm_fail += 1

    premium_hours = premium_hours_for(shifts)
    base_money = paid_hours * hour_rate
    premium_money = premium_hours * hour_rate
    gross = base_money + premium_money
    tax_money = gross * tax_rate
    net = gross - tax_money

    return {
        "shifts": shifts,
        "total_hours": total_hours,
        "paid_hours": paid_hours,
        "premium_hours": premium_hours,
        "base_money": base_money,
        "premium_money": premium_money,
        "gross": gross,
        "tax_rate": tax_rate,
        "tax_money": tax_money,
        "net": net,
        "on_time": on_time,
        "buffer": buffer_count,
        "late": late,
        "holidays": holidays,
        "norm_ok": norm_ok,
        "norm_fail": norm_fail,
        "total_weight": total_weight,
        "avg_weight": (total_weight / shifts) if shifts else 0.0,
        "next_step": next_premium_step(shifts),
        "progress": premium_progress(shifts),
    }


def month_forecast(year, month, month_data, config, today=None):
    """
    Прогноз на конец месяца: к уже записанному добавляются оставшиеся
    по графику смены выбранного оператора ("Мой оператор" в настройках).
    Возвращает None, если оператор не выбран или месяц уже прошёл.
    """
    my_op = config.get("my_operator")
    op_names = [config.get(f"op{i}") for i in range(1, 5)]
    if not my_op or my_op not in op_names:
        return None

    today = today or date.today()
    planned = planned_dates_for_operator(year, month, op_names, my_op,
                                         config.get("cycle_start"))
    remaining = [d for d in planned
                 if d >= today and d.strftime("%Y-%m-%d") not in month_data]
    if not remaining:
        return None

    base = month_summary(month_data, config)
    hour_rate = float(config.get("hour_rate") or 0.0)
    tax_rate = float(config.get("tax_rate") or 0.0)

    forecast_shifts = base["shifts"] + len(remaining)
    forecast_paid_hours = base["paid_hours"] + len(remaining) * FULL_SHIFT_HOURS
    forecast_premium = premium_hours_for(forecast_shifts)
    gross = (forecast_paid_hours + forecast_premium) * hour_rate
    net = gross * (1.0 - tax_rate)

    return {
        "remaining": len(remaining),
        "shifts": forecast_shifts,
        "premium_hours": forecast_premium,
        "gross": gross,
        "net": net,
        "next_date": remaining[0],
    }


def next_shift_info(config, today=None):
    """Ближайшая смена по графику: (дата, через сколько дней) или None."""
    my_op = config.get("my_operator")
    op_names = [config.get(f"op{i}") for i in range(1, 5)]
    if not my_op or my_op not in op_names:
        return None
    today = today or date.today()
    for offset in range(0, 31):
        d = today + timedelta(days=offset)
        if get_operator_for_date(d, op_names, config.get("cycle_start")) == my_op:
            return d, offset
    return None


# ==========================================
# СТАТИСТИКА ПО ОПЕРАТОРАМ И ЗА ГОД
# ==========================================
def operator_stats(month_data, config):
    """Сводка по каждому оператору: смены, опоздания, средняя выработка."""
    op_names = [config.get(f"op{i}") for i in range(1, 5)]
    cycle_start = config.get("cycle_start")
    stats = {name: {"shifts": 0, "late": 0, "weight": 0.0, "hours": 0.0}
             for name in op_names}

    for date_str, shift in month_data.items():
        if shift.get("status") != STATUS_WORK:
            continue
        owner = shift.get("operator")
        if owner not in stats:
            try:
                d = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                continue
            owner = get_operator_for_date(d, op_names, cycle_start)
        row = stats[owner]
        row["shifts"] += 1
        row["hours"] += float(shift.get("hours") or 0.0)
        row["weight"] += float(shift.get("weight") or 0.0)
        if (shift.get("arrival_status") or ARRIVAL_OPTIONS[0]) == ARRIVAL_OPTIONS[2]:
            row["late"] += 1

    for row in stats.values():
        row["avg_weight"] = (row["weight"] / row["shifts"]) if row["shifts"] else 0.0
    return stats


def year_summaries(year_data, config):
    """12 сводок по месяцам года из плоского словаря всех смен года."""
    buckets = {m: {} for m in range(1, 13)}
    for date_str, shift in year_data.items():
        try:
            month = int(date_str[5:7])
        except (ValueError, IndexError):
            continue
        if month in buckets:
            buckets[month][date_str] = shift
    return [month_summary(buckets[m], config) for m in range(1, 13)]


# ==========================================
# НОЧНОЙ ТРЕКЕР
# ==========================================
def _to_seconds(hhmmss):
    try:
        h, m, s = (int(x) for x in str(hhmmss).split(":"))
        return h * 3600 + m * 60 + s
    except (ValueError, AttributeError):
        return None


def break_seconds(events):
    """
    Суммарная длительность перекуров.
    events: последовательность (время, тип) в хронологическом порядке.
    Перекур закрывается ближайшим следующим событием "Работа".
    """
    total = 0
    opened = None
    for item in events:
        event_time, event_type = item[-2], item[-1]
        seconds = _to_seconds(event_time)
        if seconds is None:
            continue
        if event_type == EVENT_BREAK:
            opened = seconds
        elif event_type == EVENT_WORK and opened is not None:
            delta = seconds - opened
            if delta < 0:                 # переход через полночь
                delta += 24 * 3600
            total += delta
            opened = None
    return total


def format_duration(seconds):
    seconds = int(seconds or 0)
    hours, rest = divmod(seconds, 3600)
    minutes = rest // 60
    if hours:
        return f"{hours} ч {minutes:02d} мин"
    return f"{minutes} мин"

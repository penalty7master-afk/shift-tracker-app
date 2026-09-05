import calendar
import re
from datetime import date, datetime

from constants import (ARRIVAL_OPTIONS, DEFAULT_CYCLE_START, EVENT_BREAK,
                       EVENT_MARK, EVENT_WORK, FULL_SHIFT_HOURS,
                       LATE_SHIFT_HOURS, PREMIUM_LADDER, SHOP1, SHOP2,
                       SHOP_KEYS, STATUS_OVERSLEPT, STATUS_PREMIUM_OFF,
                       STATUS_WORK)


# ==========================================
# ФОРМАТИРОВАНИЕ
# ==========================================
def format_money(value):
    return f"{int(round(value or 0)):,}".replace(",", " ") + " ₽"


def format_signed_money(value):
    sign = "+" if value >= 0 else "−"
    return f"{sign}{format_money(abs(value))}"


def format_hours(value):
    v = float(value or 0.0)
    return f"{v:.0f}" if abs(v - round(v)) < 0.01 else f"{v:.1f}"


def format_weight(value):
    v = float(value or 0.0)
    if abs(v - round(v)) < 0.01:
        return f"{v:,.0f}".replace(",", " ")
    return f"{v:,.1f}".replace(",", " ")


# ==========================================
# КАТАЛОГ ПРОДУКЦИИ
# ==========================================
_LEADING_NUMBER = re.compile(r"^\s*(\d+)")


def product_sort_key(name):
    """Сортировка по числу в начале названия: 90, 90 ПВ, 200, 200 ПВ.
    Названия без числа уходят в конец по алфавиту."""
    text = (name or "").strip()
    match = _LEADING_NUMBER.match(text)
    if not match:
        return (1, 0, text.lower())
    number = int(match.group(1))
    rest = text[match.end():].strip().lower()
    return (0, number, rest)


def sort_products(names):
    return sorted(names, key=product_sort_key)


# ==========================================
# ГРАФИК ОПЕРАТОРОВ (одна ночь через три)
# ==========================================
def parse_cycle_start(value):
    try:
        return datetime.strptime(value or DEFAULT_CYCLE_START, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return datetime.strptime(DEFAULT_CYCLE_START, "%Y-%m-%d").date()


def get_operator_for_date(date_obj, op_names, cycle_start=None):
    """Каждый оператор выходит раз в четыре ночи."""
    base = parse_cycle_start(cycle_start)
    return op_names[(date_obj - base).days % 4]


def op_names_from(config):
    return [config.get(f"op{i}") for i in range(1, 5)]


def hours_for_arrival(arrival_value):
    """До 20:00 и Буфер -> полная смена. Опоздание -> минус один час."""
    return LATE_SHIFT_HOURS if arrival_value == ARRIVAL_OPTIONS[2] else FULL_SHIFT_HOURS


def month_dates(year, month):
    days = calendar.monthrange(year, month)[1]
    return [date(year, month, d) for d in range(1, days + 1)]


def prev_month(year, month):
    return (year - 1, 12) if month == 1 else (year, month - 1)


def norm_for_shop(shop_key, config):
    key = "norm_shop1" if shop_key == SHOP1 else "norm_shop2"
    return float(config.get(key) or 0.0)


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
    """(порог, часов_премии, сколько_смен_осталось) или None."""
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
# МОИ ИТОГИ ЗА МЕСЯЦ
# ==========================================
def month_summary(shifts_data, config):
    """Считает по уже загруженному словарю смен месяца."""
    hour_rate = float(config.get("hour_rate") or 0.0)
    tax_rate = float(config.get("tax_rate") or 0.0)

    total_hours = 0.0
    shifts = 0
    on_time = 0
    buffer_count = 0
    late = 0
    overslept = 0
    premium_off = 0
    premium_paid = 0.0

    for shift in shifts_data.values():
        status = shift.get("status")

        if status == STATUS_PREMIUM_OFF:
            # Информационная отметка: в часы и в счётчик смен не идёт,
            # но фактическая выплата учитывается в начислении.
            premium_off += 1
            premium_paid += float(shift.get("premium_pay") or 0.0)
            continue

        if status != STATUS_WORK:
            if status == STATUS_OVERSLEPT:
                overslept += 1
            continue

        shifts += 1
        total_hours += float(shift.get("hours") or 0.0)

        arrival = shift.get("arrival_status") or ARRIVAL_OPTIONS[0]
        if arrival == ARRIVAL_OPTIONS[2]:
            late += 1
        elif arrival == ARRIVAL_OPTIONS[1]:
            buffer_count += 1
        else:
            on_time += 1

    premium_hours = premium_hours_for(shifts)
    base_money = total_hours * hour_rate
    premium_money = premium_hours * hour_rate
    gross = base_money + premium_money + premium_paid
    tax_money = gross * tax_rate

    return {
        "shifts": shifts,
        "total_hours": total_hours,
        "premium_hours": premium_hours,
        "base_money": base_money,
        "premium_money": premium_money,
        "premium_paid": premium_paid,
        "premium_off": premium_off,
        "gross": gross,
        "tax_rate": tax_rate,
        "tax_money": tax_money,
        "net": gross - tax_money,
        "on_time": on_time,
        "buffer": buffer_count,
        "late": late,
        "overslept": overslept,
        "next_step": next_premium_step(shifts),
        "progress": premium_progress(shifts),
    }


def month_forecast(year, month, shifts_data, config, today=None):
    """Прикидка «если выйду во все оставшиеся дни месяца»."""
    today = today or date.today()
    if (year, month) != (today.year, today.month):
        return None

    remaining = [d for d in month_dates(year, month)
                 if d >= today and d.strftime("%Y-%m-%d") not in shifts_data]
    if not remaining:
        return None

    base = month_summary(shifts_data, config)
    hour_rate = float(config.get("hour_rate") or 0.0)
    tax_rate = float(config.get("tax_rate") or 0.0)

    forecast_shifts = base["shifts"] + len(remaining)
    forecast_hours = base["total_hours"] + len(remaining) * FULL_SHIFT_HOURS
    forecast_premium = premium_hours_for(forecast_shifts)
    gross = ((forecast_hours + forecast_premium) * hour_rate) + base["premium_paid"]

    return {
        "remaining": len(remaining),
        "shifts": forecast_shifts,
        "total_hours": forecast_hours,
        "premium_hours": forecast_premium,
        "gross": gross,
        "net": gross * (1.0 - tax_rate),
    }


def my_shift_dates(shifts_data):
    """Даты, в которые я реально был на смене — фильтр для производства."""
    return {date_str for date_str, shift in shifts_data.items()
            if shift.get("status") == STATUS_WORK}


# ==========================================
# ПРОИЗВОДСТВО
# ==========================================
def shop_values(record):
    """Приводит запись производства к виду {цех: (продукт, кг)}."""
    return {
        SHOP1: (record.get("product1"), record.get("weight1")),
        SHOP2: (record.get("product2"), record.get("weight2")),
    }


def production_summary(production_data, config, only_dates=None):
    """
    Итоги производства за месяц по каждому цеху.
    only_dates: множество дат — считать лишь по ним (мои смены).
    """
    result = {}
    for shop in SHOP_KEYS:
        result[shop] = {
            "nights": 0, "total": 0.0, "avg": 0.0,
            "norm": norm_for_shop(shop, config),
            "norm_ok": 0, "norm_fail": 0,
            "by_product": {},
        }

    for date_str, record in production_data.items():
        if only_dates is not None and date_str not in only_dates:
            continue
        for shop, (product, weight) in shop_values(record).items():
            if weight is None:
                continue
            weight = float(weight)
            row = result[shop]
            row["nights"] += 1
            row["total"] += weight
            if weight >= row["norm"]:
                row["norm_ok"] += 1
            else:
                row["norm_fail"] += 1
            if product:
                slot = row["by_product"].setdefault(product, {"nights": 0, "weight": 0.0})
                slot["nights"] += 1
                slot["weight"] += weight

    for row in result.values():
        row["avg"] = (row["total"] / row["nights"]) if row["nights"] else 0.0
    return result


def operator_stats(production_data, config):
    """Выработка по каждому оператору в разбивке по цехам."""
    names = op_names_from(config)
    cycle_start = config.get("cycle_start")
    stats = {name: {"nights": 0,
                    SHOP1: {"nights": 0, "total": 0.0, "avg": 0.0},
                    SHOP2: {"nights": 0, "total": 0.0, "avg": 0.0}}
             for name in names}

    for date_str, record in production_data.items():
        owner = record.get("operator")
        if owner not in stats:
            try:
                d = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                continue
            owner = get_operator_for_date(d, names, cycle_start)
        row = stats[owner]
        counted = False
        for shop, (_product, weight) in shop_values(record).items():
            if weight is None:
                continue
            counted = True
            row[shop]["nights"] += 1
            row[shop]["total"] += float(weight)
        if counted:
            row["nights"] += 1

    for row in stats.values():
        for shop in SHOP_KEYS:
            cell = row[shop]
            cell["avg"] = (cell["total"] / cell["nights"]) if cell["nights"] else 0.0
    return stats


def year_summaries(year_shifts, config):
    """12 сводок по месяцам года из плоского словаря всех смен года."""
    buckets = {m: {} for m in range(1, 13)}
    for date_str, shift in year_shifts.items():
        try:
            month = int(date_str[5:7])
        except (ValueError, IndexError):
            continue
        if month in buckets:
            buckets[month][date_str] = shift
    return [month_summary(buckets[m], config) for m in range(1, 13)]


def year_heatmap(year, year_shifts):
    """
    Данные годовой карты: список месяцев, в каждом — список дней
    (число, статус). Статус None означает, что день не отмечен.
    """
    months = []
    for month in range(1, 13):
        days = []
        for day in range(1, calendar.monthrange(year, month)[1] + 1):
            key = f"{year}-{month:02d}-{day:02d}"
            shift = year_shifts.get(key)
            days.append((day, (shift or {}).get("status")))
        months.append(days)
    return months


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
    Перекур закрывается ближайшим следующим событием «Работа».
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


def parse_mark(event_type):
    """Из «Отметка 1200» достаёт 1200.0. Не отметка — None."""
    if not isinstance(event_type, str) or not event_type.startswith(EVENT_MARK):
        return None
    tail = event_type[len(EVENT_MARK):].strip()
    try:
        return float(tail.replace(",", "."))
    except ValueError:
        return None


def output_curve(events):
    """
    Кривая выработки за ночь: [(минуты от старта, кг, темп кг/ч)].
    Строится по событиям «Отметка N», где N — накопленные килограммы.
    """
    points = []
    for item in events:
        event_time, event_type = item[-2], item[-1]
        weight = parse_mark(event_type)
        if weight is None:
            continue
        seconds = _to_seconds(event_time)
        if seconds is None:
            continue
        points.append((seconds, weight))
    if len(points) < 2:
        return []

    start = points[0][0]
    curve = []
    prev_seconds, prev_weight = points[0]
    for seconds, weight in points:
        elapsed = seconds - start
        if elapsed < 0:                   # переход через полночь
            elapsed += 24 * 3600
        gap = seconds - prev_seconds
        if gap < 0:
            gap += 24 * 3600
        rate = ((weight - prev_weight) / (gap / 3600.0)) if gap else 0.0
        curve.append((elapsed / 60.0, weight, max(0.0, rate)))
        prev_seconds, prev_weight = seconds, weight
    return curve


def format_duration(seconds):
    seconds = int(seconds or 0)
    hours, rest = divmod(seconds, 3600)
    minutes = rest // 60
    if hours:
        return f"{hours} ч {minutes:02d} мин"
    return f"{minutes} мин"

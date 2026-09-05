import csv
import os
from datetime import datetime

from calculations import (format_hours, format_money, format_weight, mode_of,
                          month_summary, normalize_arrival, op_names_from)
from constants import (MODE_DAY, MODE_NIGHT, MODE_TITLES, MONTH_NAMES,
                       arrival_full, tax_label, term)
from database import db

# Порядок важен: сначала видимые пользователю папки, в конце — приватное
# хранилище приложения как гарантированный запасной путь.
CANDIDATE_DIRS = [
    "/storage/emulated/0/Download",
    "/storage/emulated/0/Documents",
    "/sdcard/Download",
]

CSV_HEADER = ["Дата", "Режим", "Статус", "Часы", "Время прибытия",
              "Премия выплачена", "Заметка", "Оператор",
              "Цех 1 продукт", "Цех 1 кг", "Цех 2 продукт", "Цех 2 кг"]

MODE_CSV = {MODE_NIGHT: "Ночь", MODE_DAY: "День"}

# Системные шрифты с кириллицей. Первый найденный уходит в PDF.
FONT_CANDIDATES = [
    "/system/fonts/DejaVuSans.ttf",
    "/system/fonts/Roboto-Regular.ttf",
    "/system/fonts/NotoSans-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]

TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya", "₽": "R",
    "·": "-", "—": "-", "–": "-", "№": "N",
}


def _writable(path):
    if not path:
        return False
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".shifts_pro_probe")
        with open(probe, "w", encoding="utf-8") as handle:
            handle.write("ok")
        os.remove(probe)
        return True
    except Exception:
        return False


def export_dir():
    """Первая папка, куда реально удалось записать."""
    candidates = list(CANDIDATE_DIRS)
    candidates.append(os.getenv("FLET_APP_STORAGE_DATA"))
    candidates.append(".")
    for path in candidates:
        if _writable(path):
            return path
    raise OSError("Не найдено ни одной папки, доступной для записи")


def _stamp():
    return datetime.now().strftime("%Y%m%d_%H%M")


def _number(value):
    return "" if value is None else f"{float(value):.0f}"


# ==========================================
# CSV
# ==========================================
def export_csv():
    """
    Одна строка на смену. За дату может быть две строки — дневная и
    ночная выработка хранятся отдельными записями.
    """
    target = os.path.join(export_dir(), f"shifts_pro_{_stamp()}.csv")
    dates = db.get_all_dates()

    # utf-8-sig — чтобы Excel не показывал кракозябры на русских заголовках
    with open(target, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(CSV_HEADER)
        for date_str in dates:
            rows = dict(db.production_rows_for_export(date_str))
            # Смена и выработка теперь хранятся по каждому режиму отдельно,
            # поэтому строка выгрузки собирается на каждый режим со своими
            # данными, а не «одна смена + чужое производство».
            modes = [m for m in (MODE_NIGHT, MODE_DAY)
                     if m in rows or db.get_shift(date_str, m)]

            for mode in modes:
                shift = db.get_shift(date_str, mode) or {}
                record = rows.get(mode, {})
                own = True
                writer.writerow([
                    date_str,
                    MODE_CSV.get(mode, mode),
                    (shift.get("status") or "") if own else "",
                    (format_hours(shift.get("hours"))
                     if own and shift.get("hours") else ""),
                    (arrival_full(mode, normalize_arrival(shift.get("arrival_status")))
                     if own and shift.get("arrival_status") else ""),
                    _number(shift.get("premium_pay")) if own else "",
                    (shift.get("note") or "").replace("\n", " ") if own else "",
                    record.get("operator") or "",
                    record.get("product1") or "",
                    _number(record.get("weight1")),
                    record.get("product2") or "",
                    _number(record.get("weight2")),
                ])
    return target


# ==========================================
# PDF
# ==========================================
def _find_font():
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            return path
    return None


def _translit(text):
    """Запасной путь, если TTF с кириллицей не нашёлся: латиница вместо
    пустых квадратов. Ядро PDF знает только Latin-1."""
    out = []
    for ch in str(text):
        lower = ch.lower()
        if lower in TRANSLIT:
            replacement = TRANSLIT[lower]
            out.append(replacement.upper() if ch.isupper() else replacement)
        elif ord(ch) < 256:
            out.append(ch)
        else:
            out.append("?")
    return "".join(out)


def export_pdf(year, month, config):
    """Табель за месяц по текущему режиму: сводка сверху, таблица снизу."""
    try:
        from fpdf import FPDF
    except ImportError:
        raise OSError("Модуль fpdf2 не установлен в сборке")

    mode = mode_of(config)

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=14)
    pdf.add_page()

    font_path = _find_font()
    if font_path:
        pdf.add_font("body", "", font_path)
        pdf.set_font("body", size=10)
        text = str
    else:
        pdf.set_font("Helvetica", size=10)
        text = _translit

    shifts_data = db.get_month_shifts(year, month, mode)
    production_data = db.get_month_production(year, month, mode)
    summary = month_summary(shifts_data, config)

    # ---- шапка ----
    pdf.set_font_size(15)
    pdf.cell(0, 9, text(f"Табель — {MONTH_NAMES[month - 1]} {year}"),
             new_x="LMARGIN", new_y="NEXT")
    pdf.set_font_size(9)
    pdf.cell(0, 5, text(f"{MODE_TITLES[mode]} · сформировано "
                        f"{datetime.now().strftime('%d.%m.%Y %H:%M')}"),
             new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    # ---- сводка ----
    rows = [
        ("Отработано смен", str(summary["shifts"])),
        ("Часов", f"{format_hours(summary['total_hours'])} ч"),
        ("Оклад по часам", format_money(summary["base_money"])),
        (f"Премия за смены ({summary['premium_hours']} ч)",
         format_money(summary["premium_money"])),
    ]
    if summary["premium_paid"]:
        rows.append(("Выплачено премии", format_money(summary["premium_paid"])))
    rows += [
        ("Начислено", format_money(summary["gross"])),
        (f"Налог · {tax_label(summary['tax_rate'])}",
         format_money(summary["tax_money"])),
        ("НА РУКИ", format_money(summary["net"])),
    ]

    pdf.set_font_size(10)
    for index, (label, value) in enumerate(rows):
        bold = index == len(rows) - 1
        if bold:
            pdf.set_font_size(12)
        pdf.cell(110, 7, text(label), border=0)
        pdf.cell(0, 7, text(value), border=0, align="R",
                 new_x="LMARGIN", new_y="NEXT")
        if bold:
            pdf.set_font_size(10)
    pdf.ln(4)

    # ---- таблица дней ----
    headers = ["Дата", "Статус", "Ч", "Приход", "Оператор", "Цех 1", "Цех 2"]
    widths = [20, 34, 10, 30, 30, 30, 28]

    pdf.set_fill_color(230, 230, 235)
    for title, width in zip(headers, widths):
        pdf.cell(width, 7, text(title), border=1, align="C", fill=True)
    pdf.ln()

    for date_str in db.get_month_dates(year, month, mode):
        shift = shifts_data.get(date_str) or {}
        record = production_data.get(date_str) or {}
        hours = shift.get("hours")
        arrival = shift.get("arrival_status")
        cells = [
            date_str[8:10] + "." + date_str[5:7],
            (shift.get("status") or "")[:18],
            format_hours(hours) if hours else "",
            (arrival_full(mode, normalize_arrival(arrival))[:16]
             if arrival else ""),
            (record.get("operator") or "")[:14],
            format_weight(record["weight1"]) if record.get("weight1") is not None else "",
            format_weight(record["weight2"]) if record.get("weight2") is not None else "",
        ]
        for value, width in zip(cells, widths):
            pdf.cell(width, 6, text(value), border=1)
        pdf.ln()

    # ---- операторы по графику ----
    pdf.ln(4)
    pdf.set_font_size(9)
    names = ", ".join(n for n in op_names_from(config) if n)
    pdf.multi_cell(0, 5, text(f"Операторы ({term(mode, 'per_shift')}): {names}"))

    target = os.path.join(
        export_dir(), f"shifts_pro_{year}-{month:02d}_{mode}_{_stamp()}.pdf")
    pdf.output(target)
    return target


# ==========================================
# БЭКАП
# ==========================================
def backup_database():
    target = os.path.join(export_dir(), f"shifts_pro_backup_{_stamp()}.db")
    db.backup_to(target)
    return target


def find_backups():
    """Все найденные файлы бэкапов, свежие первыми."""
    found = []
    candidates = list(CANDIDATE_DIRS)
    candidates.append(os.getenv("FLET_APP_STORAGE_DATA"))
    candidates.append(".")
    seen = set()
    for folder in candidates:
        if not folder or folder in seen or not os.path.isdir(folder):
            continue
        seen.add(folder)
        try:
            names = os.listdir(folder)
        except Exception:
            continue
        for name in names:
            if name.startswith("shifts_pro_backup_") and name.endswith(".db"):
                full = os.path.join(folder, name)
                found.append((os.path.getmtime(full), full))
    found.sort(reverse=True)
    return [path for _mtime, path in found]


def restore_database(path):
    db.restore_from(path)
    return path

import csv
import os
from datetime import datetime

from calculations import format_hours
from database import db

# Порядок важен: сначала пробуем видимые пользователю папки,
# в конце — приватное хранилище приложения как гарантированный запасной путь.
CANDIDATE_DIRS = [
    "/storage/emulated/0/Download",
    "/storage/emulated/0/Documents",
    "/sdcard/Download",
]

CSV_HEADER = ["Дата", "Статус", "Часы", "Время прибытия", "Заметка",
              "Оператор", "Цех 1 продукт", "Цех 1 кг",
              "Цех 2 продукт", "Цех 2 кг"]


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


def export_csv():
    """Одна строка на дату: моя смена и производство рядом."""
    target = os.path.join(export_dir(), f"shifts_pro_{_stamp()}.csv")
    dates = db.get_all_dates()

    # utf-8-sig — чтобы Excel не показывал кракозябры на русских заголовках
    with open(target, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(CSV_HEADER)
        for date_str in dates:
            shift = db.get_shift(date_str) or {}
            record = db.get_production(date_str) or {}
            writer.writerow([
                date_str,
                shift.get("status") or "",
                format_hours(shift.get("hours")) if shift.get("hours") else "",
                shift.get("arrival_status") or "",
                (shift.get("note") or "").replace("\n", " "),
                record.get("operator") or "",
                record.get("product1") or "",
                _number(record.get("weight1")),
                record.get("product2") or "",
                _number(record.get("weight2")),
            ])
    return target


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

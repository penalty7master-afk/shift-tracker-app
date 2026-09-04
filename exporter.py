import csv
import os
from datetime import datetime

from calculations import format_hours, format_weight

# Порядок важен: сначала пробуем видимые пользователю папки,
# в конце — приватное хранилище приложения как гарантированный запасной путь.
CANDIDATE_DIRS = [
    "/storage/emulated/0/Download",
    "/storage/emulated/0/Documents",
    "/sdcard/Download",
]

CSV_HEADER = ["Дата", "Статус", "Оператор", "Часы", "Праздничная",
              "Время прибытия", "Продукт", "Выработка, кг", "Заметка"]


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


def export_csv(shifts):
    """shifts: список кортежей (date_str, shift_dict) из db.get_all_shifts()."""
    target = os.path.join(export_dir(), f"shifts_pro_{_stamp()}.csv")
    # utf-8-sig — чтобы Excel не показывал кракозябры на русских заголовках
    with open(target, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(CSV_HEADER)
        for date_str, shift in shifts:
            writer.writerow([
                date_str,
                shift.get("status") or "",
                shift.get("operator") or "",
                format_hours(shift.get("hours")),
                "да" if shift.get("holiday") else "",
                shift.get("arrival_status") or "",
                shift.get("product") or "",
                format_weight(shift.get("weight")),
                (shift.get("note") or "").replace("\n", " "),
            ])
    return target


def backup_database(db):
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


def restore_database(db, path):
    db.restore_from(path)
    return path

import hashlib
import os
import shutil
import sqlite3

from calculations import sort_products
from constants import (DEFAULT_ACCENT, DEFAULT_BG_THEME, DEFAULT_CYCLE_START,
                       DEFAULT_DAY_HOUR_RATE, DEFAULT_HOUR_RATE,
                       DEFAULT_NORM_SHOP1, DEFAULT_NORM_SHOP2, DEFAULT_PRODUCTS,
                       DEFAULT_SHIFT_MODE, DEFAULT_TAX, MODE_DAY, MODE_NIGHT)

PBKDF2_ROUNDS = 100_000

CONFIG_WRITABLE = (
    "hour_rate", "day_hour_rate", "theme", "bg_theme",
    "op1", "op2", "op3", "op4",
    "tax_rate", "cycle_start", "simple_bg", "norm_shop1", "norm_shop2",
    "haptics", "shift_mode", "mode_chosen",
)

CONFIG_DEFAULTS = {
    "hour_rate": DEFAULT_HOUR_RATE,
    "day_hour_rate": DEFAULT_DAY_HOUR_RATE,
    "theme": DEFAULT_ACCENT,
    "bg_theme": DEFAULT_BG_THEME,
    "op1": "Оператор 1",
    "op2": "Оператор 2",
    "op3": "Оператор 3",
    "op4": "Оператор 4",
    "tax_rate": DEFAULT_TAX,
    "cycle_start": DEFAULT_CYCLE_START,
    "simple_bg": 0,
    "norm_shop1": DEFAULT_NORM_SHOP1,
    "norm_shop2": DEFAULT_NORM_SHOP2,
    "haptics": 1,
    "shift_mode": DEFAULT_SHIFT_MODE,
    "mode_chosen": 0,          # 1 после выбора режима на первом запуске
}


def _mode(value):
    return value if value in (MODE_NIGHT, MODE_DAY) else DEFAULT_SHIFT_MODE


# ==========================================
# ДВИЖОК БАЗЫ ДАННЫХ
# ==========================================
class DBManager:
    """
    Три сущности:
      shifts     — мой день (режим хранится в колонке shift_mode);
      production — выработка смены, ключ (дата + режим): цех работает
                   круглосуточно, за одну дату бывают и день, и ночь;
      timeline   — хронология, тоже с привязкой к режиму.
    """

    def __init__(self):
        # На Android рабочая директория недоступна для записи.
        db_dir = os.getenv("FLET_APP_STORAGE_DATA") or "."
        os.makedirs(db_dir, exist_ok=True)
        self.db_path = os.path.join(db_dir, "shifts_pro.db")
        self._connect()
        self.create_tables()
        self.migrate()
        self.init_default_products()
        self.init_default_config()

    # ---------- соединение ----------
    def _connect(self):
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        # WAL сильно ускоряет частые мелкие записи на флеш-памяти телефона.
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")

    def reconnect(self):
        try:
            self.conn.close()
        except Exception:
            pass
        self._connect()
        self.create_tables()
        self.migrate()
        self.init_default_products()
        self.init_default_config()

    # ---------- схема ----------
    def create_tables(self):
        cur = self.conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS shifts (
                date TEXT,
                shift_mode TEXT,
                hours REAL,
                status TEXT,
                arrival_status TEXT,
                note TEXT,
                premium_pay REAL,
                PRIMARY KEY (date, shift_mode)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS production (
                date TEXT,
                shift_mode TEXT,
                operator TEXT,
                product1 TEXT,
                weight1 REAL,
                product2 TEXT,
                weight2 REAL,
                PRIMARY KEY (date, shift_mode)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS products (
                name TEXT PRIMARY KEY
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS timeline (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT,
                shift_mode TEXT,
                event_time TEXT,
                event_type TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS app_config (
                id INTEGER PRIMARY KEY,
                hour_rate REAL,
                day_hour_rate REAL,
                theme TEXT,
                bg_theme TEXT,
                op1 TEXT, op2 TEXT, op3 TEXT, op4 TEXT,
                pin_hash TEXT,
                pin_salt TEXT,
                tax_rate REAL,
                cycle_start TEXT,
                simple_bg INTEGER,
                norm_shop1 REAL,
                norm_shop2 REAL,
                haptics INTEGER,
                shift_mode TEXT,
                mode_chosen INTEGER
            )
        """)
        self.conn.commit()

    def _create_indexes(self):
        """Отдельным шагом после миграции: в базе прежней версии колонки
        shift_mode ещё нет, и создание индекса по ней падало на старте."""
        cur = self.conn.cursor()
        cur.execute("CREATE INDEX IF NOT EXISTS idx_timeline_date "
                    "ON timeline(date, shift_mode)")
        self.conn.commit()

    def _columns(self, table):
        cur = self.conn.cursor()
        return {r[1] for r in cur.execute(f"PRAGMA table_info({table})").fetchall()}

    def _ensure_columns(self, table, columns):
        cur = self.conn.cursor()
        existing = self._columns(table)
        for name, ddl in columns.items():
            if name not in existing:
                cur.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")

    def migrate(self):
        """Достраивает колонки и, если нужно, пересобирает таблицы."""
        self._ensure_columns("shifts", {
            "note": "TEXT",
            "premium_pay": "REAL",
            "shift_mode": "TEXT",
        })
        self._ensure_columns("app_config", {
            "day_hour_rate": "REAL",
            "bg_theme": "TEXT",
            "pin_salt": "TEXT",
            "tax_rate": "REAL",
            "cycle_start": "TEXT",
            "simple_bg": "INTEGER",
            "norm_shop1": "REAL",
            "norm_shop2": "REAL",
            "haptics": "INTEGER",
            "shift_mode": "TEXT",
            "mode_chosen": "INTEGER",
        })

        cur = self.conn.cursor()
        # Всё, что записано до появления режимов, считаем ночным.
        cur.execute("UPDATE shifts SET shift_mode=? WHERE shift_mode IS NULL",
                    (MODE_NIGHT,))

        self._migrate_shifts()
        self._migrate_production()
        self._migrate_timeline()
        self.conn.commit()
        self._create_indexes()

    def _migrate_shifts(self):
        """
        Ключом была одна дата, поэтому дневная смена затирала ночную за то
        же число. Ключ становится составным — ALTER TABLE такого не умеет,
        таблица пересоздаётся с переносом данных.
        """
        cur = self.conn.cursor()
        row = cur.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='shifts'"
        ).fetchone()
        if row and "PRIMARY KEY (date, shift_mode)" in (row[0] or ""):
            return

        cur.execute("ALTER TABLE shifts RENAME TO shifts_old")
        cur.execute("""
            CREATE TABLE shifts (
                date TEXT,
                shift_mode TEXT,
                hours REAL,
                status TEXT,
                arrival_status TEXT,
                note TEXT,
                premium_pay REAL,
                PRIMARY KEY (date, shift_mode)
            )
        """)
        cur.execute("""
            INSERT INTO shifts (date, shift_mode, hours, status,
                                arrival_status, note, premium_pay)
            SELECT date, COALESCE(shift_mode, ?), hours, status,
                   arrival_status, note, premium_pay
            FROM shifts_old
        """, (MODE_NIGHT,))
        cur.execute("DROP TABLE shifts_old")

    def _migrate_production(self):
        """
        Раньше ключом была одна дата, поэтому за 1 сентября могла
        существовать только одна запись. Ключ становится составным —
        ALTER TABLE такого не умеет, таблица пересоздаётся с переносом.
        """
        if "shift_mode" in self._columns("production"):
            return
        cur = self.conn.cursor()
        cur.execute("ALTER TABLE production RENAME TO production_old")
        cur.execute("""
            CREATE TABLE production (
                date TEXT,
                shift_mode TEXT,
                operator TEXT,
                product1 TEXT,
                weight1 REAL,
                product2 TEXT,
                weight2 REAL,
                PRIMARY KEY (date, shift_mode)
            )
        """)
        cur.execute("""
            INSERT INTO production (date, shift_mode, operator,
                                    product1, weight1, product2, weight2)
            SELECT date, ?, operator, product1, weight1, product2, weight2
            FROM production_old
        """, (MODE_NIGHT,))
        cur.execute("DROP TABLE production_old")

    def _migrate_timeline(self):
        if "shift_mode" in self._columns("timeline"):
            return
        cur = self.conn.cursor()
        cur.execute("ALTER TABLE timeline ADD COLUMN shift_mode TEXT")
        cur.execute("UPDATE timeline SET shift_mode=? WHERE shift_mode IS NULL",
                    (MODE_NIGHT,))

    def init_default_products(self):
        """Каталог намеренно пуст: типовые позиции добавляются кнопкой
        в настройках, чтобы не навязывать чужой список наименований."""
        return

    def fill_default_products(self):
        """Возвращает число реально добавленных позиций."""
        added = 0
        for name in DEFAULT_PRODUCTS:
            if self.add_product(name):
                added += 1
        return added

    def init_default_config(self):
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM app_config WHERE id=1")
        if cur.fetchone()[0] == 0:
            cur.execute("INSERT INTO app_config (id) VALUES (1)")
            self.conn.commit()

    # ---------- конфиг ----------
    def get_config(self):
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM app_config WHERE id=1")
        row = cur.fetchone()
        cols = [d[0] for d in cur.description]
        cfg = dict(zip(cols, row)) if row else {}

        for key, default in CONFIG_DEFAULTS.items():
            if cfg.get(key) in (None, ""):
                cfg[key] = default
        cfg["hour_rate"] = float(cfg["hour_rate"])
        cfg["day_hour_rate"] = float(cfg["day_hour_rate"])
        cfg["tax_rate"] = float(cfg["tax_rate"])
        cfg["norm_shop1"] = float(cfg["norm_shop1"])
        cfg["norm_shop2"] = float(cfg["norm_shop2"])
        cfg["simple_bg"] = int(cfg["simple_bg"] or 0)
        cfg["haptics"] = int(cfg["haptics"] if cfg.get("haptics") is not None else 1)
        cfg["mode_chosen"] = int(cfg["mode_chosen"] or 0)
        cfg["shift_mode"] = _mode(cfg.get("shift_mode"))
        cfg.setdefault("pin_hash", None)
        cfg.setdefault("pin_salt", None)
        return cfg

    def save_config(self, **values):
        """Пишет только переданные и разрешённые поля."""
        fields = {k: v for k, v in values.items() if k in CONFIG_WRITABLE}
        if not fields:
            return
        assignments = ", ".join(f"{k}=?" for k in fields)
        cur = self.conn.cursor()
        cur.execute(f"UPDATE app_config SET {assignments} WHERE id=1",
                    tuple(fields.values()))
        self.conn.commit()

    # ---------- PIN ----------
    @staticmethod
    def hash_pin(pin, salt):
        return hashlib.pbkdf2_hmac(
            "sha256", pin.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ROUNDS
        ).hex()

    def set_pin(self, pin):
        salt = os.urandom(16).hex()
        cur = self.conn.cursor()
        cur.execute("UPDATE app_config SET pin_hash=?, pin_salt=? WHERE id=1",
                    (self.hash_pin(pin, salt), salt))
        self.conn.commit()

    def verify_pin(self, pin):
        """Поддерживает старый формат (голый sha256 без соли): при успешной
        проверке PIN молча пересохраняется в новом формате с солью."""
        cur = self.conn.cursor()
        cur.execute("SELECT pin_hash, pin_salt FROM app_config WHERE id=1")
        row = cur.fetchone()
        if not row or not row[0]:
            return False
        stored_hash, salt = row[0], row[1]

        if salt:
            return self.hash_pin(pin, salt) == stored_hash

        legacy = hashlib.sha256(pin.encode("utf-8")).hexdigest()
        if legacy == stored_hash:
            self.set_pin(pin)
            return True
        return False

    def has_pin(self):
        cur = self.conn.cursor()
        cur.execute("SELECT pin_hash FROM app_config WHERE id=1")
        row = cur.fetchone()
        return bool(row and row[0])

    def clear_pin(self):
        cur = self.conn.cursor()
        cur.execute("UPDATE app_config SET pin_hash=NULL, pin_salt=NULL WHERE id=1")
        self.conn.commit()

    # ==========================================
    # МОЙ ДЕНЬ
    # ==========================================
    SHIFT_FIELDS = "hours, status, arrival_status, note, premium_pay, shift_mode"

    @staticmethod
    def _row_to_shift(row):
        return {"hours": row[0], "status": row[1], "arrival_status": row[2],
                "note": row[3], "premium_pay": row[4], "shift_mode": row[5]}

    def save_shift(self, date_str, hours, status, arrival_status,
                   note=None, premium_pay=None, shift_mode=None):
        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO shifts (date, shift_mode, hours, status,
                                arrival_status, note, premium_pay)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date, shift_mode) DO UPDATE SET
                hours=excluded.hours,
                status=excluded.status,
                arrival_status=excluded.arrival_status,
                note=excluded.note,
                premium_pay=excluded.premium_pay
        """, (date_str, _mode(shift_mode), hours, status, arrival_status,
              note, premium_pay))
        self.conn.commit()

    def delete_shift(self, date_str, shift_mode=None):
        """shift_mode=None — удаляются записи обоих режимов."""
        cur = self.conn.cursor()
        if shift_mode is None:
            cur.execute("DELETE FROM shifts WHERE date=?", (date_str,))
        else:
            cur.execute("DELETE FROM shifts WHERE date=? AND shift_mode=?",
                        (date_str, _mode(shift_mode)))
        self.conn.commit()

    def delete_day(self, date_str, shift_mode=None):
        """Очистка дня: моя смена, производство и хронология этого режима."""
        mode = _mode(shift_mode)
        cur = self.conn.cursor()
        cur.execute("DELETE FROM shifts WHERE date=? AND shift_mode=?",
                    (date_str, mode))
        cur.execute("DELETE FROM production WHERE date=? AND shift_mode=?",
                    (date_str, mode))
        cur.execute("DELETE FROM timeline WHERE date=? AND shift_mode=?",
                    (date_str, mode))
        self.conn.commit()

    def get_shift(self, date_str, shift_mode=None):
        """shift_mode=None — любая запись за дату (нужно только выгрузке)."""
        cur = self.conn.cursor()
        if shift_mode is None:
            cur.execute(f"SELECT {self.SHIFT_FIELDS} FROM shifts WHERE date=? "
                        "ORDER BY shift_mode LIMIT 1", (date_str,))
        else:
            cur.execute(f"SELECT {self.SHIFT_FIELDS} FROM shifts "
                        "WHERE date=? AND shift_mode=?",
                        (date_str, _mode(shift_mode)))
        row = cur.fetchone()
        return self._row_to_shift(row) if row else None

    @staticmethod
    def _month_bounds(year, month):
        start = f"{year}-{month:02d}-01"
        end_year = year + 1 if month == 12 else year
        end_month = 1 if month == 12 else month + 1
        return start, f"{end_year}-{end_month:02d}-01"

    def _shifts_range(self, start, end, shift_mode=None):
        cur = self.conn.cursor()
        # Диапазон вместо LIKE — гарантированный range-scan по ключу.
        if shift_mode is None:
            cur.execute(f"SELECT date, {self.SHIFT_FIELDS} FROM shifts "
                        "WHERE date >= ? AND date < ?", (start, end))
        else:
            cur.execute(f"SELECT date, {self.SHIFT_FIELDS} FROM shifts "
                        "WHERE date >= ? AND date < ? AND shift_mode=?",
                        (start, end, _mode(shift_mode)))
        return {r[0]: self._row_to_shift(r[1:]) for r in cur.fetchall()}

    def get_month_shifts(self, year, month, shift_mode=None):
        start, end = self._month_bounds(year, month)
        return self._shifts_range(start, end, shift_mode)

    def get_year_shifts(self, year, shift_mode=None):
        return self._shifts_range(f"{year}-01-01", f"{year + 1}-01-01",
                                  shift_mode)

    # ==========================================
    # ПРОИЗВОДСТВО ЗА СМЕНУ
    # ==========================================
    PRODUCTION_FIELDS = "operator, product1, weight1, product2, weight2"

    @staticmethod
    def _row_to_production(row):
        return {"operator": row[0], "product1": row[1], "weight1": row[2],
                "product2": row[3], "weight2": row[4]}

    def save_production(self, date_str, operator, product1, weight1,
                        product2, weight2, shift_mode=None):
        """Если за смену ничего не заполнено — запись удаляется."""
        mode = _mode(shift_mode)
        if not operator and weight1 is None and weight2 is None:
            self.delete_production(date_str, mode)
            return
        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO production (date, shift_mode, operator,
                                    product1, weight1, product2, weight2)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date, shift_mode) DO UPDATE SET
                operator=excluded.operator,
                product1=excluded.product1,
                weight1=excluded.weight1,
                product2=excluded.product2,
                weight2=excluded.weight2
        """, (date_str, mode, operator, product1, weight1, product2, weight2))
        self.conn.commit()

    def delete_production(self, date_str, shift_mode=None):
        cur = self.conn.cursor()
        cur.execute("DELETE FROM production WHERE date=? AND shift_mode=?",
                    (date_str, _mode(shift_mode)))
        self.conn.commit()

    def get_production(self, date_str, shift_mode=None):
        cur = self.conn.cursor()
        cur.execute(f"SELECT {self.PRODUCTION_FIELDS} FROM production "
                    "WHERE date=? AND shift_mode=?",
                    (date_str, _mode(shift_mode)))
        row = cur.fetchone()
        return self._row_to_production(row) if row else None

    def _production_range(self, start, end, mode):
        cur = self.conn.cursor()
        cur.execute(f"SELECT date, {self.PRODUCTION_FIELDS} FROM production "
                    "WHERE date >= ? AND date < ? AND shift_mode=?",
                    (start, end, mode))
        return {r[0]: self._row_to_production(r[1:]) for r in cur.fetchall()}

    def get_month_production(self, year, month, shift_mode=None):
        start, end = self._month_bounds(year, month)
        return self._production_range(start, end, _mode(shift_mode))

    def get_year_production(self, year, shift_mode=None):
        return self._production_range(f"{year}-01-01", f"{year + 1}-01-01",
                                      _mode(shift_mode))

    # ---------- выгрузка ----------
    def get_all_dates(self):
        """Все даты, по которым есть хоть что-то — для CSV-экспорта."""
        cur = self.conn.cursor()
        cur.execute("SELECT date FROM shifts UNION SELECT date FROM production "
                    "ORDER BY date")
        return [r[0] for r in cur.fetchall()]

    def get_month_dates(self, year, month, shift_mode=None):
        """Даты месяца, по которым есть данные — для PDF-табеля."""
        start, end = self._month_bounds(year, month)
        mode = _mode(shift_mode)
        cur = self.conn.cursor()
        cur.execute(
            "SELECT date FROM shifts WHERE date >= ? AND date < ? "
            "UNION "
            "SELECT date FROM production "
            "WHERE date >= ? AND date < ? AND shift_mode=? "
            "ORDER BY date", (start, end, start, end, mode))
        return [r[0] for r in cur.fetchall()]

    def production_rows_for_export(self, date_str):
        """Все режимы за дату — CSV выгружает и день, и ночь."""
        cur = self.conn.cursor()
        cur.execute(f"SELECT shift_mode, {self.PRODUCTION_FIELDS} FROM production "
                    "WHERE date=? ORDER BY shift_mode", (date_str,))
        return [(r[0], self._row_to_production(r[1:])) for r in cur.fetchall()]

    # ==========================================
    # ТРЕКЕР СМЕНЫ
    # ==========================================
    def add_timeline_event(self, date_str, event_type, event_time,
                           shift_mode=None):
        cur = self.conn.cursor()
        cur.execute("INSERT INTO timeline (date, shift_mode, event_time, event_type) "
                    "VALUES (?, ?, ?, ?)",
                    (date_str, _mode(shift_mode), event_time, event_type))
        self.conn.commit()
        return cur.lastrowid

    def add_timeline_bulk(self, date_str, events, shift_mode=None):
        mode = _mode(shift_mode)
        cur = self.conn.cursor()
        cur.executemany(
            "INSERT INTO timeline (date, shift_mode, event_time, event_type) "
            "VALUES (?, ?, ?, ?)",
            [(date_str, mode, t, e) for t, e in events])
        self.conn.commit()

    def get_timeline(self, date_str, shift_mode=None):
        """Возвращает (id, время, тип) — id нужен для удаления события."""
        cur = self.conn.cursor()
        cur.execute("SELECT id, event_time, event_type FROM timeline "
                    "WHERE date=? AND shift_mode=? ORDER BY id ASC",
                    (date_str, _mode(shift_mode)))
        return cur.fetchall()

    def get_timeline_dates(self, year, month, shift_mode=None):
        """Даты месяца, где есть хотя бы одно событие трекера."""
        start, end = self._month_bounds(year, month)
        cur = self.conn.cursor()
        cur.execute("SELECT DISTINCT date FROM timeline "
                    "WHERE date >= ? AND date < ? AND shift_mode=?",
                    (start, end, _mode(shift_mode)))
        return {r[0] for r in cur.fetchall()}

    def delete_timeline_events(self, event_ids):
        """Пакетное удаление — вызывается один раз по кнопке «Сохранить»."""
        if not event_ids:
            return
        cur = self.conn.cursor()
        cur.executemany("DELETE FROM timeline WHERE id=?",
                        [(event_id,) for event_id in event_ids])
        self.conn.commit()

    # ==========================================
    # КАТАЛОГ ПРОДУКЦИИ
    # ==========================================
    def get_products(self):
        """Сортировка по числу в названии: 90, 90 ПВ, 200, 200 ПВ, 500."""
        cur = self.conn.cursor()
        cur.execute("SELECT name FROM products")
        return sort_products([r[0] for r in cur.fetchall()])

    def add_product(self, name):
        try:
            cur = self.conn.cursor()
            cur.execute("INSERT INTO products (name) VALUES (?)", (name,))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def product_usage_count(self, name):
        """Сколько смен ссылается на продукт — спрашиваем перед удалением."""
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM production WHERE product1=? OR product2=?",
                    (name, name))
        return cur.fetchone()[0]

    def delete_product(self, name):
        cur = self.conn.cursor()
        cur.execute("DELETE FROM products WHERE name=?", (name,))
        self.conn.commit()

    # ==========================================
    # БЭКАП
    # ==========================================
    def backup_to(self, target_path):
        """Безопасная копия с учётом WAL — через встроенный backup API."""
        target = sqlite3.connect(target_path)
        try:
            self.conn.backup(target)
        finally:
            target.close()
        return target_path

    def restore_from(self, source_path):
        if not os.path.exists(source_path):
            raise FileNotFoundError(source_path)
        # Проверяем, что это действительно наша база, до подмены файла.
        probe = sqlite3.connect(source_path)
        try:
            probe.execute("SELECT COUNT(*) FROM shifts")
        finally:
            probe.close()
        try:
            self.conn.close()
        except Exception:
            pass

        # Запасная копия текущей базы. Без неё неудачная подмена оставляла
        # приложение и без старых данных, и без рабочего соединения.
        rescue = self.db_path + ".rescue"
        if os.path.exists(self.db_path):
            shutil.copyfile(self.db_path, rescue)

        # Хвосты журнала удаляются ДО копирования: иначе новый файл базы
        # какое-то время лежит рядом с журналом от прежней.
        for suffix in ("-wal", "-shm"):
            stale = self.db_path + suffix
            if os.path.exists(stale):
                os.remove(stale)

        try:
            shutil.copyfile(source_path, self.db_path)
            self.reconnect()
        except Exception:
            # Откат к прежней базе. reconnect() обязателен в любом случае:
            # без него дальше падал бы каждый запрос до перезапуска.
            if os.path.exists(rescue):
                shutil.copyfile(rescue, self.db_path)
            for suffix in ("-wal", "-shm"):
                stale = self.db_path + suffix
                if os.path.exists(stale):
                    os.remove(stale)
            self.reconnect()
            raise
        finally:
            if os.path.exists(rescue):
                os.remove(rescue)


db = DBManager()

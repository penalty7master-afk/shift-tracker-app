import hashlib
import os
import shutil
import sqlite3

from calculations import sort_products
from constants import (DEFAULT_ACCENT, DEFAULT_BG_THEME, DEFAULT_CYCLE_START,
                       DEFAULT_NORM_SHOP1, DEFAULT_NORM_SHOP2, DEFAULT_TAX)

PBKDF2_ROUNDS = 100_000

# Колонки app_config, которые разрешено писать через save_config()
CONFIG_WRITABLE = (
    "hour_rate", "theme", "bg_theme", "op1", "op2", "op3", "op4",
    "tax_rate", "cycle_start", "simple_bg", "norm_shop1", "norm_shop2",
)

CONFIG_DEFAULTS = {
    "hour_rate": 632.0,
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
}


# ==========================================
# ДВИЖОК БАЗЫ ДАННЫХ
# ==========================================
class DBManager:
    """
    Две независимые сущности:
      shifts     — мой день (работал / выходной / проспал, часы, приход, заметка);
      production — ночь производства (оператор, продукт и кг по каждому цеху).
    Производство можно вносить и за те ночи, когда меня на смене не было.
    """

    def __init__(self):
        # На Android рабочая директория недоступна для записи.
        # Flet передаёт путь к хранилищу приложения в FLET_APP_STORAGE_DATA.
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
                date TEXT PRIMARY KEY,
                hours REAL,
                status TEXT,
                arrival_status TEXT,
                note TEXT,
                premium_pay REAL
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS production (
                date TEXT PRIMARY KEY,
                operator TEXT,
                product1 TEXT,
                weight1 REAL,
                product2 TEXT,
                weight2 REAL
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
                event_time TEXT,
                event_type TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS app_config (
                id INTEGER PRIMARY KEY,
                hour_rate REAL,
                theme TEXT,
                bg_theme TEXT,
                op1 TEXT, op2 TEXT, op3 TEXT, op4 TEXT,
                pin_hash TEXT,
                pin_salt TEXT,
                tax_rate REAL,
                cycle_start TEXT,
                simple_bg INTEGER,
                norm_shop1 REAL,
                norm_shop2 REAL
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_timeline_date ON timeline(date)")
        self.conn.commit()

    def _ensure_columns(self, table, columns):
        cur = self.conn.cursor()
        existing = {r[1] for r in cur.execute(f"PRAGMA table_info({table})").fetchall()}
        for name, ddl in columns.items():
            if name not in existing:
                cur.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")

    def migrate(self):
        """Достраивает колонки в базах прежних версий."""
        self._ensure_columns("shifts", {
            "note": "TEXT",
            "premium_pay": "REAL",
        })
        self._ensure_columns("app_config", {
            "bg_theme": "TEXT",
            "pin_salt": "TEXT",
            "tax_rate": "REAL",
            "cycle_start": "TEXT",
            "simple_bg": "INTEGER",
            "norm_shop1": "REAL",
            "norm_shop2": "REAL",
        })
        self.conn.commit()

    def init_default_products(self):
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM products")
        if cur.fetchone()[0] == 0:
            cur.executemany("INSERT INTO products (name) VALUES (?)",
                            [("90",), ("90 ПВ",), ("200",), ("200 ПВ",),
                             ("500",), ("500 ПВ",), ("Предпомол",)])
            self.conn.commit()

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
        cfg["tax_rate"] = float(cfg["tax_rate"])
        cfg["norm_shop1"] = float(cfg["norm_shop1"])
        cfg["norm_shop2"] = float(cfg["norm_shop2"])
        cfg["simple_bg"] = int(cfg["simple_bg"] or 0)
        cfg.setdefault("pin_hash", None)
        cfg.setdefault("pin_salt", None)
        return cfg

    def save_config(self, **values):
        """Пишет только переданные и разрешённые поля — остальные не трогает."""
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
        """
        Поддерживает старый формат (голый sha256 без соли): при успешной
        проверке PIN молча пересохраняется в новом формате с солью.
        """
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
    SHIFT_FIELDS = "hours, status, arrival_status, note, premium_pay"

    @staticmethod
    def _row_to_shift(row):
        return {"hours": row[0], "status": row[1], "arrival_status": row[2],
                "note": row[3], "premium_pay": row[4]}

    def save_shift(self, date_str, hours, status, arrival_status,
                   note=None, premium_pay=None):
        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO shifts (date, hours, status, arrival_status, note, premium_pay)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                hours=excluded.hours,
                status=excluded.status,
                arrival_status=excluded.arrival_status,
                note=excluded.note,
                premium_pay=excluded.premium_pay
        """, (date_str, hours, status, arrival_status, note, premium_pay))
        self.conn.commit()

    def delete_shift(self, date_str):
        cur = self.conn.cursor()
        cur.execute("DELETE FROM shifts WHERE date=?", (date_str,))
        self.conn.commit()

    def delete_day(self, date_str):
        """Полная очистка дня: моя смена, производство и хронология."""
        cur = self.conn.cursor()
        cur.execute("DELETE FROM shifts WHERE date=?", (date_str,))
        cur.execute("DELETE FROM production WHERE date=?", (date_str,))
        cur.execute("DELETE FROM timeline WHERE date=?", (date_str,))
        self.conn.commit()

    def get_shift(self, date_str):
        """Один день — вместо загрузки всего месяца ради модалки."""
        cur = self.conn.cursor()
        cur.execute(f"SELECT {self.SHIFT_FIELDS} FROM shifts WHERE date=?", (date_str,))
        row = cur.fetchone()
        return self._row_to_shift(row) if row else None

    @staticmethod
    def _month_bounds(year, month):
        start = f"{year}-{month:02d}-01"
        end_year = year + 1 if month == 12 else year
        end_month = 1 if month == 12 else month + 1
        return start, f"{end_year}-{end_month:02d}-01"

    def _shifts_range(self, start, end):
        cur = self.conn.cursor()
        # Диапазон вместо LIKE — гарантированный range-scan по первичному ключу.
        cur.execute(f"SELECT date, {self.SHIFT_FIELDS} FROM shifts "
                    "WHERE date >= ? AND date < ?", (start, end))
        return {r[0]: self._row_to_shift(r[1:]) for r in cur.fetchall()}

    def get_month_shifts(self, year, month):
        start, end = self._month_bounds(year, month)
        return self._shifts_range(start, end)

    def get_year_shifts(self, year):
        return self._shifts_range(f"{year}-01-01", f"{year + 1}-01-01")

    # ==========================================
    # ПРОИЗВОДСТВО ЗА НОЧЬ
    # ==========================================
    PRODUCTION_FIELDS = "operator, product1, weight1, product2, weight2"

    @staticmethod
    def _row_to_production(row):
        return {"operator": row[0], "product1": row[1], "weight1": row[2],
                "product2": row[3], "weight2": row[4]}

    def save_production(self, date_str, operator, product1, weight1,
                        product2, weight2):
        """Если за ночь ничего не заполнено — запись удаляется, а не хранится пустой."""
        if not operator and weight1 is None and weight2 is None:
            self.delete_production(date_str)
            return
        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO production (date, operator, product1, weight1, product2, weight2)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                operator=excluded.operator,
                product1=excluded.product1,
                weight1=excluded.weight1,
                product2=excluded.product2,
                weight2=excluded.weight2
        """, (date_str, operator, product1, weight1, product2, weight2))
        self.conn.commit()

    def delete_production(self, date_str):
        cur = self.conn.cursor()
        cur.execute("DELETE FROM production WHERE date=?", (date_str,))
        self.conn.commit()

    def get_production(self, date_str):
        cur = self.conn.cursor()
        cur.execute(f"SELECT {self.PRODUCTION_FIELDS} FROM production WHERE date=?",
                    (date_str,))
        row = cur.fetchone()
        return self._row_to_production(row) if row else None

    def _production_range(self, start, end):
        cur = self.conn.cursor()
        cur.execute(f"SELECT date, {self.PRODUCTION_FIELDS} FROM production "
                    "WHERE date >= ? AND date < ?", (start, end))
        return {r[0]: self._row_to_production(r[1:]) for r in cur.fetchall()}

    def get_month_production(self, year, month):
        start, end = self._month_bounds(year, month)
        return self._production_range(start, end)

    def get_year_production(self, year):
        return self._production_range(f"{year}-01-01", f"{year + 1}-01-01")

    # ---------- выгрузка ----------
    def get_all_dates(self):
        """Все даты, по которым есть хоть что-то — для CSV-экспорта."""
        cur = self.conn.cursor()
        cur.execute("SELECT date FROM shifts UNION SELECT date FROM production "
                    "ORDER BY date")
        return [r[0] for r in cur.fetchall()]

    # ==========================================
    # НОЧНОЙ ТРЕКЕР
    # ==========================================
    def add_timeline_event(self, date_str, event_type, event_time):
        cur = self.conn.cursor()
        cur.execute("INSERT INTO timeline (date, event_time, event_type) VALUES (?, ?, ?)",
                    (date_str, event_time, event_type))
        self.conn.commit()
        return cur.lastrowid

    def add_timeline_bulk(self, date_str, events):
        cur = self.conn.cursor()
        cur.executemany("INSERT INTO timeline (date, event_time, event_type) VALUES (?, ?, ?)",
                        [(date_str, t, e) for t, e in events])
        self.conn.commit()

    def get_timeline(self, date_str):
        """Возвращает (id, время, тип) — id нужен для удаления события."""
        cur = self.conn.cursor()
        cur.execute("SELECT id, event_time, event_type FROM timeline "
                    "WHERE date=? ORDER BY id ASC", (date_str,))
        return cur.fetchall()

    def get_timeline_dates(self, year, month):
        """Даты месяца, где есть хотя бы одно событие трекера.
        Идёт по индексу idx_timeline_date, поэтому дешёвый."""
        start, end = self._month_bounds(year, month)
        cur = self.conn.cursor()
        cur.execute("SELECT DISTINCT date FROM timeline WHERE date >= ? AND date < ?",
                    (start, end))
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
        """Сортировка по числу в названии: 90, 90 ПВ, 200, 200 ПВ, 500, 500 ПВ."""
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
        """Сколько ночей ссылается на продукт — спрашиваем перед удалением."""
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
        shutil.copyfile(source_path, self.db_path)
        for suffix in ("-wal", "-shm"):
            stale = self.db_path + suffix
            if os.path.exists(stale):
                os.remove(stale)
        self.reconnect()


db = DBManager()

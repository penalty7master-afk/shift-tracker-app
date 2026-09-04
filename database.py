import hashlib
import os
import shutil
import sqlite3

from constants import (DEFAULT_ACCENT, DEFAULT_BG_THEME, DEFAULT_CYCLE_START,
                       DEFAULT_HOLIDAY_MULT, DEFAULT_TAX, WEIGHT_NORM)

PBKDF2_ROUNDS = 100_000

# Колонки app_config, которые разрешено писать через save_config()
CONFIG_WRITABLE = (
    "hour_rate", "theme", "bg_theme", "op1", "op2", "op3", "op4",
    "tax_rate", "cycle_start", "my_operator", "simple_bg", "holiday_mult",
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
    "my_operator": "",
    "simple_bg": 0,
    "holiday_mult": DEFAULT_HOLIDAY_MULT,
}


# ==========================================
# ДВИЖОК БАЗЫ ДАННЫХ
# ==========================================
class DBManager:
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
                product TEXT,
                weight REAL,
                arrival_status TEXT,
                operator TEXT,
                note TEXT,
                holiday INTEGER DEFAULT 0
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS products (
                name TEXT PRIMARY KEY,
                norm REAL
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
                my_operator TEXT,
                simple_bg INTEGER,
                holiday_mult REAL
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
        """Достраивает колонки в базах, созданных предыдущими версиями."""
        self._ensure_columns("shifts", {
            "operator": "TEXT",
            "note": "TEXT",
            "holiday": "INTEGER DEFAULT 0",
        })
        self._ensure_columns("products", {"norm": "REAL"})
        self._ensure_columns("app_config", {
            "bg_theme": "TEXT",
            "pin_salt": "TEXT",
            "tax_rate": "REAL",
            "cycle_start": "TEXT",
            "my_operator": "TEXT",
            "simple_bg": "INTEGER",
            "holiday_mult": "REAL",
        })
        cur = self.conn.cursor()
        cur.execute("UPDATE products SET norm=? WHERE norm IS NULL", (WEIGHT_NORM,))
        self.conn.commit()

    def init_default_products(self):
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM products")
        if cur.fetchone()[0] == 0:
            cur.executemany("INSERT INTO products (name, norm) VALUES (?, ?)",
                            [("Линия 3 (цех 2)", 2100.0),
                             ("Линии 1+2 (цех 1)", 5900.0)])
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
        cfg["holiday_mult"] = float(cfg["holiday_mult"])
        cfg["simple_bg"] = int(cfg["simple_bg"] or 0)
        cfg.setdefault("pin_hash", None)
        cfg.setdefault("pin_salt", None)
        cfg["product_norms"] = self.get_product_norms()
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

    # ---------- смены ----------
    def save_shift(self, date_str, hours, status, product, weight,
                   arrival_status, operator=None, note=None, holiday=0):
        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO shifts (date, hours, status, product, weight,
                                arrival_status, operator, note, holiday)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                hours=excluded.hours,
                status=excluded.status,
                product=excluded.product,
                weight=excluded.weight,
                arrival_status=excluded.arrival_status,
                operator=excluded.operator,
                note=excluded.note,
                holiday=excluded.holiday
        """, (date_str, hours, status, product, weight, arrival_status,
              operator, note, int(bool(holiday))))
        self.conn.commit()

    def save_shifts_bulk(self, rows):
        """Пакетная запись для автозаполнения месяца — один commit на все дни."""
        cur = self.conn.cursor()
        cur.executemany("""
            INSERT INTO shifts (date, hours, status, product, weight,
                                arrival_status, operator, note, holiday)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date) DO NOTHING
        """, rows)
        self.conn.commit()
        return cur.rowcount

    def delete_shift(self, date_str):
        cur = self.conn.cursor()
        cur.execute("DELETE FROM shifts WHERE date=?", (date_str,))
        cur.execute("DELETE FROM timeline WHERE date=?", (date_str,))
        self.conn.commit()

    @staticmethod
    def _row_to_shift(row):
        return {"hours": row[0], "status": row[1], "product": row[2],
                "weight": row[3], "arrival_status": row[4], "operator": row[5],
                "note": row[6], "holiday": bool(row[7])}

    SHIFT_FIELDS = "hours, status, product, weight, arrival_status, operator, note, holiday"

    def get_shift(self, date_str):
        """Один день — вместо загрузки всего месяца ради модалки."""
        cur = self.conn.cursor()
        cur.execute(f"SELECT {self.SHIFT_FIELDS} FROM shifts WHERE date=?", (date_str,))
        row = cur.fetchone()
        return self._row_to_shift(row) if row else None

    def _range_data(self, start, end):
        cur = self.conn.cursor()
        cur.execute(f"SELECT date, {self.SHIFT_FIELDS} FROM shifts "
                    "WHERE date >= ? AND date < ?", (start, end))
        return {r[0]: self._row_to_shift(r[1:]) for r in cur.fetchall()}

    @staticmethod
    def _month_bounds(year, month):
        start = f"{year}-{month:02d}-01"
        end_year = year + 1 if month == 12 else year
        end_month = 1 if month == 12 else month + 1
        return start, f"{end_year}-{end_month:02d}-01"

    def get_month_data(self, year, month):
        # Диапазон вместо LIKE — гарантированный range-scan по первичному ключу.
        start, end = self._month_bounds(year, month)
        return self._range_data(start, end)

    def get_year_data(self, year):
        return self._range_data(f"{year}-01-01", f"{year + 1}-01-01")

    def get_all_shifts(self):
        cur = self.conn.cursor()
        cur.execute(f"SELECT date, {self.SHIFT_FIELDS} FROM shifts ORDER BY date")
        return [(r[0], self._row_to_shift(r[1:])) for r in cur.fetchall()]

    # ---------- ночной трекер ----------
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

    def delete_timeline_event(self, event_id):
        cur = self.conn.cursor()
        cur.execute("DELETE FROM timeline WHERE id=?", (event_id,))
        self.conn.commit()

    def delete_timeline_events(self, event_ids):
        """Пакетное удаление — вызывается один раз по кнопке «Сохранить»."""
        if not event_ids:
            return
        cur = self.conn.cursor()
        cur.executemany("DELETE FROM timeline WHERE id=?",
                        [(event_id,) for event_id in event_ids])
        self.conn.commit()

    # ---------- продукция ----------
    def get_products(self):
        cur = self.conn.cursor()
        cur.execute("SELECT name, norm FROM products ORDER BY name")
        return [(r[0], float(r[1] or WEIGHT_NORM)) for r in cur.fetchall()]

    def get_product_names(self):
        return [name for name, _norm in self.get_products()]

    def get_product_norms(self):
        return {name: norm for name, norm in self.get_products()}

    def add_product(self, name, norm=WEIGHT_NORM):
        try:
            cur = self.conn.cursor()
            cur.execute("INSERT INTO products (name, norm) VALUES (?, ?)", (name, norm))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def update_product_norm(self, name, norm):
        cur = self.conn.cursor()
        cur.execute("UPDATE products SET norm=? WHERE name=?", (norm, name))
        self.conn.commit()

    def product_usage_count(self, name):
        """Сколько смен ссылается на продукт — спрашиваем перед удалением."""
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM shifts WHERE product=?", (name,))
        return cur.fetchone()[0]

    def delete_product(self, name):
        cur = self.conn.cursor()
        cur.execute("DELETE FROM products WHERE name=?", (name,))
        self.conn.commit()

    # ---------- бэкап ----------
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

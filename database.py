import sqlite3
import os
from datetime import datetime


# ==========================================
# ДВИЖОК БАЗЫ ДАННЫХ
# ==========================================
class DBManager:
    def __init__(self):
        # На Android рабочая директория недоступна для записи.
        # Flet передаёт путь к хранилищу приложения в FLET_APP_STORAGE_DATA.
        db_dir = os.getenv("FLET_APP_STORAGE_DATA") or "."
        os.makedirs(db_dir, exist_ok=True)
        db_path = os.path.join(db_dir, "shifts_pro.db")
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.create_tables()
        self.migrate()
        self.init_default_products()
        self.init_default_config()

    def create_tables(self):
        cursor = self.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS shifts (
                date TEXT PRIMARY KEY,
                hours REAL,
                status TEXT,
                product TEXT,
                weight REAL,
                arrival_status TEXT,
                operator TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS products (
                name TEXT PRIMARY KEY
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS timeline (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT,
                event_time TEXT,
                event_type TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS app_config (
                id INTEGER PRIMARY KEY,
                hour_rate REAL,
                theme TEXT,
                op1 TEXT, op2 TEXT, op3 TEXT, op4 TEXT,
                pin_hash TEXT
            )
        """)
        self.conn.commit()

    def migrate(self):
        """Добавляет новые колонки в уже созданные ранее БД."""
        cursor = self.conn.cursor()
        cols = [r[1] for r in cursor.execute("PRAGMA table_info(shifts)").fetchall()]
        if "operator" not in cols:
            cursor.execute("ALTER TABLE shifts ADD COLUMN operator TEXT")
            self.conn.commit()

    def init_default_products(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM products")
        if cursor.fetchone()[0] == 0:
            cursor.executemany("INSERT INTO products VALUES (?)",
                               [("Продукт 1",), ("Продукт 2",), ("Продукт 3",)])
            self.conn.commit()

    def init_default_config(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM app_config WHERE id=1")
        if cursor.fetchone()[0] == 0:
            cursor.execute("""
                INSERT INTO app_config (id, hour_rate, theme, op1, op2, op3, op4, pin_hash)
                VALUES (1, 632.0, 'Aurora Violet', 'Оператор 1', 'Оператор 2', 'Оператор 3', 'Оператор 4', NULL)
            """)
            self.conn.commit()

    def get_config(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT hour_rate, theme, op1, op2, op3, op4, pin_hash FROM app_config WHERE id=1")
        row = cursor.fetchone()
        return {
            "hour_rate": row[0] if row and row[0] is not None else 632.0,
            "theme": row[1] if row and row[1] else "Aurora Violet",
            "op1": row[2] if row and row[2] else "Оператор 1",
            "op2": row[3] if row and row[3] else "Оператор 2",
            "op3": row[4] if row and row[4] else "Оператор 3",
            "op4": row[5] if row and row[5] else "Оператор 4",
            "pin_hash": row[6] if row else None,
        }

    def save_config(self, hour_rate, theme, op1, op2, op3, op4):
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE app_config SET hour_rate=?, theme=?, op1=?, op2=?, op3=?, op4=? WHERE id=1
        """, (hour_rate, theme, op1, op2, op3, op4))
        self.conn.commit()

    def save_pin_hash(self, pin_hash):
        cursor = self.conn.cursor()
        cursor.execute("UPDATE app_config SET pin_hash=? WHERE id=1", (pin_hash,))
        self.conn.commit()

    def clear_pin_hash(self):
        self.save_pin_hash(None)

    def save_shift(self, date_str, hours, status, product, weight, arrival_status, operator=None):
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO shifts (date, hours, status, product, weight, arrival_status, operator)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                hours=excluded.hours,
                status=excluded.status,
                product=excluded.product,
                weight=excluded.weight,
                arrival_status=excluded.arrival_status,
                operator=excluded.operator
        """, (date_str, hours, status, product, weight, arrival_status, operator))
        self.conn.commit()

    def get_month_data(self, year, month):
        cursor = self.conn.cursor()
        prefix = f"{year}-{month:02d}%"
        cursor.execute("SELECT date, hours, status, product, weight, arrival_status, operator "
                       "FROM shifts WHERE date LIKE ?", (prefix,))
        rows = cursor.fetchall()
        return {r[0]: {"hours": r[1], "status": r[2], "product": r[3],
                       "weight": r[4], "arrival_status": r[5], "operator": r[6]} for r in rows}

    def add_timeline_event(self, date_str, event_type, event_time=None):
        cursor = self.conn.cursor()
        now_str = event_time or datetime.now().strftime("%H:%M:%S")
        cursor.execute("INSERT INTO timeline (date, event_time, event_type) VALUES (?, ?, ?)",
                       (date_str, now_str, event_type))
        self.conn.commit()

    def get_timeline(self, date_str):
        cursor = self.conn.cursor()
        cursor.execute("SELECT event_time, event_type FROM timeline WHERE date = ? ORDER BY id ASC", (date_str,))
        return cursor.fetchall()

    def get_products(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT name FROM products")
        return [r[0] for r in cursor.fetchall()]

    def add_product(self, name):
        try:
            cursor = self.conn.cursor()
            cursor.execute("INSERT INTO products VALUES (?)", (name,))
            self.conn.commit()
            return True
        except Exception:
            return False

    def delete_product(self, name):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM products WHERE name = ?", (name,))
        self.conn.commit()


db = DBManager()

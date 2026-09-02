import flet as ft
import sqlite3
import hashlib
from datetime import datetime
import calendar
import os

# ==========================================
# ДВИЖОК БАЗЫ ДАННЫХ
# ==========================================
class DBManager:
    def __init__(self):
        db_dir = os.getenv("FLET_APP_DATA_DIR", ".")
        db_path = os.path.join(db_dir, "shifts_pro.db")
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.create_tables()
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
                arrival_status TEXT
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

    def init_default_products(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM products")
        if cursor.fetchone()[0] == 0:
            cursor.executemany("INSERT INTO products VALUES (?)", [("Продукт 1",), ("Продукт 2",), ("Продукт 3",)])
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

    def save_shift(self, date_str, hours, status, product, weight, arrival_status):
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO shifts (date, hours, status, product, weight, arrival_status)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                hours=excluded.hours,
                status=excluded.status,
                product=excluded.product,
                weight=excluded.weight,
                arrival_status=excluded.arrival_status
        """, (date_str, hours, status, product, weight, arrival_status))
        self.conn.commit()

    def get_month_data(self, year, month):
        cursor = self.conn.cursor()
        prefix = f"{year}-{month:02d}%"
        cursor.execute("SELECT date, hours, status, product, weight, arrival_status FROM shifts WHERE date LIKE ?", (prefix,))
        rows = cursor.fetchall()
        return {r[0]: {"hours": r[1], "status": r[2], "product": r[3], "weight": r[4], "arrival_status": r[5]} for r in rows}

    def add_timeline_event(self, date_str, event_type):
        cursor = self.conn.cursor()
        now_str = datetime.now().strftime("%H:%M:%S")
        cursor.execute("INSERT INTO timeline (date, event_time, event_type) VALUES (?, ?, ?)", (date_str, now_str, event_type))
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

THEME_ACCENTS = {
    "Aurora Violet": "#c9a6ff",
    "Midnight Blue": "#7dd3fc",
    "Emerald Mint": "#6ee7b7",
}

ARRIVAL_OPTIONS = ["До 20:00", "Буфер (до 20:15)", "Опоздание (до 20:30)"]


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


# ==========================================
# ИНТЕРФЕЙС ПРИЛОЖЕНИЯ (iOS 26 Liquid Glass)
# ==========================================
def main(page: ft.Page):
    page.title = "КАЛЕНДАРЬ СМЕН PRO"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 0
    page.bgcolor = "#0b0818"

    current_date = datetime.now()
    config = db.get_config()

    def accent():
        return THEME_ACCENTS.get(config["theme"], THEME_ACCENTS["Aurora Violet"])

    def op_names():
        return [config["op1"], config["op2"], config["op3"], config["op4"]]

    # ---------- фон: градиент + светящиеся сферы + реальный блюр стекла ----------
    def glowing_background():
        return ft.Stack(
            expand=True,
            controls=[
                ft.Container(
                    expand=True,
                    gradient=ft.LinearGradient(
                        begin=ft.Alignment.TOP_LEFT, end=ft.Alignment.BOTTOM_RIGHT,
                        colors=["#150e34", "#241a5c", "#123a66"]
                    ),
                ),
                ft.Container(
                    width=260, height=260, border_radius=260, top=-40, left=-60,
                    bgcolor="#6693c5fd", blur=ft.Blur(70, 70),
                ),
                ft.Container(
                    width=300, height=300, border_radius=300, top=120, right=-80,
                    bgcolor="#55c9a6ff", blur=ft.Blur(80, 80),
                ),
                ft.Container(
                    width=260, height=260, border_radius=260, bottom=-40, left=60,
                    bgcolor="#556ee7b7", blur=ft.Blur(75, 75),
                ),
            ],
        )

    def glass_card(content_column, **extra):
        params = dict(
            content=content_column,
            bgcolor="#1affffff",
            border=ft.border.all(1, "#26ffffff"),
            border_radius=18,
            blur=ft.Blur(24, 24),
            padding=16,
        )
        params.update(extra)
        return ft.Container(**params)

    # ---------- корневой контейнер, который переключает экраны ----------
    root = ft.Container(expand=True)

    # ======================================================
    # PIN-ЭКРАН
    # ======================================================
    pin_mode = {"value": "verify", "first_pin": None}

    pin_title = ft.Text("Введите PIN-код", size=20, weight=ft.FontWeight.BOLD, color=accent())
    pin_hint = ft.Text("", size=12, color="rgba(255,255,255,0.6)")
    pin_field = ft.TextField(
        password=True, can_reveal_password=False, keyboard_type=ft.KeyboardType.NUMBER,
        max_length=6, text_align=ft.TextAlign.CENTER, width=200, autofocus=True,
        border_color="#33ffffff", bgcolor="#14ffffff", color="white",
    )
    pin_error = ft.Text("", color="#fca5a5", size=12)

    def hash_pin(pin):
        return hashlib.sha256(pin.encode("utf-8")).hexdigest()

    def show_pin_screen():
        cfg = db.get_config()
        config["pin_hash"] = cfg["pin_hash"]
        pin_field.value = ""
        pin_error.value = ""
        if cfg["pin_hash"]:
            pin_mode["value"] = "verify"
            pin_title.value = "Введите PIN-код"
            pin_hint.value = ""
        else:
            pin_mode["value"] = "setup_new"
            pin_mode["first_pin"] = None
            pin_title.value = "Придумайте PIN-код"
            pin_hint.value = "От 4 до 6 цифр"
        root.content = pin_view
        page.navigation_bar = None
        page.update()

    def on_pin_confirm(e):
        pin = (pin_field.value or "").strip()
        if len(pin) < 4:
            pin_error.value = "Минимум 4 цифры"
            page.update()
            return

        mode = pin_mode["value"]
        if mode == "verify":
            cfg = db.get_config()
            if hash_pin(pin) == cfg["pin_hash"]:
                show_main_screen()
            else:
                pin_error.value = "Неверный PIN-код"
                pin_field.value = ""
                page.update()
        elif mode == "setup_new":
            pin_mode["first_pin"] = pin
            pin_mode["value"] = "setup_confirm"
            pin_title.value = "Повторите PIN-код"
            pin_hint.value = ""
            pin_field.value = ""
            pin_error.value = ""
            page.update()
        elif mode == "setup_confirm":
            if pin == pin_mode["first_pin"]:
                db.save_pin_hash(hash_pin(pin))
                show_main_screen()
            else:
                pin_error.value = "PIN-коды не совпадают, попробуйте снова"
                pin_mode["value"] = "setup_new"
                pin_mode["first_pin"] = None
                pin_title.value = "Придумайте PIN-код"
                pin_hint.value = "От 4 до 6 цифр"
                pin_field.value = ""
                page.update()

    pin_view = ft.Stack(
        expand=True,
        controls=[
            glowing_background(),
            ft.Container(
                alignment=ft.alignment.center,
                expand=True,
                content=glass_card(
                    ft.Column(
                        [
                            pin_title, pin_hint, pin_field, pin_error,
                            ft.ElevatedButton("Подтвердить", on_click=on_pin_confirm, width=200),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=14
                    ),
                    width=320,
                ),
            ),
        ],
    )

    # ======================================================
    # ГЛАВНЫЙ ДАШБОРД / КАЛЕНДАРЬ
    # ======================================================
    salary_text = ft.Text("0 ₽", size=32, weight=ft.FontWeight.BOLD, color="white")
    stats_subtext = ft.Text("", size=12, color="rgba(255,255,255,0.7)")

    def update_global_dashboard():
        calc = calculate_salary_and_premium(current_date.year, current_date.month, config["hour_rate"])
        salary_text.value = f"{int(calc['total_salary']):,} ₽".replace(",", " ")
        stats_subtext.value = (f"Часы: {calc['total_hours']} ч | Премия: {int(calc['premium_money'])} ₽ "
                                f"({calc['effective_smen']} реальных см)")
        page.update()

    grid_container = ft.Column()

    def build_calendar_grid():
        grid_container.controls.clear()
        days_header = ft.Row([
            ft.Container(ft.Text(d, color="rgba(255,255,255,0.5)", size=12, weight=ft.FontWeight.BOLD),
                         expand=1, alignment=ft.alignment.center)
            for d in ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
        ], spacing=5)
        grid_container.controls.append(days_header)

        year, month = current_date.year, current_date.month
        cal = calendar.Calendar(firstweekday=0)
        month_days = cal.monthdayscalendar(year, month)
        month_data = db.get_month_data(year, month)

        for week in month_days:
            row_days = []
            for day in week:
                if day == 0:
                    row_days.append(ft.Container(expand=1))
                else:
                    d_obj = datetime(year, month, day).date()
                    d_str = d_obj.strftime("%Y-%m-%d")
                    op_name = get_operator_for_date(d_obj, op_names())

                    bg_color = "transparent"
                    border_color = "rgba(255,255,255,0.14)"

                    if d_str in month_data:
                        status = month_data[d_str]["status"]
                        if status == "Рабочая смена":
                            bg_color = "rgba(255, 255, 255, 0.10)"
                        elif status == "Выходной для премии":
                            bg_color = "rgba(76, 175, 80, 0.25)"
                            border_color = "rgba(76, 175, 80, 0.6)"
                        elif status == "Обычный выходной":
                            bg_color = "rgba(33, 150, 243, 0.25)"
                            border_color = "rgba(33, 150, 243, 0.6)"
                        elif status == "Проспал":
                            bg_color = "rgba(244, 67, 54, 0.3)"
                            border_color = "rgba(244, 67, 54, 0.7)"

                    def on_day_click(e, sel_date=d_obj):
                        show_day_details_modal(sel_date)

                    cell = ft.Container(
                        content=ft.Column([
                            ft.Text(str(day), size=14, weight=ft.FontWeight.BOLD, color="white"),
                            ft.Text(op_name.split()[-1], size=9, color="rgba(255,255,255,0.45)")
                        ], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=1),
                        expand=1, height=52, bgcolor=bg_color,
                        border=ft.border.all(1, border_color), border_radius=10,
                        on_click=on_day_click
                    )
                    row_days.append(cell)
            grid_container.controls.append(ft.Row(row_days, spacing=5))
        page.update()

    def show_day_details_modal(date_obj):
        date_str = date_obj.strftime("%Y-%m-%d")
        month_data = db.get_month_data(date_obj.year, date_obj.month)
        current_shift = month_data.get(date_str, {
            "hours": 11.0, "status": "Рабочая смена", "product": "Продукт 1",
            "weight": 2100.0, "arrival_status": ARRIVAL_OPTIONS[0]
        })

        status_dropdown = ft.Dropdown(
            label="Статус дня", value=current_shift["status"],
            options=[ft.dropdown.Option("Рабочая смена"), ft.dropdown.Option("Выходной для премии"),
                     ft.dropdown.Option("Обычный выходной"), ft.dropdown.Option("Проспал")]
        )

        hours_slider = ft.Slider(min=0, max=11, divisions=22, value=current_shift["hours"] or 11.0, label="{value} ч")

        try:
            arrival_index = ARRIVAL_OPTIONS.index(current_shift.get("arrival_status") or ARRIVAL_OPTIONS[0])
        except ValueError:
            arrival_index = 0

        def on_arrival_change(e):
            hours_slider.value = hours_for_arrival(ARRIVAL_OPTIONS[arrival_seg.selected_index])
            page.update()

        arrival_seg = ft.CupertinoSlidingSegmentedButton(
            selected_index=arrival_index,
            thumb_color=accent(),
            on_change=on_arrival_change,
            controls=[ft.Text(opt, size=11) for opt in ARRIVAL_OPTIONS],
        )

        weight_input = ft.TextField(label="Выработка продукции (кг)", value=str(current_shift.get("weight", 2100.0)),
                                     keyboard_type=ft.KeyboardType.NUMBER)
        product_dropdown = ft.Dropdown(label="Тип продукта", value=current_shift.get("product"),
                                        options=[ft.dropdown.Option(p) for p in db.get_products()])

        timeline_list = ft.Column()
        for t_time, t_type in db.get_timeline(date_str):
            timeline_list.controls.append(ft.Text(f"• {t_time} -> {t_type}", color="white", size=12))

        def add_event(e, etype):
            db.add_timeline_event(date_str, etype)
            timeline_list.controls.append(ft.Text(f"• {datetime.now().strftime('%H:%M:%S')} -> {etype}",
                                                    color="white", size=12))
            page.update()

        def save_and_close(e):
            arrival_value = ARRIVAL_OPTIONS[arrival_seg.selected_index]
            db.save_shift(date_str, float(hours_slider.value), status_dropdown.value,
                          product_dropdown.value, float(weight_input.value or 0), arrival_value)
            update_global_dashboard()
            build_calendar_grid()
            refresh_analytics_tab()
            page.close(dialog)

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"Смена: {date_obj.strftime('%d.%m.%Y')}", color="white"),
            content=ft.Container(
                content=ft.Column([
                    status_dropdown,
                    ft.Text("Время прибытия:", size=11, color="rgba(255,255,255,0.6)"),
                    arrival_seg,
                    ft.Text("Корректировка часов (ручная):", size=11, color="rgba(255,255,255,0.6)"),
                    hours_slider, product_dropdown, weight_input, ft.Divider(),
                    ft.Text("Трекер ночи (хронология):", size=12, weight=ft.FontWeight.BOLD),
                    ft.Row([
                        ft.ElevatedButton("+ Перекур", on_click=lambda e: add_event(e, "Перекур")),
                        ft.ElevatedButton("▶ Работа", on_click=lambda e: add_event(e, "Работа")),
                    ]), timeline_list
                ], scroll=ft.ScrollMode.ALWAYS, spacing=10), width=400, height=520
            ),
            actions=[
                ft.TextButton("Отмена", on_click=lambda e: page.close(dialog)),
                ft.TextButton("Сохранить", on_click=save_and_close),
            ]
        )
        page.open(dialog)

    chart_arrival = ft.PieChart(sections=[], sections_space=2, center_space_radius=20, expand=True)
    chart_weight = ft.PieChart(sections=[], sections_space=2, center_space_radius=20, expand=True)

    def refresh_analytics_tab():
        month_data = db.get_month_data(current_date.year, current_date.month)
        vv, bf, op = 0, 0, 0
        norm_ok, norm_fail = 0, 0

        for shift in month_data.values():
            if shift["status"] == "Рабочая смена":
                astat = shift.get("arrival_status") or ARRIVAL_OPTIONS[0]
                if astat == ARRIVAL_OPTIONS[0]:
                    vv += 1
                elif astat == ARRIVAL_OPTIONS[1]:
                    bf += 1
                elif astat == ARRIVAL_OPTIONS[2]:
                    op += 1

                if (shift.get("weight") or 0) >= 2100.0:
                    norm_ok += 1
                else:
                    norm_fail += 1

        total_arr = vv + bf + op
        if total_arr > 0:
            chart_arrival.sections = [
                ft.PieChartSection(vv, color="green", title=f"В-{int(vv/total_arr*100)}%", radius=20),
                ft.PieChartSection(bf, color="orange", title=f"Б-{int(bf/total_arr*100)}%", radius=20),
                ft.PieChartSection(op, color="red", title=f"О-{int(op/total_arr*100)}%", radius=20),
            ]
        else:
            chart_arrival.sections = [ft.PieChartSection(1, color="grey", title="Нет данных", radius=20)]

        total_w = norm_ok + norm_fail
        if total_w > 0:
            chart_weight.sections = [
                ft.PieChartSection(norm_ok, color="green", title=f"Норма-{int(norm_ok/total_w*100)}%", radius=20),
                ft.PieChartSection(norm_fail, color="red", title=f"Недо-{int(norm_fail/total_w*100)}%", radius=20),
            ]
        else:
            chart_weight.sections = [ft.PieChartSection(1, color="grey", title="Нет данных", radius=20)]
        page.update()

    calendar_view = ft.Column([glass_card(grid_container)])

    analytics_view = ft.Column([
        ft.Text("ДИАГРАММЫ АНАЛИТИКИ ЗА МЕСЯЦ", size=14, weight=ft.FontWeight.BOLD, color="white"),
        glass_card(ft.Column([
            ft.Text("1. Время прибытия (вовремя / буфер / опоздание):", size=11, color="rgba(255,255,255,0.8)"),
            ft.Container(chart_arrival, height=120, alignment=ft.alignment.center),
            ft.Text("2. Выработка продукции (норма 2100 кг / недовыработка):", size=11, color="rgba(255,255,255,0.8)"),
            ft.Container(chart_weight, height=120, alignment=ft.alignment.center),
        ])),
    ], scroll=ft.ScrollMode.ALWAYS, expand=True)

    tabs_content = ft.Container(content=calendar_view, expand=True)

    def on_tab_change(e):
        if e.control.selected_index == 0:
            tabs_content.content = calendar_view
        else:
            tabs_content.content = analytics_view
            refresh_analytics_tab()
        page.update()

    nav_bar = ft.NavigationBar(
        destinations=[
            ft.NavigationBarDestination(icon=ft.Icons.CALENDAR_MONTH, label="Календарь"),
            ft.NavigationBarDestination(icon=ft.Icons.BAR_CHART, label="Аналитика"),
        ],
        selected_index=0,
        on_change=on_tab_change,
        bgcolor="rgba(20, 15, 38, 0.95)"
    )

    def go_to_settings(e):
        show_settings_screen()

    settings_button = ft.IconButton(icon=ft.Icons.SETTINGS, icon_color="white", on_click=go_to_settings)

    main_layout = ft.Stack(
        expand=True,
        controls=[
            glowing_background(),
            ft.Container(
                expand=True, padding=10,
                content=ft.Column([
                    ft.SafeArea(
                        content=glass_card(
                            ft.Row([
                                ft.Column([
                                    ft.Text("КАЛЕНДАРЬ СМЕН PRO", size=12, color="rgba(255,255,255,0.5)"),
                                    salary_text, stats_subtext
                                ], spacing=1, expand=True),
                                settings_button,
                            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, vertical_alignment=ft.CrossAxisAlignment.START),
                        )
                    ),
                    tabs_content
                ], expand=True, spacing=10)
            ),
        ],
    )

    def show_main_screen():
        root.content = main_layout
        page.navigation_bar = nav_bar
        build_calendar_grid()
        update_global_dashboard()
        page.update()

    # ======================================================
    # ЭКРАН НАСТРОЕК (ставка, операторы, тема, PIN, продукция)
    # ======================================================
    rate_field = ft.TextField(label="Стоимость 1 часа оклада (₽)", keyboard_type=ft.KeyboardType.NUMBER,
                               bgcolor="#14ffffff", color="white", border_color="#33ffffff")
    op1_field = ft.TextField(label="Оператор 1", bgcolor="#14ffffff", color="white", border_color="#33ffffff")
    op2_field = ft.TextField(label="Оператор 2", bgcolor="#14ffffff", color="white", border_color="#33ffffff")
    op3_field = ft.TextField(label="Оператор 3", bgcolor="#14ffffff", color="white", border_color="#33ffffff")
    op4_field = ft.TextField(label="Оператор 4", bgcolor="#14ffffff", color="white", border_color="#33ffffff")
    theme_dropdown = ft.Dropdown(
        label="Акцентный цвет",
        options=[ft.dropdown.Option(name) for name in THEME_ACCENTS.keys()]
    )
    settings_error = ft.Text("", color="#fca5a5", size=12)

    new_product_input = ft.TextField(label="Название нового продукта", expand=True,
                                      bgcolor="#14ffffff", color="white", border_color="#33ffffff")
    products_list_view = ft.Column()

    def refresh_products_list():
        products_list_view.controls.clear()
        for p in db.get_products():
            def delete_click(e, p_name=p):
                db.delete_product(p_name)
                refresh_products_list()
                page.update()
            products_list_view.controls.append(
                ft.Row([
                    ft.Text(p, color="white", expand=True),
                    ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_color="#fca5a5", on_click=delete_click)
                ])
            )

    def add_product_click(e):
        if new_product_input.value and new_product_input.value.strip():
            db.add_product(new_product_input.value.strip())
            new_product_input.value = ""
            refresh_products_list()
            page.update()

    def open_settings_fields():
        cfg = db.get_config()
        rate_field.value = str(cfg["hour_rate"])
        op1_field.value = cfg["op1"]
        op2_field.value = cfg["op2"]
        op3_field.value = cfg["op3"]
        op4_field.value = cfg["op4"]
        theme_dropdown.value = cfg["theme"]
        settings_error.value = ""
        refresh_products_list()

    def save_settings_click(e):
        try:
            new_rate = float((rate_field.value or "632").replace(",", "."))
        except Exception:
            settings_error.value = "Некорректная ставка"
            page.update()
            return
        db.save_config(
            new_rate, theme_dropdown.value or "Aurora Violet",
            op1_field.value or "Оператор 1", op2_field.value or "Оператор 2",
            op3_field.value or "Оператор 3", op4_field.value or "Оператор 4",
        )
        config.update(db.get_config())
        pin_title.color = accent()
        show_main_screen()

    def change_pin_click(e):
        db.clear_pin_hash()
        show_pin_screen()

    def back_to_main_click(e):
        show_main_screen()

    settings_view = ft.Stack(
        expand=True,
        controls=[
            glowing_background(),
            ft.Container(
                expand=True, padding=14,
                content=ft.Column([
                    ft.Row([
                        ft.IconButton(icon=ft.Icons.ARROW_BACK, icon_color="white", on_click=back_to_main_click),
                        ft.Text("Настройки", size=18, weight=ft.FontWeight.BOLD, color="white"),
                    ]),
                    glass_card(ft.Column([rate_field], spacing=6)),
                    glass_card(ft.Column([
                        ft.Text("Имена четырёх сменных операторов", size=12, color="rgba(255,255,255,0.75)"),
                        ft.Row([op1_field, op2_field]),
                        ft.Row([op3_field, op4_field]),
                    ], spacing=6)),
                    glass_card(ft.Column([theme_dropdown], spacing=6)),
                    glass_card(ft.Column([
                        ft.Text("Каталог продукции", size=12, color="rgba(255,255,255,0.75)"),
                        ft.Row([new_product_input, ft.FloatingActionButton(icon=ft.Icons.ADD, on_click=add_product_click, mini=True)]),
                        ft.Divider(),
                        products_list_view,
                    ], spacing=6)),
                    settings_error,
                    ft.OutlinedButton("Сменить PIN-код", on_click=change_pin_click, width=300),
                    ft.ElevatedButton("Сохранить", on_click=save_settings_click, width=300),
                ], scroll=ft.ScrollMode.ALWAYS, spacing=14)
            ),
        ],
    )

    def show_settings_screen():
        open_settings_fields()
        root.content = settings_view
        page.navigation_bar = None
        page.update()

    # ---------- старт ----------
    page.add(root)
    show_pin_screen()


ft.run(main)


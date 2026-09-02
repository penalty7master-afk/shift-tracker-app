import flet as ft
import flet_charts as fch
import hashlib
from datetime import datetime
import calendar

from constants import (THEME_ACCENTS, THEME_BACKGROUNDS, DEFAULT_BG_THEME,
                       ARRIVAL_OPTIONS, ARRIVAL_LABELS, MONTH_NAMES, WEIGHT_NORM)
from database import db
from calculations import calculate_salary_and_premium, get_operator_for_date, hours_for_arrival


# ==========================================
# ИНТЕРФЕЙС ПРИЛОЖЕНИЯ (iOS 26 Liquid Glass)
# ==========================================
def main(page: ft.Page):
    page.title = "КАЛЕНДАРЬ СМЕН PRO"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 0
    page.bgcolor = "#0b0818"

    _now = datetime.now()
    # Просматриваемый месяц (переключается стрелками, не привязан к дате запуска)
    view = {"year": _now.year, "month": _now.month}
    config = db.get_config()

    def bind_event(control, handler, *names):
        """Имена событий отличаются между версиями Flet — привязываем безопасно."""
        for attr in names:
            if hasattr(control, attr):
                setattr(control, attr, handler)
                return True
        return False

    def accent():
        return THEME_ACCENTS.get(config["theme"], THEME_ACCENTS["Aurora Violet"])

    def accent_a(alpha_hex):
        """Акцент с заданной прозрачностью: accent_a('40') -> '#40c9a6ff'."""
        return f"#{alpha_hex}{accent().lstrip('#')}"

    def bg_palette():
        return THEME_BACKGROUNDS.get(config.get("bg_theme"), THEME_BACKGROUNDS[DEFAULT_BG_THEME])

    def sphere_colors():
        pal = bg_palette()
        if pal["spheres"]:
            return pal["spheres"]
        return [accent_a(a) for a in pal["sphere_alpha"]]

    def op_names():
        return [config["op1"], config["op2"], config["op3"], config["op4"]]

    def short_op(name):
        parts = (name or "").split()
        return parts[-1] if parts else "—"

    def sync_value(e):
        # Flet не всегда пишет ввод в .value до потери фокуса — синхронизируем вручную
        e.control.value = e.data

    # Ссылки на созданные фоны и стеклянные карточки — нужны для смены темы «на лету»
    _backgrounds = []
    _glass_cards = []

    # ---------- фон: градиент + светящиеся сферы + реальный блюр стекла ----------
    def glowing_background():
        pal = bg_palette()
        sph = sphere_colors()
        base = ft.Container(
            expand=True,
            gradient=ft.LinearGradient(
                begin=ft.Alignment.TOP_LEFT, end=ft.Alignment.BOTTOM_RIGHT,
                colors=list(pal["gradient"])
            ),
        )
        s1 = ft.Container(width=260, height=260, border_radius=260, top=-40, left=-60,
                          bgcolor=sph[0], blur=ft.Blur(70, 70))
        s2 = ft.Container(width=300, height=300, border_radius=300, top=120, right=-80,
                          bgcolor=sph[1], blur=ft.Blur(80, 80))
        s3 = ft.Container(width=260, height=260, border_radius=260, bottom=-40, left=60,
                          bgcolor=sph[2], blur=ft.Blur(75, 75))
        _backgrounds.append((base, s1, s2, s3))
        return ft.Stack(expand=True, controls=[base, s1, s2, s3])

    def glass_card(content_column, **extra):
        pal = bg_palette()
        params = dict(
            content=content_column,
            bgcolor=pal["glass"],
            border=ft.Border.all(1, pal["glass_border"]),
            border_radius=18,
            blur=ft.Blur(24, 24),
            padding=16,
        )
        params.update(extra)
        card = ft.Container(**params)
        _glass_cards.append(card)
        return card

    # ---------- совместимость API диалогов (Flet 0.86 vs старые версии) ----------
    def open_dialog(dlg):
        if hasattr(page, "show_dialog"):
            page.show_dialog(dlg)
        elif hasattr(page, "open"):
            page.open(dlg)
        else:
            page.dialog = dlg
            dlg.open = True
            page.update()

    def close_dialog(dlg):
        if hasattr(page, "pop_dialog"):
            page.pop_dialog()
        elif hasattr(page, "close"):
            page.close(dlg)
        else:
            dlg.open = False
            page.update()

    # ---------- корневой контейнер, который переключает экраны ----------
    root = ft.Container(expand=True)

    # ======================================================
    # PIN-ЭКРАН
    # ======================================================
    pin_mode = {"value": "verify", "first_pin": None}

    pin_title = ft.Text("Введите PIN-код", size=20, weight=ft.FontWeight.BOLD, color=accent())
    pin_hint = ft.Text("", size=12, color="#99ffffff")
    pin_field = ft.TextField(
        password=True, can_reveal_password=False, keyboard_type=ft.KeyboardType.NUMBER,
        max_length=6, text_align=ft.TextAlign.CENTER, width=200, autofocus=True,
        border_color="#33ffffff", bgcolor="#14ffffff", color="white",
    )
    pin_field.on_change = sync_value
    pin_error = ft.Text("", color="#fca5a5", size=12)

    def hash_pin(pin):
        return hashlib.sha256(pin.encode("utf-8")).hexdigest()

    def show_pin_screen(force_setup=False):
        cfg = db.get_config()
        config["pin_hash"] = cfg["pin_hash"]
        apply_accent()
        pin_field.value = ""
        pin_error.value = ""
        if cfg["pin_hash"] and not force_setup:
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
        if not pin.isdigit():
            pin_error.value = "Только цифры"
            page.update()
            return
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
                # Старый хеш перезаписывается только здесь — до этого момента
                # приложение остаётся защищённым прежним PIN-кодом.
                db.save_pin_hash(hash_pin(pin))
                config["pin_hash"] = hash_pin(pin)
                show_main_screen()
            else:
                pin_error.value = "PIN-коды не совпадают, попробуйте снова"
                pin_mode["value"] = "setup_new"
                pin_mode["first_pin"] = None
                pin_title.value = "Придумайте PIN-код"
                pin_hint.value = "От 4 до 6 цифр"
                pin_field.value = ""
                page.update()

    pin_field.on_submit = on_pin_confirm

    pin_view = ft.Stack(
        expand=True,
        controls=[
            glowing_background(),
            ft.Container(
                alignment=ft.Alignment.CENTER,
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
    stats_subtext = ft.Text("", size=12, color="#b3ffffff")
    month_label = ft.Text("", size=14, weight=ft.FontWeight.BOLD, color="white")

    def update_global_dashboard():
        calc = calculate_salary_and_premium(view["year"], view["month"], config["hour_rate"])
        salary_text.value = f"{int(calc['total_salary']):,} ₽".replace(",", " ")
        stats_subtext.value = (f"Часы: {calc['total_hours']} ч | Премия: {int(calc['premium_money'])} ₽ "
                                f"({calc['effective_smen']} реальных см)")
        month_label.value = f"{MONTH_NAMES[view['month'] - 1]} {view['year']}"
        page.update()

    grid_container = ft.Column()

    def build_calendar_grid():
        grid_container.controls.clear()
        days_header = ft.Row([
            ft.Container(ft.Text(d, color="#80ffffff", size=12, weight=ft.FontWeight.BOLD),
                         expand=1, alignment=ft.Alignment.CENTER)
            for d in ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
        ], spacing=5)
        grid_container.controls.append(days_header)

        year, month = view["year"], view["month"]
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
                    saved = month_data.get(d_str)
                    # ручная подмена оператора приоритетнее графика 4/4
                    op_name = (saved or {}).get("operator") or get_operator_for_date(d_obj, op_names())

                    bg_color = "transparent"
                    border_color = "#24ffffff"

                    if saved:
                        status = saved["status"]
                        if status == "Рабочая смена":
                            bg_color = accent_a("26")
                            border_color = accent_a("99")
                        elif status == "Выходной для премии":
                            bg_color = "#404caf50"
                            border_color = "#994caf50"
                        elif status == "Обычный выходной":
                            bg_color = "#402196f3"
                            border_color = "#992196f3"
                        elif status == "Проспал":
                            bg_color = "#4df44336"
                            border_color = "#b3f44336"

                    def on_day_click(e, sel_date=d_obj):
                        show_day_details_modal(sel_date)

                    cell = ft.Container(
                        content=ft.Column([
                            ft.Text(str(day), size=14, weight=ft.FontWeight.BOLD, color="white"),
                            ft.Text(short_op(op_name), size=9, color="#73ffffff")
                        ], alignment=ft.MainAxisAlignment.CENTER,
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=1),
                        expand=1, height=52, bgcolor=bg_color,
                        border=ft.Border.all(1, border_color), border_radius=10,
                        on_click=on_day_click
                    )
                    row_days.append(cell)
            grid_container.controls.append(ft.Row(row_days, spacing=5))
        page.update()

    def show_day_details_modal(date_obj):
        date_str = date_obj.strftime("%Y-%m-%d")
        month_data = db.get_month_data(date_obj.year, date_obj.month)
        default_op = get_operator_for_date(date_obj, op_names())
        current_shift = month_data.get(date_str, {
            "hours": 11.0, "status": "Рабочая смена", "product": "Продукт 1",
            "weight": WEIGHT_NORM, "arrival_status": ARRIVAL_OPTIONS[0], "operator": None
        })

        status_dropdown = ft.Dropdown(
            label="Статус дня", value=current_shift["status"],
            options=[ft.dropdown.Option("Рабочая смена"), ft.dropdown.Option("Выходной для премии"),
                     ft.dropdown.Option("Обычный выходной"), ft.dropdown.Option("Проспал")]
        )

        ops = op_names()
        saved_op = current_shift.get("operator") or default_op
        if saved_op not in ops:
            saved_op = default_op
        operator_dropdown = ft.Dropdown(
            label="Оператор смены (подмена)", value=saved_op,
            options=[ft.dropdown.Option(o) for o in ops]
        )

        # 0 часов — валидное значение, поэтому проверяем именно на None
        raw_hours = current_shift.get("hours")
        hours_slider = ft.Slider(
            min=0, max=11, divisions=22,
            value=11.0 if raw_hours is None else float(raw_hours),
            label="{value} ч"
        )

        try:
            arrival_index = ARRIVAL_OPTIONS.index(current_shift.get("arrival_status") or ARRIVAL_OPTIONS[0])
        except ValueError:
            arrival_index = 0

        def arrival_label(idx):
            title, sub = ARRIVAL_LABELS[idx]
            return ft.Container(
                width=92,
                alignment=ft.Alignment.CENTER,
                padding=ft.Padding.symmetric(vertical=4, horizontal=2),
                content=ft.Column([
                    ft.Text(title, size=11, color="white", text_align=ft.TextAlign.CENTER),
                    ft.Text(sub, size=9, color="#b3ffffff", text_align=ft.TextAlign.CENTER),
                ], spacing=0, tight=True,
                    alignment=ft.MainAxisAlignment.CENTER,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            )

        def on_arrival_change(e):
            # свойство selected_index может быть ещё не синхронизировано — берём из события
            try:
                idx = int(e.data)
            except (TypeError, ValueError):
                idx = arrival_seg.selected_index or 0
            arrival_seg.selected_index = idx
            hours_slider.value = hours_for_arrival(ARRIVAL_OPTIONS[idx])
            page.update()

        arrival_seg = ft.CupertinoSlidingSegmentedButton(
            selected_index=arrival_index,
            thumb_color=accent(),
            on_change=on_arrival_change,
            controls=[arrival_label(i) for i in range(len(ARRIVAL_OPTIONS))],
        )

        weight_input = ft.TextField(label="Выработка продукции (кг)",
                                     value=str(current_shift.get("weight", WEIGHT_NORM)),
                                     keyboard_type=ft.KeyboardType.NUMBER)
        weight_input.on_change = sync_value

        products = db.get_products()
        saved_product = current_shift.get("product")
        if saved_product not in products:
            saved_product = products[0] if products else None
        product_dropdown = ft.Dropdown(label="Тип продукта", value=saved_product,
                                        options=[ft.dropdown.Option(p) for p in products])

        # События трекера копятся в памяти и попадают в БД только по "Сохранить"
        saved_events = list(db.get_timeline(date_str))
        pending_events = []
        timeline_list = ft.Column(spacing=2)

        def refresh_timeline():
            timeline_list.controls = [
                ft.Text(f"• {t_time} -> {t_type}", color="white", size=12)
                for t_time, t_type in saved_events + pending_events
            ]

        refresh_timeline()

        def add_event(e, etype):
            pending_events.append((datetime.now().strftime("%H:%M:%S"), etype))
            refresh_timeline()
            page.update()

        def save_and_close(e):
            arrival_value = ARRIVAL_OPTIONS[arrival_seg.selected_index or 0]
            try:
                weight_value = float((weight_input.value or "0").replace(",", ".").strip())
            except ValueError:
                # SnackBar под модальным диалогом не виден — пишем ошибку в само поле
                weight_input.error_text = "Введите число, например 2100"
                page.update()
                return
            weight_input.error_text = None
            db.save_shift(date_str, float(hours_slider.value), status_dropdown.value,
                          product_dropdown.value, weight_value, arrival_value,
                          operator_dropdown.value)
            for t_time, t_type in pending_events:
                db.add_timeline_event(date_str, t_type, t_time)
            update_global_dashboard()
            build_calendar_grid()
            refresh_analytics_tab()
            close_dialog(dialog)

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"Смена: {date_obj.strftime('%d.%m.%Y')}", color="white"),
            content=ft.Container(
                # верхний отступ, чтобы плавающая подпись "Статус дня" не обрезалась при скролле
                padding=ft.Padding.only(top=12, left=4, right=4),
                content=ft.Column([
                    status_dropdown,
                    operator_dropdown,
                    ft.Text("Время прибытия:", size=11, color="#99ffffff"),
                    ft.Row([arrival_seg], alignment=ft.MainAxisAlignment.CENTER),
                    ft.Text("Корректировка часов (ручная):", size=11, color="#99ffffff"),
                    hours_slider, product_dropdown, weight_input, ft.Divider(),
                    ft.Text("Трекер ночи (хронология):", size=12, weight=ft.FontWeight.BOLD),
                    ft.Row([
                        ft.ElevatedButton("+ Перекур", on_click=lambda e: add_event(e, "Перекур")),
                        ft.ElevatedButton("▶ Работа", on_click=lambda e: add_event(e, "Работа")),
                    ], alignment=ft.MainAxisAlignment.CENTER),
                    timeline_list
                ], scroll=ft.ScrollMode.AUTO, spacing=10), width=340, height=520
            ),
            actions=[
                ft.TextButton("Отмена", on_click=lambda e: close_dialog(dialog)),
                ft.TextButton("Сохранить", on_click=save_and_close),
            ]
        )
        open_dialog(dialog)

    # В flet 0.86 диаграммы живут в отдельном пакете flet-charts (import flet_charts as fch)
    chart_arrival = fch.PieChart(sections=[], sections_space=2, center_space_radius=20, expand=True)
    chart_weight = fch.PieChart(sections=[], sections_space=2, center_space_radius=20, expand=True)

    TITLE_STYLE = ft.TextStyle(size=10, color="white", weight=ft.FontWeight.BOLD)

    def pie_section(value, color, title):
        return fch.PieChartSection(value=value, color=color, radius=26,
                                   title=title, title_style=TITLE_STYLE)

    def refresh_analytics_tab():
        month_data = db.get_month_data(view["year"], view["month"])
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

                if (shift.get("weight") or 0) >= WEIGHT_NORM:
                    norm_ok += 1
                else:
                    norm_fail += 1

        total_arr = vv + bf + op
        if total_arr > 0:
            chart_arrival.sections = [
                pie_section(vv, "#6ee7b7", f"В {int(vv / total_arr * 100)}%"),
                pie_section(bf, "#fbbf24", f"Б {int(bf / total_arr * 100)}%"),
                pie_section(op, "#f87171", f"О {int(op / total_arr * 100)}%"),
            ]
        else:
            chart_arrival.sections = [pie_section(1, "#4dffffff", "Нет данных")]

        total_w = norm_ok + norm_fail
        if total_w > 0:
            chart_weight.sections = [
                pie_section(norm_ok, "#6ee7b7", f"Норма {int(norm_ok / total_w * 100)}%"),
                pie_section(norm_fail, "#f87171", f"Недо {int(norm_fail / total_w * 100)}%"),
            ]
        else:
            chart_weight.sections = [pie_section(1, "#4dffffff", "Нет данных")]
        page.update()

    def shift_month(delta):
        m = view["month"] + delta
        y = view["year"]
        if m < 1:
            m, y = 12, y - 1
        elif m > 12:
            m, y = 1, y + 1
        view["month"], view["year"] = m, y
        build_calendar_grid()
        update_global_dashboard()
        refresh_analytics_tab()

    month_row = ft.Row([
        ft.IconButton(ft.Icons.CHEVRON_LEFT, icon_color="white", on_click=lambda e: shift_month(-1)),
        month_label,
        ft.IconButton(ft.Icons.CHEVRON_RIGHT, icon_color="white", on_click=lambda e: shift_month(1)),
    ], alignment=ft.MainAxisAlignment.CENTER)

    calendar_view = ft.Column([month_row, glass_card(grid_container)])

    analytics_view = ft.Column([
        ft.Text("ДИАГРАММЫ АНАЛИТИКИ ЗА МЕСЯЦ", size=14, weight=ft.FontWeight.BOLD, color="white"),
        glass_card(ft.Column([
            ft.Text("1. Время прибытия (вовремя / буфер / опоздание):", size=11, color="#ccffffff"),
            ft.Container(chart_arrival, height=140, alignment=ft.Alignment.CENTER),
            ft.Text(f"2. Выработка продукции (норма {int(WEIGHT_NORM)} кг / недовыработка):",
                    size=11, color="#ccffffff"),
            ft.Container(chart_weight, height=140, alignment=ft.Alignment.CENTER),
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
        bgcolor="#f2140f26"
    )

    def go_to_settings(e):
        show_settings_screen()

    settings_button = ft.IconButton(icon=ft.Icons.SETTINGS, icon_color="white", on_click=go_to_settings)

    def apply_accent():
        """Единая точка применения акцента и фоновой палитры ко всем экранам."""
        c = accent()
        pal = bg_palette()
        sph = sphere_colors()

        page.theme = ft.Theme(color_scheme_seed=c)
        page.bgcolor = pal["page"]
        pin_title.color = c
        salary_text.color = c
        month_label.color = c
        settings_button.icon_color = c
        nav_bar.indicator_color = accent_a("40")
        nav_bar.bgcolor = f"#f2{pal['page'].lstrip('#')}"

        for base, s1, s2, s3 in _backgrounds:
            base.gradient = ft.LinearGradient(
                begin=ft.Alignment.TOP_LEFT, end=ft.Alignment.BOTTOM_RIGHT,
                colors=list(pal["gradient"])
            )
            s1.bgcolor, s2.bgcolor, s3.bgcolor = sph

        for card in _glass_cards:
            card.bgcolor = pal["glass"]
            card.border = ft.Border.all(1, pal["glass_border"])

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
                                    ft.Text("КАЛЕНДАРЬ СМЕН PRO", size=12, color="#80ffffff"),
                                    salary_text, stats_subtext
                                ], spacing=1, expand=True),
                                settings_button,
                            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                vertical_alignment=ft.CrossAxisAlignment.START),
                        )
                    ),
                    tabs_content
                ], expand=True, spacing=10)
            ),
        ],
    )

    def show_main_screen():
        apply_accent()
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
    op1_field = ft.TextField(label="Оператор 1", expand=True, bgcolor="#14ffffff", color="white", border_color="#33ffffff")
    op2_field = ft.TextField(label="Оператор 2", expand=True, bgcolor="#14ffffff", color="white", border_color="#33ffffff")
    op3_field = ft.TextField(label="Оператор 3", expand=True, bgcolor="#14ffffff", color="white", border_color="#33ffffff")
    op4_field = ft.TextField(label="Оператор 4", expand=True, bgcolor="#14ffffff", color="white", border_color="#33ffffff")

    theme_dropdown = ft.Dropdown(
        label="Акцентный цвет",
        options=[ft.dropdown.Option(name) for name in THEME_ACCENTS.keys()]
    )
    bg_dropdown = ft.Dropdown(
        label="Фон / тональность",
        options=[ft.dropdown.Option(name) for name in THEME_BACKGROUNDS.keys()]
    )

    def preview_theme(e=None):
        # мгновенный предпросмотр; в БД значения уходят по "Сохранить" или "Назад"
        config["theme"] = theme_dropdown.value or config["theme"]
        config["bg_theme"] = bg_dropdown.value or config["bg_theme"]
        apply_accent()
        page.update()

    # В разных сборках Flet у Dropdown событие называется по-разному, а в конструктор
    # его передавать нельзя — привязываем после создания, если атрибут есть.
    bind_event(theme_dropdown, preview_theme, "on_change", "on_select", "on_changed")
    bind_event(bg_dropdown, preview_theme, "on_change", "on_select", "on_changed")

    settings_error = ft.Text("", color="#fca5a5", size=12)

    new_product_input = ft.TextField(label="Название нового продукта", expand=True,
                                      bgcolor="#14ffffff", color="white", border_color="#33ffffff")
    products_list_view = ft.Column()

    for _f in (rate_field, op1_field, op2_field, op3_field, op4_field, new_product_input):
        _f.on_change = sync_value

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
        name = (new_product_input.value or "").strip()
        if not name:
            return
        if db.add_product(name):
            new_product_input.value = ""
            new_product_input.error_text = None
        else:
            new_product_input.error_text = "Такой продукт уже есть"
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
        bg_dropdown.value = cfg["bg_theme"]
        settings_error.value = ""
        new_product_input.error_text = None
        refresh_products_list()

    def clean_op(value, default):
        value = (value or "").strip()
        return value if value else default

    def read_rate():
        try:
            return float((rate_field.value or "632").replace(",", "."))
        except ValueError:
            return None

    def persist_settings(new_rate):
        db.save_config(
            new_rate, theme_dropdown.value or "Aurora Violet",
            clean_op(op1_field.value, "Оператор 1"), clean_op(op2_field.value, "Оператор 2"),
            clean_op(op3_field.value, "Оператор 3"), clean_op(op4_field.value, "Оператор 4"),
            bg_dropdown.value or DEFAULT_BG_THEME,
        )
        config.update(db.get_config())

    def save_settings_click(e):
        new_rate = read_rate()
        if new_rate is None:
            settings_error.value = "Некорректная ставка"
            page.update()
            return
        persist_settings(new_rate)
        show_main_screen()

    def back_to_main_click(e):
        # "Назад" тоже сохраняет; при некорректной ставке остаётся прежняя
        new_rate = read_rate()
        persist_settings(config["hour_rate"] if new_rate is None else new_rate)
        show_main_screen()

    def change_pin_click(e):
        # PIN не стираем заранее: старый хеш живёт до успешного подтверждения нового
        show_pin_screen(force_setup=True)

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
                        ft.Text("Имена четырёх сменных операторов", size=12, color="#bfffffff"),
                        ft.Row([op1_field, op2_field]),
                        ft.Row([op3_field, op4_field]),
                    ], spacing=6)),
                    glass_card(ft.Column([
                        theme_dropdown,
                        bg_dropdown,
                        # запасной путь, если Dropdown в этой сборке не отдаёт событие выбора
                        ft.OutlinedButton("Применить тему", on_click=preview_theme, width=300),
                    ], spacing=10)),
                    glass_card(ft.Column([
                        ft.Text("Каталог продукции", size=12, color="#bfffffff"),
                        ft.Row([new_product_input,
                                ft.FloatingActionButton(icon=ft.Icons.ADD, on_click=add_product_click, mini=True)]),
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
        apply_accent()
        root.content = settings_view
        page.navigation_bar = None
        page.update()

    # ---------- старт ----------
    page.add(root)
    show_pin_screen()

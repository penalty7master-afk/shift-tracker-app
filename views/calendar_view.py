import calendar
from datetime import date, datetime

import flet as ft

from calculations import (format_hours, format_money, month_forecast,
                          month_summary, next_shift_info,
                          planned_dates_for_operator, get_operator_for_date)
from constants import (ARRIVAL_OPTIONS, FULL_SHIFT_HOURS, MONTH_NAMES,
                       STATUS_COLORS, STATUS_WORK, WEEKDAY_SHORT, WEIGHT_NORM)
from database import db
from views.common import confirm_dialog, info_dialog, safe_update
from views.day_modal import show_day_modal

WEEKS = 6
CELL_HEIGHT = 62
TRANSPARENT = "#00000000"

DOT_NOTE = "#7dd3fc"
DOT_HOLIDAY = "#fbbf24"
DOT_UNDER_NORM = "#f87171"


class CalendarView:
    def __init__(self, ctx):
        self.ctx = ctx
        self.page = ctx.page
        self.th = ctx.theme
        self.cells = []
        self._build()

    # ==========================================
    # СБОРКА (выполняется один раз)
    # ==========================================
    def _build(self):
        th = self.th

        self.month_label = th.text("", role="accent", size=15,
                                   weight=ft.FontWeight.BOLD)
        month_row = ft.Row([
            th.icon_button(ft.Icons.CHEVRON_LEFT,
                           on_click=lambda e: self.shift_month(-1)),
            self.month_label,
            th.icon_button(ft.Icons.CHEVRON_RIGHT,
                           on_click=lambda e: self.shift_month(1)),
        ], alignment=ft.MainAxisAlignment.CENTER)

        self.grid = ft.Column(spacing=5, tight=True)
        self.grid.controls.append(ft.Row([
            ft.Container(
                content=ft.Text(name, size=11, weight=ft.FontWeight.BOLD,
                                color=th.color("text_faint")),
                expand=1, alignment=ft.Alignment.CENTER)
            for name in WEEKDAY_SHORT
        ], spacing=5))

        self.week_rows = []
        for _week in range(WEEKS):
            row_cells = [self._make_cell() for _day in range(7)]
            self.cells.append(row_cells)
            row = ft.Row(row_cells, spacing=5)
            self.week_rows.append(row)
            self.grid.controls.append(row)

        grid_card = th.card(self.grid, padding=10)

        # свайп по календарю переключает месяц
        swipeable = ft.GestureDetector(
            content=grid_card,
            on_horizontal_drag_end=self._on_swipe,
            drag_interval=50,
        )

        self._build_premium_card()
        self._build_footer()

        self.control = ft.Column(
            [month_row, swipeable, self.premium_card, self.footer_card],
            spacing=10, scroll=ft.ScrollMode.AUTO, expand=True,
        )

    def _make_cell(self):
        day_text = ft.Text("", size=14, weight=ft.FontWeight.BOLD)
        op_text = ft.Text("", size=9)
        dots = ft.Row([self._make_dot() for _i in range(3)],
                      spacing=3, tight=True,
                      alignment=ft.MainAxisAlignment.CENTER)
        cell = ft.Container(
            content=ft.Column([day_text, op_text, dots],
                              spacing=1, tight=True,
                              alignment=ft.MainAxisAlignment.CENTER,
                              horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            expand=1, height=CELL_HEIGHT, border_radius=10,
            alignment=ft.Alignment.CENTER,
            on_click=self._on_cell_click,
        )
        return cell

    @staticmethod
    def _make_dot():
        return ft.Container(width=5, height=5, border_radius=3, visible=False)

    def _build_premium_card(self):
        th = self.th
        self.premium_title = th.text("", size=12, weight=ft.FontWeight.BOLD)
        self.premium_hint = th.text("", role="dim", size=11)
        self.premium_bar = ft.ProgressBar(value=0, color=th.accent(),
                                          bgcolor=th.color("field_bg"),
                                          bar_height=8, border_radius=4)
        self.premium_card = th.card(
            ft.Column([self.premium_title, self.premium_bar, self.premium_hint],
                      spacing=8, tight=True), padding=14)

    def _build_footer(self):
        th = self.th
        self.next_shift_text = th.text("", role="dim", size=11)
        self.forecast_text = th.text("", role="dim", size=11)
        self.autofill_button = ft.OutlinedButton(
            "Заполнить месяц по графику", on_click=self._confirm_autofill)
        self.footer_card = th.card(
            ft.Column([self.next_shift_text, self.forecast_text,
                       self.autofill_button], spacing=8, tight=True),
            padding=14)

    # ==========================================
    # НАВИГАЦИЯ
    # ==========================================
    def shift_month(self, delta):
        month = self.ctx.view["month"] + delta
        year = self.ctx.view["year"]
        if month < 1:
            month, year = 12, year - 1
        elif month > 12:
            month, year = 1, year + 1
        self.ctx.view["month"], self.ctx.view["year"] = month, year
        self.ctx.reload_month()

    def _on_swipe(self, e):
        velocity = getattr(e, "primary_velocity", None)
        if not velocity:
            return
        self.shift_month(-1 if velocity > 0 else 1)

    def _on_cell_click(self, e):
        raw = e.control.data
        if not raw:
            return
        show_day_modal(self.ctx, datetime.strptime(raw, "%Y-%m-%d").date())

    # ==========================================
    # ОТРИСОВКА
    # ==========================================
    def refresh(self):
        th = self.th
        year, month = self.ctx.view["year"], self.ctx.view["month"]
        month_data = self.ctx.month_data
        config = self.ctx.config
        ops = [config.get(f"op{i}") for i in range(1, 5)]
        cycle_start = config.get("cycle_start")
        norms = config.get("product_norms") or {}
        today = date.today()

        self.month_label.value = f"{MONTH_NAMES[month - 1]} {year}"

        weeks = calendar.Calendar(firstweekday=0).monthdayscalendar(year, month)
        for index, row in enumerate(self.week_rows):
            row.visible = index < len(weeks)

        for week_index in range(WEEKS):
            week = weeks[week_index] if week_index < len(weeks) else [0] * 7
            for day_index in range(7):
                self._paint_cell(self.cells[week_index][day_index],
                                 week[day_index], year, month, day_index,
                                 month_data, ops, cycle_start, norms, today)

        self._refresh_premium(month_data, config)
        self._refresh_footer(year, month, month_data, config, ops, cycle_start, today)
        safe_update(self.control)

    def _paint_cell(self, cell, day, year, month, weekday,
                    month_data, ops, cycle_start, norms, today):
        th = self.th
        day_text, op_text, dots = cell.content.controls

        if day == 0:
            cell.data = None
            cell.visible = False
            return

        cell.visible = True
        current = date(year, month, day)
        date_str = current.strftime("%Y-%m-%d")
        cell.data = date_str
        saved = month_data.get(date_str)

        # подмена оператора вручную приоритетнее графика 4/4
        operator = (saved or {}).get("operator") or get_operator_for_date(
            current, ops, cycle_start)

        bg_color = th.color("weekend") if weekday >= 5 else TRANSPARENT
        border_color = th.color("cell_border")
        border_width = 1

        if saved:
            status = saved.get("status")
            fill, stroke = STATUS_COLORS.get(status, (TRANSPARENT, None))
            if status == STATUS_WORK:
                bg_color = th.accent_a("26")
                border_color = th.accent_a("99")
            elif fill:
                bg_color, border_color = fill, stroke

        if current == today:
            border_color = th.accent()
            border_width = 2

        cell.bgcolor = bg_color
        cell.border = ft.Border.all(border_width, border_color)

        day_text.value = str(day)
        day_text.color = (th.accent() if current == today
                          else th.color("text_dim") if weekday >= 5
                          else th.color("text"))
        op_text.value = self._short_name(operator)
        op_text.color = th.color("text_faint")

        self._paint_dots(dots, saved, norms)

    def _paint_dots(self, dots, saved, norms):
        flags = [(False, DOT_NOTE), (False, DOT_HOLIDAY), (False, DOT_UNDER_NORM)]
        if saved:
            under_norm = False
            if saved.get("status") == STATUS_WORK:
                norm = float(norms.get(saved.get("product"), WEIGHT_NORM) or WEIGHT_NORM)
                under_norm = float(saved.get("weight") or 0.0) < norm
            flags = [
                (bool(saved.get("note")), DOT_NOTE),
                (bool(saved.get("holiday")), DOT_HOLIDAY),
                (under_norm, DOT_UNDER_NORM),
            ]
        for dot, (visible, color) in zip(dots.controls, flags):
            dot.visible = visible
            dot.bgcolor = color

    @staticmethod
    def _short_name(name):
        parts = (name or "").split()
        return parts[-1] if parts else "—"

    # ---------- премия и подвал ----------
    def _refresh_premium(self, month_data, config):
        summary = month_summary(month_data, config)
        step = summary["next_step"]

        self.premium_title.value = (
            f"Смен: {summary['shifts']} · премия {summary['premium_hours']} ч "
            f"= {format_money(summary['premium_money'])}")
        self.premium_bar.value = summary["progress"]
        self.premium_bar.color = self.th.accent()
        self.premium_bar.bgcolor = self.th.color("field_bg")

        if step is None:
            self.premium_hint.value = "Максимальная ступень премии достигнута"
        else:
            threshold, hours, left = step
            self.premium_hint.value = (
                f"До ступени {threshold} смен ({hours} ч премии) осталось: {left}")

    def _refresh_footer(self, year, month, month_data, config, ops, cycle_start, today):
        upcoming = next_shift_info(config, today)
        if upcoming is None:
            self.next_shift_text.value = (
                "Выберите «Мой оператор» в настройках — появится прогноз и график")
        else:
            shift_date, offset = upcoming
            when = ("сегодня" if offset == 0 else
                    "завтра" if offset == 1 else f"через {offset} дн.")
            weekday = WEEKDAY_SHORT[shift_date.weekday()]
            self.next_shift_text.value = (
                f"Следующая смена: {weekday}, {shift_date.strftime('%d.%m')} ({when})")

        forecast = month_forecast(year, month, month_data, config, today)
        if forecast is None:
            summary = month_summary(month_data, config)
            self.forecast_text.value = (
                f"Отработано {format_hours(summary['total_hours'])} ч · "
                f"на руки {format_money(summary['net'])}")
        else:
            self.forecast_text.value = (
                f"Прогноз на конец месяца: {forecast['shifts']} смен, "
                f"на руки {format_money(forecast['net'])} "
                f"(осталось {forecast['remaining']})")

        self.autofill_button.visible = bool(config.get("my_operator"))

    # ==========================================
    # АВТОЗАПОЛНЕНИЕ
    # ==========================================
    def _confirm_autofill(self, e=None):
        year, month = self.ctx.view["year"], self.ctx.view["month"]
        config = self.ctx.config
        ops = [config.get(f"op{i}") for i in range(1, 5)]
        my_op = config.get("my_operator")

        planned = planned_dates_for_operator(year, month, ops, my_op,
                                             config.get("cycle_start"))
        fresh = [d for d in planned
                 if d.strftime("%Y-%m-%d") not in self.ctx.month_data]

        if not fresh:
            info_dialog(self.ctx, "Нечего заполнять",
                        "Все смены этого месяца по графику уже отмечены.")
            return

        confirm_dialog(
            self.ctx, "Заполнить месяц?",
            f"Будет добавлено {len(fresh)} рабочих смен для «{my_op}». "
            "Уже существующие записи останутся нетронутыми.",
            lambda: self._do_autofill(fresh, my_op),
            confirm_label="Заполнить", danger=False,
        )

    def _do_autofill(self, dates, operator):
        products = db.get_products()
        product, norm = products[0] if products else (None, WEIGHT_NORM)
        rows = [
            (d.strftime("%Y-%m-%d"), FULL_SHIFT_HOURS, STATUS_WORK, product,
             norm, ARRIVAL_OPTIONS[0], operator, None, 0)
            for d in dates
        ]
        db.save_shifts_bulk(rows)
        self.ctx.refresh_after_change()

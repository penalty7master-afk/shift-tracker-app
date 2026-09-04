import calendar
from datetime import date, datetime

import flet as ft

from calculations import (format_hours, format_money, month_forecast,
                          month_summary, get_operator_for_date, norm_for_shop,
                          op_names_from)
from constants import (MONTH_NAMES, SHOP1, SHOP2, STATUS_COLORS, STATUS_WORK,
                       WEEKDAY_SHORT)
from views.common import safe_update
from views.day_modal import show_day_modal

WEEKS = 6
CELL_HEIGHT = 66
TRANSPARENT = "#00000000"

ARROW_UP = "#6ee7b7"
ARROW_DOWN = "#f87171"
DOT_NOTE = "#7dd3fc"
DOT_TRACKER = "#c4b5fd"


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

        self._build_legend()
        self._build_premium_card()
        self._build_forecast_card()

        self.control = ft.Column(
            [month_row, swipeable, self.legend_row,
             self.premium_card, self.forecast_card],
            spacing=10, scroll=ft.ScrollMode.AUTO, expand=True,
        )

    def _make_cell(self):
        day_text = ft.Text("", size=14, weight=ft.FontWeight.BOLD)
        op_text = ft.Text("", size=9)
        marks = ft.Row([
            ft.Icon(ft.Icons.ARROW_UPWARD, size=11, visible=False),
            ft.Icon(ft.Icons.ARROW_UPWARD, size=11, visible=False),
            self._make_dot(),
            self._make_dot(),
        ], spacing=2, tight=True, alignment=ft.MainAxisAlignment.CENTER)
        return ft.Container(
            content=ft.Column([day_text, op_text, marks],
                              spacing=1, tight=True,
                              alignment=ft.MainAxisAlignment.CENTER,
                              horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            expand=1, height=CELL_HEIGHT, border_radius=10,
            alignment=ft.Alignment.CENTER,
            on_click=self._on_cell_click,
        )

    @staticmethod
    def _make_dot():
        return ft.Container(width=5, height=5, border_radius=3, visible=False)

    def _build_legend(self):
        th = self.th
        items = [
            (ft.Icon(ft.Icons.ARROW_UPWARD, size=11, color=ARROW_UP), "цех 1"),
            (ft.Icon(ft.Icons.ARROW_DOWNWARD, size=11, color=ARROW_DOWN), "цех 2"),
            (ft.Container(width=6, height=6, border_radius=3, bgcolor=DOT_NOTE), "заметка"),
            (ft.Container(width=6, height=6, border_radius=3, bgcolor=DOT_TRACKER), "хронология"),
        ]
        controls = []
        for mark, label in items:
            controls.append(ft.Row([
                mark, ft.Text(label, size=9, color=th.color("text_faint")),
            ], spacing=4, tight=True))
        self.legend_row = ft.Row(controls, spacing=12, wrap=True,
                                 alignment=ft.MainAxisAlignment.CENTER)

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

    def _build_forecast_card(self):
        th = self.th
        self.fact_text = th.text("", role="dim", size=11)
        self.forecast_text = th.text("", role="dim", size=11)
        self.forecast_card = th.card(
            ft.Column([self.fact_text, self.forecast_text], spacing=6, tight=True),
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
        year, month = self.ctx.view["year"], self.ctx.view["month"]
        shifts_data = self.ctx.month_data
        production_data = getattr(self.ctx, "production_data", {})
        config = self.ctx.config
        ops = op_names_from(config)
        cycle_start = config.get("cycle_start")
        timeline_dates = self.ctx.timeline_dates
        norms = {SHOP1: norm_for_shop(SHOP1, config),
                 SHOP2: norm_for_shop(SHOP2, config)}
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
                                 shifts_data, production_data, ops, cycle_start,
                                 norms, timeline_dates, today)

        self._refresh_premium(shifts_data, config)
        self._refresh_forecast(year, month, shifts_data, config, today)
        safe_update(self.control)

    def _paint_cell(self, cell, day, year, month, weekday, shifts_data,
                    production_data, ops, cycle_start, norms, timeline_dates, today):
        th = self.th
        day_text, op_text, marks = cell.content.controls

        if day == 0:
            cell.data = None
            cell.visible = False
            return

        cell.visible = True
        current = date(year, month, day)
        date_str = current.strftime("%Y-%m-%d")
        cell.data = date_str
        shift = shifts_data.get(date_str)
        record = production_data.get(date_str)

        # оператор из записи производства приоритетнее графика
        operator = (record or {}).get("operator") or get_operator_for_date(
            current, ops, cycle_start)

        bg_color = th.color("weekend") if weekday >= 5 else TRANSPARENT
        border_color = th.color("cell_border")
        border_width = 1

        if shift:
            status = shift.get("status")
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

        self._paint_marks(marks, shift, record, norms,
                          date_str in timeline_dates)

    def _paint_marks(self, marks, shift, record, norms, has_timeline):
        arrow1, arrow2, dot_note, dot_tracker = marks.controls

        for arrow, key in ((arrow1, "weight1"), (arrow2, "weight2")):
            shop = SHOP1 if key == "weight1" else SHOP2
            weight = (record or {}).get(key)
            if weight is None:
                arrow.visible = False
                continue
            arrow.visible = True
            if float(weight) >= norms[shop]:
                arrow.name = ft.Icons.ARROW_UPWARD
                arrow.color = ARROW_UP
            else:
                arrow.name = ft.Icons.ARROW_DOWNWARD
                arrow.color = ARROW_DOWN

        dot_note.visible = bool(shift and shift.get("note"))
        dot_note.bgcolor = DOT_NOTE
        dot_tracker.visible = has_timeline
        dot_tracker.bgcolor = DOT_TRACKER

    @staticmethod
    def _short_name(name):
        parts = (name or "").split()
        return parts[-1] if parts else "—"

    # ---------- премия и прогноз ----------
    def _refresh_premium(self, shifts_data, config):
        summary = month_summary(shifts_data, config)
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

    def _refresh_forecast(self, year, month, shifts_data, config, today):
        summary = month_summary(shifts_data, config)
        self.fact_text.value = (
            f"Факт: {summary['shifts']} смен · "
            f"{format_hours(summary['total_hours'])} ч · "
            f"на руки {format_money(summary['net'])}")

        forecast = month_forecast(year, month, shifts_data, config, today)
        if forecast is None:
            self.forecast_text.value = "Месяц закрыт — прогноз не считается"
        else:
            self.forecast_text.value = (
                f"Если выйти во все оставшиеся {forecast['remaining']} дн.: "
                f"{forecast['shifts']} смен, премия {forecast['premium_hours']} ч, "
                f"на руки {format_money(forecast['net'])}")
        safe_update(self.control)

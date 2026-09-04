from datetime import date

import flet as ft
import flet_charts as fch

from calculations import (format_hours, format_money, format_weight,
                          month_summary, operator_stats, year_summaries)
from constants import MONTH_SHORT, tax_label
from database import db
from views.common import safe_update

PIE_HEIGHT = 150
BAR_HEIGHT = 90

COLOR_OK = "#6ee7b7"
COLOR_WARN = "#fbbf24"
COLOR_BAD = "#f87171"
COLOR_EMPTY = "#4dffffff"


class AnalyticsView:
    def __init__(self, ctx):
        self.ctx = ctx
        self.th = ctx.theme
        self.year_cache = {"year": None, "summaries": None}
        self._build()

    # ==========================================
    # СБОРКА
    # ==========================================
    def _build(self):
        th = self.th

        self.chart_arrival = fch.PieChart(sections=[], sections_space=2,
                                          center_space_radius=22, expand=True)
        self.chart_weight = fch.PieChart(sections=[], sections_space=2,
                                         center_space_radius=22, expand=True)

        self.money_rows = ft.Column(spacing=6, tight=True)
        self.operator_rows = ft.Column(spacing=8, tight=True)
        self.year_bars = ft.Row(spacing=4, tight=True,
                                vertical_alignment=ft.CrossAxisAlignment.END)
        self.year_title = th.text("", size=12, weight=ft.FontWeight.BOLD)
        self.year_total = th.text("", role="dim", size=11)

        self.control = ft.Column([
            th.card(ft.Column([
                th.text("ДЕНЬГИ ЗА МЕСЯЦ", size=12, weight=ft.FontWeight.BOLD),
                self.money_rows,
            ], spacing=10, tight=True), padding=14),

            th.card(ft.Column([
                th.text("Время прибытия", size=12, weight=ft.FontWeight.BOLD),
                th.text("вовремя / буфер / опоздание", role="dim", size=10),
                ft.Container(self.chart_arrival, height=PIE_HEIGHT,
                             alignment=ft.Alignment.CENTER),
                th.divider(),
                th.text("Выработка продукции", size=12, weight=ft.FontWeight.BOLD),
                th.text("норма выполнена / недовыработка", role="dim", size=10),
                ft.Container(self.chart_weight, height=PIE_HEIGHT,
                             alignment=ft.Alignment.CENTER),
            ], spacing=8, tight=True), padding=14),

            th.card(ft.Column([
                th.text("СРАВНЕНИЕ ОПЕРАТОРОВ", size=12, weight=ft.FontWeight.BOLD),
                self.operator_rows,
            ], spacing=10, tight=True), padding=14),

            th.card(ft.Column([
                self.year_title,
                ft.Container(self.year_bars, height=BAR_HEIGHT + 26),
                self.year_total,
            ], spacing=10, tight=True), padding=14),
        ], spacing=10, scroll=ft.ScrollMode.AUTO, expand=True)

    # ==========================================
    # ОБНОВЛЕНИЕ
    # ==========================================
    def refresh(self):
        config = self.ctx.config
        month_data = self.ctx.month_data
        summary = month_summary(month_data, config)

        self._refresh_money(summary, config)
        self._refresh_pies(summary)
        self._refresh_operators(month_data, config)
        self._refresh_year(config)
        safe_update(self.control)

    # ---------- деньги ----------
    def _refresh_money(self, summary, config):
        th = self.th
        tax_name = tax_label(summary["tax_rate"])
        rows = [
            ("Отработано часов", f"{format_hours(summary['total_hours'])} ч", None),
            ("Оплачиваемых часов", f"{format_hours(summary['paid_hours'])} ч", None),
            ("Оклад по часам", format_money(summary["base_money"]), None),
            (f"Премия ({summary['premium_hours']} ч)",
             format_money(summary["premium_money"]), None),
            ("Начислено", format_money(summary["gross"]), None),
            (f"Налог · {tax_name}", "− " + format_money(summary["tax_money"]),
             COLOR_WARN if summary["tax_money"] else None),
            ("НА РУКИ", format_money(summary["net"]), th.accent()),
        ]
        if summary["holidays"]:
            rows.insert(2, (f"Праздничных смен (×{config.get('holiday_mult'):g})",
                            str(summary["holidays"]), None))

        controls = []
        for index, (label, value, color) in enumerate(rows):
            bold = (index == len(rows) - 1)
            controls.append(ft.Row([
                ft.Text(label, size=12 if not bold else 13,
                        color=th.color("text_dim") if not bold else th.color("text"),
                        weight=ft.FontWeight.BOLD if bold else None, expand=True),
                ft.Text(value, size=12 if not bold else 16,
                        color=color or th.color("text"),
                        weight=ft.FontWeight.BOLD if bold else None),
            ]))
            if index == len(rows) - 2:
                controls.append(th.divider())
        self.money_rows.controls = controls

    # ---------- круговые диаграммы ----------
    def _section(self, value, color, title):
        return fch.PieChartSection(
            value=value, color=color, radius=28, title=title,
            title_style=ft.TextStyle(size=10, color="#ffffff",
                                     weight=ft.FontWeight.BOLD))

    def _refresh_pies(self, summary):
        on_time, buffer_count, late = (summary["on_time"], summary["buffer"],
                                       summary["late"])
        total = on_time + buffer_count + late
        if total:
            self.chart_arrival.sections = [
                self._section(on_time, COLOR_OK, f"В {round(on_time / total * 100)}%"),
                self._section(buffer_count, COLOR_WARN, f"Б {round(buffer_count / total * 100)}%"),
                self._section(late, COLOR_BAD, f"О {round(late / total * 100)}%"),
            ]
        else:
            self.chart_arrival.sections = [self._section(1, COLOR_EMPTY, "Нет данных")]

        ok, fail = summary["norm_ok"], summary["norm_fail"]
        total_weight = ok + fail
        if total_weight:
            self.chart_weight.sections = [
                self._section(ok, COLOR_OK, f"Норма {round(ok / total_weight * 100)}%"),
                self._section(fail, COLOR_BAD, f"Недо {round(fail / total_weight * 100)}%"),
            ]
        else:
            self.chart_weight.sections = [self._section(1, COLOR_EMPTY, "Нет данных")]

    # ---------- операторы ----------
    def _refresh_operators(self, month_data, config):
        th = self.th
        stats = operator_stats(month_data, config)
        max_shifts = max([row["shifts"] for row in stats.values()] + [1])

        controls = []
        for name, row in stats.items():
            if row["shifts"]:
                detail = (f"{row['shifts']} см · опозданий {row['late']} · "
                          f"средняя {format_weight(row['avg_weight'])} кг")
            else:
                detail = "нет смен"
            controls.append(ft.Column([
                ft.Row([
                    ft.Text(name, size=12, color=th.color("text"), expand=True),
                    ft.Text(f"{format_hours(row['hours'])} ч", size=11,
                            color=th.color("text_dim")),
                ]),
                ft.ProgressBar(value=row["shifts"] / max_shifts,
                               color=th.accent(), bgcolor=th.color("field_bg"),
                               bar_height=6, border_radius=3),
                ft.Text(detail, size=10, color=th.color("text_faint")),
            ], spacing=3, tight=True))
        self.operator_rows.controls = controls

    # ---------- год ----------
    def _refresh_year(self, config):
        th = self.th
        year = self.ctx.view["year"]

        # год перечитывается только при смене года, а не при каждом показе вкладки
        if self.year_cache["year"] != year:
            self.year_cache["year"] = year
            self.year_cache["summaries"] = year_summaries(db.get_year_data(year), config)
        summaries = self.year_cache["summaries"]

        values = [item["net"] for item in summaries]
        peak = max(values + [1.0])
        total = sum(values)
        current_month = self.ctx.view["month"]

        bars = []
        for index, value in enumerate(values):
            height = max(3, int(BAR_HEIGHT * (value / peak))) if value else 3
            active = (index + 1) == current_month
            bars.append(ft.Column([
                ft.Container(
                    width=16, height=height, border_radius=4,
                    bgcolor=th.accent() if active else th.accent_a("59"),
                ),
                ft.Text(MONTH_SHORT[index], size=8,
                        color=th.color("text") if active else th.color("text_faint")),
            ], spacing=3, tight=True,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER))
        self.year_bars.controls = bars

        self.year_title.value = f"ГОД {year} — на руки по месяцам"
        self.year_total.value = f"Итого за год: {format_money(total)}"

    def invalidate_year(self):
        self.year_cache["year"] = None

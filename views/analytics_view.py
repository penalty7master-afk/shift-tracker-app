import flet as ft
import flet_charts as fch

from calculations import (format_hours, format_money, format_weight, mode_of,
                          month_summary, my_shift_dates, operator_stats,
                          production_summary, year_heatmap, year_summaries)
from constants import (HEATMAP_COLORS, HEATMAP_EMPTY, MONTH_SHORT, SHOP_KEYS,
                       SHOP_SHORT, SHOP_TITLES, STATUS_DAY_OFF, STATUS_OVERSLEPT,
                       STATUS_PREMIUM_OFF, STATUS_WORK, tax_label, term)
from database import db
from views.common import bind_event, refresh_tree, safe_update, touch

PIE_HEIGHT = 150
BAR_HEIGHT = 90
HEAT_CELL = 9
HEAT_GAP = 2

COLOR_OK = "#6ee7b7"
COLOR_WARN = "#fbbf24"
COLOR_BAD = "#f87171"
COLOR_EMPTY = "#4dffffff"


class AnalyticsView:
    """Шесть разделов: моё за месяц, приход, производство, операторы,
    год по месяцам, годовая карта."""

    def __init__(self, ctx):
        self.ctx = ctx
        self.th = ctx.theme
        self.year_cache = {"year": None, "mode": None,
                           "summaries": None, "heatmap": None}
        self.only_mine = False
        self._build()

    # ==========================================
    # СБОРКА
    # ==========================================
    def _build(self):
        th = self.th

        self.chart_arrival = fch.PieChart(sections=[], sections_space=2,
                                          center_space_radius=22, expand=True)

        self.money_rows = ft.Column(spacing=6, tight=True)
        self.production_rows = ft.Column(spacing=10, tight=True)
        self.operator_rows = ft.Column(spacing=10, tight=True)

        # Без tight: иначе карточка сжималась по ширине двенадцати столбиков
        # и выглядела уже остальных.
        self.year_bars = ft.Row(spacing=4,
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                vertical_alignment=ft.CrossAxisAlignment.END)
        self.year_title = th.text("", size=12, weight=ft.FontWeight.BOLD)
        self.year_total = th.text("", role="dim", size=11)

        self.mine_switch = ft.Switch(value=False, scale=0.8,
                                     active_color=th.accent())
        bind_event(self.mine_switch, self._on_mine_toggle,
                   "on_change", "on_changed")
        self.production_title = th.text("", size=12, weight=ft.FontWeight.BOLD,
                                        expand=True)
        self.production_caption = th.text("", role="faint", size=10)
        self.operators_caption = th.text("", role="faint", size=10)

        # Подписи месяцев живут отдельной неподвижной колонкой: раньше они
        # ехали вместе с квадратами и при свайпе к концу месяца пропадали.
        self.heatmap_months = ft.Column(spacing=HEAT_GAP, tight=True)
        self.heatmap_column = ft.Column(spacing=HEAT_GAP, tight=True)
        self.heatmap_legend = ft.Row(spacing=8, wrap=True)

        self.control = ft.Column([
            th.card(ft.Column([
                th.text("МОЁ ЗА МЕСЯЦ", size=12, weight=ft.FontWeight.BOLD),
                self.money_rows,
            ], spacing=10, tight=True), padding=14),

            th.card(ft.Column([
                th.text("Время прибытия", size=12, weight=ft.FontWeight.BOLD),
                th.text("вовремя / буфер / опоздание", role="dim", size=10),
                ft.Container(self.chart_arrival, height=PIE_HEIGHT,
                             alignment=ft.Alignment.CENTER),
            ], spacing=8, tight=True), padding=14),

            th.card(ft.Column([
                ft.Row([
                    self.production_title,
                    th.text("только мои", role="faint", size=10),
                    self.mine_switch,
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                self.production_caption,
                self.production_rows,
            ], spacing=10, tight=True), padding=14),

            th.card(ft.Column([
                th.text("ОПЕРАТОРЫ", size=12, weight=ft.FontWeight.BOLD),
                self.operators_caption,
                self.operator_rows,
            ], spacing=10, tight=True), padding=14),

            th.card(ft.Column([
                self.year_title,
                ft.Container(self.year_bars, height=BAR_HEIGHT + 26),
                self.year_total,
            ], spacing=10, tight=True), padding=14),

            th.card(ft.Column([
                th.text("МОЙ ГОД", size=12, weight=ft.FontWeight.BOLD),
                th.text("Каждый квадрат — день. Пустые не отмечены.",
                        role="faint", size=10),
                ft.Row([
                    self.heatmap_months,
                    ft.Row([self.heatmap_column], scroll=ft.ScrollMode.HIDDEN,
                           expand=True),
                ], spacing=6, vertical_alignment=ft.CrossAxisAlignment.START),
                self.heatmap_legend,
            ], spacing=10, tight=True), padding=14),
            # Запас снизу не нужен: отступ под навигацией даёт распорка,
            # которую вставляет ui.py.
        ], spacing=10, scroll=ft.ScrollMode.AUTO, expand=True)

    # ==========================================
    # ОБНОВЛЕНИЕ
    # ==========================================
    def refresh(self):
        config = self.ctx.config
        shifts_data = self.ctx.month_data
        production_data = self.ctx.production_data

        summary = month_summary(shifts_data, config)
        self._refresh_money(summary)
        self._refresh_arrival(summary)
        self._refresh_production(production_data, shifts_data, config)
        self._refresh_operators(production_data, config)
        self._refresh_year(config)
        self._refresh_heatmap()
        safe_update(self.control)

    # ---------- деньги ----------
    def _refresh_money(self, summary):
        th = self.th
        rows = [
            ("Отработано смен", str(summary["shifts"]), None),
            ("Часов", f"{format_hours(summary['total_hours'])} ч", None),
            ("Оклад по часам", format_money(summary["base_money"]), None),
            (f"Премия за смены ({summary['premium_hours']} ч)",
             format_money(summary["premium_money"]), None),
        ]
        if summary["premium_off"] or summary["premium_paid"]:
            rows.append((f"Выплачено премии ({summary['premium_off']} дн.)",
                         format_money(summary["premium_paid"]), COLOR_OK))
        rows += [
            ("Начислено", format_money(summary["gross"]), None),
            (f"Налог · {tax_label(summary['tax_rate'])}",
             "− " + format_money(summary["tax_money"]),
             COLOR_WARN if summary["tax_money"] else None),
            ("НА РУКИ", format_money(summary["net"]), th.accent()),
        ]
        if summary["overslept"]:
            rows.insert(1, ("Проспал", str(summary["overslept"]), COLOR_BAD))

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

    # ---------- приход ----------
    def _section(self, value, color, title):
        return fch.PieChartSection(
            value=value, color=color, radius=28, title=title,
            title_style=ft.TextStyle(size=10, color="#ffffff",
                                     weight=ft.FontWeight.BOLD))

    def _refresh_arrival(self, summary):
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

    # ---------- производство ----------
    def _on_mine_toggle(self, e=None):
        touch(self.ctx)
        self.only_mine = bool(self.mine_switch.value)
        self._refresh_production(self.ctx.production_data, self.ctx.month_data,
                                 self.ctx.config)
        refresh_tree(self.production_rows, self.production_caption)

    def _refresh_production(self, production_data, shifts_data, config):
        th = self.th
        mode = mode_of(config)
        short = term(mode, "shifts_short")
        only = my_shift_dates(shifts_data) if self.only_mine else None
        stats = production_summary(production_data, config, only_dates=only)

        self.production_title.value = term(mode, "production_title")
        self.production_caption.value = (
            term(mode, "production_hint_mine") if self.only_mine
            else term(mode, "production_hint_all"))

        controls = []
        for shop in SHOP_KEYS:
            row = stats[shop]
            controls.append(ft.Row([
                th.text(SHOP_TITLES[shop], size=12, weight=ft.FontWeight.BOLD,
                        expand=True),
                th.text(f"{row['nights']} {short}", role="faint", size=10),
            ]))

            if not row["nights"]:
                controls.append(th.text("Данных нет", role="faint", size=11))
                controls.append(th.divider())
                continue

            share = row["norm_ok"] / row["nights"]
            controls.append(th.text(
                f"Всего {format_weight(row['total'])} кг · "
                f"в среднем {format_weight(row['avg'])} кг "
                f"{term(mode, 'per_shift')}",
                role="dim", size=11))
            controls.append(ft.ProgressBar(
                value=share, color=COLOR_OK, bgcolor=COLOR_BAD,
                bar_height=6, border_radius=3))
            controls.append(th.text(
                f"Норма {format_weight(row['norm'])} кг выполнена в "
                f"{row['norm_ok']} из {row['nights']} ({round(share * 100)}%)",
                role="faint", size=10))

            for product, slot in sorted(row["by_product"].items(),
                                        key=lambda kv: -kv[1]["weight"]):
                controls.append(ft.Row([
                    ft.Text(f"   {product}", size=11,
                            color=th.color("text_dim"), expand=True),
                    ft.Text(f"{format_weight(slot['weight'])} кг · "
                            f"{slot['nights']} {short}",
                            size=11, color=th.color("text_faint")),
                ]))
            controls.append(th.divider())

        if controls and isinstance(controls[-1], ft.Divider):
            controls.pop()
        self.production_rows.controls = controls

    # ---------- операторы ----------
    def _refresh_operators(self, production_data, config):
        th = self.th
        mode = mode_of(config)
        short = term(mode, "shifts_short")
        stats = operator_stats(production_data, config)
        peak = max([row["nights"] for row in stats.values()] + [1])

        # Дневная и ночная выработка хранятся раздельно, поэтому цифры
        # относятся только к текущему режиму — говорим об этом прямо.
        self.operators_caption.value = (
            f"Показана выработка {term(mode, 'per_shift')}.")

        controls = []
        for name, row in stats.items():
            if not row["nights"]:
                detail = "нет данных"
            else:
                parts = []
                for shop in SHOP_KEYS:
                    cell = row[shop]
                    if cell["nights"]:
                        parts.append(f"{SHOP_SHORT[shop]}: "
                                     f"средн. {format_weight(cell['avg'])} кг "
                                     f"({cell['nights']} {short})")
                detail = " · ".join(parts) if parts else "нет данных"

            controls.append(ft.Column([
                ft.Row([
                    ft.Text(name, size=12, color=th.color("text"), expand=True),
                    ft.Text(f"{row['nights']} {short}", size=11,
                            color=th.color("text_dim")),
                ]),
                ft.ProgressBar(value=row["nights"] / peak,
                               color=th.accent(), bgcolor=th.color("field_bg"),
                               bar_height=6, border_radius=3),
                ft.Text(detail, size=10, color=th.color("text_faint")),
            ], spacing=3, tight=True))
        self.operator_rows.controls = controls

    # ---------- год ----------
    def _year_data(self, config):
        year = self.ctx.view["year"]
        mode = mode_of(config)
        # Год перечитывается при смене года или режима: ставка и лестница
        # премий у них разные, значит суммы тоже.
        if self.year_cache["year"] != year or self.year_cache["mode"] != mode:
            shifts = db.get_year_shifts(year, mode)
            self.year_cache["year"] = year
            self.year_cache["mode"] = mode
            self.year_cache["summaries"] = year_summaries(shifts, config)
            self.year_cache["heatmap"] = year_heatmap(year, shifts)
        return year

    def _refresh_year(self, config):
        th = self.th
        year = self._year_data(config)
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

    # ---------- тепловая карта ----------
    def _heat_color(self, status):
        if status is None:
            return HEATMAP_EMPTY
        color = HEATMAP_COLORS.get(status, HEATMAP_EMPTY)
        return self.th.accent() if color is None else color

    def _refresh_heatmap(self):
        th = self.th
        months = self.year_cache["heatmap"] or []

        rows = []
        labels = []
        for index, days in enumerate(months):
            labels.append(ft.Container(
                width=26, height=HEAT_CELL,
                alignment=ft.Alignment.CENTER_LEFT,
                content=ft.Text(MONTH_SHORT[index], size=8,
                                color=th.color("text_faint"))))
            cells = []
            for _day, status in days:
                cells.append(ft.Container(
                    width=HEAT_CELL, height=HEAT_CELL, border_radius=2,
                    bgcolor=self._heat_color(status)))
            rows.append(ft.Row(cells, spacing=HEAT_GAP, tight=True))
        self.heatmap_months.controls = labels
        self.heatmap_column.controls = rows

        legend = []
        for label, status in (("смена", STATUS_WORK),
                              ("вых. для премии", STATUS_PREMIUM_OFF),
                              ("выходной", STATUS_DAY_OFF),
                              ("проспал", STATUS_OVERSLEPT)):
            legend.append(ft.Row([
                ft.Container(width=8, height=8, border_radius=2,
                             bgcolor=self._heat_color(status)),
                ft.Text(label, size=9, color=th.color("text_faint")),
            ], spacing=4, tight=True))
        self.heatmap_legend.controls = legend

    def invalidate_year(self):
        self.year_cache["year"] = None

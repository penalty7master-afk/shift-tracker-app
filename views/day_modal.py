from datetime import datetime

import flet as ft

from calculations import (break_seconds, format_duration, format_weight,
                          get_operator_for_date, hours_for_arrival,
                          norm_for_shop, op_names_from)
from constants import (ARRIVAL_LABELS, ARRIVAL_OPTIONS, DAY_STATUSES, EVENT_BREAK,
                       EVENT_WORK, FULL_SHIFT_HOURS, SHOP1, SHOP2, SHOP_TITLES,
                       STATUS_WORK, WEIGHT_MAX)
from database import db
from views.common import (bind_event, close_dialog, confirm_dialog, dialog_height,
                          dialog_width, open_dialog, safe_update, sync_value)

ON_ACCENT_TEXT = "#101014"

# Служебное значение выпадающего списка: день не отмечен как мой.
# Позволяет открыть день только ради внесения производства из журнала.
STATUS_NONE = "— не отмечено —"


def show_day_modal(ctx, date_obj):
    DayModal(ctx, date_obj).open()


class DayModal:
    """
    Два независимых блока:
      «Моя смена» — статус, приход, часы, трекер, заметка;
      «Производство за ночь» — оператор и выработка цехов, доступно всегда.
    """

    def __init__(self, ctx, date_obj):
        self.ctx = ctx
        self.page = ctx.page
        self.th = ctx.theme
        self.config = ctx.config
        self.date_obj = date_obj
        self.date_str = date_obj.strftime("%Y-%m-%d")

        self.products = db.get_products()
        self.shift = db.get_shift(self.date_str)
        self.production = db.get_production(self.date_str)

        self.saved_events = list(db.get_timeline(self.date_str))
        self.pending_events = []
        # Удаления отложены: до "Сохранить" база не трогается,
        # поэтому "Отмена" честно возвращает всё на место.
        self.removed_ids = set()

        self._build()

    # ==========================================
    # СБОРКА
    # ==========================================
    def _build(self):
        th = self.th

        self._build_my_shift()
        self._build_production()

        self.error_text = ft.Text("", color="#fca5a5", size=12)

        self.body = ft.Column([
            th.text("МОЯ СМЕНА", size=12, weight=ft.FontWeight.BOLD),
            self.status_dropdown,
            self.work_block,
            th.divider(),
            th.text("ПРОИЗВОДСТВО ЗА НОЧЬ", size=12, weight=ft.FontWeight.BOLD),
            th.text("Заполняется и в дни, когда меня не было на смене.",
                    role="faint", size=10),
            self.production_block,
            self.error_text,
        ], scroll=ft.ScrollMode.AUTO, spacing=10, expand=True)

        self._apply_status_visibility(initial=True)

        actions = [
            ft.TextButton("Отмена", on_click=self._cancel),
            ft.TextButton("Сохранить", on_click=self._save),
        ]
        if self.shift or self.production or self.saved_events:
            actions.insert(0, ft.TextButton(
                "Очистить", on_click=self._confirm_delete,
                style=ft.ButtonStyle(color="#f87171")))

        self.dialog = ft.AlertDialog(
            modal=True,
            title=th.text(f"{self.date_obj.strftime('%d.%m.%Y')}",
                          size=16, weight=ft.FontWeight.BOLD),
            content=ft.Container(
                width=dialog_width(self.page),
                height=dialog_height(self.page),
                padding=ft.Padding.only(top=10, left=4, right=4),
                content=self.body,
            ),
            actions=actions,
        )

    # ---------- блок «Моя смена» ----------
    def _build_my_shift(self):
        th = self.th
        current_status = (self.shift or {}).get("status") or STATUS_NONE

        self.status_dropdown = ft.Dropdown(
            label="Статус дня", value=current_status,
            options=[ft.dropdown.Option(STATUS_NONE)] +
                    [ft.dropdown.Option(s) for s in DAY_STATUSES],
        )
        bind_event(self.status_dropdown, self._on_status_change,
                   "on_change", "on_select", "on_changed")

        raw_hours = (self.shift or {}).get("hours")
        self.hours_slider = ft.Slider(
            min=0, max=11, divisions=22,
            value=FULL_SHIFT_HOURS if raw_hours is None else float(raw_hours),
            label="{value} ч",
            active_color=th.accent(),
        )

        self._build_arrival()

        self.note_input = th.field(
            label="Заметка к смене", value=(self.shift or {}).get("note") or "",
            multiline=True, min_lines=2, max_lines=4,
        )

        self._build_timeline()

        self.work_block = ft.Column([
            th.text("Время прибытия:", role="dim", size=11),
            self.arrival_row,
            th.text("Корректировка часов (ручная):", role="dim", size=11),
            self.hours_slider,
            self.note_input,
            th.text("Трекер ночи (хронология):", size=12, weight=ft.FontWeight.BOLD),
            self.break_total,
            ft.Row([
                ft.ElevatedButton("+ Перекур",
                                  on_click=lambda e: self._add_event(EVENT_BREAK)),
                ft.ElevatedButton("▶ Работа",
                                  on_click=lambda e: self._add_event(EVENT_WORK)),
            ], alignment=ft.MainAxisAlignment.CENTER),
            self.timeline_list,
        ], spacing=10, tight=True)

    def _build_arrival(self):
        try:
            index = ARRIVAL_OPTIONS.index(
                (self.shift or {}).get("arrival_status") or ARRIVAL_OPTIONS[0])
        except ValueError:
            index = 0
        self.arrival_index = index
        self.arrival_cells = []

        for position, (title, subtitle) in enumerate(ARRIVAL_LABELS):
            cell = ft.Container(
                expand=1, height=44, border_radius=9, padding=2,
                alignment=ft.Alignment.CENTER,
                content=ft.Column([
                    ft.Text(title, size=11, text_align=ft.TextAlign.CENTER),
                    ft.Text(subtitle, size=9, text_align=ft.TextAlign.CENTER),
                ], spacing=0, tight=True,
                    alignment=ft.MainAxisAlignment.CENTER,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                on_click=lambda e, n=position: self._select_arrival(n),
            )
            self.arrival_cells.append(cell)

        self.arrival_row = ft.Container(
            bgcolor=self.th.color("field_bg"), border_radius=11, padding=3,
            content=ft.Row(self.arrival_cells, spacing=3),
        )
        self._paint_arrival()

    def _paint_arrival(self):
        th = self.th
        for position, cell in enumerate(self.arrival_cells):
            active = position == self.arrival_index
            cell.bgcolor = th.accent() if active else "#00000000"
            cell.content.controls[0].color = ON_ACCENT_TEXT if active else th.color("text")
            cell.content.controls[1].color = (f"#cc{ON_ACCENT_TEXT.lstrip('#')}"
                                              if active else th.color("text_dim"))

    def _select_arrival(self, index):
        self.arrival_index = index
        self.hours_slider.value = hours_for_arrival(ARRIVAL_OPTIONS[index])
        self._paint_arrival()
        safe_update(self.arrival_row)
        safe_update(self.hours_slider)

    # ---------- блок «Производство за ночь» ----------
    def _build_production(self):
        th = self.th
        record = self.production or {}
        ops = op_names_from(self.config)

        saved_op = record.get("operator")
        if saved_op not in ops:
            saved_op = get_operator_for_date(self.date_obj, ops,
                                             self.config.get("cycle_start"))
        self.operator_dropdown = ft.Dropdown(
            label="Оператор смены", value=saved_op,
            options=[ft.dropdown.Option(o) for o in ops],
        )

        self.shop_controls = {}
        rows = [
            self.operator_dropdown,
            th.text("По графику оператор подставляется сам, при подмене — измените.",
                    role="faint", size=10),
        ]

        for shop, product_key, weight_key in (
            (SHOP1, "product1", "weight1"),
            (SHOP2, "product2", "weight2"),
        ):
            product = record.get(product_key)
            if product not in self.products:
                product = None
            weight = record.get(weight_key)

            product_dropdown = ft.Dropdown(
                label="Продукция", value=product,
                options=[ft.dropdown.Option(p) for p in self.products],
            )
            weight_input = th.field(
                label="Выработка, кг",
                value="" if weight is None else format_weight(weight).replace(" ", ""),
                keyboard_type=ft.KeyboardType.NUMBER,
            )
            hint = th.text("", role="faint", size=11)

            weight_input.on_change = (lambda e, s=shop: self._on_weight_change(e, s))
            self.shop_controls[shop] = {
                "product": product_dropdown, "weight": weight_input, "hint": hint,
            }

            norm = norm_for_shop(shop, self.config)
            rows.append(th.divider())
            rows.append(ft.Row([
                th.text(SHOP_TITLES[shop], size=12, weight=ft.FontWeight.BOLD,
                        expand=True),
                th.text(f"норма {format_weight(norm)}", role="faint", size=10),
            ]))
            rows.append(ft.Row([product_dropdown, weight_input], spacing=8))
            rows.append(hint)
            self._refresh_hint(shop)

        rows.append(th.text("Цех 2 работает не каждую ночь — оставьте поля пустыми, "
                            "если линия не запускалась.", role="faint", size=10))

        self.production_block = ft.Column(rows, spacing=8, tight=True)

    def _parse_weight(self, shop, silent=False):
        """None — данных нет. False — ошибка ввода."""
        field = self.shop_controls[shop]["weight"]
        raw = (field.value or "").replace(",", ".").replace(" ", "").strip()
        if not raw:
            field.error_text = None
            return None
        try:
            value = float(raw)
        except ValueError:
            if not silent:
                field.error_text = "Введите число"
            return False
        if value < 0:
            if not silent:
                field.error_text = "Не может быть отрицательным"
            return False
        if value > WEIGHT_MAX:
            if not silent:
                field.error_text = f"Максимум {int(WEIGHT_MAX)}"
            return False
        field.error_text = None
        return value

    def _refresh_hint(self, shop):
        hint = self.shop_controls[shop]["hint"]
        norm = norm_for_shop(shop, self.config)
        value = self._parse_weight(shop, silent=True)

        if value is None or value is False:
            hint.value = "Данных нет"
            hint.color = self.th.color("text_faint")
            return
        delta = value - norm
        if delta >= 0:
            hint.value = f"↑ Норма выполнена: +{format_weight(delta)} кг"
            hint.color = "#6ee7b7"
        else:
            hint.value = f"↓ Недовыработка: {format_weight(-delta)} кг"
            hint.color = "#f87171"

    def _on_weight_change(self, e, shop):
        sync_value(e)
        self._refresh_hint(shop)
        safe_update(self.shop_controls[shop]["hint"])

    # ---------- трекер ----------
    def _build_timeline(self):
        self.timeline_list = ft.Column(spacing=2, tight=True)
        self.break_total = self.th.text("", role="dim", size=11)
        self._refresh_timeline()

    def _all_events(self):
        """Сохранённые минус помеченные к удалению, плюс ещё не записанные."""
        kept = [row for row in self.saved_events if row[0] not in self.removed_ids]
        return kept + [(None, t, e) for t, e in self.pending_events]

    def _refresh_timeline(self):
        th = self.th
        rows = []
        for event_id, event_time, event_type in self._all_events():
            pending = event_id is None
            label = f"• {event_time} → {event_type}" + ("  (не сохранено)" if pending else "")
            rows.append(ft.Row([
                ft.Text(label, size=12,
                        color=th.color("text_dim") if pending else th.color("text"),
                        expand=True),
                ft.IconButton(ft.Icons.CLOSE, icon_size=15, icon_color="#fca5a5",
                              on_click=lambda e, i=event_id, t=event_time:
                                  self._remove_event(i, t)),
            ], spacing=0, tight=True))
        self.timeline_list.controls = rows

        total = break_seconds([(t, e) for _i, t, e in self._all_events()])
        self.break_total.value = (f"Перекуры за смену: {format_duration(total)}"
                                  if total else "Перекуров пока нет")

    def _add_event(self, event_type):
        self.pending_events.append((datetime.now().strftime("%H:%M:%S"), event_type))
        self._refresh_timeline()
        safe_update(self.timeline_list)
        safe_update(self.break_total)

    def _remove_event(self, event_id, event_time):
        if event_id is None:
            self.pending_events = [(t, e) for t, e in self.pending_events
                                   if t != event_time]
        else:
            # только помечаем: реальное удаление произойдёт по "Сохранить"
            self.removed_ids.add(event_id)
        self._refresh_timeline()
        safe_update(self.timeline_list)
        safe_update(self.break_total)

    # ---------- статус ----------
    def _on_status_change(self, e=None):
        value = self.status_dropdown.value or (e.data if e else None)
        if value:
            self.status_dropdown.value = value
        self._apply_status_visibility()
        safe_update(self.work_block)
        safe_update(self.body)

    def _apply_status_visibility(self, initial=False):
        is_work = (self.status_dropdown.value == STATUS_WORK)
        self.work_block.visible = is_work
        if not is_work:
            # нерабочий день не должен тянуть за собой часы
            self.hours_slider.value = 0
        elif not initial and self.hours_slider.value == 0:
            self.hours_slider.value = hours_for_arrival(ARRIVAL_OPTIONS[self.arrival_index])

    # ==========================================
    # СОХРАНЕНИЕ И УДАЛЕНИЕ
    # ==========================================
    def _save(self, e=None):
        weights = {}
        for shop in (SHOP1, SHOP2):
            value = self._parse_weight(shop)
            if value is False:
                self.error_text.value = "Проверьте выработку — введено не число"
                safe_update(self.shop_controls[shop]["weight"])
                safe_update(self.error_text)
                return
            weights[shop] = value
        self.error_text.value = ""

        # ---- мой день ----
        status = self.status_dropdown.value
        if status == STATUS_NONE:
            db.delete_shift(self.date_str)
        elif status == STATUS_WORK:
            db.save_shift(
                self.date_str, float(self.hours_slider.value), status,
                ARRIVAL_OPTIONS[self.arrival_index],
                (self.note_input.value or "").strip() or None,
            )
        else:
            db.save_shift(self.date_str, 0.0, status, None, None)

        # ---- производство ----
        if weights[SHOP1] is None and weights[SHOP2] is None:
            db.delete_production(self.date_str)
        else:
            db.save_production(
                self.date_str, self.operator_dropdown.value,
                self.shop_controls[SHOP1]["product"].value, weights[SHOP1],
                self.shop_controls[SHOP2]["product"].value, weights[SHOP2],
            )

        # ---- трекер ----
        db.delete_timeline_events(self.removed_ids)
        if self.pending_events:
            db.add_timeline_bulk(self.date_str, self.pending_events)

        close_dialog(self.page, self.dialog)
        self.ctx.refresh_after_change()

    def _cancel(self, e=None):
        # Ничего не записано и ничего не удалено — просто закрываем.
        close_dialog(self.page, self.dialog)

    def _confirm_delete(self, e=None):
        def do_delete():
            db.delete_day(self.date_str)
            close_dialog(self.page, self.dialog)
            self.ctx.refresh_after_change()

        confirm_dialog(
            self.ctx, "Очистить день?",
            f"За {self.date_obj.strftime('%d.%m.%Y')} будут удалены моя смена, "
            "данные производства и хронология. Это необратимо.",
            do_delete, confirm_label="Очистить",
        )

    def open(self):
        open_dialog(self.page, self.dialog)

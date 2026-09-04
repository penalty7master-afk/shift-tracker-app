from datetime import datetime

import flet as ft

from calculations import (break_seconds, format_duration, format_weight,
                          get_operator_for_date, hours_for_arrival)
from constants import from datetime import datetime

import flet as ft

from calculations import (break_seconds, format_duration, format_weight,
                          get_operator_for_date, hours_for_arrival)
from constants import (ARRIVAL_LABELS, ARRIVAL_OPTIONS, DAY_STATUSES, EVENT_BREAK,
                       EVENT_WORK, FULL_SHIFT_HOURS, STATUS_WORK, WEIGHT_MAX,
                       WEIGHT_NORM)
from database import db
from views.common import (bind_event, close_dialog, confirm_dialog, dialog_height,
                          dialog_width, open_dialog, safe_update, sync_value)

ON_ACCENT_TEXT = "#101014"


def show_day_modal(ctx, date_obj):
    DayModal(ctx, date_obj).open()


class DayModal:
    def __init__(self, ctx, date_obj):
        self.ctx = ctx
        self.page = ctx.page
        self.th = ctx.theme
        self.config = ctx.config
        self.date_obj = date_obj
        self.date_str = date_obj.strftime("%Y-%m-%d")

        self.products = db.get_products()
        self.norms = {name: norm for name, norm in self.products}

        self.existing = db.get_shift(self.date_str)
        self.shift = self.existing or self._blank_shift()

        self.saved_events = list(db.get_timeline(self.date_str))
        self.pending_events = []
        # Удаления тоже отложены: до "Сохранить" база не трогается,
        # поэтому "Отмена" честно возвращает всё на место.
        self.removed_ids = set()

        self._build()

    # ==========================================
    # ИСХОДНЫЕ ДАННЫЕ
    # ==========================================
    def _blank_shift(self):
        first_product = self.products[0][0] if self.products else None
        return {
            "hours": FULL_SHIFT_HOURS,
            "status": STATUS_WORK,
            "product": first_product,
            "weight": self.norms.get(first_product, WEIGHT_NORM),
            "arrival_status": ARRIVAL_OPTIONS[0],
            "operator": None,
            "note": "",
            "holiday": False,
        }

    def _op_names(self):
        return [self.config.get(f"op{i}") for i in range(1, 5)]

    # ==========================================
    # СБОРКА
    # ==========================================
    def _build(self):
        th = self.th
        ops = self._op_names()
        default_op = get_operator_for_date(self.date_obj, ops,
                                           self.config.get("cycle_start"))

        self.status_dropdown = ft.Dropdown(
            label="Статус дня",
            value=self.shift.get("status") or STATUS_WORK,
            options=[ft.dropdown.Option(s) for s in DAY_STATUSES],
        )
        bind_event(self.status_dropdown, self._on_status_change,
                   "on_change", "on_select", "on_changed")

        saved_op = self.shift.get("operator") or default_op
        if saved_op not in ops:
            saved_op = default_op
        self.operator_dropdown = ft.Dropdown(
            label="Оператор смены (подмена)",
            value=saved_op,
            options=[ft.dropdown.Option(o) for o in ops],
        )

        mult = self.config.get("holiday_mult") or 1.0
        self.holiday_switch = ft.Switch(
            label=f"Праздничная смена (×{mult:g})",
            value=bool(self.shift.get("holiday")),
            active_color=th.accent(),
        )

        raw_hours = self.shift.get("hours")
        self.hours_slider = ft.Slider(
            min=0, max=11, divisions=22,
            value=FULL_SHIFT_HOURS if raw_hours is None else float(raw_hours),
            label="{value} ч",
            active_color=th.accent(),
        )

        self._build_arrival()
        self._build_product()
        self._build_note()
        self._build_timeline()

        self.error_text = ft.Text("", color="#fca5a5", size=12)

        # Шапка вне скролла: подпись "Статус дня" не уезжает и не режется.
        self.header = ft.Column(
            [self.status_dropdown, self.operator_dropdown, self.holiday_switch],
            spacing=10, tight=True,
        )

        self.work_block = ft.Column([
            th.text("Время прибытия:", role="dim", size=11),
            self.arrival_row,
            th.text("Корректировка часов (ручная):", role="dim", size=11),
            self.hours_slider,
            self.product_dropdown,
            self.weight_input,
            self.norm_hint,
            th.divider(),
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

        self.body = ft.Column(
            [self.work_block, th.divider(), self.note_input, self.error_text],
            scroll=ft.ScrollMode.AUTO, spacing=10, expand=True,
        )

        self._apply_status_visibility(initial=True)

        actions = [
            ft.TextButton("Отмена", on_click=self._cancel),
            ft.TextButton("Сохранить", on_click=self._save),
        ]
        if self.existing:
            actions.insert(0, ft.TextButton(
                "Очистить", on_click=self._confirm_delete,
                style=ft.ButtonStyle(color="#f87171")))

        self.dialog = ft.AlertDialog(
            modal=True,
            title=th.text(f"Смена: {self.date_obj.strftime('%d.%m.%Y')}",
                          size=16, weight=ft.FontWeight.BOLD),
            content=ft.Container(
                width=dialog_width(self.page),
                height=dialog_height(self.page),
                padding=ft.Padding.only(top=10, left=4, right=4),
                content=ft.Column([self.header, self.body], spacing=10, expand=True),
            ),
            actions=actions,
        )

    # ---------- время прибытия ----------
    def _build_arrival(self):
        try:
            index = ARRIVAL_OPTIONS.index(
                self.shift.get("arrival_status") or ARRIVAL_OPTIONS[0])
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

    # ---------- линия и выработка ----------
    def _build_product(self):
        names = [name for name, _norm in self.products]
        saved = self.shift.get("product")
        if saved not in names:
            saved = names[0] if names else None

        self.product_dropdown = ft.Dropdown(
            label="Линия / участок", value=saved,
            options=[ft.dropdown.Option(n) for n in names],
        )
        bind_event(self.product_dropdown, self._on_product_change,
                   "on_change", "on_select", "on_changed")

        self.weight_input = self.th.field(
            label="Выработка за смену (кг)",
            value=format_weight(self.shift.get("weight", WEIGHT_NORM)),
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        self.weight_input.on_change = self._on_weight_change
        self.norm_hint = self.th.text("", role="faint", size=11)
        self._refresh_norm_hint()

    def _current_norm(self):
        return float(self.norms.get(self.product_dropdown.value, WEIGHT_NORM) or WEIGHT_NORM)

    def _refresh_norm_hint(self):
        norm = self._current_norm()
        value = self._parse_weight(silent=True)
        if value is None:
            self.norm_hint.value = f"Норма этой линии: {format_weight(norm)} кг"
            self.norm_hint.color = self.th.color("text_faint")
            return
        delta = value - norm
        if delta >= 0:
            self.norm_hint.value = f"Норма выполнена: +{format_weight(delta)} кг"
            self.norm_hint.color = "#6ee7b7"
        else:
            self.norm_hint.value = (f"Недовыработка: {format_weight(-delta)} кг "
                                    f"из {format_weight(norm)}")
            self.norm_hint.color = "#fbbf24"

    def _on_product_change(self, e=None):
        value = self.product_dropdown.value or (e.data if e else None)
        if value:
            self.product_dropdown.value = value
        self._refresh_norm_hint()
        safe_update(self.norm_hint)

    def _on_weight_change(self, e):
        sync_value(e)
        self._refresh_norm_hint()
        safe_update(self.norm_hint)

    def _parse_weight(self, silent=False):
        raw = (self.weight_input.value or "").replace(",", ".").strip()
        try:
            value = float(raw)
        except ValueError:
            if not silent:
                self.weight_input.error_text = "Введите число, например 2100"
            return None
        if value < 0:
            if not silent:
                self.weight_input.error_text = "Выработка не может быть отрицательной"
            return None
        if value > WEIGHT_MAX:
            if not silent:
                self.weight_input.error_text = f"Слишком много, максимум {int(WEIGHT_MAX)}"
            return None
        return value

    # ---------- заметка ----------
    def _build_note(self):
        self.note_input = self.th.field(
            label="Заметка к смене", value=self.shift.get("note") or "",
            multiline=True, min_lines=2, max_lines=4,
        )

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
        self.holiday_switch.visible = is_work
        if not is_work:
            # нерабочий день не должен тянуть за собой часы и коэффициент
            self.hours_slider.value = 0
            self.holiday_switch.value = False
        elif not initial and self.hours_slider.value == 0:
            self.hours_slider.value = hours_for_arrival(ARRIVAL_OPTIONS[self.arrival_index])

    # ==========================================
    # СОХРАНЕНИЕ И УДАЛЕНИЕ
    # ==========================================
    def _save(self, e=None):
        is_work = (self.status_dropdown.value == STATUS_WORK)

        if is_work:
            weight = self._parse_weight()
            if weight is None:
                # SnackBar под модальным диалогом не виден — пишем в само поле
                safe_update(self.weight_input)
                return
            self.weight_input.error_text = None
            hours = float(self.hours_slider.value)
            arrival = ARRIVAL_OPTIONS[self.arrival_index]
            product = self.product_dropdown.value
            holiday = bool(self.holiday_switch.value)
        else:
            weight, hours, arrival, product, holiday = 0.0, 0.0, None, None, False

        db.save_shift(
            self.date_str, hours, self.status_dropdown.value, product, weight,
            arrival, self.operator_dropdown.value,
            (self.note_input.value or "").strip() or None, holiday,
        )
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
            db.delete_shift(self.date_str)
            close_dialog(self.page, self.dialog)
            self.ctx.refresh_after_change()

        confirm_dialog(
            self.ctx, "Очистить день?",
            f"Запись за {self.date_obj.strftime('%d.%m.%Y')} и её хронология "
            "будут удалены безвозвратно.",
            do_delete, confirm_label="Очистить",
        )

    def open(self):
        open_dialog(self.page, self.dialog)(ARRIVAL_LABELS, ARRIVAL_OPTIONS, DAY_STATUSES, EVENT_BREAK,
                       EVENT_WORK, FULL_SHIFT_HOURS, STATUS_WORK, WEIGHT_MAX,
                       WEIGHT_NORM)
from database import db
from views.common import (bind_event, close_dialog, confirm_dialog, dialog_height,
                          dialog_width, open_dialog, safe_update, sync_value)

ON_ACCENT_TEXT = "#101014"


def show_day_modal(ctx, date_obj):
    DayModal(ctx, date_obj).open()


class DayModal:
    def __init__(self, ctx, date_obj):
        self.ctx = ctx
        self.page = ctx.page
        self.th = ctx.theme
        self.config = ctx.config
        self.date_obj = date_obj
        self.date_str = date_obj.strftime("%Y-%m-%d")

        self.existing = db.get_shift(self.date_str)
        self.shift = self.existing or self._blank_shift()

        self.products = db.get_products()
        self.norms = {name: norm for name, norm in self.products}

        self.saved_events = list(db.get_timeline(self.date_str))
        self.pending_events = []

        self._build()

    # ==========================================
    # ИСХОДНЫЕ ДАННЫЕ
    # ==========================================
    def _blank_shift(self):
        first_product = self.products[0][0] if getattr(self, "products", None) else None
        return {
            "hours": FULL_SHIFT_HOURS,
            "status": STATUS_WORK,
            "product": first_product,
            "weight": WEIGHT_NORM,
            "arrival_status": ARRIVAL_OPTIONS[0],
            "operator": None,
            "note": "",
            "holiday": False,
        }

    def _op_names(self):
        return [self.config.get(f"op{i}") for i in range(1, 5)]

    # ==========================================
    # СБОРКА
    # ==========================================
    def _build(self):
        th = self.th
        ops = self._op_names()
        default_op = get_operator_for_date(self.date_obj, ops,
                                           self.config.get("cycle_start"))

        # исходный словарь мог собраться до загрузки products
        if not self.shift.get("product") and self.products:
            self.shift["product"] = self.products[0][0]

        self.status_dropdown = ft.Dropdown(
            label="Статус дня",
            value=self.shift.get("status") or STATUS_WORK,
            options=[ft.dropdown.Option(s) for s in DAY_STATUSES],
        )
        bind_event(self.status_dropdown, self._on_status_change,
                   "on_change", "on_select", "on_changed")

        saved_op = self.shift.get("operator") or default_op
        if saved_op not in ops:
            saved_op = default_op
        self.operator_dropdown = ft.Dropdown(
            label="Оператор смены (подмена)",
            value=saved_op,
            options=[ft.dropdown.Option(o) for o in ops],
        )

        mult = self.config.get("holiday_mult") or 1.0
        self.holiday_switch = ft.Switch(
            label=f"Праздничная смена (×{mult:g})",
            value=bool(self.shift.get("holiday")),
            active_color=th.accent(),
        )

        raw_hours = self.shift.get("hours")
        self.hours_slider = ft.Slider(
            min=0, max=11, divisions=22,
            value=FULL_SHIFT_HOURS if raw_hours is None else float(raw_hours),
            label="{value} ч",
            active_color=th.accent(),
        )

        self._build_arrival()
        self._build_product()
        self._build_note()
        self._build_timeline()

        self.error_text = ft.Text("", color="#fca5a5", size=12)

        # Шапка вне скролла: подпись "Статус дня" не уезжает и не режется.
        self.header = ft.Column(
            [self.status_dropdown, self.operator_dropdown, self.holiday_switch],
            spacing=10, tight=True,
        )

        self.work_block = ft.Column([
            th.text("Время прибытия:", role="dim", size=11),
            self.arrival_row,
            th.text("Корректировка часов (ручная):", role="dim", size=11),
            self.hours_slider,
            self.product_dropdown,
            self.weight_input,
            self.norm_hint,
            th.divider(),
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

        self.body = ft.Column(
            [self.work_block, th.divider(), self.note_input, self.error_text],
            scroll=ft.ScrollMode.AUTO, spacing=10, expand=True,
        )

        self._apply_status_visibility(initial=True)

        actions = [
            ft.TextButton("Отмена", on_click=lambda e: close_dialog(self.page, self.dialog)),
            ft.TextButton("Сохранить", on_click=self._save),
        ]
        if self.existing:
            actions.insert(0, ft.TextButton(
                "Очистить", on_click=self._confirm_delete,
                style=ft.ButtonStyle(color="#f87171")))

        self.dialog = ft.AlertDialog(
            modal=True,
            title=th.text(f"Смена: {self.date_obj.strftime('%d.%m.%Y')}",
                          size=16, weight=ft.FontWeight.BOLD),
            content=ft.Container(
                width=dialog_width(self.page),
                height=dialog_height(self.page),
                padding=ft.Padding.only(top=10, left=4, right=4),
                content=ft.Column([self.header, self.body], spacing=10, expand=True),
            ),
            actions=actions,
        )

    # ---------- время прибытия ----------
    def _build_arrival(self):
        try:
            index = ARRIVAL_OPTIONS.index(
                self.shift.get("arrival_status") or ARRIVAL_OPTIONS[0])
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

    # ---------- продукт и выработка ----------
    def _build_product(self):
        names = [name for name, _norm in self.products]
        saved = self.shift.get("product")
        if saved not in names:
            saved = names[0] if names else None

        self.product_dropdown = ft.Dropdown(
            label="Тип продукта", value=saved,
            options=[ft.dropdown.Option(n) for n in names],
        )
        bind_event(self.product_dropdown, self._on_product_change,
                   "on_change", "on_select", "on_changed")

        self.weight_input = self.th.field(
            label="Выработка продукции (кг)",
            value=format_weight(self.shift.get("weight", WEIGHT_NORM)),
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        self.weight_input.on_change = self._on_weight_change
        self.norm_hint = self.th.text("", role="faint", size=11)
        self._refresh_norm_hint()

    def _current_norm(self):
        return float(self.norms.get(self.product_dropdown.value, WEIGHT_NORM) or WEIGHT_NORM)

    def _refresh_norm_hint(self):
        norm = self._current_norm()
        value = self._parse_weight(silent=True)
        if value is None:
            self.norm_hint.value = f"Норма продукта: {format_weight(norm)} кг"
            self.norm_hint.color = self.th.color("text_faint")
            return
        delta = value - norm
        if delta >= 0:
            self.norm_hint.value = f"Норма выполнена: +{format_weight(delta)} кг"
            self.norm_hint.color = "#6ee7b7"
        else:
            self.norm_hint.value = f"Недовыработка: {format_weight(-delta)} кг из {format_weight(norm)}"
            self.norm_hint.color = "#fbbf24"

    def _on_product_change(self, e=None):
        self._refresh_norm_hint()
        safe_update(self.norm_hint)

    def _on_weight_change(self, e):
        sync_value(e)
        self._refresh_norm_hint()
        safe_update(self.norm_hint)

    def _parse_weight(self, silent=False):
        raw = (self.weight_input.value or "").replace(",", ".").strip()
        try:
            value = float(raw)
        except ValueError:
            if not silent:
                self.weight_input.error_text = "Введите число, например 2100"
            return None
        if value < 0:
            if not silent:
                self.weight_input.error_text = "Выработка не может быть отрицательной"
            return None
        if value > WEIGHT_MAX:
            if not silent:
                self.weight_input.error_text = f"Слишком много, максимум {int(WEIGHT_MAX)}"
            return None
        return value

    # ---------- заметка ----------
    def _build_note(self):
        self.note_input = self.th.field(
            label="Заметка к смене", value=self.shift.get("note") or "",
            multiline=True, min_lines=2, max_lines=4,
        )

    # ---------- трекер ----------
    def _build_timeline(self):
        self.timeline_list = ft.Column(spacing=2, tight=True)
        self.break_total = self.th.text("", role="dim", size=11)
        self._refresh_timeline()

    def _all_events(self):
        return list(self.saved_events) + [(None, t, e) for t, e in self.pending_events]

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
            db.delete_timeline_event(event_id)
            self.saved_events = [r for r in self.saved_events if r[0] != event_id]
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
        self.holiday_switch.visible = is_work
        if not is_work:
            # нерабочий день не должен тянуть за собой часы и коэффициент
            self.hours_slider.value = 0
            self.holiday_switch.value = False
        elif not initial and self.hours_slider.value == 0:
            self.hours_slider.value = hours_for_arrival(ARRIVAL_OPTIONS[self.arrival_index])

    # ==========================================
    # СОХРАНЕНИЕ И УДАЛЕНИЕ
    # ==========================================
    def _save(self, e=None):
        is_work = (self.status_dropdown.value == STATUS_WORK)

        if is_work:
            weight = self._parse_weight()
            if weight is None:
                # SnackBar под модальным диалогом не виден — пишем в само поле
                safe_update(self.weight_input)
                return
            self.weight_input.error_text = None
            hours = float(self.hours_slider.value)
            arrival = ARRIVAL_OPTIONS[self.arrival_index]
            product = self.product_dropdown.value
            holiday = bool(self.holiday_switch.value)
        else:
            weight, hours, arrival, product, holiday = 0.0, 0.0, None, None, False

        db.save_shift(
            self.date_str, hours, self.status_dropdown.value, product, weight,
            arrival, self.operator_dropdown.value,
            (self.note_input.value or "").strip() or None, holiday,
        )
        if self.pending_events:
            db.add_timeline_bulk(self.date_str, self.pending_events)

        close_dialog(self.page, self.dialog)
        self.ctx.refresh_after_change()

    def _confirm_delete(self, e=None):
        def do_delete():
            db.delete_shift(self.date_str)
            close_dialog(self.page, self.dialog)
            self.ctx.refresh_after_change()

        confirm_dialog(
            self.ctx, "Очистить день?",
            f"Запись за {self.date_obj.strftime('%d.%m.%Y')} и её хронология "
            "будут удалены безвозвратно.",
            do_delete, confirm_label="Очистить",
        )

    def open(self):
        open_dialog(self.page, self.dialog)

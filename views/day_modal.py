from datetime import datetime

import flet as ft

import haptics
from calculations import (break_seconds, format_duration, format_weight,
                          get_operator_for_date, hours_for_arrival,
                          norm_for_shop, op_names_from)
from constants import (ARRIVAL_LABELS, ARRIVAL_OPTIONS, DAY_STATUSES, EVENT_BREAK,
                       EVENT_WORK, FULL_SHIFT_HOURS, PREMIUM_PAY_MAX, SHOP1, SHOP2,
                       SHOP_TITLES, STATUS_PREMIUM_OFF, STATUS_WORK, WEIGHT_MAX)
from database import db
from views.common import (bind_event, close_dialog, confirm_dialog, dialog_height,
                          dialog_width, open_dialog, refresh_tree, release_focus,
                          safe_update, sync_value, touch)

# Служебное значение выпадающего списка: день не отмечен как мой.
STATUS_NONE = "— не отмечено —"

WEIGHT_FIELD_WIDTH = 92          # хватает на 5 символов
PRODUCT_GAP = 8

_INSTANCE = {"modal": None}


def show_day_modal(ctx, date_obj):
    """
    Один экземпляр на всё приложение. Раньше DayModal собирался заново на
    каждый клик по дню: ~70 контролов и диалог уходили по сокету целиком,
    отсюда была заметная пауза при открытии.
    """
    modal = _INSTANCE.get("modal")
    if modal is None or modal.ctx is not ctx:
        modal = DayModal(ctx)
        _INSTANCE["modal"] = modal
    modal.open_for(date_obj)


def drop_day_modal():
    """Сбрасывает кэш — например, после восстановления базы."""
    _INSTANCE["modal"] = None


class DayModal:
    """
    Два независимых блока:
      «Моя смена» — статус, приход, часы, трекер, заметка;
      «Производство за ночь» — оператор и выработка цехов, доступно всегда.
    """

    def __init__(self, ctx):
        self.ctx = ctx
        self.page = ctx.page
        self.th = ctx.theme
        self.config = ctx.config

        self.date_obj = None
        self.date_str = None
        self.shift = None
        self.production = None
        self.products = []
        self.saved_events = []
        self.pending_events = []
        self.removed_ids = set()
        self.saved_once = False       # после первого сохранения «Отмена» → «Выход»

        # Дерево модалки строится один раз и не регистрируется в теме.
        self.th.begin_temp()
        try:
            self._build()
        finally:
            self.th.end_temp()

    # ==========================================
    # СБОРКА (один раз)
    # ==========================================
    def _build(self):
        th = self.th

        self._build_my_shift()
        self._build_production()

        self.error_text = ft.Text("", color="#fca5a5", size=12)
        self.saved_hint = ft.Text("", color="#6ee7b7", size=11)

        self.title_text = th.text("", size=16, weight=ft.FontWeight.BOLD)

        self.body = ft.Column([
            th.text("МОЯ СМЕНА", size=12, weight=ft.FontWeight.BOLD),
            self.status_dropdown,
            self.premium_pay_block,
            self.work_block,
            self.note_input,
            th.divider(),
            th.text("ПРОИЗВОДСТВО ЗА НОЧЬ", size=12, weight=ft.FontWeight.BOLD),
            self.production_block,
            self.error_text,
            self.saved_hint,
        ], scroll=ft.ScrollMode.HIDDEN, spacing=10, expand=True)

        self.clear_button = ft.TextButton(
            "Очистить", on_click=self._confirm_delete,
            style=ft.ButtonStyle(color="#f87171"))
        self.exit_button = ft.TextButton("Отмена", on_click=self._exit)

        # Очистить слева · Сохранить в центре · Выход справа
        self.actions_row = ft.Row([
            self.clear_button,
            ft.Container(expand=True),
            ft.TextButton("Сохранить", on_click=self._save),
            ft.Container(expand=True),
            self.exit_button,
        ], spacing=2, tight=True,
            vertical_alignment=ft.CrossAxisAlignment.CENTER)

        self.content_holder = ft.Container(
            padding=ft.Padding.only(top=10, left=4, right=4),
            content=self.body,
        )

        self.dialog = ft.AlertDialog(
            modal=True,
            title=self.title_text,
            content=self.content_holder,
            actions=[self.actions_row],
        )

    # ---------- блок «Моя смена» ----------
    def _build_my_shift(self):
        th = self.th

        self.status_dropdown = ft.Dropdown(
            label="Статус дня", value=STATUS_NONE,
            options=[ft.dropdown.Option(STATUS_NONE)] +
                    [ft.dropdown.Option(s) for s in DAY_STATUSES],
        )
        bind_event(self.status_dropdown, self._on_status_change,
                   "on_change", "on_select", "on_changed")

        self.hours_slider = ft.Slider(
            min=0, max=11, divisions=22, value=FULL_SHIFT_HOURS,
            label="{value} ч", active_color=th.accent(),
        )

        self._build_arrival()

        self.note_input = th.field(
            label="Заметка к дню", value="",
            multiline=True, min_lines=2, max_lines=4,
        )

        self.premium_pay_input = th.field(
            label="Фактически выплаченная премия, ₽", value="",
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        self.premium_pay_block = ft.Column([
            self.premium_pay_input,
            th.text("Сумма войдёт в начисление и в аналитику за месяц.",
                    role="faint", size=10),
        ], spacing=6, tight=True)

        self._build_timeline()

        self.work_block = ft.Column([
            th.text("Время прибытия:", role="dim", size=11),
            self.arrival_row,
            th.text("Корректировка часов (ручная):", role="dim", size=11),
            self.hours_slider,
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
        th = self.th
        self.arrival_index = 0
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
            bgcolor=th.color("field_bg"), border_radius=11, padding=3,
            content=ft.Row(self.arrival_cells, spacing=3),
        )
        self._paint_arrival()

    def _paint_arrival(self):
        th = self.th
        for position, cell in enumerate(self.arrival_cells):
            active = position == self.arrival_index
            cell.bgcolor = th.accent() if active else "#00000000"
            cell.content.controls[0].color = (th.on_accent() if active
                                              else th.color("text"))
            cell.content.controls[1].color = (th.on_accent() if active
                                              else th.color("text_dim"))

    def _select_arrival(self, index):
        touch(self.ctx)
        self.arrival_index = index
        self.hours_slider.value = hours_for_arrival(ARRIVAL_OPTIONS[index])
        self.ctx.dialog_dirty = True
        haptics.select()
        self._paint_arrival()
        refresh_tree(self.arrival_row, self.hours_slider)

    # ---------- блок «Производство за ночь» ----------
    def _build_production(self):
        th = self.th

        self.operator_dropdown = ft.Dropdown(label="Оператор смены", options=[])

        self.shop_controls = {}
        rows = [
            self.operator_dropdown,
            th.text("По графику оператор подставляется сам, при подмене — измените.",
                    role="faint", size=10),
        ]

        for shop in (SHOP1, SHOP2):
            # Ширина выпадающего списка считается от ширины окна: с expand
            # внутри tight-колонки Flet отдавал ему почти нулевую ширину,
            # и слово «Продукция» ломалось на четыре строки.
            product_dropdown = ft.Dropdown(
                label="Продукция", options=[], dense=True, text_size=13,
                width=self._product_width(),
            )
            weight_input = th.field(
                label="кг", width=WEIGHT_FIELD_WIDTH, value="",
                text_align=ft.TextAlign.RIGHT, dense=True, text_size=13,
                keyboard_type=ft.KeyboardType.NUMBER,
            )
            hint = th.text("", role="faint", size=11)

            weight_input.on_change = (lambda e, s=shop: self._on_weight_change(e, s))
            norm_text = th.text("", role="faint", size=10)

            self.shop_controls[shop] = {
                "product": product_dropdown, "weight": weight_input,
                "hint": hint, "norm": norm_text,
            }

            rows.append(th.divider())
            rows.append(ft.Row([
                th.text(SHOP_TITLES[shop], size=12, weight=ft.FontWeight.BOLD,
                        expand=True),
                norm_text,
            ]))
            rows.append(ft.Row([product_dropdown, weight_input],
                               spacing=PRODUCT_GAP,
                               vertical_alignment=ft.CrossAxisAlignment.START))
            rows.append(hint)

        rows.append(th.text("Цех 2 работает не каждую ночь — оставьте поля пустыми, "
                            "если линия не запускалась.", role="faint", size=10))

        self.production_block = ft.Column(rows, spacing=8, tight=True)

    def _product_width(self):
        return max(150, dialog_width(self.page) - WEIGHT_FIELD_WIDTH
                   - PRODUCT_GAP - 34)

    # ==========================================
    # ОТКРЫТИЕ: перезаполнение готового дерева
    # ==========================================
    def open_for(self, date_obj):
        self.date_obj = date_obj
        self.date_str = date_obj.strftime("%Y-%m-%d")
        self.saved_once = False

        self.products = db.get_products()
        self.shift = db.get_shift(self.date_str)
        self.production = db.get_production(self.date_str)
        self.saved_events = list(db.get_timeline(self.date_str))
        self.pending_events = []
        self.removed_ids = set()

        self._load_my_shift()
        self._load_production()
        self._refresh_timeline()

        self.title_text.value = date_obj.strftime("%d.%m.%Y")
        self.error_text.value = ""
        self.saved_hint.value = ""
        self.exit_button.text = "Отмена"
        self.clear_button.visible = bool(self.shift or self.production
                                         or self.saved_events)

        width = dialog_width(self.page)
        self.content_holder.width = width
        self.content_holder.height = dialog_height(self.page)
        for shop in (SHOP1, SHOP2):
            self.shop_controls[shop]["product"].width = self._product_width()

        self.ctx.dialog_dirty = False
        open_dialog(self.page, self.dialog, self.ctx)

    def _load_my_shift(self):
        shift = self.shift or {}
        self.status_dropdown.value = shift.get("status") or STATUS_NONE

        raw_hours = shift.get("hours")
        self.hours_slider.value = (FULL_SHIFT_HOURS if raw_hours is None
                                   else float(raw_hours))
        self.hours_slider.active_color = self.th.accent()

        try:
            self.arrival_index = ARRIVAL_OPTIONS.index(
                shift.get("arrival_status") or ARRIVAL_OPTIONS[0])
        except ValueError:
            self.arrival_index = 0
        self._paint_arrival()

        self.note_input.value = shift.get("note") or ""
        self.note_input.error_text = None

        raw_pay = shift.get("premium_pay")
        self.premium_pay_input.value = ("" if raw_pay is None
                                        else f"{float(raw_pay):.0f}")
        self.premium_pay_input.error_text = None

        self._apply_status_visibility(initial=True)

    def _load_production(self):
        record = self.production or {}
        ops = op_names_from(self.config)

        saved_op = record.get("operator")
        if saved_op not in ops:
            saved_op = get_operator_for_date(self.date_obj, ops,
                                             self.config.get("cycle_start"))
        self.operator_dropdown.options = [ft.dropdown.Option(o) for o in ops]
        self.operator_dropdown.value = saved_op

        for shop, product_key, weight_key in (
            (SHOP1, "product1", "weight1"),
            (SHOP2, "product2", "weight2"),
        ):
            slot = self.shop_controls[shop]
            product = record.get(product_key)
            if product not in self.products:
                product = None
            weight = record.get(weight_key)

            slot["product"].options = [ft.dropdown.Option(p) for p in self.products]
            slot["product"].value = product
            slot["weight"].value = ("" if weight is None
                                    else format_weight(weight).replace(" ", ""))
            slot["weight"].error_text = None
            slot["norm"].value = f"норма {format_weight(norm_for_shop(shop, self.config))}"
            self._refresh_hint(shop)

    # ==========================================
    # ВВОД
    # ==========================================
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
                field.error_text = "Число"
            return False
        if value < 0 or value > WEIGHT_MAX:
            if not silent:
                field.error_text = "Диапазон"
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
        touch(self.ctx)
        sync_value(e)
        self.ctx.dialog_dirty = True
        self._refresh_hint(shop)
        safe_update(self.shop_controls[shop]["hint"])

    def _parse_premium_pay(self, silent=False):
        raw = (self.premium_pay_input.value or "").replace(",", ".").replace(" ", "").strip()
        if not raw:
            self.premium_pay_input.error_text = None
            return None
        try:
            value = float(raw)
        except ValueError:
            if not silent:
                self.premium_pay_input.error_text = "Введите число"
            return False
        if value < 0 or value > PREMIUM_PAY_MAX:
            if not silent:
                self.premium_pay_input.error_text = "Недопустимая сумма"
            return False
        self.premium_pay_input.error_text = None
        return value

    # ---------- трекер ----------
    def _build_timeline(self):
        self.timeline_list = ft.Column(spacing=2, tight=True)
        self.break_total = self.th.text("", role="dim", size=11)

    def _all_events(self):
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
        touch(self.ctx)
        haptics.select()
        self.pending_events.append((datetime.now().strftime("%H:%M:%S"), event_type))
        self.ctx.dialog_dirty = True
        self._refresh_timeline()
        refresh_tree(self.timeline_list, self.break_total)

    def _remove_event(self, event_id, event_time):
        touch(self.ctx)
        if event_id is None:
            self.pending_events = [(t, e) for t, e in self.pending_events
                                   if t != event_time]
        else:
            # только помечаем: реальное удаление произойдёт по «Сохранить»
            self.removed_ids.add(event_id)
        self.ctx.dialog_dirty = True
        self._refresh_timeline()
        refresh_tree(self.timeline_list, self.break_total)

    # ---------- статус ----------
    def _on_status_change(self, e=None):
        touch(self.ctx)
        value = self.status_dropdown.value or (e.data if e else None)
        if value:
            self.status_dropdown.value = value
        self.ctx.dialog_dirty = True
        self._apply_status_visibility()
        refresh_tree(self.work_block, self.premium_pay_block, self.body)

    def _apply_status_visibility(self, initial=False):
        status = self.status_dropdown.value
        is_work = (status == STATUS_WORK)
        is_premium_off = (status == STATUS_PREMIUM_OFF)

        self.work_block.visible = is_work
        self.premium_pay_block.visible = is_premium_off

        if not is_work:
            self.hours_slider.value = 0
        elif not initial and self.hours_slider.value == 0:
            self.hours_slider.value = hours_for_arrival(ARRIVAL_OPTIONS[self.arrival_index])

    # ==========================================
    # СОХРАНЕНИЕ
    # ==========================================
    def _collect(self):
        weights = {}
        for shop in (SHOP1, SHOP2):
            value = self._parse_weight(shop)
            if value is False:
                self.error_text.value = "Проверьте выработку — введено не число"
                refresh_tree(self.shop_controls[shop]["weight"], self.error_text)
                return False
            weights[shop] = value

        premium_pay = self._parse_premium_pay()
        if premium_pay is False:
            self.error_text.value = "Проверьте сумму премии"
            refresh_tree(self.premium_pay_input, self.error_text)
            return False

        self.error_text.value = ""
        return weights, premium_pay

    def _persist(self):
        collected = self._collect()
        if collected is False:
            return False
        weights, premium_pay = collected

        status = self.status_dropdown.value
        note = (self.note_input.value or "").strip() or None

        # ---- мой день ----
        if status == STATUS_NONE:
            if note:
                db.save_shift(self.date_str, 0.0, None, None, note, None)
            else:
                db.delete_shift(self.date_str)
        elif status == STATUS_WORK:
            db.save_shift(self.date_str, float(self.hours_slider.value), status,
                          ARRIVAL_OPTIONS[self.arrival_index], note, None)
        elif status == STATUS_PREMIUM_OFF:
            db.save_shift(self.date_str, 0.0, status, None, note, premium_pay)
        else:
            db.save_shift(self.date_str, 0.0, status, None, note, None)

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
        self.removed_ids = set()
        self.saved_events = list(db.get_timeline(self.date_str))
        self.pending_events = []
        self._refresh_timeline()
        return True

    def _save(self, e=None):
        """Сохраняет и оставляет окно открытым: можно сразу продолжить ввод."""
        touch(self.ctx)
        release_focus(self.page, self.note_input, self.premium_pay_input,
                      self.shop_controls[SHOP1]["weight"],
                      self.shop_controls[SHOP2]["weight"])
        if not self._persist():
            haptics.warn()
            return

        haptics.confirm()
        self.shift = db.get_shift(self.date_str)
        self.production = db.get_production(self.date_str)
        self.clear_button.visible = bool(self.shift or self.production
                                         or self.saved_events)
        # После сохранения «Отмена» вводит в заблуждение: данные уже в базе,
        # кнопка просто закрывает окно.
        self.saved_once = True
        self.exit_button.text = "Выход"
        self.ctx.dialog_dirty = False
        self.saved_hint.value = (f"Сохранено в "
                                 f"{datetime.now().strftime('%H:%M:%S')} — "
                                 "можно продолжать ввод")

        self.ctx.refresh_after_change()
        refresh_tree(self.saved_hint, self.actions_row,
                     self.timeline_list, self.break_total, self.body)

    def _exit(self, e=None):
        """Закрывает окно. Уже сохранённое остаётся в базе, последние
        несохранённые правки теряются — это и означает подпись кнопки."""
        touch(self.ctx)
        close_dialog(self.page, self.dialog, self.ctx)

    def _confirm_delete(self, e=None):
        touch(self.ctx)

        def do_delete():
            db.delete_day(self.date_str)
            close_dialog(self.page, self.dialog, self.ctx)
            self.ctx.refresh_after_change()

        confirm_dialog(
            self.ctx, "Очистить день?",
            f"За {self.date_obj.strftime('%d.%m.%Y')} будут удалены моя смена, "
            "данные производства и хронология. Это необратимо.",
            do_delete, confirm_label="Очистить",
        )

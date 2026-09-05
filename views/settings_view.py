from datetime import datetime

import flet as ft

import haptics
from calculations import format_weight, is_day_mode, mode_of
from constants import (DEFAULT_ACCENT, DEFAULT_BG_THEME, MODE_DAY, MODE_NIGHT,
                       MODE_SUBTITLES, MODE_TITLES, SHOP1, SHOP2, SHOP_TITLES,
                       TAX_OPTIONS, THEME_ACCENTS, THEME_BACKGROUNDS,
                       WEIGHT_MAX, term)
from database import db
from exporter import (backup_database, export_csv, export_pdf, find_backups,
                      restore_database)
from views.color_picker import show_color_picker
from views.common import (bind_event, confirm_dialog, info_dialog, refresh_tree,
                          release_focus, safe_update, touch)

BACK_KEY_SIZE = 46
SWATCH_SIZE = 42
PRODUCT_ROW_HEIGHT = 34
CYCLE_FIELD_WIDTH = 168

# Боковой отступ карточек — тот же, что у календаря и аналитики в ui.py.
SIDE_PADDING = 10
MAX_CONTENT_WIDTH = 620


class SettingsView:
    def __init__(self, ctx):
        self.ctx = ctx
        self.page = ctx.page
        self.th = ctx.theme
        self.pending_delete = None
        self._build()

    # ==========================================
    # СБОРКА
    # ==========================================
    def _build(self):
        th = self.th

        self._build_mode()

        self.rate_field = th.field(label="Стоимость 1 часа оклада (₽)",
                                   keyboard_type=ft.KeyboardType.NUMBER)
        bind_event(self.rate_field, self._validate_rate, "on_blur")
        self.rate_hint = th.text("", role="faint", size=10)

        # Имена операторов по центру ячейки
        self.op_fields = [th.field(label=f"Оператор {i}", expand=True,
                                   text_align=ft.TextAlign.CENTER)
                          for i in range(1, 5)]

        self.cycle_field = th.field(label="Старт графика",
                                    width=CYCLE_FIELD_WIDTH,
                                    hint_text="ГГГГ-ММ-ДД")
        bind_event(self.cycle_field, self._validate_cycle, "on_blur")
        self.cycle_hint = th.text("", role="faint", size=10, expand=True)

        self.norm1_field = th.field(label=SHOP_TITLES[SHOP1], expand=True,
                                    keyboard_type=ft.KeyboardType.NUMBER)
        self.norm2_field = th.field(label=SHOP_TITLES[SHOP2], expand=True,
                                    keyboard_type=ft.KeyboardType.NUMBER)
        bind_event(self.norm1_field, self._validate_norms, "on_blur")
        bind_event(self.norm2_field, self._validate_norms, "on_blur")
        self.norm_title = th.text("", size=12, weight=ft.FontWeight.BOLD)

        self._build_tax()
        self._build_theme()
        self._build_products()
        self._build_data()

        self.error_text = ft.Text("", color="#fca5a5", size=12)

        back_key = th.glass_key(
            ft.Icon(ft.Icons.ARROW_BACK, size=20, color=th.color("text")),
            self._back, size=BACK_KEY_SIZE)

        self.scroll_column = ft.Column([
            ft.SafeArea(content=ft.Container(
                padding=ft.Padding.only(top=8, bottom=4, left=6),
                content=ft.Row([
                    back_key,
                    th.text("Настройки", size=18, weight=ft.FontWeight.BOLD),
                ], spacing=14,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER),
            )),

            th.card(ft.Column([
                th.text("Режим работы", size=12, weight=ft.FontWeight.BOLD),
                self.mode_row,
                self.mode_hint,
            ], spacing=10, tight=True)),

            th.card(ft.Column([
                th.text("Оплата", size=12, weight=ft.FontWeight.BOLD),
                self.rate_field,
                self.rate_hint,
                th.text("Налог с начисленного", role="dim", size=11),
                self.tax_row,
            ], spacing=10, tight=True)),

            th.card(ft.Column([
                self.norm_title,
                self.norm1_field,
                self.norm2_field,
            ], spacing=10, tight=True)),

            th.card(ft.Column([
                th.text("Операторы и их график", size=12, weight=ft.FontWeight.BOLD),
                ft.Row([self.op_fields[0], self.op_fields[1]], spacing=8),
                ft.Row([self.op_fields[2], self.op_fields[3]], spacing=8),
                # Поле короткое — освободившееся место справа занимает
                # пояснение, которое раньше отнимало отдельную строку.
                ft.Row([self.cycle_field, self.cycle_hint], spacing=10,
                       vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ], spacing=10, tight=True)),

            th.card(ft.Column([
                th.text("Акцентный цвет", size=12, weight=ft.FontWeight.BOLD),
                self.accent_row,
                th.divider(),
                th.text("Фон / тональность", size=12, weight=ft.FontWeight.BOLD),
                self.bg_column,
                th.divider(),
                self.simple_bg_switch,
                th.text("Отключает блюр, светящиеся сферы и анимацию переходов. "
                        "Включайте, если интерфейс подтормаживает.",
                        role="faint", size=10),
                self.haptics_switch,
            ], spacing=10, tight=True)),

            th.card(ft.Column([
                th.text("Каталог продукции", size=12, weight=ft.FontWeight.BOLD),
                ft.Row([self.new_product_input, self.add_product_button], spacing=8),
                th.divider(),
                self.products_list,
                self.fill_button,
            ], spacing=10, tight=True)),

            th.card(ft.Column([
                th.text("Данные", size=12, weight=ft.FontWeight.BOLD),
                ft.Row([self.export_button, self.pdf_button], spacing=8),
                ft.Row([self.backup_button, self.restore_button], spacing=8),
                self.data_hint,
            ], spacing=10, tight=True)),

            self.error_text,
            ft.Row([ft.OutlinedButton("Сменить PIN-код",
                                      on_click=self._change_pin, width=300)],
                   alignment=ft.MainAxisAlignment.CENTER),
            # «Готово» вместо «Сохранить»: акцент, фон, режим и каталог
            # пишутся сразу, а ставка, нормы, операторы и налог — отсюда,
            # с проверкой введённого.
            ft.Row([ft.ElevatedButton("Готово", on_click=self._save, width=300)],
                   alignment=ft.MainAxisAlignment.CENTER),
            ft.Container(height=90),
        ], spacing=14, scroll=ft.ScrollMode.AUTO, expand=True)

        # Карточки упирались в края экрана, тогда как в календаре и
        # аналитике у них есть боковой отступ. Ширина ограничена сверху,
        # чтобы на планшете колонка не расползалась во весь экран.
        self.control = ft.Container(
            expand=True, alignment=ft.Alignment.TOP_CENTER,
            padding=ft.Padding.symmetric(horizontal=SIDE_PADDING),
            content=ft.Container(expand=True, width=MAX_CONTENT_WIDTH,
                                 content=self.scroll_column),
        )

    # ---------- режим смены ----------
    def _build_mode(self):
        th = self.th
        self.mode_cells = []
        cells = []
        for mode in (MODE_NIGHT, MODE_DAY):
            cell = ft.Container(
                expand=1, height=48, border_radius=10,
                alignment=ft.Alignment.CENTER,
                content=ft.Column([
                    ft.Text(MODE_TITLES[mode], size=12,
                            text_align=ft.TextAlign.CENTER),
                    ft.Text(MODE_SUBTITLES[mode], size=9,
                            text_align=ft.TextAlign.CENTER),
                ], spacing=0, tight=True,
                    alignment=ft.MainAxisAlignment.CENTER,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                on_click=lambda e, m=mode: self._select_mode(m),
            )
            self.mode_cells.append((cell, mode))
            cells.append(cell)

        self.mode_row = ft.Container(
            bgcolor=th.color("field_bg"), border_radius=12, padding=3,
            content=ft.Row(cells, spacing=3),
        )
        self.mode_hint = th.text("", role="faint", size=10)

    def _select_mode(self, mode):
        touch(self.ctx)
        if mode_of(self.ctx.config) == mode:
            return
        haptics.select()
        # Пишем сразу: данные разных режимов лежат раздельно, поэтому
        # переключение ничего не теряет и не требует подтверждения.
        db.save_config(shift_mode=mode)
        self.ctx.config.update(db.get_config())
        # Ставка своя у каждого режима: без перечитывания поле осталось бы
        # со старым числом и затёрло бы настройку нового режима.
        self.rate_field.value = str(self.ctx.config[self._rate_key()])
        self.rate_field.error_text = None
        self._paint_mode()
        self._sync_mode_labels()
        # Календарь, аналитика и модалка пересобираются под новый режим.
        self.ctx.rebuild_for_mode()
        refresh_tree(self.mode_row, self.mode_hint, self.rate_field,
                     self.rate_hint, self.norm_title, self.cycle_hint,
                     self.scroll_column)

    def _paint_mode(self):
        th = self.th
        current = mode_of(self.ctx.config)
        for cell, mode in self.mode_cells:
            active = mode == current
            cell.bgcolor = th.accent() if active else "#00000000"
            cell.content.controls[0].color = (th.on_accent() if active
                                              else th.color("text"))
            cell.content.controls[0].weight = (ft.FontWeight.BOLD if active
                                               else None)
            cell.content.controls[1].color = (th.on_accent() if active
                                              else th.color("text_dim"))

    def _sync_mode_labels(self):
        """Подписи, зависящие от режима, обновляются на месте."""
        mode = mode_of(self.ctx.config)
        day = is_day_mode(self.ctx.config)

        self.mode_hint.value = (
            "Расчёты, график операторов и подписи подстроены под "
            f"{'дневную' if day else 'ночную'} смену. Данные другого режима "
            "сохраняются отдельно и не теряются.")
        self.rate_field.label = ("Стоимость 1 часа, дневная смена (₽)" if day
                                 else "Стоимость 1 часа, ночная смена (₽)")
        self.rate_hint.value = ("Ставка своя для каждого режима — "
                                "переключение её не затирает.")
        self.norm_title.value = f"Нормы выработки {term(mode, 'per_shift')}, кг"
        self.cycle_hint.value = (
            "Цикл: день → ночь → отсыпной → выходной. Укажите дату, в которую "
            "Оператор 1 выходил в НОЧЬ — дневная сетка сдвигается сама.")

    # ---------- налог ----------
    def _build_tax(self):
        self.tax_value = 0.0
        self.tax_cells = []
        for label, rate in TAX_OPTIONS:
            cell = ft.Container(
                expand=1, height=40, border_radius=9,
                alignment=ft.Alignment.CENTER,
                content=ft.Text(label, size=11, text_align=ft.TextAlign.CENTER),
                on_click=lambda e, r=rate: self._select_tax(r),
            )
            self.tax_cells.append((cell, rate))
        self.tax_row = ft.Container(
            bgcolor=self.th.color("field_bg"), border_radius=11, padding=3,
            content=ft.Row([cell for cell, _r in self.tax_cells], spacing=3),
        )

    def _select_tax(self, rate):
        touch(self.ctx)
        haptics.select()
        self.tax_value = rate
        self._paint_tax()
        safe_update(self.tax_row)

    def _paint_tax(self):
        th = self.th
        for cell, rate in self.tax_cells:
            active = abs(rate - self.tax_value) < 0.0001
            cell.bgcolor = th.accent() if active else "#00000000"
            cell.content.color = th.on_accent() if active else th.color("text")
            cell.content.weight = ft.FontWeight.BOLD if active else None

    # ---------- тема ----------
    def _build_theme(self):
        th = self.th
        self.accent_cells = []
        cells = []
        for name, color in THEME_ACCENTS.items():
            cell = ft.Container(
                width=SWATCH_SIZE, height=SWATCH_SIZE, border_radius=SWATCH_SIZE // 2,
                bgcolor=color, tooltip=name,
                on_click=lambda e, n=name: self._select_accent(n),
            )
            self.accent_cells.append((cell, name))
            cells.append(cell)

        # Шестая кнопка: произвольный цвет из палитры
        self.custom_cell = ft.Container(
            width=SWATCH_SIZE, height=SWATCH_SIZE, border_radius=SWATCH_SIZE // 2,
            tooltip="Свой цвет",
            gradient=ft.SweepGradient(colors=[
                "#ff6b6b", "#ffd166", "#6ee7b7", "#7dd3fc",
                "#c9a6ff", "#f9a8d4", "#ff6b6b",
            ]),
            content=ft.Icon(ft.Icons.COLORIZE, size=18, color="#ffffff"),
            alignment=ft.Alignment.CENTER,
            on_click=self._open_picker,
        )
        cells.append(self.custom_cell)
        self.accent_row = ft.Row(cells, spacing=10, wrap=True)

        self.bg_cells = []
        rows = []
        for name, palette in THEME_BACKGROUNDS.items():
            swatch = ft.Container(
                width=34, height=34, border_radius=10,
                gradient=ft.LinearGradient(
                    begin=ft.Alignment.TOP_LEFT, end=ft.Alignment.BOTTOM_RIGHT,
                    colors=list(palette["gradient"])),
            )
            label = ft.Text(name, size=12, color=th.color("text"), expand=True)
            row = ft.Container(
                padding=6, border_radius=10,
                content=ft.Row([swatch, label], spacing=10),
                on_click=lambda e, n=name: self._select_bg(n),
            )
            self.bg_cells.append((row, label, name))
            rows.append(row)
        self.bg_column = ft.Column(rows, spacing=4, tight=True)

        self.simple_bg_switch = ft.Switch(label="Режим скорости",
                                          active_color=th.accent())
        bind_event(self.simple_bg_switch, self._on_simple_bg,
                   "on_change", "on_changed")

        self.haptics_switch = ft.Switch(label="Виброотклик",
                                        active_color=th.accent())
        bind_event(self.haptics_switch, self._on_haptics,
                   "on_change", "on_changed")

    def _select_accent(self, name):
        touch(self.ctx)
        haptics.select()
        self.ctx.config["theme"] = name
        self._apply_and_stay()

    def _open_picker(self, e=None):
        touch(self.ctx)

        def apply(color):
            self.ctx.config["theme"] = color
            self._apply_and_stay()

        show_color_picker(self.ctx, self.ctx.config.get("theme"), apply)

    def _select_bg(self, name):
        touch(self.ctx)
        haptics.select()
        self.ctx.config["bg_theme"] = name
        self._apply_and_stay()

    def _on_simple_bg(self, e=None):
        touch(self.ctx)
        self.ctx.config["simple_bg"] = 1 if self.simple_bg_switch.value else 0
        self._apply_and_stay()

    def _on_haptics(self, e=None):
        touch(self.ctx)
        enabled = bool(self.haptics_switch.value)
        self.ctx.config["haptics"] = 1 if enabled else 0
        haptics.set_enabled(enabled)
        if enabled:
            haptics.confirm()
        db.save_config(haptics=1 if enabled else 0)

    def _apply_and_stay(self):
        """Перекрашивает интерфейс, не сбрасывая прокрутку."""
        self.ctx.theme.apply(self.page)
        # Фон живёт в корневом Stack вне дерева настроек: без этой строки
        # выбранная тональность появлялась только после следующего действия.
        self.ctx.theme.refresh_background()
        self._paint_theme_selection()
        self._paint_tax()
        self._paint_mode()
        self._refresh_products()
        self.simple_bg_switch.active_color = self.th.accent()
        self.haptics_switch.active_color = self.th.accent()
        refresh_tree(self.accent_row, self.bg_column, self.tax_row,
                     self.mode_row, self.products_list, self.scroll_column)

    def _paint_theme_selection(self):
        th = self.th
        current = self.ctx.config.get("theme")
        custom = isinstance(current, str) and current.startswith("#")

        for cell, name in self.accent_cells:
            selected = (not custom) and (name == current)
            cell.border = ft.Border.all(3, th.color("text")) if selected else None
            cell.scale = 1.0 if selected else 0.86

        self.custom_cell.border = (ft.Border.all(3, th.color("text")) if custom
                                   else None)
        self.custom_cell.scale = 1.0 if custom else 0.86

        current_bg = self.ctx.config.get("bg_theme")
        for row, label, name in self.bg_cells:
            selected = (name == current_bg)
            row.bgcolor = th.accent_a("33") if selected else "#00000000"
            row.border = ft.Border.all(1, th.accent()) if selected else None
            label.color = th.color("text")
            label.weight = ft.FontWeight.BOLD if selected else None

    # ---------- продукция ----------
    def _build_products(self):
        th = self.th
        self.new_product_input = th.field(label="Новый продукт", expand=True)
        self.add_product_button = ft.ElevatedButton("Добавить",
                                                    on_click=self._add_product)
        self.products_list = ft.Column(spacing=2, tight=True)
        self.fill_button = ft.TextButton("Заполнить типовыми",
                                         on_click=self._fill_products)

    def _refresh_products(self):
        """Подтверждение удаления показывается прямо в строке: диалог
        заставлял страницу настроек прыгать наверх."""
        th = self.th
        mode = mode_of(self.ctx.config)
        short = term(mode, "shifts_short")
        controls = []
        for name in db.get_products():
            label = ft.Text(name, size=14, color=th.color("text"), expand=True)

            if self.pending_delete == name:
                used = db.product_usage_count(name)
                caption = "Удалить?" if not used else f"Удалить? (в {used} {short})"
                controls.append(ft.Row([
                    ft.Text(caption, size=11, color="#fbbf24", expand=True),
                    ft.TextButton("Да", on_click=lambda e, n=name: self._delete_product(n),
                                  style=ft.ButtonStyle(color="#f87171")),
                    ft.TextButton("Нет", on_click=lambda e: self._cancel_delete()),
                ], spacing=2, vertical_alignment=ft.CrossAxisAlignment.CENTER))
                continue

            # height у строки: стандартный IconButton держал 48 px, и семь
            # позиций растягивали карточку на полтора экрана.
            controls.append(ft.Container(height=PRODUCT_ROW_HEIGHT, content=ft.Row([
                label,
                ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_color="#fca5a5",
                              icon_size=18, padding=0,
                              on_click=lambda e, n=name: self._ask_delete(n)),
            ], spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER)))

        self.fill_button.visible = not controls
        self.products_list.controls = controls

    def _fill_products(self, e=None):
        """Каталог при установке пуст: список наименований у каждого свой."""
        touch(self.ctx)
        db.fill_default_products()
        haptics.confirm()
        self.pending_delete = None
        self._refresh_products()
        refresh_tree(self.products_list, self.fill_button)

    def _ask_delete(self, name):
        touch(self.ctx)
        self.pending_delete = name
        self._refresh_products()
        safe_update(self.products_list)

    def _cancel_delete(self):
        self.pending_delete = None
        self._refresh_products()
        safe_update(self.products_list)

    def _delete_product(self, name):
        db.delete_product(name)
        self.pending_delete = None
        self._refresh_products()
        safe_update(self.products_list)

    def _add_product(self, e=None):
        touch(self.ctx)
        name = (self.new_product_input.value or "").strip()
        if not name:
            return
        if db.add_product(name):
            self.new_product_input.value = ""
            self.new_product_input.error_text = None
            release_focus(self.page, self.new_product_input)
        else:
            self.new_product_input.error_text = "Такой продукт уже есть"
        self.pending_delete = None
        self._refresh_products()
        refresh_tree(self.products_list, self.new_product_input)

    # ---------- данные ----------
    def _build_data(self):
        self.export_button = ft.OutlinedButton("Экспорт CSV", expand=True,
                                               on_click=self._export_csv)
        self.pdf_button = ft.OutlinedButton("Экспорт PDF", expand=True,
                                            on_click=self._export_pdf)
        self.backup_button = ft.OutlinedButton("Бэкап базы", expand=True,
                                               on_click=self._backup)
        self.restore_button = ft.OutlinedButton("Восстановить", expand=True,
                                                on_click=self._restore)
        self.data_hint = self.th.text("", role="faint", size=10)

    def _export_csv(self, e=None):
        touch(self.ctx)
        try:
            path = export_csv()
        except Exception as error:
            info_dialog(self.ctx, "Не удалось выгрузить", str(error))
            return
        info_dialog(self.ctx, "Экспорт готов",
                    f"Файл сохранён:\n\n{path}\n\nОткройте его файловым "
                    "менеджером или отправьте себе.")

    def _export_pdf(self, e=None):
        touch(self.ctx)
        year, month = self.ctx.view["year"], self.ctx.view["month"]
        try:
            path = export_pdf(year, month, self.ctx.config)
        except Exception as error:
            info_dialog(self.ctx, "Не удалось выгрузить", str(error))
            return
        info_dialog(self.ctx, "PDF готов",
                    f"Табель за выбранный месяц сохранён:\n\n{path}")

    def _backup(self, e=None):
        touch(self.ctx)
        try:
            path = backup_database()
        except Exception as error:
            info_dialog(self.ctx, "Не удалось сохранить", str(error))
            return
        info_dialog(self.ctx, "Бэкап создан", f"Файл базы сохранён:\n\n{path}")

    def _restore(self, e=None):
        touch(self.ctx)
        backups = find_backups()
        if not backups:
            info_dialog(self.ctx, "Бэкапы не найдены",
                        "Положите файл вида shifts_pro_backup_*.db в папку "
                        "Download и повторите.")
            return
        newest = backups[0]

        def do_restore():
            try:
                restore_database(newest)
            except Exception as error:
                info_dialog(self.ctx, "Не удалось восстановить", str(error))
                return
            self.ctx.config.update(db.get_config())
            self.ctx.show_pin(force_setup=False)

        confirm_dialog(
            self.ctx, "Восстановить базу?",
            f"Текущие данные будут заменены содержимым файла:\n\n{newest}\n\n"
            "Это действие необратимо.",
            do_restore, confirm_label="Восстановить",
        )

    # ==========================================
    # ЗАГРУЗКА / СОХРАНЕНИЕ
    # ==========================================
    def _rate_key(self):
        return "day_hour_rate" if is_day_mode(self.ctx.config) else "hour_rate"

    def load(self):
        config = db.get_config()
        self.ctx.config.update(config)

        self.rate_field.value = str(config[self._rate_key()])
        self.cycle_field.value = config["cycle_start"]
        self.norm1_field.value = format_weight(config["norm_shop1"]).replace(" ", "")
        self.norm2_field.value = format_weight(config["norm_shop2"]).replace(" ", "")
        for index, field in enumerate(self.op_fields):
            field.value = config[f"op{index + 1}"]
            field.error_text = None

        self.tax_value = config["tax_rate"]
        self._paint_tax()
        self._paint_mode()
        self._sync_mode_labels()
        self._paint_theme_selection()
        self.simple_bg_switch.value = bool(config["simple_bg"])
        self.haptics_switch.value = bool(config.get("haptics", 1))
        self.rate_field.error_text = None
        self.cycle_field.error_text = None
        self.norm1_field.error_text = None
        self.norm2_field.error_text = None
        self.error_text.value = ""
        self.new_product_input.error_text = None
        self.pending_delete = None
        self._refresh_products()
        self.data_hint.value = ("CSV содержит обе смены. PDF — табель за "
                                "текущий месяц и режим. Бэкап — копия базы.")

    # ---------- валидация на лету ----------
    def _read_number(self, field, minimum=0.0):
        try:
            value = float((field.value or "").replace(",", ".").replace(" ", ""))
        except ValueError:
            return None
        if value <= minimum or value > WEIGHT_MAX:
            return None
        return value

    def _read_cycle_start(self):
        raw = (self.cycle_field.value or "").strip()
        try:
            datetime.strptime(raw, "%Y-%m-%d")
            return raw
        except ValueError:
            return None

    def _validate_rate(self, e=None):
        bad = self._read_number(self.rate_field) is None
        self.rate_field.error_text = "Введите число больше нуля" if bad else None
        safe_update(self.rate_field)

    def _validate_norms(self, e=None):
        for field in (self.norm1_field, self.norm2_field):
            bad = self._read_number(field) is None
            field.error_text = "Введите число больше нуля" if bad else None
            safe_update(field)

    def _validate_cycle(self, e=None):
        bad = self._read_cycle_start() is None
        self.cycle_field.error_text = "Формат ГГГГ-ММ-ДД" if bad else None
        safe_update(self.cycle_field)

    def _persist(self, rate, norm1, norm2):
        names = [(field.value or "").strip() or f"Оператор {i + 1}"
                 for i, field in enumerate(self.op_fields)]
        values = dict(
            theme=self.ctx.config.get("theme") or DEFAULT_ACCENT,
            bg_theme=self.ctx.config.get("bg_theme") or DEFAULT_BG_THEME,
            op1=names[0], op2=names[1], op3=names[2], op4=names[3],
            tax_rate=self.tax_value,
            cycle_start=self._read_cycle_start() or self.ctx.config["cycle_start"],
            simple_bg=1 if self.simple_bg_switch.value else 0,
            haptics=1 if self.haptics_switch.value else 0,
            norm_shop1=norm1, norm_shop2=norm2,
            shift_mode=mode_of(self.ctx.config),
        )
        # Ставка пишется в ключ своего режима — вторая остаётся нетронутой.
        values[self._rate_key()] = rate
        db.save_config(**values)
        self.ctx.config.update(db.get_config())

    def _save(self, e=None):
        touch(self.ctx)
        release_focus(self.page, self.rate_field, self.cycle_field,
                      self.norm1_field, self.norm2_field,
                      self.new_product_input, *self.op_fields)

        rate = self._read_number(self.rate_field)
        if rate is None:
            self._validate_rate()
            self.error_text.value = "Некорректная ставка"
            safe_update(self.error_text)
            return
        norm1 = self._read_number(self.norm1_field)
        norm2 = self._read_number(self.norm2_field)
        if norm1 is None or norm2 is None:
            self._validate_norms()
            self.error_text.value = "Некорректная норма выработки"
            safe_update(self.error_text)
            return
        if self._read_cycle_start() is None:
            self._validate_cycle()
            self.error_text.value = "Дата старта графика в формате ГГГГ-ММ-ДД"
            safe_update(self.error_text)
            return

        self._persist(rate, norm1, norm2)
        haptics.confirm()
        self.ctx.show_main()

    def _fallback_persist(self):
        """«Назад» и смена PIN тоже сохраняют; некорректные поля остаются прежними."""
        config = self.ctx.config
        self._persist(
            self._read_number(self.rate_field) or config[self._rate_key()],
            self._read_number(self.norm1_field) or config["norm_shop1"],
            self._read_number(self.norm2_field) or config["norm_shop2"],
        )

    def _back(self, e=None):
        touch(self.ctx)
        self._fallback_persist()
        self.ctx.show_main()

    def _change_pin(self, e=None):
        touch(self.ctx)
        # PIN не стираем заранее: старый хеш живёт до подтверждения нового
        self._fallback_persist()
        self.ctx.show_pin(force_setup=True)

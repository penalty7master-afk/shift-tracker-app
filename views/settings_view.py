from datetime import datetime

import flet as ft

from calculations import parse_cycle_start
from constants import (DEFAULT_ACCENT, DEFAULT_BG_THEME, TAX_OPTIONS,
                       THEME_ACCENTS, THEME_BACKGROUNDS, WEIGHT_NORM)
from database import db
from exporter import (backup_database, export_csv, find_backups, restore_database)
from views.common import (bind_event, confirm_dialog, info_dialog, safe_update,
                          sync_value)


class SettingsView:
    def __init__(self, ctx):
        self.ctx = ctx
        self.page = ctx.page
        self.th = ctx.theme
        self._build()

    # ==========================================
    # СБОРКА
    # ==========================================
    def _build(self):
        th = self.th

        self.rate_field = th.field(label="Стоимость 1 часа оклада (₽)",
                                   keyboard_type=ft.KeyboardType.NUMBER)
        self.op_fields = [th.field(label=f"Оператор {i}", expand=True)
                          for i in range(1, 5)]
        self.cycle_field = th.field(label="Старт графика 4/4 (ГГГГ-ММ-ДД)")
        self.holiday_field = th.field(label="Коэффициент праздничной смены",
                                      keyboard_type=ft.KeyboardType.NUMBER)

        self.my_operator_dropdown = ft.Dropdown(label="Мой оператор (для прогноза)",
                                                options=[])
        bind_event(self.my_operator_dropdown, self._on_my_operator,
                   "on_change", "on_select", "on_changed")

        self._build_tax()
        self._build_theme()
        self._build_products()
        self._build_data()

        self.error_text = ft.Text("", color="#fca5a5", size=12)

        self.control = ft.Column([
            ft.Row([
                th.icon_button(ft.Icons.ARROW_BACK, on_click=self._back),
                th.text("Настройки", size=18, weight=ft.FontWeight.BOLD),
            ]),

            th.card(ft.Column([
                th.text("Оплата", size=12, weight=ft.FontWeight.BOLD),
                self.rate_field,
                self.holiday_field,
                th.text("Налог с начисленного", role="dim", size=11),
                self.tax_row,
            ], spacing=10, tight=True)),

            th.card(ft.Column([
                th.text("Операторы и график", size=12, weight=ft.FontWeight.BOLD),
                ft.Row([self.op_fields[0], self.op_fields[1]], spacing=8),
                ft.Row([self.op_fields[2], self.op_fields[3]], spacing=8),
                self.my_operator_dropdown,
                self.cycle_field,
                th.text("От этой даты отсчитывается ротация операторов.",
                        role="faint", size=10),
            ], spacing=10, tight=True)),

            th.card(ft.Column([
                th.text("Акцентный цвет", size=12, weight=ft.FontWeight.BOLD),
                self.accent_row,
                th.divider(),
                th.text("Фон / тональность", size=12, weight=ft.FontWeight.BOLD),
                self.bg_column,
                th.divider(),
                self.simple_bg_switch,
                th.text("Отключает светящиеся сферы и размытие — для слабых устройств.",
                        role="faint", size=10),
            ], spacing=10, tight=True)),

            th.card(ft.Column([
                th.text("Каталог продукции", size=12, weight=ft.FontWeight.BOLD),
                th.text("У каждого продукта своя норма выработки, кг.",
                        role="faint", size=10),
                ft.Row([self.new_product_input, self.new_norm_input], spacing=8),
                ft.Row([self.add_product_button],
                       alignment=ft.MainAxisAlignment.END),
                th.divider(),
                self.products_list,
            ], spacing=10, tight=True)),

            th.card(ft.Column([
                th.text("Данные", size=12, weight=ft.FontWeight.BOLD),
                ft.Row([self.export_button, self.backup_button], spacing=8),
                self.restore_button,
                self.data_hint,
            ], spacing=10, tight=True)),

            self.error_text,
            ft.OutlinedButton("Сменить PIN-код", on_click=self._change_pin, width=300),
            ft.ElevatedButton("Сохранить", on_click=self._save, width=300),
        ], spacing=14, scroll=ft.ScrollMode.AUTO, expand=True)

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
        self.tax_value = rate
        self._paint_tax()
        safe_update(self.tax_row)

    def _paint_tax(self):
        th = self.th
        for cell, rate in self.tax_cells:
            active = abs(rate - self.tax_value) < 0.0001
            cell.bgcolor = th.accent() if active else "#00000000"
            cell.content.color = "#101014" if active else th.color("text")
            cell.content.weight = ft.FontWeight.BOLD if active else None

    # ---------- тема ----------
    def _build_theme(self):
        th = self.th
        self.accent_cells = []
        for name, color in THEME_ACCENTS.items():
            cell = ft.Container(
                width=42, height=42, border_radius=21, bgcolor=color,
                tooltip=name,
                on_click=lambda e, n=name: self._select_accent(n),
            )
            self.accent_cells.append((cell, name))
        self.accent_row = ft.Row([cell for cell, _n in self.accent_cells],
                                 spacing=10, wrap=True)

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

        self.simple_bg_switch = ft.Switch(label="Упрощённый фон (экономия)",
                                          active_color=th.accent())
        bind_event(self.simple_bg_switch, self._on_simple_bg,
                   "on_change", "on_changed")

    def _select_accent(self, name):
        self.ctx.config["theme"] = name
        self._paint_theme_selection()
        self.ctx.apply_theme()

    def _select_bg(self, name):
        self.ctx.config["bg_theme"] = name
        self._paint_theme_selection()
        self.ctx.apply_theme()

    def _on_simple_bg(self, e=None):
        self.ctx.config["simple_bg"] = 1 if self.simple_bg_switch.value else 0
        self.ctx.apply_theme()

    def _paint_theme_selection(self):
        th = self.th
        current_accent = self.ctx.config.get("theme")
        for cell, name in self.accent_cells:
            selected = (name == current_accent)
            cell.border = ft.Border.all(3, th.color("text")) if selected else None
            cell.scale = 1.0 if selected else 0.86

        current_bg = self.ctx.config.get("bg_theme")
        for row, label, name in self.bg_cells:
            selected = (name == current_bg)
            row.bgcolor = th.accent_a("33") if selected else "#00000000"
            row.border = ft.Border.all(1, th.accent()) if selected else None
            label.weight = ft.FontWeight.BOLD if selected else None

    # ---------- продукция ----------
    def _build_products(self):
        th = self.th
        self.new_product_input = th.field(label="Новый продукт", expand=True)
        self.new_norm_input = th.field(label="Норма, кг", width=110,
                                       keyboard_type=ft.KeyboardType.NUMBER,
                                       value=str(int(WEIGHT_NORM)))
        self.add_product_button = ft.ElevatedButton("Добавить",
                                                    on_click=self._add_product)
        self.products_list = ft.Column(spacing=4, tight=True)

    def _refresh_products(self):
        th = self.th
        controls = []
        for name, norm in db.get_products():
            norm_field = th.field(value=str(int(norm)), width=90, dense=True,
                                  keyboard_type=ft.KeyboardType.NUMBER)
            norm_field.on_change = (
                lambda e, n=name: self._update_norm(n, e))
            controls.append(ft.Row([
                ft.Text(name, size=12, color=th.color("text"), expand=True),
                norm_field,
                ft.IconButton(ft.Icons.DELETE_OUTLINE, icon_color="#fca5a5",
                              icon_size=20,
                              on_click=lambda e, n=name: self._confirm_delete_product(n)),
            ], spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER))
        self.products_list.controls = controls

    def _update_norm(self, name, e):
        sync_value(e)
        try:
            value = float((e.control.value or "").replace(",", "."))
        except ValueError:
            return
        if value > 0:
            db.update_product_norm(name, value)
            self.ctx.config["product_norms"] = db.get_product_norms()

    def _add_product(self, e=None):
        name = (self.new_product_input.value or "").strip()
        if not name:
            return
        try:
            norm = float((self.new_norm_input.value or "").replace(",", "."))
        except ValueError:
            norm = WEIGHT_NORM
        if db.add_product(name, norm if norm > 0 else WEIGHT_NORM):
            self.new_product_input.value = ""
            self.new_product_input.error_text = None
        else:
            self.new_product_input.error_text = "Такой продукт уже есть"
        self.ctx.config["product_norms"] = db.get_product_norms()
        self._refresh_products()
        safe_update(self.products_list)
        safe_update(self.new_product_input)

    def _confirm_delete_product(self, name):
        used = db.product_usage_count(name)
        message = f"Продукт «{name}» будет удалён из каталога."
        if used:
            message += (f"\n\nОн уже указан в {used} смен(ах) — эти записи "
                        "сохранятся, но останутся со ссылкой на удалённый продукт.")

        def do_delete():
            db.delete_product(name)
            self.ctx.config["product_norms"] = db.get_product_norms()
            self._refresh_products()
            safe_update(self.products_list)

        confirm_dialog(self.ctx, "Удалить продукт?", message, do_delete)

    # ---------- данные ----------
    def _build_data(self):
        self.export_button = ft.OutlinedButton("Экспорт CSV", expand=True,
                                               on_click=self._export_csv)
        self.backup_button = ft.OutlinedButton("Бэкап базы", expand=True,
                                               on_click=self._backup)
        self.restore_button = ft.OutlinedButton("Восстановить из бэкапа", width=300,
                                                on_click=self._restore)
        self.data_hint = self.th.text("", role="faint", size=10)

    def _export_csv(self, e=None):
        try:
            path = export_csv(db.get_all_shifts())
        except Exception as error:
            info_dialog(self.ctx, "Не удалось выгрузить", str(error))
            return
        info_dialog(self.ctx, "Экспорт готов",
                    f"Файл сохранён:\n\n{path}\n\nОткройте его файловым "
                    "менеджером или отправьте себе.")

    def _backup(self, e=None):
        try:
            path = backup_database(db)
        except Exception as error:
            info_dialog(self.ctx, "Не удалось сохранить", str(error))
            return
        info_dialog(self.ctx, "Бэкап создан", f"Файл базы сохранён:\n\n{path}")

    def _restore(self, e=None):
        backups = find_backups()
        if not backups:
            info_dialog(self.ctx, "Бэкапы не найдены",
                        "Положите файл вида shifts_pro_backup_*.db в папку "
                        "Download и повторите.")
            return
        newest = backups[0]

        def do_restore():
            try:
                restore_database(db, newest)
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
    def load(self):
        config = db.get_config()
        self.ctx.config.update(config)

        self.rate_field.value = str(config["hour_rate"])
        self.holiday_field.value = f"{config['holiday_mult']:g}"
        self.cycle_field.value = config["cycle_start"]
        for index, field in enumerate(self.op_fields):
            field.value = config[f"op{index + 1}"]

        self._refresh_my_operator_options()
        self.tax_value = config["tax_rate"]
        self._paint_tax()
        self._paint_theme_selection()
        self.simple_bg_switch.value = bool(config["simple_bg"])
        self.error_text.value = ""
        self.new_product_input.error_text = None
        self._refresh_products()
        self.data_hint.value = ("CSV открывается в Excel. Бэкап — полная копия "
                                "базы, её можно вернуть на любом устройстве.")

    def _refresh_my_operator_options(self):
        names = [(field.value or "").strip() or f"Оператор {i + 1}"
                 for i, field in enumerate(self.op_fields)]
        self.my_operator_dropdown.options = (
            [ft.dropdown.Option("")] + [ft.dropdown.Option(n) for n in names])
        current = self.ctx.config.get("my_operator")
        self.my_operator_dropdown.value = current if current in names else ""

    def _on_my_operator(self, e=None):
        self.ctx.config["my_operator"] = self.my_operator_dropdown.value or ""

    def _read_rate(self):
        try:
            return float((self.rate_field.value or "").replace(",", "."))
        except ValueError:
            return None

    def _read_holiday_mult(self):
        try:
            value = float((self.holiday_field.value or "").replace(",", "."))
            return value if value > 0 else None
        except ValueError:
            return None

    def _read_cycle_start(self):
        raw = (self.cycle_field.value or "").strip()
        try:
            datetime.strptime(raw, "%Y-%m-%d")
            return raw
        except ValueError:
            return None

    def _persist(self, rate):
        names = [(field.value or "").strip() or f"Оператор {i + 1}"
                 for i, field in enumerate(self.op_fields)]
        my_op = self.my_operator_dropdown.value or ""
        db.save_config(
            hour_rate=rate,
            theme=self.ctx.config.get("theme") or DEFAULT_ACCENT,
            bg_theme=self.ctx.config.get("bg_theme") or DEFAULT_BG_THEME,
            op1=names[0], op2=names[1], op3=names[2], op4=names[3],
            tax_rate=self.tax_value,
            cycle_start=self._read_cycle_start() or self.ctx.config["cycle_start"],
            my_operator=my_op if my_op in names else "",
            simple_bg=1 if self.simple_bg_switch.value else 0,
            holiday_mult=self._read_holiday_mult() or self.ctx.config["holiday_mult"],
        )
        self.ctx.config.update(db.get_config())

    def _save(self, e=None):
        rate = self._read_rate()
        if rate is None or rate <= 0:
            self.error_text.value = "Некорректная ставка"
            safe_update(self.error_text)
            return
        if self._read_cycle_start() is None:
            self.error_text.value = "Дата старта графика в формате ГГГГ-ММ-ДД"
            safe_update(self.error_text)
            return
        self._persist(rate)
        self.ctx.show_main()

    def _back(self, e=None):
        # "Назад" тоже сохраняет; при некорректной ставке остаётся прежняя
        rate = self._read_rate()
        self._persist(rate if rate and rate > 0 else self.ctx.config["hour_rate"])
        self.ctx.show_main()

    def _change_pin(self, e=None):
        # PIN не стираем заранее: старый хеш живёт до подтверждения нового
        rate = self._read_rate()
        self._persist(rate if rate and rate > 0 else self.ctx.config["hour_rate"])
        self.ctx.show_pin(force_setup=True)

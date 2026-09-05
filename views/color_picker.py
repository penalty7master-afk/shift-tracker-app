"""Выбор произвольного акцентного цвета. Результат — HEX-строка,
она пишется прямо в config["theme"]; колонка в базе уже TEXT,
поэтому миграция не нужна."""
import colorsys

import flet as ft

from views.common import (close_dialog, dialog_width, open_dialog, refresh_tree,
                          safe_update)

HUE_STEPS = 30
PREVIEW_SIZE = 64


def hsv_to_hex(hue, sat, val):
    r, g, b = colorsys.hsv_to_rgb((hue % 360) / 360.0, sat, val)
    return "#{:02x}{:02x}{:02x}".format(int(r * 255), int(g * 255), int(b * 255))


def hex_to_hsv(value):
    """Возвращает (тон, насыщенность, яркость) или None, если не HEX."""
    if not isinstance(value, str) or not value.startswith("#"):
        return None
    raw = value.lstrip("#")
    if len(raw) == 8:          # #AARRGGBB — отбрасываем альфу
        raw = raw[2:]
    if len(raw) != 6:
        return None
    try:
        r = int(raw[0:2], 16) / 255.0
        g = int(raw[2:4], 16) / 255.0
        b = int(raw[4:6], 16) / 255.0
    except ValueError:
        return None
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    return h * 360.0, s, v


def show_color_picker(ctx, current, on_apply):
    ColorPicker(ctx, current, on_apply).open()


class ColorPicker:
    def __init__(self, ctx, current, on_apply):
        self.ctx = ctx
        self.page = ctx.page
        self.th = ctx.theme
        self.on_apply = on_apply

        parsed = hex_to_hsv(current)
        # Акценты приложения светлые и мягкие, поэтому по умолчанию
        # берём невысокую насыщенность.
        self.hue, self.sat, self.val = parsed or (268.0, 0.35, 1.0)

        self._build()

    def _build(self):
        th = self.th

        self.preview = ft.Container(
            width=PREVIEW_SIZE, height=PREVIEW_SIZE, border_radius=PREVIEW_SIZE // 2,
            bgcolor=self.current_hex(),
            border=ft.Border.all(2, th.color("text")),
        )
        self.hex_label = th.text(self.current_hex().upper(), role="dim", size=13)

        # Радужная шкала: подсказка, какому положению ползунка какой тон
        self.hue_strip = ft.Container(
            height=14, border_radius=7,
            content=ft.Row([
                ft.Container(expand=1, bgcolor=hsv_to_hex(i * 360 / HUE_STEPS, 0.62, 1.0))
                for i in range(HUE_STEPS)
            ], spacing=0),
        )

        self.hue_slider = ft.Slider(min=0, max=359, value=self.hue,
                                    on_change=self._on_hue)
        self.sat_slider = ft.Slider(min=0, max=100, value=self.sat * 100,
                                    on_change=self._on_sat)
        self.val_slider = ft.Slider(min=25, max=100, value=self.val * 100,
                                    on_change=self._on_val)

        body = ft.Column([
            ft.Row([self.preview, ft.Column([
                th.text("Свой цвет", size=13, weight=ft.FontWeight.BOLD),
                self.hex_label,
            ], spacing=2, tight=True)], spacing=14,
                vertical_alignment=ft.CrossAxisAlignment.CENTER),
            th.text("Тон", role="dim", size=11),
            self.hue_strip,
            self.hue_slider,
            th.text("Насыщенность", role="dim", size=11),
            self.sat_slider,
            th.text("Яркость", role="dim", size=11),
            self.val_slider,
        ], spacing=8, tight=True, scroll=ft.ScrollMode.HIDDEN)

        self.dialog = ft.AlertDialog(
            modal=True,
            title=th.text("Акцентный цвет", size=16, weight=ft.FontWeight.BOLD),
            content=ft.Container(width=dialog_width(self.page), content=body),
            actions=[
                ft.TextButton("Отмена", on_click=self._cancel),
                ft.TextButton("Применить", on_click=self._accept),
            ],
        )

    def current_hex(self):
        return hsv_to_hex(self.hue, self.sat, self.val)

    def _sync(self):
        color = self.current_hex()
        self.preview.bgcolor = color
        self.hex_label.value = color.upper()
        refresh_tree(self.preview, self.hex_label)

    def _on_hue(self, e):
        self.hue = float(e.control.value)
        self._sync()

    def _on_sat(self, e):
        self.sat = float(e.control.value) / 100.0
        self._sync()

    def _on_val(self, e):
        self.val = float(e.control.value) / 100.0
        self._sync()

    def _cancel(self, e=None):
        close_dialog(self.page, self.dialog, self.ctx)

    def _accept(self, e=None):
        close_dialog(self.page, self.dialog, self.ctx)
        self.on_apply(self.current_hex())

    def open(self):
        open_dialog(self.page, self.dialog, self.ctx)

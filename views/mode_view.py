"""
Экран первого запуска: выбор режима работы до создания PIN-кода.
Показывается один раз за всю историю пользования — дальше режим
меняется переключателем в настройках.
"""
import flet as ft

import haptics
from constants import (MODE_DAY, MODE_NIGHT, MODE_SUBTITLES, MODE_TITLES,
                       SHIFT_MODES)
from database import db
from views.common import refresh_tree

CARD_HEIGHT = 132
ICONS = {
    MODE_NIGHT: ft.Icons.BEDTIME_OUTLINED,
    MODE_DAY: ft.Icons.LIGHT_MODE_OUTLINED,
}


class ModeView:
    def __init__(self, ctx, on_done):
        self.ctx = ctx
        self.th = ctx.theme
        self.on_done = on_done
        self.selected = MODE_NIGHT
        self._build()

    def _build(self):
        th = self.th

        self.cards = {}
        cards = []
        for mode in SHIFT_MODES:
            icon = ft.Icon(ICONS[mode], size=30)
            title = ft.Text(MODE_TITLES[mode], size=16,
                            weight=ft.FontWeight.BOLD)
            subtitle = ft.Text(MODE_SUBTITLES[mode], size=12)
            check = ft.Icon(ft.Icons.CHECK_CIRCLE, size=22, visible=False)

            card = ft.Container(
                height=CARD_HEIGHT, border_radius=18, padding=18,
                content=ft.Row([
                    icon,
                    ft.Column([title, subtitle], spacing=3, tight=True,
                              expand=True),
                    check,
                ], spacing=16,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER),
                on_click=lambda e, m=mode: self._select(m),
                animate_scale=ft.Animation(120, ft.AnimationCurve.EASE_OUT),
            )
            self.cards[mode] = (card, icon, title, subtitle, check)
            cards.append(card)

        self.control = ft.SafeArea(
            expand=True,
            content=ft.Container(
                expand=True, padding=24,
                alignment=ft.Alignment.CENTER,
                content=ft.Column([
                    th.text("КАЛЕНДАРЬ СМЕН PRO", role="faint", size=12),
                    th.text("Как вы работаете?", size=26,
                            weight=ft.FontWeight.BOLD),
                    th.text("Приложение подстроит расчёты, график операторов "
                            "и подписи под выбранный режим. Позже это можно "
                            "изменить в настройках.",
                            role="dim", size=13,
                            text_align=ft.TextAlign.CENTER),
                    ft.Container(height=18),
                    cards[0],
                    ft.Container(height=10),
                    cards[1],
                    ft.Container(height=24),
                    ft.Row([ft.ElevatedButton("Продолжить", width=280,
                                              height=48,
                                              on_click=self._confirm)],
                           alignment=ft.MainAxisAlignment.CENTER),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=6, tight=True,
                    scroll=ft.ScrollMode.HIDDEN),
            ),
        )
        self._paint()

    def _paint(self):
        th = self.th
        for mode, (card, icon, title, subtitle, check) in self.cards.items():
            active = mode == self.selected
            # Блюр только на выбранной карточке: их всего две, и это
            # единственный экран, где стекло действительно заметно.
            card.bgcolor = th.accent_a("2e") if active else th.color("glass")
            card.border = ft.Border.all(2 if active else 1,
                                        th.accent() if active
                                        else th.color("glass_border"))
            card.blur = (ft.Blur(18, 18) if (active and not th.simple_bg())
                         else None)
            card.scale = 1.0 if active else 0.97
            icon.color = th.accent() if active else th.color("text_dim")
            title.color = th.color("text")
            subtitle.color = th.color("text_dim") if active else th.color("text_faint")
            check.color = th.accent()
            check.visible = active

    def _select(self, mode):
        if mode == self.selected:
            return
        haptics.select()
        self.selected = mode
        self._paint()
        refresh_tree(*[card for card, *_rest in self.cards.values()])

    def _confirm(self, e=None):
        haptics.confirm()
        db.save_config(shift_mode=self.selected, mode_chosen=1)
        self.ctx.config.update(db.get_config())
        self.on_done()

    def show(self):
        self.selected = self.ctx.config.get("shift_mode") or MODE_NIGHT
        self._paint()

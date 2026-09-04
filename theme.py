import flet as ft

from constants import (DEFAULT_ACCENT, DEFAULT_BG_THEME, THEME_ACCENTS,
                       THEME_BACKGROUNDS)

TRANSPARENT = "#00000000"

# Роль -> ключ палитры. "accent" обрабатывается отдельно.
TEXT_ROLES = {
    "normal": "text",
    "dim": "text_dim",
    "faint": "text_faint",
}


def sync_value(e):
    """Flet не всегда пишет ввод в .value до потери фокуса — синхронизируем вручную.
    Здесь сознательно нет page.update(): раньше он дёргался на каждый символ."""
    e.control.value = e.data


class Theme:
    """Единая точка правды по цветам. Держит ссылки на созданные контролы,
    чтобы смена палитры применялась мгновенно и без перестройки дерева."""

    def __init__(self, config):
        self.config = config
        self._backgrounds = []
        self._cards = []
        self._texts = []
        self._fields = []
        self._icons = []
        self._dividers = []

    # ==========================================
    # ЦВЕТА
    # ==========================================
    def accent(self):
        return THEME_ACCENTS.get(self.config.get("theme"), THEME_ACCENTS[DEFAULT_ACCENT])

    def accent_a(self, alpha_hex):
        """Акцент с прозрачностью: accent_a('40') -> '#40c9a6ff'."""
        return f"#{alpha_hex}{self.accent().lstrip('#')}"

    def palette(self):
        return THEME_BACKGROUNDS.get(self.config.get("bg_theme"),
                                     THEME_BACKGROUNDS[DEFAULT_BG_THEME])

    def color(self, key):
        return self.palette().get(key, "#ffffff")

    def is_dark(self):
        return bool(self.palette().get("dark", True))

    def simple_bg(self):
        return bool(self.config.get("simple_bg"))

    def _role_color(self, role):
        if role == "accent":
            return self.accent()
        return self.color(TEXT_ROLES.get(role, "text"))

    def _sphere_colors(self):
        pal = self.palette()
        if pal.get("spheres"):
            return list(pal["spheres"])
        return [self.accent_a(a) for a in pal["sphere_alpha"]]

    # ==========================================
    # ФАБРИКИ КОНТРОЛОВ
    # ==========================================
    def text(self, value="", role="normal", **kwargs):
        control = ft.Text(value, **kwargs)
        control.color = self._role_color(role)
        self._texts.append((control, role))
        return control

    def field(self, **kwargs):
        kwargs.setdefault("on_change", sync_value)
        control = ft.TextField(**kwargs)
        self._paint_field(control)
        self._fields.append(control)
        return control

    def icon_button(self, icon, role="normal", **kwargs):
        control = ft.IconButton(icon, **kwargs)
        control.icon_color = self._role_color(role)
        self._icons.append((control, role))
        return control

    def divider(self):
        control = ft.Divider(color=self.color("glass_border"), height=9)
        self._dividers.append(control)
        return control

    def _paint_field(self, control):
        control.bgcolor = self.color("field_bg")
        control.color = self.color("text")
        control.border_color = self.color("field_border")
        control.label_style = ft.TextStyle(color=self.color("text_dim"))

    # ==========================================
    # СТЕКЛО
    # ==========================================
    def card(self, content, blur=False, **extra):
        """blur=True оставляем только для одной верхней карточки:
        backdrop-blur на Android — самая дорогая операция отрисовки."""
        params = dict(
            content=content,
            bgcolor=self.color("glass"),
            border=ft.Border.all(1, self.color("glass_border")),
            border_radius=18,
            padding=16,
        )
        if blur and not self.simple_bg():
            params["blur"] = ft.Blur(18, 18)
        params.update(extra)
        card = ft.Container(**params)
        self._cards.append((card, blur))
        return card

    # ==========================================
    # ФОН
    # ==========================================
    def background(self):
        """Один фон на всё приложение, кладётся в самый низ корневого Stack."""
        pal = self.palette()
        base = ft.Container(
            expand=True,
            gradient=ft.LinearGradient(
                begin=ft.Alignment.TOP_LEFT, end=ft.Alignment.BOTTOM_RIGHT,
                colors=list(pal["gradient"]),
            ),
        )
        geometry = [
            dict(width=280, height=280, border_radius=280, top=-60, left=-70),
            dict(width=320, height=320, border_radius=320, top=140, right=-90),
            dict(width=280, height=280, border_radius=280, bottom=-60, left=50),
        ]
        spheres = [ft.Container(**g) for g in geometry]
        self._backgrounds.append((base, spheres))
        self._paint_spheres(spheres)
        return ft.Stack(expand=True, controls=[base] + spheres)

    def _paint_spheres(self, spheres):
        colors = self._sphere_colors()
        for sphere, color in zip(spheres, colors):
            if self.simple_bg():
                # режим экономии: сфер нет вообще, только градиент
                sphere.gradient = None
                sphere.bgcolor = TRANSPARENT
                sphere.visible = False
                continue
            sphere.visible = True
            sphere.bgcolor = None
            # радиальный градиент с прозрачным краем даёт тот же мягкий ореол,
            # что и Blur, но стоит на порядок дешевле при отрисовке
            sphere.gradient = ft.RadialGradient(
                colors=[color, TRANSPARENT], stops=[0.0, 1.0]
            )

    # ==========================================
    # ПРИМЕНЕНИЕ ТЕМЫ
    # ==========================================
    def apply(self, page):
        pal = self.palette()
        page.theme = ft.Theme(color_scheme_seed=self.accent())
        page.theme_mode = ft.ThemeMode.DARK if self.is_dark() else ft.ThemeMode.LIGHT
        page.bgcolor = pal["page"]

        for base, spheres in self._backgrounds:
            base.gradient = ft.LinearGradient(
                begin=ft.Alignment.TOP_LEFT, end=ft.Alignment.BOTTOM_RIGHT,
                colors=list(pal["gradient"]),
            )
            self._paint_spheres(spheres)

        for card, blur in self._cards:
            card.bgcolor = pal["glass"]
            card.border = ft.Border.all(1, pal["glass_border"])
            card.blur = ft.Blur(18, 18) if (blur and not self.simple_bg()) else None

        for control, role in self._texts:
            control.color = self._role_color(role)

        for control in self._fields:
            self._paint_field(control)

        for control, role in self._icons:
            control.icon_color = self._role_color(role)

        for control in self._dividers:
            control.color = pal["glass_border"]

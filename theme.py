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

# Радиальный градиент круглой кнопки: прозрачный в центре, светлеющий к краю.
GLASS_KEY_COLORS = ["#0fffffff", "#14ffffff", "#3dffffff"]
GLASS_KEY_STOPS = [0.0, 0.68, 1.0]

# Верхний блик карточки в режиме скорости — заменяет backdrop-blur.
GLOSS_STOPS = [0.0, 0.5]

# Имя свойства иконки различается между сборками Flet — ищем реальное.
ICON_ATTRS = ("icon", "name", "value")


def safe_update(control):
    """
    Точечное обновление вместо page.update(): контрол может быть ещё не
    добавлен на страницу, и тогда update() бросает исключение.
    Живёт здесь, а не в views/common, чтобы Theme мог им пользоваться
    без обратного импорта (граф импортов остаётся линейным).
    """
    try:
        control.update()
    except Exception:
        pass


def sync_value(e):
    """Flet не всегда пишет ввод в .value до потери фокуса — синхронизируем вручную.
    Здесь сознательно нет page.update(): раньше он дёргался на каждый символ."""
    e.control.value = e.data


def set_icon(control, icon_value):
    """
    Меняет символ у ft.Icon. Прямое присваивание .name в Flet 0.86 создаёт
    новый атрибут вместо смены иконки — отсюда были стрелки, всегда
    смотрящие вверх. Ищем то свойство, которое у контрола реально есть.
    """
    for attr in ICON_ATTRS:
        if hasattr(control, attr):
            setattr(control, attr, icon_value)
            return True
    return False


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
        self._glass_keys = []
        # Подпись палитры: пока она не менялась, полная перекраска не нужна.
        self._signature = None

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
        """Режим скорости: без блюра, без сфер, без анимации переходов."""
        return bool(self.config.get("simple_bg"))

    def on_accent(self):
        """Цвет текста поверх акцентной заливки: на светлом акценте — тёмный."""
        return "#101014"

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

    def icon(self, icon_value, role="normal", **kwargs):
        """Иконка, перекрашиваемая вместе с темой."""
        control = ft.Icon(icon_value, **kwargs)
        control.color = self._role_color(role)
        self._icons.append((control, role))
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

    @staticmethod
    def _paint_icon(control, color):
        """У IconButton цвет в icon_color, у Icon — в color."""
        if hasattr(control, "icon_color"):
            control.icon_color = color
        else:
            control.color = color

    # ==========================================
    # СТЕКЛЯННАЯ КРУГЛАЯ КНОПКА
    # ==========================================
    def glass_key(self, content, on_press=None, size=68, animate=True):
        """
        Круглая кнопка «жидкого стекла»: радиальный градиент, светлеющий к краю.
        Blur снят намеренно и в обоих режимах: под клавишами лежит гладкий
        градиент, размывать там нечего, а 14 BackdropFilter на экране PIN
        роняли частоту кадров. ink=False по той же причине — материаловский
        ripple перерисовывал клавишу все 300 мс своей анимации.
        """
        key = ft.Container(
            width=size, height=size, border_radius=size // 2,
            alignment=ft.Alignment.CENTER,
            content=content,
            ink=False,
        )
        if animate:
            key.animate_scale = ft.Animation(90, ft.AnimationCurve.EASE_OUT)
        self._glass_keys.append(key)
        self._paint_glass_key(key)

        if on_press is None:
            return key

        # Нажатие вешаем на GestureDetector ради «сжатия» кнопки; если в этой
        # сборке Flet нет tap_down/tap_up — откатываемся на обычный on_click.
        detector = ft.GestureDetector(content=key)
        has_down = self._bind(detector, lambda e, k=key: self.squeeze(k, True),
                              "on_tap_down")
        has_up = self._bind(detector, lambda e, k=key, f=on_press:
                            self._release(k, f), "on_tap_up")
        if has_down and has_up:
            return detector

        key.on_click = lambda e, f=on_press: f()
        return key

    @staticmethod
    def _bind(control, handler, name):
        if hasattr(control, name):
            setattr(control, name, handler)
            return True
        return False

    def squeeze(self, key, pressed):
        key.scale = 0.9 if pressed else 1.0
        safe_update(key)

    def _release(self, key, action):
        self.squeeze(key, False)
        action()

    def _paint_glass_key(self, key):
        key.gradient = ft.RadialGradient(colors=list(GLASS_KEY_COLORS),
                                         stops=list(GLASS_KEY_STOPS))
        key.border = ft.Border.all(1, self.color("glass_border"))
        key.blur = None
        key.scale = 1.0

    # ==========================================
    # СТЕКЛО (карточки)
    # ==========================================
    def card(self, content, blur=False, **extra):
        """blur=True оставляем только для шапки и навигации: их всего две,
        и в режиме «Максимум» это по карману даже слабому GPU."""
        params = dict(content=content, border_radius=18, padding=16)
        params.update(extra)
        card = ft.Container(**params)
        self._cards.append((card, blur))
        self._paint_card(card, blur)
        return card

    def _gloss_gradient(self):
        """
        Верхний блик — замена блюра в режиме скорости. Градиент в Flutter
        перекрывает bgcolor, поэтому цвет стекла включён нижним стопом.
        """
        top = "#33ffffff" if self.is_dark() else "#e6ffffff"
        return ft.LinearGradient(
            begin=ft.Alignment.TOP_CENTER, end=ft.Alignment.BOTTOM_CENTER,
            colors=[top, self.color("glass")], stops=list(GLOSS_STOPS))

    def _paint_card(self, card, blur):
        pal = self.palette()
        card.bgcolor = pal["glass"]
        card.border = ft.Border.all(1, pal["glass_border"])
        if self.simple_bg():
            card.blur = None
            card.gradient = self._gloss_gradient()
        else:
            card.gradient = None
            card.blur = ft.Blur(18, 18) if blur else None

    # ==========================================
    # ПОЛОСА ПРОКРУТКИ
    # ==========================================
    def _scrollbar_theme(self):
        """Тонкая полупрозрачная полоса вместо толстой системной.
        Набор полей ScrollbarTheme отличается между сборками — пробуем
        от полного к минимальному."""
        cls = getattr(ft, "ScrollbarTheme", None)
        if cls is None:
            return None
        variants = (
            dict(thickness=4, interactive=False, thumb_visibility=True,
                 track_visibility=False, radius=2,
                 thumb_color=self.color("text_faint")),
            dict(thickness=4, interactive=False,
                 thumb_color=self.color("text_faint")),
            dict(thickness=4, thumb_color=self.color("text_faint")),
            dict(thickness=4),
        )
        for kwargs in variants:
            try:
                return cls(**kwargs)
            except Exception:
                continue
        return None

    def _make_page_theme(self):
        seed = self.accent()
        bar = self._scrollbar_theme()
        if bar is not None:
            try:
                return ft.Theme(color_scheme_seed=seed, scrollbar_theme=bar)
            except Exception:
                pass
        return ft.Theme(color_scheme_seed=seed)

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
                # режим скорости: сфер нет вообще, только градиент
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

    def refresh_background(self):
        """Фон лежит в корневом Stack вне экранов, поэтому обычное обновление
        экрана его не задевает — отсюда был баг «фон меняется не сразу»."""
        for base, spheres in self._backgrounds:
            safe_update(base)
            for sphere in spheres:
                safe_update(sphere)

    # ==========================================
    # ПРИМЕНЕНИЕ ТЕМЫ
    # ==========================================
    def apply(self, page):
        """
        Перекрашивает уже созданные контролы на месте.
        Возвращает True, если палитра действительно изменилась — тогда
        вызывающему нужен page.update() ради page.bgcolor и page.theme.
        При простой навигации между экранами возвращает False, и полный
        диф всего дерева не отправляется.
        """
        signature = (self.config.get("theme"), self.config.get("bg_theme"),
                     self.simple_bg())
        if signature == self._signature:
            return False
        self._signature = signature

        pal = self.palette()
        page.theme = self._make_page_theme()
        page.theme_mode = ft.ThemeMode.DARK if self.is_dark() else ft.ThemeMode.LIGHT
        page.bgcolor = pal["page"]

        for base, spheres in self._backgrounds:
            base.gradient = ft.LinearGradient(
                begin=ft.Alignment.TOP_LEFT, end=ft.Alignment.BOTTOM_RIGHT,
                colors=list(pal["gradient"]),
            )
            self._paint_spheres(spheres)

        for card, blur in self._cards:
            self._paint_card(card, blur)

        for key in self._glass_keys:
            self._paint_glass_key(key)

        for control, role in self._texts:
            control.color = self._role_color(role)

        for control in self._fields:
            self._paint_field(control)

        for control, role in self._icons:
            self._paint_icon(control, self._role_color(role))

        for control in self._dividers:
            control.color = pal["glass_border"]

        return True

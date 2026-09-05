import flet as ft

from constants import (DEFAULT_ACCENT, DEFAULT_BG_THEME, THEME_ACCENTS,
                       THEME_BACKGROUNDS)

TRANSPARENT = "#00000000"

TEXT_ROLES = {
    "normal": "text",
    "dim": "text_dim",
    "faint": "text_faint",
}

GLASS_KEY_COLORS = ["#0fffffff", "#14ffffff", "#3dffffff"]
GLASS_KEY_STOPS = [0.0, 0.68, 1.0]

# Верхний блик карточки в режиме скорости — заменяет backdrop-blur.
GLOSS_STOPS = [0.0, 0.5]

ICON_ATTRS = ("icon", "name", "value")


def safe_update(control):
    """Точечное обновление: контрол может быть ещё не добавлен на страницу.
    Живёт здесь, чтобы Theme мог им пользоваться без обратного импорта."""
    try:
        control.update()
    except Exception:
        pass


def sync_value(e):
    """Flet не всегда пишет ввод в .value до потери фокуса."""
    e.control.value = e.data


def set_icon(control, icon_value):
    """Прямое присваивание .name в Flet 0.86 создаёт новый атрибут вместо
    смены иконки — ищем то свойство, которое у контрола реально есть."""
    for attr in ICON_ATTRS:
        if hasattr(control, attr):
            setattr(control, attr, icon_value)
            return True
    return False


def release_focus(page, *controls):
    """
    Снимает фокус с полей ввода и убирает клавиатуру. Метода «закрыть
    клавиатуру» во Flet нет, поэтому используем приём с read_only:
    переключение отпускает фокус во Flutter.
    """
    for control in controls:
        if control is None:
            continue
        blur = getattr(control, "blur_focus", None) or getattr(control, "unfocus", None)
        if callable(blur):
            try:
                blur()
                continue
            except Exception:
                pass
        if hasattr(control, "read_only"):
            try:
                was = control.read_only
                control.read_only = True
                safe_update(control)
                control.read_only = was
                safe_update(control)
            except Exception:
                pass


class Theme:
    """Единая точка правды по цветам."""

    def __init__(self, config):
        self.config = config
        self._backgrounds = []
        self._cards = []
        self._texts = []
        self._fields = []
        self._icons = []
        self._dividers = []
        self._glass_keys = []
        self._signature = None
        # Временные контролы (модалки) не регистрируются: раньше каждое
        # открытие дня добавляло ~25 ссылок навсегда, списки росли, и
        # перекраска темы перебирала свалку мёртвых контролов.
        self._tracking = True

    # ==========================================
    # РЕЖИМ ВРЕМЕННЫХ КОНТРОЛОВ
    # ==========================================
    def begin_temp(self):
        self._tracking = False

    def end_temp(self):
        self._tracking = True

    def _track(self, store, item):
        if self._tracking:
            store.append(item)

    # ==========================================
    # ЦВЕТА
    # ==========================================
    def accent(self):
        value = self.config.get("theme")
        # Цвет из палитры хранится как HEX прямо в конфиге.
        if isinstance(value, str) and value.startswith("#"):
            return value
        return THEME_ACCENTS.get(value, THEME_ACCENTS[DEFAULT_ACCENT])

    def accent_a(self, alpha_hex):
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
        self._track(self._texts, (control, role))
        return control

    def field(self, **kwargs):
        kwargs.setdefault("on_change", sync_value)
        control = ft.TextField(**kwargs)
        self._paint_field(control)
        self._track(self._fields, control)
        return control

    def icon(self, icon_value, role="normal", **kwargs):
        control = ft.Icon(icon_value, **kwargs)
        control.color = self._role_color(role)
        self._track(self._icons, (control, role))
        return control

    def icon_button(self, icon, role="normal", **kwargs):
        control = ft.IconButton(icon, **kwargs)
        control.icon_color = self._role_color(role)
        self._track(self._icons, (control, role))
        return control

    def divider(self):
        control = ft.Divider(color=self.color("glass_border"), height=9)
        self._track(self._dividers, control)
        return control

    def _paint_field(self, control):
        control.bgcolor = self.color("field_bg")
        control.color = self.color("text")
        control.border_color = self.color("field_border")
        control.label_style = ft.TextStyle(color=self.color("text_dim"))

    @staticmethod
    def _paint_icon(control, color):
        if hasattr(control, "icon_color"):
            control.icon_color = color
        else:
            control.color = color

    # ==========================================
    # СТЕКЛЯННАЯ КРУГЛАЯ КНОПКА
    # ==========================================
    def glass_key(self, content, on_press=None, size=68, animate=True):
        """
        Blur снят намеренно в обоих режимах: под клавишами лежит гладкий
        градиент, размывать нечего, а 14 BackdropFilter на экране PIN
        роняли частоту кадров. ink=False — ripple перерисовывал клавишу
        все 300 мс своей анимации.
        """
        key = ft.Container(
            width=size, height=size, border_radius=size // 2,
            alignment=ft.Alignment.CENTER,
            content=content,
            ink=False,
        )
        if animate:
            key.animate_scale = ft.Animation(90, ft.AnimationCurve.EASE_OUT)
        self._track(self._glass_keys, key)
        self._paint_glass_key(key)

        if on_press is None:
            return key

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
    @staticmethod
    def _stretch_row():
        """
        Невидимая распорка. Column с tight=True получает ширину по самому
        широкому потомку, поэтому карточки с коротким содержимым выходили
        уже остальных. Растянутый Row внутри заставляет колонку занять
        всю доступную ширину.
        """
        return ft.Row([ft.Container(height=0, expand=True)], spacing=0,
                      height=0)

    def card(self, content, blur=False, stretch=True, **extra):
        """blur=True — только для шапки и навигации."""
        if stretch and isinstance(content, ft.Column):
            content.controls.insert(0, self._stretch_row())

        params = dict(content=content, border_radius=18, padding=16)
        params.update(extra)
        card = ft.Container(**params)
        self._track(self._cards, (card, blur))
        self._paint_card(card, blur)
        return card

    def _gloss_gradient(self):
        """Верхний блик — замена блюра в режиме скорости. Градиент
        перекрывает bgcolor, поэтому цвет стекла идёт нижним стопом."""
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
        """
        Тонкая полупрозрачная полоса, видимая только во время прокрутки.
        Набор полей ScrollbarTheme отличается между сборками, поэтому
        добавляем свойства по одному и оставляем те, что приняты.
        """
        cls = getattr(ft, "ScrollbarTheme", None)
        if cls is None:
            return None

        candidates = (
            ("thickness", 4),
            ("thumb_visibility", False),   # видна только при прокрутке
            ("track_visibility", False),
            ("interactive", False),
            ("radius", 2),
            ("thumb_color", self.color("text_faint")),
            ("main_axis_margin", 6),
            ("cross_axis_margin", 2),
        )
        accepted = {}
        for name, value in candidates:
            trial = dict(accepted)
            trial[name] = value
            try:
                cls(**trial)
                accepted = trial
            except Exception:
                continue
        if not accepted:
            return None
        try:
            return cls(**accepted)
        except Exception:
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
                sphere.gradient = None
                sphere.bgcolor = TRANSPARENT
                sphere.visible = False
                continue
            sphere.visible = True
            sphere.bgcolor = None
            sphere.gradient = ft.RadialGradient(
                colors=[color, TRANSPARENT], stops=[0.0, 1.0]
            )

    def refresh_background(self):
        """Фон лежит в корневом Stack вне экранов, обычное обновление
        экрана его не задевает."""
        for base, spheres in self._backgrounds:
            safe_update(base)
            for sphere in spheres:
                safe_update(sphere)

    # ==========================================
    # ПРИМЕНЕНИЕ ТЕМЫ
    # ==========================================
    def apply(self, page):
        """Возвращает True, если палитра изменилась и нужен page.update()."""
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

import time

import flet as ft

from database import db
from views.common import bind_event, safe_update

MAX_ATTEMPTS = 5
BASE_LOCKOUT_SECONDS = 30
MIN_PIN = 4          # с этой длины начинаем проверять существующий PIN
SETUP_PIN = 6        # новый PIN задаётся ровно такой длины
MAX_PIN = 6

KEY_SIZE = 68
KEY_GAP = 16

# Буквы под цифрами — как на клавиатуре телефона
KEY_LETTERS = {
    "2": "ABC", "3": "DEF", "4": "GHI", "5": "JKL",
    "6": "MNO", "7": "PQRS", "8": "TUV", "9": "WXYZ",
}

ERROR_COLOR = "#fca5a5"


class PinView:
    """
    Цифровая клавиатура вместо TextField: системная клавиатура не всплывает.
    Введённые цифры живут в обычной строке, поля ввода на экране нет вообще.
    """

    def __init__(self, ctx, on_success):
        self.ctx = ctx
        self.on_success = on_success
        th = ctx.theme

        self.mode = "verify"
        self.first_pin = None
        self.digits = ""
        self.attempts = 0
        self.lockouts = 0
        self.locked_until = 0.0

        self.title = th.text("Введите PIN-код", size=20, weight=ft.FontWeight.BOLD)
        self.hint = th.text("", role="dim", size=12)
        self.error = ft.Text("", color=ERROR_COLOR, size=12,
                             text_align=ft.TextAlign.CENTER)

        self.dots = [self._make_dot() for _i in range(MAX_PIN)]
        self.dots_row = ft.Row(self.dots, spacing=14, tight=True,
                               alignment=ft.MainAxisAlignment.CENTER)

        self.keys = []
        self.control = ft.SafeArea(
            expand=True,
            content=ft.Container(
                alignment=ft.Alignment.CENTER,
                expand=True,
                padding=20,
                content=ft.Column([
                    self.title,
                    self.hint,
                    ft.Container(self.dots_row,
                                 padding=ft.Padding.only(top=14, bottom=6)),
                    self.error,
                    ft.Container(self._build_keypad(),
                                 padding=ft.Padding.only(top=10)),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=6, tight=True),
            ),
        )

        self._paint_dots()
        self._paint_keys()

    # ==========================================
    # ЭЛЕМЕНТЫ
    # ==========================================
    @staticmethod
    def _make_dot():
        return ft.Container(width=13, height=13, border_radius=7)

    @staticmethod
    def _spacer():
        """Пустой слот той же ширины: держит 0 под восьмёркой, стирание под девяткой."""
        return ft.Container(width=KEY_SIZE, height=KEY_SIZE)

    def _glass_key(self, content, on_press):
        """
        Стеклянная круглая кнопка: реальный backdrop-блюр плюс радиальный
        градиент, светлеющий к краю — имитация выпуклого стекла.
        Настоящее преломление требует фрагментного шейдера, которого во Flet нет.
        """
        key = ft.Container(
            width=KEY_SIZE, height=KEY_SIZE, border_radius=KEY_SIZE // 2,
            alignment=ft.Alignment.CENTER,
            content=content,
            ink=True,
            animate_scale=ft.Animation(90, ft.AnimationCurve.EASE_OUT),
        )
        self.keys.append(key)

        # Нажатие вешаем на GestureDetector ради «сжатия» кнопки; если в этой
        # сборке Flet нет tap_down/tap_up — откатываемся на обычный on_click.
        detector = ft.GestureDetector(content=key)
        has_down = bind_event(detector, lambda e, k=key: self._squeeze(k, True),
                              "on_tap_down")
        has_up = bind_event(detector, lambda e, k=key, f=on_press:
                            self._release(k, f), "on_tap_up")
        if has_down and has_up:
            return detector

        key.on_click = lambda e, f=on_press: f()
        return key

    def _squeeze(self, key, pressed):
        key.scale = 0.9 if pressed else 1.0
        safe_update(key)

    def _release(self, key, action):
        self._squeeze(key, False)
        action()

    def _digit_key(self, digit):
        th = self.ctx.theme
        letters = KEY_LETTERS.get(digit)
        rows = [ft.Text(digit, size=26, weight=ft.FontWeight.W_400,
                        color=th.color("text"))]
        if letters:
            rows.append(ft.Text(letters, size=9, weight=ft.FontWeight.BOLD,
                                color=th.color("text_dim")))
        content = ft.Column(rows, spacing=0, tight=True,
                            alignment=ft.MainAxisAlignment.CENTER,
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER)
        return self._glass_key(content, lambda d=digit: self._press(d))

    def _build_keypad(self):
        rows = []
        for line in (("1", "2", "3"), ("4", "5", "6"), ("7", "8", "9")):
            rows.append(ft.Row([self._digit_key(d) for d in line],
                               spacing=KEY_GAP, tight=True,
                               alignment=ft.MainAxisAlignment.CENTER))

        th = self.ctx.theme
        backspace = self._glass_key(
            ft.Icon(ft.Icons.BACKSPACE_OUTLINED, size=22,
                    color=th.color("text_dim")),
            self._backspace)
        rows.append(ft.Row([self._spacer(), self._digit_key("0"), backspace],
                           spacing=KEY_GAP, tight=True,
                           alignment=ft.MainAxisAlignment.CENTER))

        return ft.Column(rows, spacing=KEY_GAP, tight=True,
                         horizontal_alignment=ft.CrossAxisAlignment.CENTER)

    # ==========================================
    # ОТРИСОВКА
    # ==========================================
    def _paint_dots(self):
        th = self.ctx.theme
        filled = len(self.digits)
        for index, dot in enumerate(self.dots):
            if index < filled:
                dot.bgcolor = th.accent()
                dot.border = None
            else:
                dot.bgcolor = "#00000000"
                dot.border = ft.Border.all(1, th.color("text_faint"))

    def _flash_dots(self):
        for dot in self.dots:
            dot.bgcolor = "#00000000"
            dot.border = ft.Border.all(1, ERROR_COLOR)

    def _paint_keys(self):
        th = self.ctx.theme
        simple = bool(self.ctx.config.get("simple_bg"))
        for key in self.keys:
            key.gradient = ft.RadialGradient(
                colors=["#0fffffff", "#14ffffff", "#3dffffff"],
                stops=[0.0, 0.68, 1.0],
            )
            key.border = ft.Border.all(1, th.color("glass_border"))
            key.blur = None if simple else ft.Blur(14, 14)
            key.scale = 1.0

    # ==========================================
    # ПОКАЗ ЭКРАНА
    # ==========================================
    def show(self, force_setup=False):
        self.digits = ""
        self.first_pin = None
        self.error.value = ""
        if db.has_pin() and not force_setup:
            self.mode = "verify"
            self.title.value = "Введите PIN-код"
            self.hint.value = ""
        else:
            self.mode = "setup_new"
            self.title.value = "Придумайте PIN-код"
            self.hint.value = f"{SETUP_PIN} цифр"
        self._paint_dots()
        self._paint_keys()

    def _refresh(self):
        for control in (self.title, self.hint, self.error, self.dots_row):
            safe_update(control)

    # ==========================================
    # БЛОКИРОВКА ПОСЛЕ НЕУДАЧ
    # ==========================================
    def _remaining_lock(self):
        return max(0, int(self.locked_until - time.monotonic()))

    def _register_failure(self):
        self.attempts += 1
        if self.attempts >= MAX_ATTEMPTS:
            self.lockouts += 1
            self.attempts = 0
            delay = BASE_LOCKOUT_SECONDS * (2 ** (self.lockouts - 1))
            self.locked_until = time.monotonic() + delay
            return delay
        return 0

    # ==========================================
    # ВВОД
    # ==========================================
    def _press(self, digit):
        remaining = self._remaining_lock()
        if remaining:
            self.error.value = f"Слишком много попыток. Подождите {remaining} с"
            self._refresh()
            return
        if len(self.digits) >= MAX_PIN:
            return

        self.digits += digit
        self.error.value = ""
        self._paint_dots()
        self._refresh()

        if self.mode == "verify":
            if len(self.digits) >= MIN_PIN:
                self._try_verify()
        elif len(self.digits) == SETUP_PIN:
            self._commit_setup()

    def _backspace(self):
        if not self.digits:
            return
        self.digits = self.digits[:-1]
        self.error.value = ""
        self._paint_dots()
        self._refresh()

    def _reset_input(self):
        self.digits = ""
        self._paint_dots()

    # ==========================================
    # ПРОВЕРКА И СОЗДАНИЕ
    # ==========================================
    def _try_verify(self):
        """
        Проверяем на каждой цифре начиная с четвёртой — так работают старые
        короткие PIN-коды. Попытку тратим только когда набраны все шесть.
        """
        if db.verify_pin(self.digits):
            self.attempts = 0
            self.lockouts = 0
            self._reset_input()
            self.error.value = ""
            self.on_success()
            return

        if len(self.digits) < MAX_PIN:
            return

        delay = self._register_failure()
        if delay:
            self.error.value = f"Вход заблокирован на {delay} с"
        else:
            left = MAX_ATTEMPTS - self.attempts
            self.error.value = f"Неверный PIN-код. Осталось попыток: {left}"
        self._flash_dots()
        self._refresh()
        self._reset_input()
        self._refresh()

    def _commit_setup(self):
        if self.mode == "setup_new":
            self.first_pin = self.digits
            self.mode = "setup_confirm"
            self.title.value = "Повторите PIN-код"
            self.hint.value = ""
            self.error.value = ""
            self._reset_input()
            self._refresh()
            return

        if self.digits == self.first_pin:
            # Старый хеш перезаписывается только здесь: до этого момента
            # приложение остаётся защищённым прежним PIN-кодом.
            db.set_pin(self.digits)
            self.ctx.config.update(db.get_config())
            self._reset_input()
            self.error.value = ""
            self.on_success()
            return

        self.mode = "setup_new"
        self.first_pin = None
        self.title.value = "Придумайте PIN-код"
        self.hint.value = f"{SETUP_PIN} цифр"
        self.error.value = "PIN-коды не совпадают, попробуйте снова"
        self._flash_dots()
        self._refresh()
        self._reset_input()
        self._refresh()

import time

import flet as ft

from database import db
from views.common import refresh_tree, safe_update

MAX_ATTEMPTS = 5
BASE_LOCKOUT_SECONDS = 30
MIN_PIN = 4
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

    # ==========================================
    # ЭЛЕМЕНТЫ
    # ==========================================
    @staticmethod
    def _make_dot():
        return ft.Container(width=13, height=13, border_radius=7)

    @staticmethod
    def _slot(content=None):
        """Слот фиксированной ширины: держит столбцы выровненными,
        даже когда кнопка внутри скрыта."""
        return ft.Container(width=KEY_SIZE, height=KEY_SIZE, content=content)

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
        return th.glass_key(content, lambda d=digit: self._press(d), size=KEY_SIZE)

    def _build_keypad(self):
        th = self.ctx.theme
        rows = []

        for line in (("1", "2", "3"), ("4", "5", "6"), ("7", "8", "9")):
            rows.append(ft.Row([self._digit_key(d) for d in line],
                               spacing=KEY_GAP, tight=True,
                               alignment=ft.MainAxisAlignment.CENTER))

        # Нижний ряд: галочка стоит в столбце семёрки, то есть прямо под ней.
        # Семёрка при этом никуда не девается.
        self.confirm_slot = self._slot(th.glass_key(
            ft.Icon(ft.Icons.CHECK, size=24, color=th.accent()),
            self._commit_setup, size=KEY_SIZE))
        self.confirm_slot.visible = False
        self.empty_slot = self._slot()

        backspace = th.glass_key(
            ft.Icon(ft.Icons.BACKSPACE_OUTLINED, size=22,
                    color=th.color("text_dim")),
            self._backspace, size=KEY_SIZE)

        rows.append(ft.Row([
            ft.Stack([self.empty_slot, self.confirm_slot],
                     width=KEY_SIZE, height=KEY_SIZE),
            self._digit_key("0"),
            backspace,
        ], spacing=KEY_GAP, tight=True, alignment=ft.MainAxisAlignment.CENTER))

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

    def _confirm_threshold(self):
        """
        При первом наборе кнопка появляется с четвёртой цифры.
        При повторе — ровно с той длины, что была задана в первый раз.
        """
        if self.mode == "setup_confirm" and self.first_pin:
            return len(self.first_pin)
        return MIN_PIN

    def _sync_confirm(self):
        setup = self.mode.startswith("setup")
        self.confirm_slot.visible = (setup and
                                     len(self.digits) >= self._confirm_threshold())

    def _refresh(self):
        refresh_tree(self.title, self.hint, self.error,
                     self.dots_row, self.confirm_slot)

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
            self.hint.value = "От 4 до 6 цифр"
        self._paint_dots()
        self._sync_confirm()

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
        self._sync_confirm()
        self._refresh()

        # При обычном входе подтверждать нечем — проверяем сами с четвёртой цифры.
        if self.mode == "verify" and len(self.digits) >= MIN_PIN:
            self._try_verify()

    def _backspace(self):
        if not self.digits:
            return
        self.digits = self.digits[:-1]
        self.error.value = ""
        self._paint_dots()
        self._sync_confirm()
        self._refresh()

    def _reset_input(self):
        self.digits = ""
        self._paint_dots()
        self._sync_confirm()

    # ==========================================
    # ПРОВЕРКА И СОЗДАНИЕ
    # ==========================================
    def _try_verify(self):
        """
        Проверяем на каждой цифре начиная с четвёртой — так работают
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
        if len(self.digits) < self._confirm_threshold():
            return

        if self.mode == "setup_new":
            self.first_pin = self.digits
            self.mode = "setup_confirm"
            self.title.value = "Повторите PIN-код"
            self.hint.value = f"{len(self.first_pin)} цифр"
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
        self.hint.value = "От 4 до 6 цифр"
        self.error.value = "PIN-коды не совпадают, попробуйте снова"
        self._flash_dots()
        self._refresh()
        self._reset_input()
        self._refresh()

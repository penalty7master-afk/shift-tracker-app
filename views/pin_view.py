import time

import flet as ft

from database import db
from views.common import safe_update

MAX_ATTEMPTS = 5
BASE_LOCKOUT_SECONDS = 30


class PinView:
    def __init__(self, ctx, on_success):
        self.ctx = ctx
        self.on_success = on_success
        th = ctx.theme

        self.mode = "verify"
        self.first_pin = None
        self.attempts = 0
        self.lockouts = 0
        self.locked_until = 0.0

        self.title = th.text("Введите PIN-код", role="accent", size=20,
                             weight=ft.FontWeight.BOLD)
        self.hint = th.text("", role="dim", size=12)
        self.error = ft.Text("", color="#fca5a5", size=12,
                             text_align=ft.TextAlign.CENTER)

        self.field = th.field(
            password=True, can_reveal_password=False,
            keyboard_type=ft.KeyboardType.NUMBER, max_length=6,
            text_align=ft.TextAlign.CENTER, width=200, autofocus=True,
        )
        self.field.on_submit = self.confirm

        self.button = ft.ElevatedButton("Подтвердить", on_click=self.confirm, width=200)

        self.control = ft.Container(
            alignment=ft.Alignment.CENTER,
            expand=True,
            content=th.card(
                ft.Column(
                    [self.title, self.hint, self.field, self.error, self.button],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=14,
                    tight=True,
                ),
                blur=True,
                width=320,
            ),
        )

    # ---------- показ ----------
    def show(self, force_setup=False):
        self.field.value = ""
        self.error.value = ""
        self.first_pin = None
        if db.has_pin() and not force_setup:
            self.mode = "verify"
            self.title.value = "Введите PIN-код"
            self.hint.value = ""
        else:
            self.mode = "setup_new"
            self.title.value = "Придумайте PIN-код"
            self.hint.value = "От 4 до 6 цифр"

    # ---------- блокировка ----------
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

    def _refresh(self):
        for control in (self.title, self.hint, self.field, self.error):
            safe_update(control)

    # ---------- обработка ----------
    def confirm(self, e=None):
        remaining = self._remaining_lock()
        if remaining:
            self.error.value = f"Слишком много попыток. Подождите {remaining} с"
            self._refresh()
            return

        pin = (self.field.value or "").strip()
        if not pin.isdigit():
            self.error.value = "Только цифры"
            self._refresh()
            return
        if len(pin) < 4:
            self.error.value = "Минимум 4 цифры"
            self._refresh()
            return

        if self.mode == "verify":
            self._handle_verify(pin)
        elif self.mode == "setup_new":
            self._handle_setup_new(pin)
        else:
            self._handle_setup_confirm(pin)

    def _handle_verify(self, pin):
        if db.verify_pin(pin):
            self.attempts = 0
            self.lockouts = 0
            self.field.value = ""
            self.error.value = ""
            self.on_success()
            return
        delay = self._register_failure()
        if delay:
            self.error.value = f"Вход заблокирован на {delay} с"
        else:
            left = MAX_ATTEMPTS - self.attempts
            self.error.value = f"Неверный PIN-код. Осталось попыток: {left}"
        self.field.value = ""
        self._refresh()

    def _handle_setup_new(self, pin):
        self.first_pin = pin
        self.mode = "setup_confirm"
        self.title.value = "Повторите PIN-код"
        self.hint.value = ""
        self.field.value = ""
        self.error.value = ""
        self._refresh()

    def _handle_setup_confirm(self, pin):
        if pin == self.first_pin:
            # Старый хеш перезаписывается только здесь: до этого момента
            # приложение остаётся защищённым прежним PIN-кодом.
            db.set_pin(pin)
            self.ctx.config.update(db.get_config())
            self.field.value = ""
            self.error.value = ""
            self.on_success()
            return
        self.mode = "setup_new"
        self.first_pin = None
        self.title.value = "Придумайте PIN-код"
        self.hint.value = "От 4 до 6 цифр"
        self.field.value = ""
        self.error.value = "PIN-коды не совпадают, попробуйте снова"
        self._refresh()

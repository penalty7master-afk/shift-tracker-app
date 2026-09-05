import flet as ft

from theme import (release_focus, safe_update, set_icon,  # noqa: F401
                   sync_value)


class AppContext:
    """Общее состояние, которое экраны передают друг другу.
    Колбэки заполняются в ui.py после сборки всех экранов."""

    def __init__(self, page, config, theme):
        self.page = page
        self.config = config
        self.theme = theme

        self.view = {"year": 0, "month": 0}
        self.month_data = {}          # кэш смен месяца: один запрос вместо трёх
        self.production_data = {}     # кэш производства месяца
        self.timeline_dates = set()   # дни месяца с хронологией
        self.analytics_dirty = True   # аналитика пересчитывается при показе

        self.compare_text = ""        # «+12 400 ₽ к августу» для карточки прогноза
        self.on_unlock = None         # снимается автоблокировкой после ввода PIN
        self.rebuild_for_mode = None  # пересборка после смены режима день/ночь

        # Текущий открытый диалог. Нужен блокировке по бездействию:
        # AlertDialog живёт в отдельном слое над деревом страницы, поэтому
        # подмена экрана его не убирает — он остался бы висеть поверх PIN.
        self.dialog = None
        self.dialog_dirty = False     # в диалоге есть несохранённые правки

        # заполняются в ui.py
        self.show_pin = None
        self.show_main = None
        self.show_settings = None
        self.reload_month = None
        self.refresh_after_change = None
        self.apply_theme = None
        self.touch = None             # отметка активности для автоблокировки


def touch(ctx):
    """Продлевает сессию. Вызывается из обработчиков всех экранов."""
    if ctx is not None and callable(getattr(ctx, "touch", None)):
        ctx.touch()


# ==========================================
# СОВМЕСТИМОСТЬ API ДИАЛОГОВ (Flet 0.86 vs старые версии)
# ==========================================
def open_dialog(page, dialog, ctx=None):
    if ctx is not None:
        ctx.dialog = dialog
    if hasattr(page, "show_dialog"):
        page.show_dialog(dialog)
    elif hasattr(page, "open"):
        page.open(dialog)
    else:
        page.dialog = dialog
        dialog.open = True
        page.update()


def close_dialog(page, dialog, ctx=None):
    if ctx is not None and ctx.dialog is dialog:
        ctx.dialog = None
        ctx.dialog_dirty = False
    if hasattr(page, "pop_dialog"):
        page.pop_dialog()
    elif hasattr(page, "close"):
        page.close(dialog)
    else:
        dialog.open = False
        page.update()


def force_close_dialog(ctx):
    """Закрывает то, что открыто сейчас. Нужно перед принудительным
    переходом на другой экран (автоблокировка, восстановление базы)."""
    if ctx is None or ctx.dialog is None:
        return
    dialog = ctx.dialog
    ctx.dialog = None
    ctx.dialog_dirty = False
    try:
        close_dialog(ctx.page, dialog)
    except Exception:
        pass


def bind_event(control, handler, *names):
    """Имена событий отличаются между сборками Flet — привязываем безопасно."""
    for attr in names:
        if hasattr(control, attr):
            setattr(control, attr, handler)
            return True
    return False


def refresh_tree(*controls):
    """
    Обновляет несколько контролов подряд. Нужен там, где раньше стоял
    page.update(): полное обновление страницы сбрасывает позицию прокрутки
    в начало, и настройки прыгали наверх при выборе темы или удалении продукта.
    """
    for control in controls:
        safe_update(control)


# ==========================================
# ТИПОВЫЕ ДИАЛОГИ
# ==========================================
def info_dialog(ctx, title, message):
    th = ctx.theme
    dialog = ft.AlertDialog(
        modal=True,
        title=th.text(title, size=16, weight=ft.FontWeight.BOLD),
        content=ft.Container(
            width=dialog_width(ctx.page),
            content=ft.Column([th.text(message, role="dim", size=13,
                                       selectable=True)],
                              scroll=ft.ScrollMode.HIDDEN, tight=True),
        ),
        actions=[ft.TextButton(
            "Понятно",
            on_click=lambda e: close_dialog(ctx.page, dialog, ctx))],
    )
    style_dialog(th, dialog)
    open_dialog(ctx.page, dialog, ctx)
    return dialog


def confirm_dialog(ctx, title, message, on_confirm, confirm_label="Удалить",
                   danger=True):
    th = ctx.theme

    def accept(e):
        close_dialog(ctx.page, dialog, ctx)
        on_confirm()

    dialog = ft.AlertDialog(
        modal=True,
        title=th.text(title, size=16, weight=ft.FontWeight.BOLD),
        content=ft.Container(
            width=dialog_width(ctx.page),
            content=th.text(message, role="dim", size=13),
        ),
        actions=[
            ft.TextButton("Отмена",
                          on_click=lambda e: close_dialog(ctx.page, dialog, ctx)),
            ft.TextButton(confirm_label, on_click=accept,
                          style=ft.ButtonStyle(color="#f87171") if danger else None),
        ],
    )
    style_dialog(th, dialog)
    open_dialog(ctx.page, dialog, ctx)
    return dialog


def style_dialog(th, dialog):
    """
    Модалка в общей гамме: системный чёрный прямоугольник выбивался из
    палитры. Значения вычисляются лениво и присваиваются по одному — набор
    полей AlertDialog и вспомогательных классов отличается между сборками.
    """
    recipes = (
        ("bgcolor", lambda: th.dialog_bgcolor()),
        ("surface_tint_color", lambda: "#00000000"),
        ("shape", lambda: ft.RoundedRectangleBorder(radius=22)),
        ("inset_padding", lambda: ft.Padding.symmetric(horizontal=10, vertical=26)),
        ("content_padding",
         lambda: ft.Padding.only(top=8, left=14, right=14, bottom=4)),
        ("title_padding",
         lambda: ft.Padding.only(top=18, left=18, right=18, bottom=2)),
        ("actions_padding",
         lambda: ft.Padding.only(left=8, right=8, bottom=6, top=2)),
    )
    for name, make in recipes:
        try:
            setattr(dialog, name, make())
        except Exception:
            continue
    return dialog


def dialog_width(page, maximum=560):
    """
    Полезная ширина содержимого модалки. Вычитаются inset_padding (по 10)
    и content_padding (по 14) — иначе поле выработки уезжало за правый край.
    """
    width = page.width or 380
    return int(min(maximum, max(280, width - 2 * (10 + 14))))


def dialog_height(page, maximum=680):
    height = page.height or 700
    return int(min(maximum, max(360, height - 180)))

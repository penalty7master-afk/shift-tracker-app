import flet as ft

from theme import set_icon, sync_value  # noqa: F401  (реэкспорт для экранов)


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
        self.timeline_dates = set()   # дни месяца, где велась хронология
        self.analytics_dirty = True   # аналитика пересчитывается только при показе

        # заполняются в ui.py
        self.show_pin = None
        self.show_main = None
        self.show_settings = None
        self.reload_month = None
        self.refresh_after_change = None
        self.apply_theme = None


# ==========================================
# СОВМЕСТИМОСТЬ API ДИАЛОГОВ (Flet 0.86 vs старые версии)
# ==========================================
def open_dialog(page, dialog):
    if hasattr(page, "show_dialog"):
        page.show_dialog(dialog)
    elif hasattr(page, "open"):
        page.open(dialog)
    else:
        page.dialog = dialog
        dialog.open = True
        page.update()


def close_dialog(page, dialog):
    if hasattr(page, "pop_dialog"):
        page.pop_dialog()
    elif hasattr(page, "close"):
        page.close(dialog)
    else:
        dialog.open = False
        page.update()


def bind_event(control, handler, *names):
    """Имена событий отличаются между сборками Flet — привязываем безопасно."""
    for attr in names:
        if hasattr(control, attr):
            setattr(control, attr, handler)
            return True
    return False


def safe_update(control):
    """Точечное обновление вместо page.update(): контрол может быть ещё не
    добавлен на страницу, и тогда update() бросает исключение."""
    try:
        control.update()
    except Exception:
        pass


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
            width=min(320, (ctx.page.width or 360) - 60),
            content=ft.Column([th.text(message, role="dim", size=13,
                                       selectable=True)],
                              scroll=ft.ScrollMode.AUTO, tight=True),
        ),
        actions=[ft.TextButton("Понятно",
                               on_click=lambda e: close_dialog(ctx.page, dialog))],
    )
    open_dialog(ctx.page, dialog)
    return dialog


def confirm_dialog(ctx, title, message, on_confirm, confirm_label="Удалить",
                   danger=True):
    th = ctx.theme

    def accept(e):
        close_dialog(ctx.page, dialog)
        on_confirm()

    dialog = ft.AlertDialog(
        modal=True,
        title=th.text(title, size=16, weight=ft.FontWeight.BOLD),
        content=ft.Container(
            width=min(320, (ctx.page.width or 360) - 60),
            content=th.text(message, role="dim", size=13),
        ),
        actions=[
            ft.TextButton("Отмена", on_click=lambda e: close_dialog(ctx.page, dialog)),
            ft.TextButton(confirm_label, on_click=accept,
                          style=ft.ButtonStyle(color="#f87171") if danger else None),
        ],
    )
    open_dialog(ctx.page, dialog)
    return dialog


def dialog_width(page, maximum=360):
    """Модалки считаются от ширины экрана, а не фиксированные 340 px."""
    width = page.width or 380
    return int(min(maximum, max(260, width - 48)))


def dialog_height(page, maximum=600):
    height = page.height or 700
    return int(min(maximum, max(360, height - 200)))

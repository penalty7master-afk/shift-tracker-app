from datetime import date, datetime

import flet as ft

import haptics
from calculations import (format_hours, format_money, format_signed_money,
                          mode_of, month_summary, prev_month)
from constants import ARRIVAL_ON_TIME, FULL_SHIFT_HOURS, MONTH_NAMES, STATUS_WORK
from database import db
from lock import IdleLock
from theme import Theme
from views.analytics_view import AnalyticsView
from views.calendar_view import CalendarView
from views.common import AppContext, bind_event, force_close_dialog, refresh_tree
from views.day_modal import drop_day_modal
from views.mode_view import ModeView
from views.pin_view import PinView
from views.settings_view import SettingsView

# Анимация смены экрана выключена намеренно: AnimatedSwitcher держит в
# дереве оба экрана и рисует их через слой прозрачности — отсюда была
# «заморозка» при входе в настройки. Поставь True, чтобы вернуть переход.
USE_SCREEN_ANIMATION = False
SWITCHER_MS = 140

# Высоты плавающих панелей заданы явно: от них считаются распорки внутри
# прокрутки, а вычисленная высота зависела бы от того, как лягут шрифты.
HEADER_CARD_HEIGHT = 104
NAV_CARD_HEIGHT = 52
HEADER_KEY_SIZE = 48

# Навигация — маленькая таблетка: сильное размытие делало её матовой,
# тогда как широкая шапка при том же значении выглядит прозрачной.
NAV_BLUR = 9

# Жёсткий зазор между панелью и ближайшей карточкой — одинаков на любом
# устройстве, меняется только системная часть отступа.
GAP_TOP = 10
GAP_BOTTOM = 10

FALLBACK_INSET_TOP = 28
FALLBACK_INSET_BOTTOM = 24

SIDE_PADDING = 10


# ==========================================
# СБОРКА ПРИЛОЖЕНИЯ
# ==========================================
def main(page: ft.Page):
    page.title = "КАЛЕНДАРЬ СМЕН PRO"
    page.padding = 0

    haptics.setup(page)

    config = db.get_config()
    haptics.set_enabled(bool(config.get("haptics", 1)))
    theme = Theme(config)
    ctx = AppContext(page, config, theme)

    now = datetime.now()
    ctx.view["year"], ctx.view["month"] = now.year, now.month

    # ---------- шапка ----------
    salary_text = theme.text("0 ₽", role="accent", size=30,
                             weight=ft.FontWeight.BOLD)
    stats_subtext = theme.text("", role="dim", size=11)
    # Круглые стеклянные кнопки вместо IconButton: у того активная зона
    # была немногим больше самой иконки, и попасть по шестерёнке с первого
    # раза не получалось. Здесь зона нажатия — весь круг 48 px.
    settings_button = theme.glass_key(
        theme.icon(ft.Icons.SETTINGS, role="accent", size=25),
        lambda: show_settings(), size=HEADER_KEY_SIZE)
    today_button = theme.glass_key(
        theme.icon(ft.Icons.CHECK_CIRCLE_OUTLINE, role="accent", size=25),
        lambda: mark_today(), size=HEADER_KEY_SIZE)

    header_card = theme.card(
        ft.Row([
            ft.Column([
                theme.text("КАЛЕНДАРЬ СМЕН PRO", role="faint", size=11),
                salary_text, stats_subtext,
            ], spacing=1, expand=True),
            # Обе кнопки в ряд и по центру карточки по вертикали:
            # столбиком шестерёнка проваливалась к нижнему краю.
            ft.Row([today_button, settings_button], spacing=8, tight=True,
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER),
        blur=True, height=HEADER_CARD_HEIGHT, stretch=False,
    )

    # ==========================================
    # СИСТЕМНЫЕ ОТСТУПЫ
    # ==========================================
    def system_inset(side):
        """Высота статус-бара и навигационной полосы в dp: Flet отдаёт их
        в page.media и обновляет при повороте экрана."""
        fallback = FALLBACK_INSET_TOP if side == "top" else FALLBACK_INSET_BOTTOM
        media = getattr(page, "media", None)
        padding = getattr(media, "padding", None) if media else None
        value = getattr(padding, side, None) if padding else None
        try:
            value = float(value)
        except (TypeError, ValueError):
            return fallback
        return value if value > 0 else fallback

    # ---------- экраны ----------
    calendar_view = CalendarView(ctx)
    pin_view = PinView(ctx, on_success=lambda: show_main())
    mode_view = ModeView(ctx, on_done=lambda: show_pin())
    screens = {}
    spacers = []

    def add_edge_spacers(control):
        """Отступ живёт внутри прокрутки: если обрезать viewport padding'ом,
        контент упрётся в границу и не сможет проехать под шапкой."""
        if not hasattr(control, "controls"):
            return
        top = ft.Container(height=1)
        bottom = ft.Container(height=1)
        control.controls.insert(0, top)
        control.controls.append(bottom)
        spacers.append((top, bottom))

    def sync_spacers():
        top_height = system_inset("top") + HEADER_CARD_HEIGHT + GAP_TOP
        bottom_height = system_inset("bottom") + NAV_CARD_HEIGHT + GAP_BOTTOM
        for top, bottom in spacers:
            top.height = top_height
            bottom.height = bottom_height
            refresh_tree(top, bottom)

    add_edge_spacers(calendar_view.control)

    def get_analytics():
        view = screens.get("analytics")
        if view is None:
            view = AnalyticsView(ctx)
            add_edge_spacers(view.control)
            screens["analytics"] = view
            sync_spacers()
        return view

    def get_settings():
        view = screens.get("settings")
        if view is None:
            view = SettingsView(ctx)
            screens["settings"] = view
        return view

    tab_holder = ft.Container(content=calendar_view.control, expand=True)

    def on_tab_change(index):
        ctx.touch()
        haptics.select()
        if index == 0:
            tab_holder.content = calendar_view.control
        else:
            analytics = get_analytics()
            tab_holder.content = analytics.control
            if ctx.analytics_dirty:
                analytics.refresh()
                ctx.analytics_dirty = False
        paint_nav(index)
        refresh_tree(tab_holder, nav_bar)

    # ---------- навигация ----------
    nav_state = {"index": 0}
    nav_items = []

    def make_nav_item(index, icon, label):
        icon_control = ft.Icon(icon, size=20)
        text_control = ft.Text(label, size=11)
        pill = ft.Container(
            content=ft.Row([icon_control, text_control], spacing=8, tight=True,
                           alignment=ft.MainAxisAlignment.CENTER),
            padding=ft.Padding.symmetric(horizontal=18, vertical=10),
            border_radius=22,
            on_click=lambda e, i=index: on_tab_change(i),
        )
        nav_items.append((pill, icon_control, text_control))
        return pill

    def paint_nav(index):
        nav_state["index"] = index
        for position, (pill, icon_control, text_control) in enumerate(nav_items):
            active = position == index
            pill.bgcolor = theme.accent_a("33") if active else "#00000000"
            pill.border = (ft.Border.all(1, theme.accent_a("66")) if active
                           else None)
            color = theme.accent() if active else theme.color("text_dim")
            icon_control.color = color
            text_control.color = color
            text_control.weight = ft.FontWeight.BOLD if active else None

    # stretch=False: навигация остаётся «таблеткой» по центру, а не
    # растягивается на всю ширину, как обычные карточки.
    nav_bar = theme.card(
        ft.Row([
            make_nav_item(0, ft.Icons.CALENDAR_MONTH, "Календарь"),
            make_nav_item(1, ft.Icons.BAR_CHART, "Аналитика"),
        ], alignment=ft.MainAxisAlignment.CENTER, spacing=10),
        blur=True, blur_sigma=NAV_BLUR, padding=6, border_radius=26,
        height=NAV_CARD_HEIGHT, stretch=False,
    )
    paint_nav(0)

    # Stack вместо Column: контент лежит на всю высоту, шапка и навигация —
    # поверх него. Только так карточки проезжают под стеклом и блюр
    # получает что размывать.
    main_layout = ft.Stack([
        ft.Container(
            expand=True,
            padding=ft.Padding.symmetric(horizontal=SIDE_PADDING),
            content=tab_holder,
        ),
        ft.Container(
            top=0, left=SIDE_PADDING, right=SIDE_PADDING,
            content=ft.SafeArea(content=header_card),
        ),
        ft.Container(
            bottom=0, left=SIDE_PADDING, right=SIDE_PADDING,
            content=ft.SafeArea(content=ft.Row(
                [nav_bar], alignment=ft.MainAxisAlignment.CENTER)),
        ),
    ], expand=True)

    # ---------- роутер ----------
    if USE_SCREEN_ANIMATION and hasattr(ft, "AnimatedSwitcher"):
        screen_holder = ft.AnimatedSwitcher(
            content=ft.Container(), expand=True, duration=SWITCHER_MS,
            transition=ft.AnimatedSwitcherTransition.FADE,
        )
    else:
        screen_holder = ft.Container(expand=True)

    def sync_switcher():
        if hasattr(screen_holder, "duration"):
            screen_holder.duration = 0 if theme.simple_bg() else SWITCHER_MS

    def set_screen(control, full=False):
        screen_holder.content = control
        # page.update() гоняет по сокету всё дерево (~400 узлов одного
        # календаря), поэтому остаётся только там, где менялись свойства
        # самой страницы: bgcolor, theme, theme_mode.
        if full:
            page.update()
        else:
            refresh_tree(screen_holder)

    # ---------- данные ----------
    def apply_theme():
        changed = theme.apply(page)
        paint_nav(nav_state["index"])
        sync_switcher()
        theme.refresh_background()
        if changed:
            page.update()
        else:
            refresh_tree(screen_holder)

    def update_header():
        summary = month_summary(ctx.month_data, config)
        salary_text.value = format_money(summary["net"])
        stats_subtext.value = (
            f"{MONTH_NAMES[ctx.view['month'] - 1]} · "
            f"{format_hours(summary['total_hours'])} ч · "
            f"{summary['shifts']} смен · премия "
            f"{format_money(summary['premium_money'] + summary['premium_paid'])}")
        refresh_tree(salary_text, stats_subtext, header_card)

    def update_comparison(current_net):
        """Сравнение с прошлым месяцем — один дополнительный запрос."""
        year, month = prev_month(ctx.view["year"], ctx.view["month"])
        previous = month_summary(db.get_month_shifts(year, month, mode_of(config)),
                                 config)
        if not previous["shifts"] and not previous["premium_paid"]:
            ctx.compare_text = ""
            return
        delta = current_net - previous["net"]
        ctx.compare_text = (f"{format_signed_money(delta)} "
                            f"к {MONTH_NAMES[month - 1].lower()}")

    def reload_month():
        """Единственное чтение месяца из БД — им пользуются все экраны."""
        year, month = ctx.view["year"], ctx.view["month"]
        mode = mode_of(config)
        ctx.month_data = db.get_month_shifts(year, month, mode)
        # Производство и трекер читаются только по текущему режиму:
        # дневные и ночные записи лежат раздельно и не смешиваются.
        ctx.production_data = db.get_month_production(year, month, mode)
        ctx.timeline_dates = db.get_timeline_dates(year, month, mode)
        update_comparison(month_summary(ctx.month_data, config)["net"])
        update_header()
        calendar_view.refresh()
        ctx.analytics_dirty = True
        analytics = screens.get("analytics")
        if analytics is not None and tab_holder.content is analytics.control:
            analytics.refresh()
            ctx.analytics_dirty = False

    def refresh_after_change():
        analytics = screens.get("analytics")
        if analytics is not None:
            analytics.invalidate_year()
        reload_month()

    def rebuild_for_mode():
        """
        Пересборка после смены режима. Модалка дня строится один раз, и
        её подписи с сеткой прихода зашиты при сборке — поэтому кэш
        сбрасывается, дерево соберётся заново с новыми надписями.
        """
        drop_day_modal()
        analytics = screens.get("analytics")
        if analytics is not None:
            analytics.invalidate_year()
        reload_month()

    # ---------- быстрый ввод ----------
    def mark_today():
        """Одно нажатие: сегодня — рабочая смена с приходом вовремя."""
        ctx.touch()
        today = date.today()
        date_str = today.strftime("%Y-%m-%d")
        existing = db.get_shift(date_str, mode_of(config)) or {}
        if existing.get("status") == STATUS_WORK:
            haptics.warn()
            return

        db.save_shift(date_str, FULL_SHIFT_HOURS, STATUS_WORK,
                      ARRIVAL_ON_TIME, existing.get("note"), None,
                      mode_of(config))
        haptics.confirm()

        # Если открыт другой месяц — перебрасываем на текущий, иначе
        # отметка появится «где-то там» и будет незаметна.
        ctx.view["year"], ctx.view["month"] = today.year, today.month
        refresh_after_change()

    # ---------- автоблокировка ----------
    def do_lock():
        """Сначала закрываем диалог: AlertDialog живёт в отдельном слое
        над деревом, подмена экрана его не убирает — он остался бы
        висеть поверх PIN."""
        force_close_dialog(ctx)
        show_pin()

    idle_lock = IdleLock(on_lock=do_lock)
    idle_lock.set_dirty_check(lambda: bool(ctx.dialog_dirty))
    ctx.touch = idle_lock.touch
    ctx.on_unlock = idle_lock.arm
    ctx.rebuild_for_mode = rebuild_for_mode

    # ---------- переходы ----------
    def show_mode_choice():
        """Первый запуск: выбор режима до создания PIN-кода."""
        idle_lock.disarm()
        mode_view.show()
        changed = theme.apply(page)
        sync_switcher()
        set_screen(mode_view.control, full=changed)

    def show_pin(force_setup=False):
        idle_lock.disarm()
        pin_view.show(force_setup=force_setup)
        changed = theme.apply(page)
        sync_switcher()
        set_screen(pin_view.control, full=changed)

    def show_main():
        changed = theme.apply(page)
        paint_nav(nav_state["index"])
        sync_switcher()
        sync_spacers()
        analytics = screens.get("analytics")
        if analytics is not None:
            analytics.invalidate_year()
        reload_month()
        set_screen(main_layout, full=changed)

    def show_settings():
        ctx.touch()
        view = get_settings()
        view.load()
        changed = theme.apply(page)
        sync_switcher()
        set_screen(view.control, full=changed)

    def on_layout_change(e=None):
        sync_spacers()

    def on_app_state(e=None):
        idle_lock.handle_app_state(getattr(e, "data", None) or e)

    # Имена событий отличаются между сборками Flet — привязываем безопасно.
    bind_event(page, on_layout_change,
               "on_media_change", "on_media_changed", "on_resized", "on_resize")
    bind_event(page, on_app_state,
               "on_app_lifecycle_state_change", "on_app_lifecycle_state",
               "on_lifecycle_state_change")

    ctx.show_pin = show_pin
    ctx.show_main = show_main
    ctx.show_settings = show_settings
    ctx.reload_month = reload_month
    ctx.refresh_after_change = refresh_after_change
    ctx.apply_theme = apply_theme

    # ---------- старт ----------
    drop_day_modal()
    page.add(ft.Stack(expand=True, controls=[theme.background(), screen_holder]))
    # Режим спрашивается один раз за всю историю пользования.
    if config.get("mode_chosen"):
        show_pin()
    else:
        show_mode_choice()

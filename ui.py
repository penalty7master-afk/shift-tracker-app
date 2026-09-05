from datetime import datetime

import flet as ft

import haptics
from calculations import format_hours, format_money, month_summary
from constants import MONTH_NAMES
from database import db
from theme import Theme
from views.analytics_view import AnalyticsView
from views.calendar_view import CalendarView
from views.common import AppContext, refresh_tree
from views.pin_view import PinView
from views.settings_view import SettingsView

# Анимация смены экрана выключена намеренно. AnimatedSwitcher держит в дереве
# сразу оба экрана и рисует их через слой прозрачности — отсюда была
# «заморозка» при входе в настройки и выходе из них.
# Поставь True, чтобы вернуть плавный переход.
USE_SCREEN_ANIMATION = False
SWITCHER_MS = 140

# Высота слоёв, лежащих поверх контента. Ровно на столько же отступают
# распорки внутри прокрутки, иначе первая карточка окажется под шапкой.
# Значения подобраны под экран 720p; правь здесь, если не сойдётся.
HEADER_SPACE = 112
NAV_SPACE = 76

SIDE_PADDING = 10


# ==========================================
# СБОРКА ПРИЛОЖЕНИЯ
# ==========================================
def main(page: ft.Page):
    page.title = "КАЛЕНДАРЬ СМЕН PRO"
    page.padding = 0

    # Виброотклик: сервис регистрируется один раз, дальше зовётся из экранов.
    haptics.setup(page)

    config = db.get_config()
    theme = Theme(config)
    ctx = AppContext(page, config, theme)

    now = datetime.now()
    ctx.view["year"], ctx.view["month"] = now.year, now.month

    # ---------- шапка ----------
    salary_text = theme.text("0 ₽", role="accent", size=30,
                             weight=ft.FontWeight.BOLD)
    stats_subtext = theme.text("", role="dim", size=11)
    settings_button = theme.icon_button(ft.Icons.SETTINGS, role="accent",
                                        on_click=lambda e: show_settings())

    header_card = theme.card(
        ft.Row([
            ft.Column([
                theme.text("КАЛЕНДАРЬ СМЕН PRO", role="faint", size=11),
                salary_text, stats_subtext,
            ], spacing=1, expand=True),
            settings_button,
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.START),
        blur=True,
    )

    # ---------- экраны ----------
    # Аналитика и настройки строятся при первом показе: раньше все четыре
    # экрана висели в дереве постоянно и участвовали в каждом дифе.
    calendar_view = CalendarView(ctx)
    pin_view = PinView(ctx, on_success=lambda: show_main())
    screens = {}

    def add_edge_spacers(control):
        """
        Пустые распорки внутри прокручиваемой колонки. Отступ должен жить
        именно здесь, а не снаружи: если обрезать viewport padding'ом,
        контент упрётся в границу и не сможет проехать под шапкой.
        """
        if not hasattr(control, "controls"):
            return
        control.controls.insert(0, ft.Container(height=HEADER_SPACE))
        control.controls.append(ft.Container(height=NAV_SPACE))

    add_edge_spacers(calendar_view.control)

    def get_analytics():
        view = screens.get("analytics")
        if view is None:
            view = AnalyticsView(ctx)
            add_edge_spacers(view.control)
            screens["analytics"] = view
        return view

    def get_settings():
        view = screens.get("settings")
        if view is None:
            view = SettingsView(ctx)
            screens["settings"] = view
        return view

    tab_holder = ft.Container(content=calendar_view.control, expand=True)

    def on_tab_change(index):
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

    # Стеклянная навигация вместо системного NavigationBar с чёрной плашкой
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

    nav_bar = theme.card(
        ft.Row([
            make_nav_item(0, ft.Icons.CALENDAR_MONTH, "Календарь"),
            make_nav_item(1, ft.Icons.BAR_CHART, "Аналитика"),
        ], alignment=ft.MainAxisAlignment.CENTER, spacing=10),
        blur=True, padding=6, border_radius=26,
    )
    paint_nav(0)

    # Stack вместо Column: контент лежит на всю высоту экрана, шапка и
    # навигация — поверх него. Только так карточки проезжают под стеклом,
    # и backdrop-blur получает что размывать. В Column слои не пересекались,
    # и блюр размывал ровный градиент, то есть не давал ничего.
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
    # У обоих вариантов держателя есть .content, остальной код от выбора
    # не зависит.
    if USE_SCREEN_ANIMATION and hasattr(ft, "AnimatedSwitcher"):
        screen_holder = ft.AnimatedSwitcher(
            content=ft.Container(), expand=True, duration=SWITCHER_MS,
            transition=ft.AnimatedSwitcherTransition.FADE,
        )
    else:
        screen_holder = ft.Container(expand=True)

    def sync_switcher():
        """В режиме скорости анимация экранов гасится полностью."""
        if hasattr(screen_holder, "duration"):
            screen_holder.duration = 0 if theme.simple_bg() else SWITCHER_MS

    def set_screen(control, full=False):
        screen_holder.content = control
        # page.update() гоняет по сокету всё дерево (один календарь — это
        # ~400 узлов), поэтому он остаётся только там, где реально менялись
        # свойства самой страницы: bgcolor, theme, theme_mode.
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
        # Точечное обновление: без него цифра в шапке ждала ближайшего
        # общего page.update() и отставала от нижней карточки.
        refresh_tree(salary_text, stats_subtext, header_card)

    def reload_month():
        """Единственное чтение месяца из БД — им пользуются все экраны."""
        year, month = ctx.view["year"], ctx.view["month"]
        ctx.month_data = db.get_month_shifts(year, month)
        ctx.production_data = db.get_month_production(year, month)
        ctx.timeline_dates = db.get_timeline_dates(year, month)
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

    # ---------- переходы ----------
    def show_pin(force_setup=False):
        pin_view.show(force_setup=force_setup)
        changed = theme.apply(page)
        sync_switcher()
        set_screen(pin_view.control, full=changed)

    def show_main():
        changed = theme.apply(page)
        paint_nav(nav_state["index"])
        sync_switcher()
        analytics = screens.get("analytics")
        if analytics is not None:
            analytics.invalidate_year()
        reload_month()
        set_screen(main_layout, full=changed)

    def show_settings():
        view = get_settings()
        view.load()
        changed = theme.apply(page)
        sync_switcher()
        set_screen(view.control, full=changed)

    ctx.show_pin = show_pin
    ctx.show_main = show_main
    ctx.show_settings = show_settings
    ctx.reload_month = reload_month
    ctx.refresh_after_change = refresh_after_change
    ctx.apply_theme = apply_theme

    # ---------- старт ----------
    # Один фон на всё приложение вместо отдельного на каждом экране.
    page.add(ft.Stack(expand=True, controls=[theme.background(), screen_holder]))
    show_pin()

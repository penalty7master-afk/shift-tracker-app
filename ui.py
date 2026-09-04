from datetime import datetime

import flet as ft

from calculations import format_hours, format_money, month_summary
from constants import MONTH_NAMES
from database import db
from theme import Theme
from views.analytics_view import AnalyticsView
from views.calendar_view import CalendarView
from views.common import AppContext
from views.pin_view import PinView
from views.settings_view import SettingsView


# ==========================================
# СБОРКА ПРИЛОЖЕНИЯ
# ==========================================
def main(page: ft.Page):
    page.title = "КАЛЕНДАРЬ СМЕН PRO"
    page.padding = 0

    config = db.get_config()
    theme = Theme(config)
    ctx = AppContext(page, config, theme)
    ctx.production_data = {}

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
    calendar_view = CalendarView(ctx)
    analytics_view = AnalyticsView(ctx)
    settings_view = SettingsView(ctx)
    pin_view = PinView(ctx, on_success=lambda: show_main())

    tab_holder = ft.Container(content=calendar_view.control, expand=True)

    def on_tab_change(e):
        if e.control.selected_index == 0:
            tab_holder.content = calendar_view.control
        else:
            tab_holder.content = analytics_view.control
            if ctx.analytics_dirty:
                analytics_view.refresh()
                ctx.analytics_dirty = False
        page.update()

    nav_bar = ft.NavigationBar(
        destinations=[
            ft.NavigationBarDestination(icon=ft.Icons.CALENDAR_MONTH, label="Календарь"),
            ft.NavigationBarDestination(icon=ft.Icons.BAR_CHART, label="Аналитика"),
        ],
        selected_index=0, on_change=on_tab_change,
    )

    main_layout = ft.Container(
        expand=True, padding=10,
        content=ft.Column([ft.SafeArea(content=header_card), tab_holder],
                          expand=True, spacing=10),
    )

    # ---------- роутер ----------
    # AnimatedSwitcher есть не во всех сборках: у обоих вариантов есть .content
    if hasattr(ft, "AnimatedSwitcher"):
        screen_holder = ft.AnimatedSwitcher(
            content=ft.Container(), expand=True, duration=220,
            transition=ft.AnimatedSwitcherTransition.FADE,
        )
    else:
        screen_holder = ft.Container(expand=True)

    def set_screen(control, nav=None):
        screen_holder.content = control
        page.navigation_bar = nav
        page.update()

    # ---------- данные ----------
    def apply_theme():
        theme.apply(page)
        page.update()

    def update_header():
        summary = month_summary(ctx.month_data, config)
        salary_text.value = format_money(summary["net"])
        stats_subtext.value = (
            f"{MONTH_NAMES[ctx.view['month'] - 1]} · "
            f"{format_hours(summary['total_hours'])} ч · "
            f"{summary['shifts']} смен · премия "
            f"{format_money(summary['premium_money'])}")

    def reload_month():
        """Единственное чтение месяца из БД — им пользуются все экраны."""
        year, month = ctx.view["year"], ctx.view["month"]
        ctx.month_data = db.get_month_shifts(year, month)
        ctx.production_data = db.get_month_production(year, month)
        ctx.timeline_dates = db.get_timeline_dates(year, month)
        update_header()
        calendar_view.refresh()
        ctx.analytics_dirty = True
        if tab_holder.content is analytics_view.control:
            analytics_view.refresh()
            ctx.analytics_dirty = False

    def refresh_after_change():
        analytics_view.invalidate_year()
        reload_month()

    # ---------- переходы ----------
    def show_pin(force_setup=False):
        pin_view.show(force_setup=force_setup)
        theme.apply(page)
        set_screen(pin_view.control, nav=None)

    def show_main():
        theme.apply(page)
        analytics_view.invalidate_year()
        reload_month()
        set_screen(main_layout, nav=nav_bar)

    def show_settings():
        settings_view.load()
        theme.apply(page)
        set_screen(settings_view.control, nav=None)

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

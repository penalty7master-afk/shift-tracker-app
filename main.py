import os
import sqlite3
import json
import hashlib
from datetime import date
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.spinner import Spinner
from kivy.uix.scrollview import ScrollView
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.slider import Slider
from kivy.uix.widget import Widget
from kivy.uix.image import Image as KivyImage
from kivy.uix.popup import Popup
from kivy.core.window import Window
from kivy.graphics import Color, Ellipse, RoundedRectangle, Line
from kivy.utils import get_color_from_hex

# ---------------------------------------------------------------------------
# Базовая настройка окна
# ---------------------------------------------------------------------------
Window.clearcolor = get_color_from_hex("#1c144a")
# Чтобы системная клавиатура не перекрывала поля ввода (сдвигает контент вверх)
Window.softinput_mode = "below_target"

MONTH_DAYS = {'Сентябрь': 30, 'Октябрь': 31, 'Ноябрь': 30, 'Декабрь': 31}

# Акцентные цвета тем (влияют на заголовки и подсветку)
THEME_ACCENTS = {
    "Aurora Violet": "#c9a6ff",
    "Midnight Blue": "#7dd3fc",
    "Emerald Mint": "#6ee7b7",
}

GLASS_FILL = (1, 1, 1, 0.10)      # полупрозрачная заливка "стекла"
GLASS_BORDER = (1, 1, 1, 0.22)    # тонкая светлая обводка
CARD_RADIUS = 22

ACCENT_GREEN = "#6ee7b7"
ACCENT_YELLOW = "#fde68a"
ACCENT_RED = "#fca5a5"
ACCENT_BLUE = "#93c5fd"
TEXT_DIM = "#c9c3e8"
TEXT_MAIN = "#f5f3ff"


def add_glass_background(widget, radius=CARD_RADIUS, fill=GLASS_FILL, border=GLASS_BORDER):
    """Рисует на canvas виджета полупрозрачную скруглённую 'стеклянную' панель,
    которая сама следует за изменением размера/позиции виджета."""
    with widget.canvas.before:
        Color(*fill)
        rect = RoundedRectangle(pos=widget.pos, size=widget.size, radius=[radius])
        Color(*border)
        line = Line(rounded_rectangle=(widget.x, widget.y, widget.width, widget.height, radius), width=1.1)

    def _update(instance, _value):
        rect.pos = instance.pos
        rect.size = instance.size
        line.rounded_rectangle = (instance.x, instance.y, instance.width, instance.height, radius)

    widget.bind(pos=_update, size=_update)


class GlassPanel(BoxLayout):
    """Контейнер-карточка в стиле 'жидкого стекла': скруглённые углы,
    полупрозрачная заливка, мягкая обводка."""
    def __init__(self, **kwargs):
        radius = kwargs.pop('radius', CARD_RADIUS)
        super().__init__(**kwargs)
        add_glass_background(self, radius=radius)


def styled_field(widget_cls, **kwargs):
    """Хелпер для полей ввода/спиннеров: убирает стандартный фон Kivy
    и красит его в полупрозрачный 'стеклянный' стиль."""
    kwargs.setdefault('background_normal', '')
    kwargs.setdefault('background_active', '')
    kwargs.setdefault('background_color', (1, 1, 1, 0.14))
    kwargs.setdefault('foreground_color', get_color_from_hex(TEXT_MAIN))
    kwargs.setdefault('cursor_color', get_color_from_hex(ACCENT_BLUE))
    kwargs.setdefault('padding', [14, 10, 14, 10])
    return widget_cls(**kwargs)


def section_label(text, color=None, size='13sp'):
    return Label(
        text=text, font_size=size, bold=True,
        color=get_color_from_hex(color or ACCENT_BLUE),
        size_hint_y=None, height=26, halign='left', valign='middle'
    )


class BackgroundScreen(Screen):
    """Базовый экран с общим градиентным фоном 'Liquid Glass'."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.root_float = FloatLayout()
        bg = KivyImage(source='background.png', allow_stretch=True, keep_ratio=False,
                        size_hint=(1, 1), pos_hint={'x': 0, 'y': 0})
        self.root_float.add_widget(bg)
        super(BackgroundScreen, self).add_widget(self.root_float)

    def add_widget(self, widget, *args, **kwargs):
        # Пока root_float ещё не создан (во время super().__init__ у подклассов) —
        # ведём себя как обычный Screen.
        if not hasattr(self, 'root_float'):
            return super().add_widget(widget, *args, **kwargs)
        return self.root_float.add_widget(widget, *args, **kwargs)


class PieChart(Widget):
    """Кольцевая (donut) диаграмма в стиле Liquid Glass."""
    def __init__(self, custom_colors=None, hole_color="#241a5c", **kwargs):
        super().__init__(**kwargs)
        self.data = []
        self.custom_colors = custom_colors if custom_colors else ["#6ee7b7", "#fde68a", "#fca5a5"]
        self.hole_color = hole_color
        self.bind(pos=self.draw, size=self.draw)

    def update_data(self, values_list):
        total = sum(values_list)
        if total == 0:
            self.data = []
        else:
            self.data = [v / total * 360 for v in values_list]
        self.draw()

    def draw(self, *args):
        self.canvas.clear()
        if not self.data or sum(self.data) == 0:
            with self.canvas:
                Color(1, 1, 1, 0.10)
                Ellipse(pos=self.pos, size=self.size)
            return
        current_angle = 0
        with self.canvas:
            for angle, color in zip(self.data, self.custom_colors):
                if angle == 0:
                    continue
                Color(*get_color_from_hex(color))
                Ellipse(pos=self.pos, size=self.size, angle_start=current_angle, angle_end=current_angle + angle)
                current_angle += angle
            # "дырка" пончика — делает диаграмму кольцевой
            hole_ratio = 0.55
            hx = self.x + self.width * (1 - hole_ratio) / 2
            hy = self.y + self.height * (1 - hole_ratio) / 2
            Color(*get_color_from_hex(self.hole_color))
            Ellipse(pos=(hx, hy), size=(self.width * hole_ratio, self.height * hole_ratio))


class DonutWithLabel(FloatLayout):
    """Кольцевая диаграмма с числом-процентом по центру."""
    def __init__(self, custom_colors=None, **kwargs):
        super().__init__(size_hint=(None, None), size=(96, 96), **kwargs)
        self.chart = PieChart(custom_colors=custom_colors, size_hint=(1, 1))
        self.center_label = Label(text="", font_size='15sp', bold=True,
                                   color=get_color_from_hex(TEXT_MAIN), size_hint=(1, 1))
        self.add_widget(self.chart)
        self.add_widget(self.center_label)

    def update_data(self, values_list, center_text=""):
        self.chart.update_data(values_list)
        self.center_label.text = center_text


class MainScreen(BackgroundScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app = App.get_running_app()
        self.breaks_data = []

        root = BoxLayout(orientation='vertical', padding=14, spacing=10, size_hint=(1, 1))

        # Верхний тулбар
        top_bar = BoxLayout(orientation='horizontal', size_hint_y=None, height=42)
        self.title_lbl = Label(text="Мой Календарь Смен", font_size='19sp', bold=True,
                                color=get_color_from_hex(THEME_ACCENTS["Aurora Violet"]), halign='left')
        top_bar.add_widget(self.title_lbl)
        btn_settings = Button(text="\u22ee", font_size='22sp', size_hint_x=None, width=44,
                               background_normal='', background_color=(1, 1, 1, 0.12),
                               color=get_color_from_hex(TEXT_MAIN))
        btn_settings.bind(on_press=self.go_to_settings)
        top_bar.add_widget(btn_settings)
        root.add_widget(top_bar)

        # Панель даты — стеклянная карточка
        date_card = GlassPanel(orientation='horizontal', size_hint_y=None, height=48,
                                spacing=8, padding=6)
        self.month_spinner = styled_field(Spinner, text='Сентябрь',
                                           values=('Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'))
        self.month_spinner.bind(text=self.on_month_change)
        date_card.add_widget(self.month_spinner)

        day_values = [str(i) for i in range(1, MONTH_DAYS['Сентябрь'] + 1)]
        self.day_spinner = styled_field(Spinner, text='1', values=day_values)
        self.day_spinner.bind(text=self.load_day_data)
        date_card.add_widget(self.day_spinner)
        root.add_widget(date_card)

        # Карточка параметров смены
        day_scroll = ScrollView(size_hint_y=None, height=240)
        day_card = GlassPanel(orientation='vertical', size_hint_y=None, padding=12, spacing=6)
        day_card.bind(minimum_height=day_card.setter('height'))
        grid = GridLayout(cols=2, spacing=8, size_hint_y=None)
        grid.bind(minimum_height=grid.setter('height'))

        grid.add_widget(section_label("Статус дня:", TEXT_DIM, '12sp'))
        self.status_spinner = styled_field(
            Spinner, text='Отработал',
            values=('Отработал', 'Обычный выходной / Болел', 'Выходной под премию (День 1)',
                    'Выходной под премию (День 2)', 'Проспал (не пустила охрана)'),
            size_hint_y=None, height=34
        )
        self.status_spinner.bind(text=self.on_status_change)
        grid.add_widget(self.status_spinner)

        self.lbl_dynamic = section_label("Время приезда (ЧЧ:ММ):", TEXT_DIM, '12sp')
        grid.add_widget(self.lbl_dynamic)
        self.input_dynamic = styled_field(TextInput, text="20:00", multiline=False, halign='center',
                                           size_hint_y=None, height=34)
        grid.add_widget(self.input_dynamic)

        grid.add_widget(section_label("Фактический старт:", TEXT_DIM, '12sp'))
        self.input_work_start = styled_field(TextInput, text="20:00", multiline=False, halign='center',
                                              size_hint_y=None, height=34)
        grid.add_widget(self.input_work_start)

        grid.add_widget(section_label("Напарник:", TEXT_DIM, '12sp'))
        self.input_partner = styled_field(TextInput, text="", multiline=False, halign='center',
                                           size_hint_y=None, height=34)
        grid.add_widget(self.input_partner)

        grid.add_widget(section_label("Старший (Оператор):", TEXT_DIM, '12sp'))
        self.operator_spinner = styled_field(Spinner, text='Оператор 1',
                                              values=('Оператор 1', 'Оператор 2', 'Оператор 3', 'Оператор 4'),
                                              size_hint_y=None, height=34)
        grid.add_widget(self.operator_spinner)

        grid.add_widget(section_label("Тип продукции:", TEXT_DIM, '12sp'))
        self.prod_type_spinner = styled_field(Spinner, text='Не выбрано',
                                               values=['Не выбрано', '+ Добавить новый тип...'],
                                               size_hint_y=None, height=34)
        self.prod_type_spinner.bind(text=self.on_prod_spinner_select)
        grid.add_widget(self.prod_type_spinner)

        grid.add_widget(section_label("Вес продукции (кг):", TEXT_DIM, '12sp'))
        self.input_prod = styled_field(TextInput, text="", multiline=False, input_filter='float',
                                        halign='center', size_hint_y=None, height=34)
        grid.add_widget(self.input_prod)

        self.btn_add_break = Button(text="+ Перекур / сбой", size_hint_y=None, height=34,
                                     background_normal='', background_color=(0.55, 0.75, 1, 0.28),
                                     color=get_color_from_hex(TEXT_MAIN))
        self.btn_add_break.bind(on_press=self.show_add_break_popup)
        grid.add_widget(self.btn_add_break)

        self.lbl_breaks_count = Label(text="Событий записано: 0", color=get_color_from_hex(TEXT_DIM),
                                       font_size='12sp', size_hint_y=None, height=34)
        grid.add_widget(self.lbl_breaks_count)

        day_card.add_widget(grid)
        day_scroll.add_widget(day_card)
        root.add_widget(day_scroll)

        btn_save = Button(text="Сохранить смену", font_size='15sp', bold=True, size_hint_y=None, height=46,
                           background_normal='', background_color=get_color_from_hex(ACCENT_GREEN),
                           color=(0.08, 0.1, 0.08, 1))
        btn_save.bind(on_press=self.save_day_data)
        root.add_widget(btn_save)

        # --- Аналитика ---
        analytics_scroll = ScrollView()
        analytics_box = BoxLayout(orientation='vertical', spacing=10, size_hint_y=None)
        analytics_box.bind(minimum_height=analytics_box.setter('height'))

        card1 = GlassPanel(orientation='horizontal', size_hint_y=None, height=110, padding=12, spacing=14)
        col1 = BoxLayout(orientation='vertical', spacing=2)
        col1.add_widget(section_label("АНАЛИТИКА ПРИБЫТИЯ НА СМЕНУ", ACCENT_GREEN, '12sp'))
        self.lbl_stat_ontime = Label(text="[color=6ee7b7]\u25cf[/color] Вовремя: 0%", markup=True,
                                      halign='left', font_size='12sp', color=get_color_from_hex(TEXT_MAIN))
        self.lbl_stat_buffer = Label(text="[color=fde68a]\u25cf[/color] Ожидание: 0%", markup=True,
                                      halign='left', font_size='12sp', color=get_color_from_hex(TEXT_MAIN))
        self.lbl_stat_late = Label(text="[color=fca5a5]\u25cf[/color] Опоздание: 0%", markup=True,
                                    halign='left', font_size='12sp', color=get_color_from_hex(TEXT_MAIN))
        for lb in (self.lbl_stat_ontime, self.lbl_stat_buffer, self.lbl_stat_late):
            lb.bind(size=lambda i, v: setattr(i, 'text_size', (i.width, None)))
            col1.add_widget(lb)
        card1.add_widget(col1)
        self.chart_time = DonutWithLabel(custom_colors=[ACCENT_GREEN, ACCENT_YELLOW, ACCENT_RED])
        card1.add_widget(self.chart_time)
        analytics_box.add_widget(card1)

        card2 = GlassPanel(orientation='horizontal', size_hint_y=None, height=110, padding=12, spacing=14)
        col2 = BoxLayout(orientation='vertical', spacing=2)
        col2.add_widget(section_label("ВЫРАБОТКА (норма 2100 кг)", ACCENT_BLUE, '12sp'))
        self.lbl_prod_high = Label(text="[color=6ee7b7]\u25cf[/color] Норма выполнена: 0%", markup=True,
                                    halign='left', font_size='12sp', color=get_color_from_hex(TEXT_MAIN))
        self.lbl_prod_low = Label(text="[color=fca5a5]\u25cf[/color] Меньше нормы: 0%", markup=True,
                                   halign='left', font_size='12sp', color=get_color_from_hex(TEXT_MAIN))
        for lb in (self.lbl_prod_high, self.lbl_prod_low):
            lb.bind(size=lambda i, v: setattr(i, 'text_size', (i.width, None)))
            col2.add_widget(lb)
        card2.add_widget(col2)
        self.chart_prod = DonutWithLabel(custom_colors=[ACCENT_GREEN, ACCENT_RED])
        card2.add_widget(self.chart_prod)
        analytics_box.add_widget(card2)

        card3 = GlassPanel(orientation='vertical', size_hint_y=None, padding=14, spacing=6)
        card3.bind(minimum_height=card3.setter('height'))
        card3.add_widget(section_label("РАСЧЁТ НАЧИСЛЕНИЙ ЗА МЕСЯЦ", "#c9a6ff", '13sp'))
        self.lbl_out_shifts = Label(text="Отработано смен: 0 ночей", size_hint_y=None, height=22,
                                     halign='left', font_size='13sp', color=get_color_from_hex(TEXT_MAIN))
        self.lbl_out_money = Label(text="Чистый оклад за часы: 0 \u20bd", size_hint_y=None, height=22,
                                    halign='left', font_size='13sp', color=get_color_from_hex(TEXT_MAIN))
        self.lbl_out_hours = Label(text="Часов премии по таблице: 0 ч.", size_hint_y=None, height=22,
                                    halign='left', font_size='13sp', color=get_color_from_hex(TEXT_MAIN))
        self.lbl_out_bonus = Label(text="Сумма премий из таблицы: 0 \u20bd", size_hint_y=None, height=22,
                                    halign='left', font_size='13sp', color=get_color_from_hex(TEXT_MAIN))
        self.lbl_out_virtual = Label(text="На премиальных выходных: 0 \u20bd", size_hint_y=None, height=22,
                                      halign='left', font_size='13sp', color=get_color_from_hex(TEXT_MAIN))
        self.lbl_out_total = Label(text="ИТОГО К ВЫПЛАТЕ: 0 \u20bd", font_size='17sp', bold=True,
                                    size_hint_y=None, height=32, color=get_color_from_hex(ACCENT_RED))
        for lb in (self.lbl_out_shifts, self.lbl_out_money, self.lbl_out_hours,
                   self.lbl_out_bonus, self.lbl_out_virtual, self.lbl_out_total):
            lb.bind(size=lambda i, v: setattr(i, 'text_size', (i.width, None)))
            card3.add_widget(lb)
        analytics_box.add_widget(card3)

        analytics_scroll.add_widget(analytics_box)
        root.add_widget(analytics_scroll)
        self.add_widget(root)

    def on_enter(self):
        accent = THEME_ACCENTS.get(self.app.config_theme, THEME_ACCENTS["Aurora Violet"])
        self.title_lbl.color = get_color_from_hex(accent)
        self.update_products_list()
        self.update_operators_list()
        self.load_day_data(None, self.day_spinner.text)
        self.calculate_all_totals()

    def go_to_settings(self, instance):
        self.manager.current = 'settings'

    def update_products_list(self):
        self.app.cursor.execute("SELECT DISTINCT type_name FROM production_types ORDER BY type_name")
        rows = self.app.cursor.fetchall()
        menu_items = ['Не выбрано'] + [r[0] for r in rows] + ['+ Добавить новый тип...']
        self.prod_type_spinner.values = menu_items

    def update_operators_list(self):
        self.operator_spinner.values = (self.app.op1, self.app.op2, self.app.op3, self.app.op4)

    def auto_calculate_operator(self, day_num):
        try:
            months_dict = {'Сентябрь': 9, 'Октябрь': 10, 'Ноябрь': 11, 'Декабрь': 12}
            m_num = months_dict.get(self.month_spinner.text, 9)
            d_start = date(2026, 9, 1)
            d_current = date(2026, m_num, int(day_num))
            delta_days = (d_current - d_start).days
            operators = [self.app.op1, self.app.op2, self.app.op3, self.app.op4]
            idx = delta_days % 4
            return operators[idx]
        except Exception:
            return self.app.op1

    def on_prod_spinner_select(self, spinner, text):
        if text == '+ Добавить новый тип...':
            self.show_add_product_popup()

    def show_add_product_popup(self):
        box = BoxLayout(orientation='vertical', padding=10, spacing=10)
        box.add_widget(Label(text="Введите название продукции:", font_size='14sp'))
        new_input = styled_field(TextInput, multiline=False, halign='center', size_hint_y=None, height=35)
        box.add_widget(new_input)
        btn_layout = BoxLayout(orientation='horizontal', spacing=8, size_hint_y=None, height=40)
        btn_add = Button(text="Добавить", bold=True, background_normal='',
                          background_color=get_color_from_hex(ACCENT_GREEN))
        btn_close = Button(text="Отмена", background_normal='',
                            background_color=get_color_from_hex(ACCENT_RED))
        btn_layout.add_widget(btn_add)
        btn_layout.add_widget(btn_close)
        box.add_widget(btn_layout)
        popup = Popup(title="Новый товар", content=box, size_hint=(0.85, 0.4), auto_dismiss=False)

        def save_new_type(instance):
            name = new_input.text.strip()
            if name:
                self.app.cursor.execute("INSERT OR IGNORE INTO production_types (type_name) VALUES (?)", (name,))
                self.app.conn.commit()
                self.update_products_list()
                self.prod_type_spinner.text = name
            popup.dismiss()

        btn_add.bind(on_press=save_new_type)
        btn_close.bind(on_press=popup.dismiss)
        popup.open()

    def show_add_break_popup(self):
        box = BoxLayout(orientation='vertical', padding=10, spacing=8)
        grid = GridLayout(cols=2, spacing=5, size_hint_y=None, height=110)
        grid.add_widget(Label(text="Ушли (ЧЧ:ММ):"))
        inp_start = styled_field(TextInput, text="22:00", multiline=False, halign='center')
        grid.add_widget(inp_start)
        grid.add_widget(Label(text="Вернулись (ЧЧ:ММ):"))
        inp_end = styled_field(TextInput, text="22:15", multiline=False, halign='center')
        grid.add_widget(inp_end)
        grid.add_widget(Label(text="Причина / Сбой:"))
        inp_comment = styled_field(TextInput, text="Перекур", multiline=False, halign='center')
        grid.add_widget(inp_comment)
        box.add_widget(grid)
        btn_layout = BoxLayout(orientation='horizontal', spacing=8, size_hint_y=None, height=40)
        btn_add = Button(text="Записать", bold=True, background_normal='',
                          background_color=get_color_from_hex(ACCENT_GREEN))
        btn_close = Button(text="Закрыть", background_normal='',
                            background_color=get_color_from_hex(ACCENT_RED))
        btn_layout.add_widget(btn_add)
        btn_layout.add_widget(btn_close)
        box.add_widget(btn_layout)
        popup = Popup(title="Фиксация тайминга события", content=box, size_hint=(0.9, 0.55), auto_dismiss=False)

        def add_break(instance):
            t_start = inp_start.text.strip()
            t_end = inp_end.text.strip()
            comm = inp_comment.text.strip()
            if t_start and t_end:
                self.breaks_data.append({"start": t_start, "end": t_end, "comment": comm})
                self.lbl_breaks_count.text = f"Событий записано: {len(self.breaks_data)}"
            popup.dismiss()

        btn_add.bind(on_press=add_break)
        btn_close.bind(on_press=popup.dismiss)
        popup.open()

    def on_status_change(self, spinner, text):
        disabled_status = (text != 'Отработал')
        self.input_dynamic.disabled = self.input_partner.disabled = self.prod_type_spinner.disabled = \
            self.input_prod.disabled = self.input_work_start.disabled = self.btn_add_break.disabled = \
            self.operator_spinner.disabled = disabled_status
        if text == 'Отработал':
            self.lbl_dynamic.text = "Время приезда (ЧЧ:ММ):"
            self.input_dynamic.text = "20:00"
        elif 'Выходной под премию' in text:
            self.lbl_dynamic.text = "Сумма выплаты премии (\u20bd):"
            self.input_dynamic.text = "0"
            self.breaks_data = []
            self.lbl_breaks_count.text = "Событий записано: 0"
        else:
            self.lbl_dynamic.text = "Параметры дня:"
            self.input_dynamic.text = "0"
            self.breaks_data = []
            self.lbl_breaks_count.text = "Событий записано: 0"

    def on_month_change(self, spinner, text):
        max_day = MONTH_DAYS.get(text, 31)
        self.day_spinner.values = [str(i) for i in range(1, max_day + 1)]
        if int(self.day_spinner.text) > max_day:
            self.day_spinner.text = '1'
        self.load_day_data(None, self.day_spinner.text)
        self.calculate_all_totals()

    def load_day_data(self, spinner, day_text):
        month = self.month_spinner.text
        day = int(day_text)
        self.app.cursor.execute(
            "SELECT status, value_data, partner_name, production_type, production_kg, work_start_time, "
            "breaks_json, shift_operator FROM calendar_days WHERE month=? AND day=?", (month, day))
        row = self.app.cursor.fetchone()
        if row:
            self.status_spinner.text = row[0]
            self.on_status_change(None, row[0])
            self.input_dynamic.text = str(row[1] or "")
            self.input_partner.text = str(row[2] or "")
            self.prod_type_spinner.text = str(row[3] or "Не выбрано")
            self.input_prod.text = str(row[4] or "")
            self.input_work_start.text = str(row[5] or "20:00")
            try:
                self.breaks_data = json.loads(row[6] or "[]")
            except Exception:
                self.breaks_data = []
            self.lbl_breaks_count.text = f"Событий записано: {len(self.breaks_data)}"
            self.operator_spinner.text = str(row[7] or self.auto_calculate_operator(day_text))
        else:
            self.status_spinner.text = 'Отработал'
            self.on_status_change(None, 'Отработал')
            self.input_dynamic.text = "20:00"
            self.input_work_start.text = "20:00"
            self.input_partner.text = self.input_prod.text = ""
            self.prod_type_spinner.text = 'Не выбрано'
            self.breaks_data = []
            self.lbl_breaks_count.text = "Событий записано: 0"
            self.operator_spinner.text = self.auto_calculate_operator(day_text)

    def save_day_data(self, instance):
        month = self.month_spinner.text
        day = int(self.day_spinner.text)
        status = self.status_spinner.text
        value_data = self.input_dynamic.text
        partner = self.input_partner.text
        prod_type = self.prod_type_spinner.text
        prod_weight = self.input_prod.text
        work_start = self.input_work_start.text
        breaks_str = json.dumps(self.breaks_data)
        op_name = self.operator_spinner.text
        self.app.cursor.execute('''
            INSERT OR REPLACE INTO calendar_days (month, day, status, value_data, partner_name, production_type, production_kg, work_start_time, breaks_json, shift_operator)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (month, day, status, value_data, partner, prod_type, prod_weight, work_start, breaks_str, op_name))
        self.app.conn.commit()
        self.calculate_all_totals()

    def calculate_all_totals(self):
        month = self.month_spinner.text
        self.app.cursor.execute("SELECT status, value_data, production_kg FROM calendar_days WHERE month=?", (month,))
        all_days = self.app.cursor.fetchall()
        total_shifts, total_hours, virtual_bonus = 0, 0.0, 0.0
        stat_ontime, stat_buffer, stat_late = 0, 0, 0
        prod_high, prod_low = 0, 0

        for status, value_data, production_kg in all_days:
            if status == 'Отработал':
                total_shifts += 1
                try:
                    h, m = map(int, value_data.split(':'))
                    minutes = h * 60 + m
                except Exception:
                    minutes = 20 * 60
                t20_00, t20_15 = 20 * 60, 20 * 60 + 15
                if minutes <= t20_00:
                    stat_ontime += 1
                    total_hours += 11.0
                elif t20_00 < minutes <= t20_15:
                    stat_buffer += 1
                    total_hours += 11.0
                else:
                    stat_late += 1
                    total_hours += 10.0
                try:
                    weight = float(production_kg or 0)
                    if weight >= 2100.0:
                        prod_high += 1
                    else:
                        prod_low += 1
                except Exception:
                    prod_low += 1
            elif 'Выходной под премию' in status:
                try:
                    virtual_bonus += float(value_data or 0)
                except Exception:
                    pass

        t_time = stat_ontime + stat_buffer + stat_late
        ontime_pct = round(stat_ontime / t_time * 100) if t_time > 0 else 0
        self.chart_time.update_data([stat_ontime, stat_buffer, stat_late], f"{ontime_pct}%")

        t_prod = prod_high + prod_low
        prod_pct = round(prod_high / t_prod * 100) if t_prod > 0 else 0
        self.chart_prod.update_data([prod_high, prod_low], f"{prod_pct}%")

        self.lbl_stat_ontime.text = (f"[color=6ee7b7]\u25cf[/color] Вовремя: "
                                      f"{(stat_ontime / t_time * 100):.0f}% ({stat_ontime} см)") if t_time > 0 \
            else "[color=6ee7b7]\u25cf[/color] Вовремя: 0%"
        self.lbl_stat_buffer.text = (f"[color=fde68a]\u25cf[/color] Ожидание: "
                                      f"{(stat_buffer / t_time * 100):.0f}% ({stat_buffer} см)") if t_time > 0 \
            else "[color=fde68a]\u25cf[/color] Ожидание: 0%"
        self.lbl_stat_late.text = (f"[color=fca5a5]\u25cf[/color] Опоздание: "
                                    f"{(stat_late / t_time * 100):.0f}% ({stat_late} см)") if t_time > 0 \
            else "[color=fca5a5]\u25cf[/color] Опоздание: 0%"

        self.lbl_prod_high.text = (f"[color=6ee7b7]\u25cf[/color] Норма выполнена: "
                                    f"{(prod_high / t_prod * 100):.0f}% ({prod_high} см)") if t_prod > 0 \
            else "[color=6ee7b7]\u25cf[/color] Норма выполнена: 0%"
        self.lbl_prod_low.text = (f"[color=fca5a5]\u25cf[/color] Меньше нормы: "
                                   f"{(prod_low / t_prod * 100):.0f}% ({prod_low} см)") if t_prod > 0 \
            else "[color=fca5a5]\u25cf[/color] Меньше нормы: 0%"

        hour_cost = self.app.config_hour_rate
        salary_money = total_hours * hour_cost

        if total_shifts >= 25:
            bonus_hours = 21
        elif total_shifts == 24:
            bonus_hours = 20
        elif total_shifts == 23:
            bonus_hours = 18
        elif 21 <= total_shifts <= 22:
            bonus_hours = 16
        elif 19 <= total_shifts <= 20:
            bonus_hours = 12
        elif 17 <= total_shifts <= 18:
            bonus_hours = 9
        else:
            bonus_hours = 0

        table_bonus_money = bonus_hours * hour_cost
        grand_total = salary_money + table_bonus_money + virtual_bonus

        self.lbl_out_shifts.text = f"Отработано смен за месяц: {total_shifts} ночей"
        self.lbl_out_money.text = f"Чистый оклад за часы: {salary_money:,.0f} \u20bd".replace(",", " ")
        self.lbl_out_hours.text = f"Часов премии по таблице: {bonus_hours} ч."
        self.lbl_out_bonus.text = f"Сумма премий из таблицы: {table_bonus_money:,.0f} \u20bd".replace(",", " ")
        self.lbl_out_virtual.text = f"На премиальных выходных: {virtual_bonus:,.0f} \u20bd".replace(",", " ")
        self.lbl_out_total.text = f"ИТОГО К ВЫПЛАТЕ: {grand_total:,.0f} \u20bd".replace(",", " ")


class SettingsScreen(BackgroundScreen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app = App.get_running_app()

        outer = BoxLayout(orientation='vertical', padding=14, size_hint=(1, 1))
        scroll = ScrollView()
        content = BoxLayout(orientation='vertical', spacing=12, size_hint_y=None, padding=(0, 4))
        content.bind(minimum_height=content.setter('height'))

        content.add_widget(section_label("Настройки", "#c9a6ff", '17sp'))

        card_rate = GlassPanel(orientation='vertical', size_hint_y=None, padding=12, spacing=6)
        card_rate.bind(minimum_height=card_rate.setter('height'))
        card_rate.add_widget(section_label("Стоимость 1 часа оклада (\u20bd):", TEXT_DIM, '12sp'))
        self.input_rate = styled_field(TextInput, text=str(self.app.config_hour_rate), multiline=False,
                                        input_filter='float', halign='center', size_hint_y=None, height=38)
        card_rate.add_widget(self.input_rate)
        content.add_widget(card_rate)

        card_ops = GlassPanel(orientation='vertical', size_hint_y=None, padding=12, spacing=8)
        card_ops.bind(minimum_height=card_ops.setter('height'))
        card_ops.add_widget(section_label("Имена четырёх сменных операторов:", ACCENT_BLUE, '12sp'))
        grid_ops = GridLayout(cols=2, spacing=6, size_hint_y=None, height=80)
        self.in_op1 = styled_field(TextInput, text=self.app.op1, multiline=False, halign='center')
        self.in_op2 = styled_field(TextInput, text=self.app.op2, multiline=False, halign='center')
        self.in_op3 = styled_field(TextInput, text=self.app.op3, multiline=False, halign='center')
        self.in_op4 = styled_field(TextInput, text=self.app.op4, multiline=False, halign='center')
        for w in (self.in_op1, self.in_op2, self.in_op3, self.in_op4):
            grid_ops.add_widget(w)
        card_ops.add_widget(grid_ops)
        content.add_widget(card_ops)

        card_theme = GlassPanel(orientation='vertical', size_hint_y=None, padding=12, spacing=8)
        card_theme.bind(minimum_height=card_theme.setter('height'))
        card_theme.add_widget(section_label("Акцентный цвет интерфейса:", TEXT_DIM, '12sp'))
        self.theme_spinner = styled_field(Spinner, text=self.app.config_theme,
                                           values=tuple(THEME_ACCENTS.keys()), size_hint_y=None, height=38)
        card_theme.add_widget(self.theme_spinner)
        card_theme.add_widget(section_label("Размер шрифта статистики:", TEXT_DIM, '12sp'))
        self.font_slider = Slider(min=10, max=22, value=self.app.config_font_size, size_hint_y=None, height=32)
        card_theme.add_widget(self.font_slider)
        content.add_widget(card_theme)

        btn_change_pin = Button(text="Сменить PIN-код", size_hint_y=None, height=42,
                                 background_normal='', background_color=(1, 1, 1, 0.14),
                                 color=get_color_from_hex(TEXT_MAIN))
        btn_change_pin.bind(on_press=self.change_pin)
        content.add_widget(btn_change_pin)

        btn_back = Button(text="Применить и назад", bold=True, size_hint_y=None, height=48,
                           background_normal='', background_color=get_color_from_hex(ACCENT_GREEN),
                           color=(0.08, 0.1, 0.08, 1))
        btn_back.bind(on_press=self.save_settings)
        content.add_widget(btn_back)

        scroll.add_widget(content)
        outer.add_widget(scroll)
        self.add_widget(outer)

    def change_pin(self, instance):
        self.app.cursor.execute("UPDATE app_config SET pin_hash=NULL WHERE id=1")
        self.app.conn.commit()
        self.manager.current = 'pin'

    def save_settings(self, instance):
        try:
            self.app.config_hour_rate = float(self.input_rate.text or 632.0)
        except Exception:
            self.app.config_hour_rate = 632.0
        self.app.op1 = self.in_op1.text.strip() or "Оператор 1"
        self.app.op2 = self.in_op2.text.strip() or "Оператор 2"
        self.app.op3 = self.in_op3.text.strip() or "Оператор 3"
        self.app.op4 = self.in_op4.text.strip() or "Оператор 4"
        self.app.config_theme = self.theme_spinner.text
        self.app.config_font_size = int(self.font_slider.value)
        self.app.cursor.execute('''
            INSERT OR REPLACE INTO app_config (id, hour_rate, theme, font_size, op1, op2, op3, op4, pin_hash)
            VALUES (1, ?, ?, ?, ?, ?, ?, ?, (SELECT pin_hash FROM app_config WHERE id=1))
        ''', (self.app.config_hour_rate, self.app.config_theme, self.app.config_font_size,
              self.app.op1, self.app.op2, self.app.op3, self.app.op4))
        self.app.conn.commit()
        self.manager.current = 'main'


class PinScreen(BackgroundScreen):
    """Экран блокировки: создание PIN при первом запуске, ввод PIN при последующих."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app = App.get_running_app()
        self.mode = 'verify'
        self.first_pin_temp = None

        outer = FloatLayout(size_hint=(1, 1))
        card = GlassPanel(orientation='vertical', padding=26, spacing=14,
                           size_hint=(0.86, None), height=280,
                           pos_hint={'center_x': 0.5, 'center_y': 0.55})

        self.title_lbl = Label(text="Введите PIN-код", font_size='19sp', bold=True,
                                color=get_color_from_hex("#c9a6ff"), size_hint_y=None, height=32)
        card.add_widget(self.title_lbl)

        self.hint_lbl = Label(text="", font_size='12sp', color=get_color_from_hex(TEXT_DIM),
                               size_hint_y=None, height=20)
        card.add_widget(self.hint_lbl)

        self.pin_input = styled_field(TextInput, text="", password=True, multiline=False, halign='center',
                                       input_filter='int', font_size='22sp', size_hint_y=None, height=52)
        self.pin_input.bind(text=self.on_pin_text)
        card.add_widget(self.pin_input)

        self.error_lbl = Label(text="", color=get_color_from_hex(ACCENT_RED),
                                font_size='12sp', size_hint_y=None, height=22)
        card.add_widget(self.error_lbl)

        self.btn_confirm = Button(text="Подтвердить", bold=True, size_hint_y=None, height=46,
                                   background_normal='', background_color=get_color_from_hex(ACCENT_GREEN),
                                   color=(0.08, 0.1, 0.08, 1))
        self.btn_confirm.bind(on_press=self.on_confirm)
        card.add_widget(self.btn_confirm)

        outer.add_widget(card)
        self.add_widget(outer)

    def on_pin_text(self, instance, value):
        if len(value) > 6:
            self.pin_input.text = value[:6]

    def on_enter(self):
        self.error_lbl.text = ""
        self.pin_input.text = ""
        stored_hash = self.get_stored_hash()
        if stored_hash:
            self.mode = 'verify'
            self.title_lbl.text = "Введите PIN-код"
            self.hint_lbl.text = ""
        else:
            self.mode = 'setup_new'
            self.first_pin_temp = None
            self.title_lbl.text = "Придумайте PIN-код"
            self.hint_lbl.text = "От 4 до 6 цифр"

    def get_stored_hash(self):
        self.app.cursor.execute("SELECT pin_hash FROM app_config WHERE id=1")
        row = self.app.cursor.fetchone()
        if row and row[0]:
            return row[0]
        return None

    @staticmethod
    def hash_pin(pin):
        return hashlib.sha256(pin.encode('utf-8')).hexdigest()

    def on_confirm(self, instance):
        pin = self.pin_input.text.strip()
        if len(pin) < 4:
            self.error_lbl.text = "Минимум 4 цифры"
            return

        if self.mode == 'verify':
            if self.hash_pin(pin) == self.get_stored_hash():
                self.manager.current = 'main'
            else:
                self.error_lbl.text = "Неверный PIN-код"
                self.pin_input.text = ""

        elif self.mode == 'setup_new':
            self.first_pin_temp = pin
            self.mode = 'setup_confirm'
            self.title_lbl.text = "Повторите PIN-код"
            self.hint_lbl.text = ""
            self.pin_input.text = ""
            self.error_lbl.text = ""

        elif self.mode == 'setup_confirm':
            if pin == self.first_pin_temp:
                self.save_pin(pin)
                self.manager.current = 'main'
            else:
                self.error_lbl.text = "PIN-коды не совпадают, попробуйте снова"
                self.mode = 'setup_new'
                self.first_pin_temp = None
                self.title_lbl.text = "Придумайте PIN-код"
                self.hint_lbl.text = "От 4 до 6 цифр"
                self.pin_input.text = ""

    def save_pin(self, pin):
        pin_hash = self.hash_pin(pin)
        self.app.cursor.execute("SELECT id FROM app_config WHERE id=1")
        exists = self.app.cursor.fetchone()
        if exists:
            self.app.cursor.execute("UPDATE app_config SET pin_hash=? WHERE id=1", (pin_hash,))
        else:
            self.app.cursor.execute("INSERT INTO app_config (id, pin_hash) VALUES (1, ?)", (pin_hash,))
        self.app.conn.commit()


class ShiftTrackerApp(App):
    def build(self):
        self.config_hour_rate = 632.0
        self.config_theme = "Aurora Violet"
        self.config_font_size = 13
        self.op1, self.op2, self.op3, self.op4 = "Оператор 1", "Оператор 2", "Оператор 3", "Оператор 4"
        self.init_db()
        sm = ScreenManager()
        sm.add_widget(PinScreen(name='pin'))
        sm.add_widget(MainScreen(name='main'))
        sm.add_widget(SettingsScreen(name='settings'))
        sm.current = 'pin'
        return sm

    def init_db(self):
        db_path = os.path.join(self.user_data_dir, "smart_hours.db")
        self.conn = sqlite3.connect(db_path)
        self.cursor = self.conn.cursor()
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS calendar_days (
                month TEXT, day INTEGER, status TEXT, value_data TEXT,
                partner_name TEXT, production_type TEXT, production_kg TEXT,
                work_start_time TEXT, breaks_json TEXT, shift_operator TEXT,
                PRIMARY KEY (month, day)
            )
        ''')
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS app_config (
                id INTEGER PRIMARY KEY, hour_rate REAL, theme TEXT, font_size INTEGER,
                op1 TEXT, op2 TEXT, op3 TEXT, op4 TEXT, pin_hash TEXT
            )
        ''')
        try:
            self.cursor.execute("ALTER TABLE app_config ADD COLUMN pin_hash TEXT")
            self.conn.commit()
        except sqlite3.OperationalError:
            pass
        self.cursor.execute('CREATE TABLE IF NOT EXISTS production_types (type_name TEXT PRIMARY KEY)')
        self.conn.commit()
        self.cursor.execute("SELECT hour_rate, theme, font_size, op1, op2, op3, op4 FROM app_config WHERE id=1")
        row = self.cursor.fetchone()
        if row:
            self.config_hour_rate = row[0] or 632.0
            self.config_theme = row[1] or "Aurora Violet"
            self.config_font_size = row[2] or 13
            self.op1, self.op2, self.op3, self.op4 = (row[3] or "Оператор 1", row[4] or "Оператор 2",
                                                        row[5] or "Оператор 3", row[6] or "Оператор 4")


if __name__ == '__main__':
    ShiftTrackerApp().run()

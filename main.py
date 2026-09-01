import os
import sqlite3
import json
import hashlib
from datetime import date
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.spinner import Spinner
from kivy.uix.scrollview import ScrollView
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.slider import Slider
from kivy.uix.widget import Widget
from kivy.uix.popup import Popup
from kivy.core.window import Window
from kivy.graphics import Color, Ellipse
from kivy.utils import get_color_from_hex

# Базовая темная тема iOS 26
Window.clearcolor = get_color_from_hex("#111116")

# Кол-во дней в каждом месяце сезона (используется для валидности выбора дня)
MONTH_DAYS = {'Сентябрь': 30, 'Октябрь': 31, 'Ноябрь': 30, 'Декабрь': 31}

THEME_COLORS = {
    "Deep Space Gray": ("#111116", "#cba6f7"),
    "Midnight Blue": ("#0f172a", "#38bdf8"),
    "Emerald Mint": ("#064e3b", "#34d399"),
}


class PieChart(Widget):
    """Графический модуль круговой диаграммы Apple Style"""
    def __init__(self, custom_colors=None, **kwargs):
        super().__init__(**kwargs)
        self.data = []
        self.custom_colors = custom_colors if custom_colors else ["#a6e3a1", "#f9e2af", "#f38ba8"]
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
                Color(*get_color_from_hex("#313244"))
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


class PinScreen(Screen):
    """Экран блокировки: создание PIN при первом запуске, ввод PIN при последующих."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app = App.get_running_app()
        self.mode = 'verify'  # 'verify' | 'setup_new' | 'setup_confirm'
        self.first_pin_temp = None

        root = BoxLayout(orientation='vertical', padding=40, spacing=15)

        self.title_lbl = Label(
            text="Введите PIN-код", font_size='20sp', bold=True,
            color=get_color_from_hex("#cba6f7"), size_hint_y=None, height=40
        )
        root.add_widget(self.title_lbl)

        self.hint_lbl = Label(
            text="", font_size='12sp', color=get_color_from_hex("#a6adc8"),
            size_hint_y=None, height=20
        )
        root.add_widget(self.hint_lbl)

        self.pin_input = TextInput(
            text="", password=True, multiline=False, halign='center',
            input_filter='int', font_size='24sp',
            background_color=get_color_from_hex("#313244"),
            foreground_color=(1, 1, 1, 1), size_hint_y=None, height=50
        )
        self.pin_input.bind(text=self.on_pin_text)
        root.add_widget(self.pin_input)

        self.error_lbl = Label(
            text="", color=get_color_from_hex("#f38ba8"),
            size_hint_y=None, height=25
        )
        root.add_widget(self.error_lbl)

        self.btn_confirm = Button(
            text="Подтвердить", bold=True, size_hint_y=None, height=45,
            background_color=get_color_from_hex("#a6e3a1")
        )
        self.btn_confirm.bind(on_press=self.on_confirm)
        root.add_widget(self.btn_confirm)

        self.add_widget(root)

    def on_pin_text(self, instance, value):
        if len(value) > 6:
            self.pin_input.text = value[:6]

    def on_enter(self):
        self.apply_theme_colors()
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

    def apply_theme_colors(self):
        theme = self.app.config_theme
        bg, text_color = THEME_COLORS.get(theme, THEME_COLORS["Deep Space Gray"])
        Window.clearcolor = get_color_from_hex(bg)
        self.title_lbl.color = get_color_from_hex(text_color)

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


class MainScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app = App.get_running_app()
        self.breaks_data = []
        root = BoxLayout(orientation='vertical', padding=10, spacing=8)

        # Верхний тулбар iOS
        top_bar = BoxLayout(orientation='horizontal', size_hint_y=None, height=40)
        self.title_lbl = Label(text="Мой Календарь Смен", font_size='18sp', bold=True, color=get_color_from_hex("#cba6f7"), halign='left')
        top_bar.add_widget(self.title_lbl)
        btn_settings = Button(text="⚙️", font_size='20sp', size_hint_x=None, width=40, background_color=(0, 0, 0, 0), color=get_color_from_hex("#b4befe"))
        btn_settings.bind(on_press=self.go_to_settings)
        top_bar.add_widget(btn_settings)
        root.add_widget(top_bar)

        # Календарная панель
        date_box = BoxLayout(orientation='horizontal', size_hint_y=None, height=38, spacing=6)
        self.month_spinner = Spinner(text='Сентябрь', values=('Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'), background_color=get_color_from_hex("#1e1e2e"))
        self.month_spinner.bind(text=self.on_month_change)
        date_box.add_widget(self.month_spinner)

        day_values = [str(i) for i in range(1, MONTH_DAYS['Сентябрь'] + 1)]
        self.day_spinner = Spinner(text='1', values=day_values, background_color=get_color_from_hex("#1e1e2e"))
        self.day_spinner.bind(text=self.load_day_data)
        date_box.add_widget(self.day_spinner)
        root.add_widget(date_box)

        # Скролл-карточка параметров смены
        day_scroll = ScrollView(size_hint_y=None, height=220)
        self.day_card = GridLayout(cols=2, spacing=8, size_hint_y=None, padding=8)
        self.day_card.bind(minimum_height=self.day_card.setter('height'))

        self.day_card.add_widget(Label(text="Статус дня:", color=get_color_from_hex("#a6adc8"), size_hint_y=None, height=32))
        self.status_spinner = Spinner(
            text='Отработал',
            values=('Отработал', 'Обычный выходной / Болел', 'Выходной под премию (День 1)', 'Выходной под премию (День 2)', 'Проспал (не пустила охрана)'),
            background_color=get_color_from_hex("#313244"), size_hint_y=None, height=32
        )
        self.status_spinner.bind(text=self.on_status_change)
        self.day_card.add_widget(self.status_spinner)

        self.lbl_dynamic = Label(text="Время приезда (ЧЧ:ММ):", color=get_color_from_hex("#a6adc8"), size_hint_y=None, height=32)
        self.day_card.add_widget(self.lbl_dynamic)
        self.input_dynamic = TextInput(text="20:00", multiline=False, halign='center', background_color=get_color_from_hex("#313244"), foreground_color=(1, 1, 1, 1), size_hint_y=None, height=32)
        self.day_card.add_widget(self.input_dynamic)

        self.lbl_work_start = Label(text="Фактический старт:", color=get_color_from_hex("#a6adc8"), size_hint_y=None, height=32)
        self.day_card.add_widget(self.lbl_work_start)
        self.input_work_start = TextInput(text="20:00", multiline=False, halign='center', background_color=get_color_from_hex("#313244"), foreground_color=(1, 1, 1, 1), size_hint_y=None, height=32)
        self.day_card.add_widget(self.input_work_start)

        self.lbl_partner = Label(text="Напарник:", color=get_color_from_hex("#a6adc8"), size_hint_y=None, height=32)
        self.day_card.add_widget(self.lbl_partner)
        self.input_partner = TextInput(text="", multiline=False, halign='center', background_color=get_color_from_hex("#313244"), foreground_color=(1, 1, 1, 1), size_hint_y=None, height=32)
        self.day_card.add_widget(self.input_partner)

        self.lbl_operator = Label(text="Старший (Оператор):", color=get_color_from_hex("#a6adc8"), size_hint_y=None, height=32)
        self.day_card.add_widget(self.lbl_operator)
        self.operator_spinner = Spinner(text='Оператор 1', values=('Оператор 1', 'Оператор 2', 'Оператор 3', 'Оператор 4'), background_color=get_color_from_hex("#313244"), size_hint_y=None, height=32)
        self.day_card.add_widget(self.operator_spinner)

        self.lbl_prod_type = Label(text="Тип продукции:", color=get_color_from_hex("#a6adc8"), size_hint_y=None, height=32)
        self.day_card.add_widget(self.lbl_prod_type)
        self.prod_type_spinner = Spinner(text='Не выбрано', values=['Не выбрано', '+ Добавить новый тип...'], background_color=get_color_from_hex("#313244"), size_hint_y=None, height=32)
        self.prod_type_spinner.bind(text=self.on_prod_spinner_select)
        self.day_card.add_widget(self.prod_type_spinner)

        self.lbl_prod = Label(text="Вес продукции (кг):", color=get_color_from_hex("#a6adc8"), size_hint_y=None, height=32)
        self.day_card.add_widget(self.lbl_prod)
        self.input_prod = TextInput(text="", multiline=False, input_filter='float', halign='center', background_color=get_color_from_hex("#313244"), foreground_color=(1, 1, 1, 1), size_hint_y=None, height=32)
        self.day_card.add_widget(self.input_prod)

        self.btn_add_break = Button(text="+ Добавить перекур / сбой", size_hint_y=None, height=32, background_color=get_color_from_hex("#38bdf8"))
        self.btn_add_break.bind(on_press=self.show_add_break_popup)
        self.day_card.add_widget(self.btn_add_break)

        self.lbl_breaks_count = Label(text="Событий записано: 0", color=get_color_from_hex("#a6adc8"))
        self.day_card.add_widget(self.lbl_breaks_count)

        day_scroll.add_widget(self.day_card)
        root.add_widget(day_scroll)

        btn_save = Button(text="Сохранить смену в память", font_size='15sp', bold=True, size_hint_y=None, height=42, background_color=get_color_from_hex("#a6e3a1"), color=(0, 0, 0, 1))
        btn_save.bind(on_press=self.save_day_data)
        root.add_widget(btn_save)

        # --- БЛОК АНАЛИТИКИ И ДВУХ ДИАГРАММ С СКРОЛЛОМ ---
        analytics_scroll = ScrollView()
        analytics_box = BoxLayout(orientation='vertical', padding=5, spacing=10, size_hint_y=None)
        analytics_box.bind(minimum_height=analytics_box.setter('height'))

        analytics_box.add_widget(Label(text="📊 Аналитика прибытия на смену", font_size='13sp', bold=True, size_hint_y=None, height=20, color=get_color_from_hex("#a6e3a1")))
        chart_layout1 = BoxLayout(orientation='horizontal', size_hint_y=None, height=85, spacing=10)
        self.chart_time = PieChart(custom_colors=["#a6e3a1", "#f9e2af", "#f38ba8"], size_hint=(None, None), size=(80, 80))
        chart_layout1.add_widget(self.chart_time)

        legend_layout1 = BoxLayout(orientation='vertical', spacing=1)
        self.lbl_stat_ontime = Label(text="🟢 Вовремя: 0%", halign='left', font_size='11sp')
        self.lbl_stat_buffer = Label(text="🟡 Ожидание: 0%", halign='left', font_size='11sp')
        self.lbl_stat_late = Label(text="🔴 Опоздание: 0%", halign='left', font_size='11sp')
        legend_layout1.add_widget(self.lbl_stat_ontime)
        legend_layout1.add_widget(self.lbl_stat_buffer)
        legend_layout1.add_widget(self.lbl_stat_late)
        chart_layout1.add_widget(legend_layout1)
        analytics_box.add_widget(chart_layout1)

        analytics_box.add_widget(Label(text="🏭 Эффективность выработки (Норма: 2100 кг)", font_size='13sp', bold=True, size_hint_y=None, height=20, color=get_color_from_hex("#89b4fa")))
        chart_layout2 = BoxLayout(orientation='horizontal', size_hint_y=None, height=85, spacing=10)
        self.chart_prod = PieChart(custom_colors=["#a6e3a1", "#f38ba8"], size_hint=(None, None), size=(80, 80))
        chart_layout2.add_widget(self.chart_prod)

        legend_layout2 = BoxLayout(orientation='vertical', spacing=2)
        self.lbl_prod_high = Label(text="🟢 Норма выполнена: 0%", halign='left', font_size='11sp')
        self.lbl_prod_low = Label(text="🔴 Меньше нормы: 0%", halign='left', font_size='11sp')
        legend_layout2.add_widget(self.lbl_prod_high)
        legend_layout2.add_widget(self.lbl_prod_low)

        chart_layout2.add_widget(legend_layout2)
        analytics_box.add_widget(chart_layout2)
        analytics_box.add_widget(Label(text="💰 Расчет начислений за месяц", font_size='13sp', bold=True, size_hint_y=None, height=18, color=get_color_from_hex("#cba6f7")))
        self.lbl_out_shifts = Label(text="Отработано смен: 0 ночей", size_hint_y=None, height=20, halign='left')
        self.lbl_out_money = Label(text="Чистый оклад за часы: 0 ₽", size_hint_y=None, height=20, halign='left')
        self.lbl_out_hours = Label(text="Часов премии по таблице: 0 ч.", size_hint_y=None, height=20, halign='left')
        self.lbl_out_bonus = Label(text="Сумма премий из таблицы: 0 ₽", size_hint_y=None, height=20, halign='left')
        self.lbl_out_virtual = Label(text="Получено на премиальных выходных: 0 ₽", size_hint_y=None, height=20, halign='left')
        self.lbl_out_total = Label(text="ИТОГО К ВЫПЛАТЕ: 0 ₽", font_size='15sp', bold=True, size_hint_y=None, height=28, color=get_color_from_hex("#f38ba8"))
        analytics_box.add_widget(self.lbl_out_shifts)
        analytics_box.add_widget(self.lbl_out_money)
        analytics_box.add_widget(self.lbl_out_hours)
        analytics_box.add_widget(self.lbl_out_bonus)
        analytics_box.add_widget(self.lbl_out_virtual)
        analytics_box.add_widget(self.lbl_out_total)
        analytics_scroll.add_widget(analytics_box)
        root.add_widget(analytics_scroll)
        self.add_widget(root)

    def on_enter(self):
        self.apply_theme_colors()
        self.update_products_list()
        self.update_operators_list()
        self.load_day_data(None, self.day_spinner.text)
        self.calculate_all_totals()

    def go_to_settings(self, instance):
        self.manager.current = 'settings'

    def apply_theme_colors(self):
        theme = self.app.config_theme
        bg, text_color = THEME_COLORS.get(theme, THEME_COLORS["Deep Space Gray"])
        Window.clearcolor = get_color_from_hex(bg)
        self.title_lbl.color = get_color_from_hex(text_color)

    def update_products_list(self):
        self.app.cursor.execute("SELECT DISTINCT type_name FROM production_types ORDER BY type_name")
        rows = self.app.cursor.fetchall()
        menu_items = ['Не выбрано'] + [r[0] for r in rows] + ['+ Добавить новый тип...']
        self.prod_type_spinner.values = menu_items

    def update_operators_list(self):
        self.operator_spinner.values = (self.app.op1, self.app.op2, self.app.op3, self.app.op4)

    def auto_calculate_operator(self, day_num):
        """Циклический расчет дежурства операторов по дате."""
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
        new_input = TextInput(multiline=False, halign='center', size_hint_y=None, height=35)
        box.add_widget(new_input)
        btn_layout = BoxLayout(orientation='horizontal', spacing=8, size_hint_y=None, height=40)
        btn_add = Button(text="Добавить", bold=True, background_color=get_color_from_hex("#a6e3a1"))
        btn_close = Button(text="Отмена", background_color=get_color_from_hex("#f38ba8"))
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
        inp_start = TextInput(text="22:00", multiline=False, halign='center')
        grid.add_widget(inp_start)
        grid.add_widget(Label(text="Вернулись (ЧЧ:ММ):"))
        inp_end = TextInput(text="22:15", multiline=False, halign='center')
        grid.add_widget(inp_end)
        grid.add_widget(Label(text="Причина / Сбой:"))
        inp_comment = TextInput(text="Перекур", multiline=False, halign='center')
        grid.add_widget(inp_comment)
        box.add_widget(grid)
        btn_layout = BoxLayout(orientation='horizontal', spacing=8, size_hint_y=None, height=40)
        btn_add = Button(text="Записать", bold=True, background_color=get_color_from_hex("#a6e3a1"))
        btn_close = Button(text="Закрыть", background_color=get_color_from_hex("#f38ba8"))
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
        self.input_dynamic.disabled = self.input_partner.disabled = self.prod_type_spinner.disabled = self.input_prod.disabled = self.input_work_start.disabled = self.btn_add_break.disabled = self.operator_spinner.disabled = disabled_status
        if text == 'Отработал':
            self.lbl_dynamic.text = "Время приезда (ЧЧ:ММ):"
            self.input_dynamic.text = "20:00"
        elif 'Выходной под премию' in text:
            self.lbl_dynamic.text = "Сумма выплаты премии (₽):"
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
        self.app.cursor.execute("SELECT status, value_data, partner_name, production_type, production_kg, work_start_time, breaks_json, shift_operator FROM calendar_days WHERE month=? AND day=?", (month, day))
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

        self.chart_time.update_data([stat_ontime, stat_buffer, stat_late])
        self.chart_prod.update_data([prod_high, prod_low])

        t_time = stat_ontime + stat_buffer + stat_late
        self.lbl_stat_ontime.text = f"🟢 Вовремя: {(stat_ontime / t_time * 100):.0f}% ({stat_ontime} см)" if t_time > 0 else "🟢 Вовремя: 0%"
        self.lbl_stat_buffer.text = f"🟡 Ожидание: {(stat_buffer / t_time * 100):.0f}% ({stat_buffer} см)" if t_time > 0 else "🟡 Ожидание: 0%"
        self.lbl_stat_late.text = f"🔴 Опоздание: {(stat_late / t_time * 100):.0f}% ({stat_late} см)" if t_time > 0 else "🔴 Опоздание: 0%"

        t_prod = prod_high + prod_low
        self.lbl_prod_high.text = f"🟢 Норма выполнена: {(prod_high / t_prod * 100):.0f}% ({prod_high} см)" if t_prod > 0 else "🟢 Норма выполнена: 0%"
        self.lbl_prod_low.text = f"🔴 Меньше нормы: {(prod_low / t_prod * 100):.0f}% ({prod_low} см)" if t_prod > 0 else "🔴 Меньше нормы: 0%"

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
        self.lbl_out_money.text = f"Чистый оклад за часы: {salary_money:,.0f} ₽".replace(",", " ")
        self.lbl_out_hours.text = f"Часов премии по таблице: {bonus_hours} ч."
        self.lbl_out_bonus.text = f"Сумма премий из таблицы: {table_bonus_money:,.0f} ₽".replace(",", " ")
        self.lbl_out_virtual.text = f"Получено на премиальных выходных: {virtual_bonus:,.0f} ₽".replace(",", " ")
        self.lbl_out_total.text = f"ИТОГО К ВЫПЛАТЕ: {grand_total:,.0f} ₽".replace(",", " ")


class SettingsScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app = App.get_running_app()
        root = BoxLayout(orientation='vertical', padding=10, spacing=8)
        root.add_widget(Label(text="Настройки iOS 26", font_size='16sp', bold=True, color=get_color_from_hex("#cba6f7"), size_hint_y=None, height=30))
        root.add_widget(Label(text="Стоимость 1 часа оклада (₽):", size_hint_y=None, height=18, color=get_color_from_hex("#a6adc8")))
        self.input_rate = TextInput(text=str(self.app.config_hour_rate), multiline=False, input_filter='float', halign='center', size_hint_y=None, height=35)
        root.add_widget(self.input_rate)
        root.add_widget(Label(text="Имена четырех сменных операторов:", font_size='13sp', bold=True, size_hint_y=None, height=18, color=get_color_from_hex("#89b4fa")))
        grid_ops = GridLayout(cols=2, spacing=5, size_hint_y=None, height=75)
        self.in_op1 = TextInput(text=self.app.op1, multiline=False, halign='center')
        self.in_op2 = TextInput(text=self.app.op2, multiline=False, halign='center')
        self.in_op3 = TextInput(text=self.app.op3, multiline=False, halign='center')
        self.in_op4 = TextInput(text=self.app.op4, multiline=False, halign='center')
        grid_ops.add_widget(self.in_op1)
        grid_ops.add_widget(self.in_op2)
        grid_ops.add_widget(self.in_op3)
        grid_ops.add_widget(self.in_op4)
        root.add_widget(grid_ops)
        root.add_widget(Label(text="Цветовая палитра интерфейса:", size_hint_y=None, height=18, color=get_color_from_hex("#a6adc8")))
        self.theme_spinner = Spinner(text=self.app.config_theme, values=('Deep Space Gray', 'Midnight Blue', 'Emerald Mint'), size_hint_y=None, height=35)
        root.add_widget(self.theme_spinner)
        root.add_widget(Label(text="Размер шрифта статистики:", size_hint_y=None, height=18, color=get_color_from_hex("#a6adc8")))
        self.font_slider = Slider(min=10, max=22, value=self.app.config_font_size, size_hint_y=None, height=30)
        root.add_widget(self.font_slider)

        btn_change_pin = Button(text="🔒 Сменить PIN-код", size_hint_y=None, height=38, background_color=get_color_from_hex("#f9e2af"), color=(0, 0, 0, 1))
        btn_change_pin.bind(on_press=self.change_pin)
        root.add_widget(btn_change_pin)

        btn_back = Button(text="Применить и Назад", bold=True, size_hint_y=None, height=42, background_color=get_color_from_hex("#a6e3a1"))
        btn_back.bind(on_press=self.save_settings)
        root.add_widget(btn_back)
        self.add_widget(root)

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
        ''', (self.app.config_hour_rate, self.app.config_theme, self.app.config_font_size, self.app.op1, self.app.op2, self.app.op3, self.app.op4))
        self.app.conn.commit()
        self.manager.current = 'main'


class ShiftTrackerApp(App):
    def build(self):
        self.config_hour_rate = 632.0
        self.config_theme = "Deep Space Gray"
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
        # Пишем БД в каталог данных приложения (обязательно для Android — иначе
        # относительный путь может оказаться в недоступной для записи папке)
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
        # Миграция для баз, созданных до появления PIN-кода
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
            self.config_hour_rate, self.config_theme, self.config_font_size = row[0], row[1], row[2]
            self.op1, self.op2, self.op3, self.op4 = row[3], row[4], row[5], row[6]


if __name__ == '__main__':
    ShiftTrackerApp().run()

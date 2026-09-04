# ==========================================
# КОНСТАНТЫ, ПАЛИТРЫ И СПРАВОЧНИКИ
# ==========================================

# ---------- акцентные цвета ----------
THEME_ACCENTS = {
    "Aurora Violet": "#c9a6ff",
    "Midnight Blue": "#7dd3fc",
    "Emerald Mint": "#6ee7b7",
    "Sunset Coral": "#fb9c8a",
    "Amber Gold": "#fbbf24",
    "Rose Quartz": "#f9a8d4",
}

DEFAULT_ACCENT = "Aurora Violet"

# ---------- фоновые палитры ----------
# spheres=None -> сферы подсвечиваются акцентным цветом с прозрачностью
# из sphere_alpha. text/text_dim/text_faint нужны для светлой темы.
THEME_BACKGROUNDS = {
    "Космос (по умолчанию)": {
        "dark": True,
        "page": "#0b0818",
        "gradient": ["#150e34", "#241a5c", "#123a66"],
        "spheres": ["#6693c5fd", "#55c9a6ff", "#556ee7b7"],
        "sphere_alpha": ["66", "55", "55"],
        "glass": "#1affffff",
        "glass_border": "#26ffffff",
        "text": "#ffffff",
        "text_dim": "#b3ffffff",
        "text_faint": "#73ffffff",
        "field_bg": "#14ffffff",
        "field_border": "#33ffffff",
        "cell_border": "#24ffffff",
        "weekend": "#14ffffff",
    },
    "Тёмный графит": {
        "dark": True,
        "page": "#07070a",
        "gradient": ["#0d0d11", "#15151c", "#1c1c26"],
        "spheres": None,
        "sphere_alpha": ["2e", "24", "1c"],
        "glass": "#14ffffff",
        "glass_border": "#1fffffff",
        "text": "#ffffff",
        "text_dim": "#b3ffffff",
        "text_faint": "#73ffffff",
        "field_bg": "#12ffffff",
        "field_border": "#2affffff",
        "cell_border": "#1fffffff",
        "weekend": "#10ffffff",
    },
    "Тёмная ночь": {
        "dark": True,
        "page": "#04060a",
        "gradient": ["#070b12", "#0b1220", "#101a2b"],
        "spheres": None,
        "sphere_alpha": ["33", "26", "1f"],
        "glass": "#12ffffff",
        "glass_border": "#1cffffff",
        "text": "#ffffff",
        "text_dim": "#b3ffffff",
        "text_faint": "#73ffffff",
        "field_bg": "#12ffffff",
        "field_border": "#2affffff",
        "cell_border": "#1cffffff",
        "weekend": "#10ffffff",
    },
    "Тёмный изумруд": {
        "dark": True,
        "page": "#040a08",
        "gradient": ["#06120f", "#0a1c17", "#0e2620"],
        "spheres": None,
        "sphere_alpha": ["30", "26", "1e"],
        "glass": "#14ffffff",
        "glass_border": "#1fffffff",
        "text": "#ffffff",
        "text_dim": "#b3ffffff",
        "text_faint": "#73ffffff",
        "field_bg": "#12ffffff",
        "field_border": "#2affffff",
        "cell_border": "#1fffffff",
        "weekend": "#10ffffff",
    },
    "Светлая (день)": {
        "dark": False,
        "page": "#eef1f7",
        "gradient": ["#f6f8fc", "#e9eef8", "#dfe7f4"],
        "spheres": None,
        "sphere_alpha": ["40", "33", "26"],
        "glass": "#b3ffffff",
        "glass_border": "#1a000000",
        "text": "#101828",
        "text_dim": "#475467",
        "text_faint": "#98a2b3",
        "field_bg": "#ccffffff",
        "field_border": "#26000000",
        "cell_border": "#1f000000",
        "weekend": "#0d000000",
    },
}

DEFAULT_BG_THEME = "Космос (по умолчанию)"

# ---------- статусы моего дня ----------
STATUS_WORK = "Рабочая смена"
STATUS_PREMIUM_OFF = "Выходной для премии"
STATUS_DAY_OFF = "Обычный выходной"
STATUS_OVERSLEPT = "Проспал"

DAY_STATUSES = [STATUS_WORK, STATUS_PREMIUM_OFF, STATUS_DAY_OFF, STATUS_OVERSLEPT]

# Цвета заливки/рамки ячеек календаря по статусу.
# None -> используется акцентный цвет темы.
STATUS_COLORS = {
    STATUS_WORK: (None, None),
    STATUS_PREMIUM_OFF: ("#404caf50", "#994caf50"),
    STATUS_DAY_OFF: ("#402196f3", "#992196f3"),
    STATUS_OVERSLEPT: ("#4df44336", "#b3f44336"),
}

# ---------- цеха ----------
# Цех 1 работает всегда, цех 2 подключается по наличию людей.
SHOP1 = "shop1"
SHOP2 = "shop2"

SHOP_TITLES = {
    SHOP1: "Цех 1 — линии 1+2",
    SHOP2: "Цех 2 — линия 3",
}

SHOP_SHORT = {
    SHOP1: "Цех 1",
    SHOP2: "Цех 2",
}

SHOP_KEYS = [SHOP1, SHOP2]

DEFAULT_NORM_SHOP1 = 5900.0
DEFAULT_NORM_SHOP2 = 2100.0

# Максимально допустимая выработка при вводе (защита от опечаток)
WEIGHT_MAX = 100000.0

# ---------- время прибытия ----------
ARRIVAL_OPTIONS = ["До 20:00", "Буфер (до 20:15)", "Опоздание (до 20:30)"]
ARRIVAL_LABELS = [("Вовремя", "до 20:00"), ("Буфер", "до 20:15"), ("Опоздание", "до 20:30")]

FULL_SHIFT_HOURS = 11.0
LATE_SHIFT_HOURS = 10.0

# ---------- налоги ----------
# Порядок важен: он же порядок кнопок в настройках.
TAX_OPTIONS = [
    ("Без налога", 0.0),
    ("6 % (самозанятый)", 0.06),
    ("13 % (НДФЛ)", 0.13),
]
DEFAULT_TAX = 0.0


def tax_label(rate):
    """Подпись налоговой ставки по её числовому значению."""
    for name, value in TAX_OPTIONS:
        if abs(value - float(rate or 0.0)) < 0.0001:
            return name
    return f"{float(rate) * 100:g} %"


# ---------- премия ----------
# (минимальное число смен, часов премии). Ищется наибольший порог <= смен.
PREMIUM_LADDER = [(17, 9), (19, 12), (21, 16), (23, 18), (24, 20), (25, 21)]

# ---------- прочее ----------
MONTH_NAMES = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
               "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]

MONTH_SHORT = ["Янв", "Фев", "Мар", "Апр", "Май", "Июн",
               "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"]

WEEKDAY_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

# Дата, от которой отсчитывается ротация операторов «одна ночь через три»
DEFAULT_CYCLE_START = "2026-09-01"

# Типы событий ночного трекера
EVENT_BREAK = "Перекур"
EVENT_WORK = "Работа"

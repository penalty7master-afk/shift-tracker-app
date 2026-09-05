# ==========================================
# КОНСТАНТЫ, ПАЛИТРЫ И СПРАВОЧНИКИ
# ==========================================

# ---------- режим смены ----------
MODE_NIGHT = "night"
MODE_DAY = "day"
SHIFT_MODES = [MODE_NIGHT, MODE_DAY]
DEFAULT_SHIFT_MODE = MODE_NIGHT

MODE_TITLES = {
    MODE_NIGHT: "Ночные смены",
    MODE_DAY: "Дневные смены",
}

MODE_SUBTITLES = {
    MODE_NIGHT: "с 20:00 до 08:00",
    MODE_DAY: "с 08:00 до 20:00",
}

# Все зависящие от режима слова собраны здесь, чтобы не искать их
# потом по всему коду и не забыть очередную надпись.
TERMS = {
    MODE_NIGHT: {
        "shift": "ночь",
        "shift_gen": "ночи",
        "per_shift": "за ночь",
        "per_shift_caps": "ЗА НОЧЬ",
        "shifts_short": "ноч.",
        "production_title": "ПРОИЗВОДСТВО ЗА МЕСЯЦ",
        "production_hint_all": "По всем ночам, включая мои выходные.",
        "production_hint_mine": "Только ночи, в которые я был на смене.",
        "tracker": "Трекер ночи (хронология):",
        "modal_production": "ПРОИЗВОДСТВО ЗА НОЧЬ",
        "shop2_hint": ("Цех 2 работает не каждую ночь — оставьте поля пустыми, "
                       "если линия не запускалась."),
        "operator_label": "Оператор ночной смены",
    },
    MODE_DAY: {
        "shift": "день",
        "shift_gen": "дня",
        "per_shift": "за день",
        "per_shift_caps": "ЗА ДЕНЬ",
        "shifts_short": "дн.",
        "production_title": "ПРОИЗВОДСТВО ЗА МЕСЯЦ",
        "production_hint_all": "По всем дневным сменам, включая мои выходные.",
        "production_hint_mine": "Только дни, в которые я был на смене.",
        "tracker": "Трекер смены (хронология):",
        "modal_production": "ПРОИЗВОДСТВО ЗА ДЕНЬ",
        "shop2_hint": ("Цех 2 работает не каждую смену — оставьте поля пустыми, "
                       "если линия не запускалась."),
        "operator_label": "Оператор дневной смены",
    },
}


def term(mode, key):
    """Подпись, зависящая от режима. Неизвестный режим — считаем ночным."""
    return TERMS.get(mode or DEFAULT_SHIFT_MODE, TERMS[MODE_NIGHT]).get(key, "")


# ---------- акцентные цвета ----------
THEME_ACCENTS = {
    "Aurora Violet": "#c9a6ff",
    "Emerald Mint": "#6ee7b7",
    "Sunset Coral": "#fb9c8a",
    "Amber Gold": "#fbbf24",
    "Pure White": "#f5f5f7",
}

DEFAULT_ACCENT = "Aurora Violet"

# ---------- фоновые палитры ----------
THEME_BACKGROUNDS = {
    "Космос (по умолчанию)": {
        "dark": True,
        "page": "#0b0818",
        "gradient": ["#150e34", "#241a5c", "#123a66"],
        "spheres": ["#6693c5fd", "#55c9a6ff", "#556ee7b7"],
        "sphere_alpha": ["66", "55", "55"],
        "dialog": "#f21b1440",
        "glass": "#1affffff",
        "glass_border": "#26ffffff",
        "text": "#ffffff",
        "text_dim": "#b3ffffff",
        "text_faint": "#73ffffff",
        "field_bg": "#14ffffff",
        "field_border": "#33ffffff",
        "cell_border": "#24ffffff",
        "weekend": "#14ffffff",
        "nav": "#26ffffff",
    },
    "Тёмный графит": {
        "dark": True,
        "page": "#07070a",
        "gradient": ["#0d0d11", "#15151c", "#1c1c26"],
        "spheres": None,
        "sphere_alpha": ["2e", "24", "1c"],
        "dialog": "#f2181820",
        "glass": "#14ffffff",
        "glass_border": "#1fffffff",
        "text": "#ffffff",
        "text_dim": "#b3ffffff",
        "text_faint": "#73ffffff",
        "field_bg": "#12ffffff",
        "field_border": "#2affffff",
        "cell_border": "#1fffffff",
        "weekend": "#10ffffff",
        "nav": "#1fffffff",
    },
    "Тёмная ночь": {
        "dark": True,
        "page": "#04060a",
        "gradient": ["#070b12", "#0b1220", "#101a2b"],
        "spheres": None,
        "sphere_alpha": ["33", "26", "1f"],
        "dialog": "#f20e1524",
        "glass": "#12ffffff",
        "glass_border": "#1cffffff",
        "text": "#ffffff",
        "text_dim": "#b3ffffff",
        "text_faint": "#73ffffff",
        "field_bg": "#12ffffff",
        "field_border": "#2affffff",
        "cell_border": "#1cffffff",
        "weekend": "#10ffffff",
        "nav": "#1cffffff",
    },
    "Тёмный изумруд": {
        "dark": True,
        "page": "#040a08",
        "gradient": ["#06120f", "#0a1c17", "#0e2620"],
        "spheres": None,
        "sphere_alpha": ["30", "26", "1e"],
        "dialog": "#f20c1f1a",
        "glass": "#14ffffff",
        "glass_border": "#1fffffff",
        "text": "#ffffff",
        "text_dim": "#b3ffffff",
        "text_faint": "#73ffffff",
        "field_bg": "#12ffffff",
        "field_border": "#2affffff",
        "cell_border": "#1fffffff",
        "weekend": "#10ffffff",
        "nav": "#1fffffff",
    },
    "Светлая (день)": {
        "dark": False,
        # Фон заметно холоднее и темнее карточек: раньше белое стекло
        # сливалось с белым фоном, и границы карточек пропадали.
        "page": "#dde3ee",
        "gradient": ["#e4e9f3", "#d6deee", "#c9d5e8"],
        "spheres": None,
        "sphere_alpha": ["4d", "40", "33"],
        "dialog": "#f7f7f9fd",
        "glass": "#e6ffffff",
        "glass_border": "#26000000",
        "text": "#0f172a",
        "text_dim": "#3f4a5f",
        "text_faint": "#5b6577",
        "field_bg": "#f2ffffff",
        "field_border": "#33000000",
        "cell_border": "#2b000000",
        "weekend": "#14000000",
        "nav": "#33000000",
    },
}

DEFAULT_BG_THEME = "Космос (по умолчанию)"

# ---------- статусы моего дня ----------
STATUS_WORK = "Рабочая смена"
STATUS_PREMIUM_OFF = "Выходной для премии"
STATUS_DAY_OFF = "Обычный выходной"
STATUS_OVERSLEPT = "Проспал"

DAY_STATUSES = [STATUS_WORK, STATUS_PREMIUM_OFF, STATUS_DAY_OFF, STATUS_OVERSLEPT]

STATUS_COLORS = {
    STATUS_WORK: (None, None),
    STATUS_PREMIUM_OFF: ("#404caf50", "#994caf50"),
    STATUS_DAY_OFF: ("#402196f3", "#992196f3"),
    STATUS_OVERSLEPT: ("#4df44336", "#b3f44336"),
}

HEATMAP_COLORS = {
    STATUS_WORK: None,                  # None -> акцентный цвет темы
    STATUS_PREMIUM_OFF: "#4caf50",
    STATUS_DAY_OFF: "#2196f3",
    STATUS_OVERSLEPT: "#f44336",
}
HEATMAP_EMPTY = "#1fffffff"

# ---------- цеха ----------
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

# Типовой каталог: добавляется вручную кнопкой в настройках.
# PW латиницей заглавными — так наименования выглядят в журнале.
DEFAULT_PRODUCTS = ["90", "90PW", "200", "200PW", "500", "500PW", "Предпомол"]

DEFAULT_NORM_SHOP1 = 5900.0
DEFAULT_NORM_SHOP2 = 2100.0

WEIGHT_MAX = 100000.0
PREMIUM_PAY_MAX = 1000000.0

# ==========================================
# ВРЕМЯ ПРИБЫТИЯ
# ==========================================
# В базу пишется ключ, а не подпись: иначе при смене режима все ранее
# сохранённые дни («До 20:00») перестали бы опознаваться, и статистика
# прихода обнулилась бы.
ARRIVAL_ON_TIME = "on_time"
ARRIVAL_BUFFER = "buffer"
ARRIVAL_LATE = "late"

ARRIVAL_KEYS = [ARRIVAL_ON_TIME, ARRIVAL_BUFFER, ARRIVAL_LATE]

ARRIVAL_TIMES = {
    MODE_NIGHT: {
        ARRIVAL_ON_TIME: "до 20:00",
        ARRIVAL_BUFFER: "до 20:15",
        ARRIVAL_LATE: "до 20:30",
    },
    MODE_DAY: {
        ARRIVAL_ON_TIME: "до 08:00",
        ARRIVAL_BUFFER: "до 08:15",
        ARRIVAL_LATE: "до 08:30",
    },
}

ARRIVAL_NAMES = {
    ARRIVAL_ON_TIME: "Вовремя",
    ARRIVAL_BUFFER: "Буфер",
    ARRIVAL_LATE: "Опоздание",
}

# Значения из версий до появления режимов — переводятся при чтении.
LEGACY_ARRIVAL = {
    "До 20:00": ARRIVAL_ON_TIME,
    "Буфер (до 20:15)": ARRIVAL_BUFFER,
    "Опоздание (до 20:30)": ARRIVAL_LATE,
}


def arrival_labels(mode):
    """[(название, время)] для переключателя в модалке."""
    times = ARRIVAL_TIMES.get(mode or DEFAULT_SHIFT_MODE, ARRIVAL_TIMES[MODE_NIGHT])
    return [(ARRIVAL_NAMES[key], times[key]) for key in ARRIVAL_KEYS]


def arrival_full(mode, key):
    """«Вовремя (до 08:00)» — для выгрузок и подписей."""
    times = ARRIVAL_TIMES.get(mode or DEFAULT_SHIFT_MODE, ARRIVAL_TIMES[MODE_NIGHT])
    if key not in ARRIVAL_NAMES:
        return ""
    return f"{ARRIVAL_NAMES[key]} ({times[key]})"


FULL_SHIFT_HOURS = 11.0
LATE_SHIFT_HOURS = 10.0

# ---------- налоги ----------
# 13 % убран: в текущем режиме работы неактуален. Переключатель оставлен,
# чтобы можно было сравнить суммы с налогом и без.
TAX_OPTIONS = [
    ("Без налога", 0.0),
    ("6 % (самозанятый)", 0.06),
]
DEFAULT_TAX = 0.0


def tax_label(rate):
    for name, value in TAX_OPTIONS:
        if abs(value - float(rate or 0.0)) < 0.0001:
            return name
    return f"{float(rate) * 100:g} %"


# ==========================================
# ПРЕМИЯ
# ==========================================
# (минимальное число смен, часов премии). Ищется наибольший порог <= смен.
NIGHT_PREMIUM_LADDER = [(17, 9), (19, 12), (21, 16), (23, 18), (24, 20), (25, 21)]

# Дневная лестница пока копия ночной: точные пороги ещё уточняются.
# Список отдельный намеренно — правка дневных значений не заденет ночные.
DAY_PREMIUM_LADDER = [(17, 9), (19, 12), (21, 16), (23, 18), (24, 20), (25, 21)]

PREMIUM_LADDERS = {
    MODE_NIGHT: NIGHT_PREMIUM_LADDER,
    MODE_DAY: DAY_PREMIUM_LADDER,
}

# Совместимость со старым именем
PREMIUM_LADDER = NIGHT_PREMIUM_LADDER

# ---------- ставки ----------
DEFAULT_HOUR_RATE = 632.0
# Дневная смена: 5885 ₽ за 11 часов.
DEFAULT_DAY_HOUR_RATE = round(5885.0 / FULL_SHIFT_HOURS, 2)

# ---------- прочее ----------
MONTH_NAMES = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
               "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]

MONTH_SHORT = ["Янв", "Фев", "Мар", "Апр", "Май", "Июн",
               "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"]

WEEKDAY_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

# Дата, от которой отсчитывается ротация. Привязана к НОЧНОЙ смене:
# в этот день Оператор 1 выходит в ночь. Дневная сетка сдвинута на сутки.
DEFAULT_CYCLE_START = "2026-09-01"

# Типы событий трекера
EVENT_BREAK = "Перекур"
EVENT_WORK = "Работа"
EVENT_MARK = "Отметка"

# ---------- автоблокировка ----------
LOCK_TIMEOUT_SECONDS = 300
LOCK_CHECK_INTERVAL = 15

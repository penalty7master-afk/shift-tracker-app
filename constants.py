THEME_ACCENTS = {
    "Aurora Violet": "#c9a6ff",
    "Midnight Blue": "#7dd3fc",
    "Emerald Mint": "#6ee7b7",
}

# Фоновые палитры. spheres=None -> сферы подсвечиваются акцентным цветом
# с прозрачностью из sphere_alpha.
THEME_BACKGROUNDS = {
    "Космос (по умолчанию)": {
        "page": "#0b0818",
        "gradient": ["#150e34", "#241a5c", "#123a66"],
        "spheres": ["#6693c5fd", "#55c9a6ff", "#556ee7b7"],
        "glass": "#1affffff",
        "glass_border": "#26ffffff",
    },
    "Тёмный графит": {
        "page": "#07070a",
        "gradient": ["#0d0d11", "#15151c", "#1c1c26"],
        "spheres": None,
        "sphere_alpha": ["2e", "24", "1c"],
        "glass": "#14ffffff",
        "glass_border": "#1fffffff",
    },
    "Тёмная ночь": {
        "page": "#04060a",
        "gradient": ["#070b12", "#0b1220", "#101a2b"],
        "spheres": None,
        "sphere_alpha": ["33", "26", "1f"],
        "glass": "#12ffffff",
        "glass_border": "#1cffffff",
    },
    "Тёмный изумруд": {
        "page": "#040a08",
        "gradient": ["#06120f", "#0a1c17", "#0e2620"],
        "spheres": None,
        "sphere_alpha": ["30", "26", "1e"],
        "glass": "#14ffffff",
        "glass_border": "#1fffffff",
    },
}

DEFAULT_BG_THEME = "Космос (по умолчанию)"

ARRIVAL_OPTIONS = ["До 20:00", "Буфер (до 20:15)", "Опоздание (до 20:30)"]

# Двухстрочные подписи для сегментированной кнопки (заголовок / время)
ARRIVAL_LABELS = [("Вовремя", "до 20:00"), ("Буфер", "до 20:15"), ("Опоздание", "до 20:30")]

MONTH_NAMES = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
               "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]

# Норма выработки продукции за смену, кг
WEIGHT_NORM = 2100.0

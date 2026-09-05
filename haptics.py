"""
Виброотклик. Сервис ft.HapticFeedback не рисуется на экране, он только
шлёт команду во Flutter, который дёргает системный performHapticFeedback.
Разрешение VIBRATE в манифесте не требуется.

ВАЖНО: методы сервиса в Flet 0.86 асинхронные. Синхронный вызов возвращает
корутину, которая никогда не выполняется — ошибки нет, вибрации тоже.
Поэтому всё идёт через page.run_task().

Если сервиса в сборке нет или системный виброотклик выключен в настройках
телефона, приложение работает как обычно, просто молча.
"""
import inspect
import threading
import time

import flet as ft

# Пауза между толчками серии. Меньше 100 мс — толчки слипаются в один.
PULSE_GAP = 0.12

_state = {"service": None, "page": None, "enabled": True}


def setup(page):
    """Регистрирует сервис на странице. Зовётся один раз при старте."""
    _state["page"] = page

    cls = getattr(ft, "HapticFeedback", None)
    if cls is None:
        return False
    try:
        service = cls()
    except Exception:
        return False

    # В Flet 0.86 сервисы живут в page.services, в старых сборках — в overlay.
    for holder in ("services", "overlay"):
        target = getattr(page, holder, None)
        if target is None:
            continue
        try:
            target.append(service)
            _state["service"] = service
            return True
        except Exception:
            continue

    # Держим ссылку даже без контейнера: в некоторых сборках сервис
    # работает и без явной регистрации.
    _state["service"] = service
    return False


def set_enabled(flag):
    _state["enabled"] = bool(flag)


def is_enabled():
    return bool(_state["enabled"])


def _fire(method):
    service = _state["service"]
    if service is None or not _state["enabled"]:
        return
    action = getattr(service, method, None)
    if action is None:
        return

    page = _state["page"]
    runner = getattr(page, "run_task", None) if page is not None else None
    if runner is not None:
        try:
            runner(action)
            return
        except Exception:
            pass

    # Запасной путь для сборок без run_task.
    try:
        result = action()
        if inspect.isawaitable(result):
            # Цикла событий нет — закрываем корутину, иначе Python
            # засорит лог предупреждением "never awaited".
            result.close()
    except Exception:
        pass


# ==========================================
# ОДИНОЧНЫЕ ТОЛЧКИ
# ==========================================
def tap():
    """Нажатие цифры — самый тихий отклик."""
    _fire("light_impact")


def select():
    """Переключение вкладки, выбор варианта."""
    _fire("selection_click")


def confirm():
    """Успех: верный PIN, сохранение."""
    _fire("medium_impact")


def warn():
    """Одиночный сильный толчок."""
    _fire("heavy_impact")


# ==========================================
# СЕРИЯ
# ==========================================
def _burst(count, gap):
    for index in range(count):
        if index:
            time.sleep(gap)
        _fire("heavy_impact")


def error(count=3, gap=PULSE_GAP):
    """
    Серия толчков на ошибку. Идёт в фоновом потоке: пауза в основном
    потоке заморозила бы интерфейс на всё время серии.
    Поток только шлёт команды сервису и не трогает дерево контролов.
    """
    if _state["service"] is None or not _state["enabled"]:
        return
    threading.Thread(target=_burst, args=(count, gap), daemon=True).start()

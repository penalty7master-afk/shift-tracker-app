"""
Автоблокировка по бездействию. Без неё PIN защищает только первый запуск:
свёрнутое приложение оставалось открытым сколько угодно.

Два независимых сценария:
  возврат из фона — сравниваем метки времени, поэтому заморозка процесса
  системой на результат не влияет;
  бездействие при открытом экране — фоновый поток раз в LOCK_CHECK_INTERVAL
  секунд смотрит, давно ли была активность.

Активность отмечают сами экраны вызовом touch(): глобального события
«что-то произошло на экране» во Flet нет — нажатие внутри кнопки до
родительского обработчика не доходит.
"""
import threading
import time

from constants import LOCK_CHECK_INTERVAL, LOCK_TIMEOUT_SECONDS


class IdleLock:
    def __init__(self, on_lock, timeout=LOCK_TIMEOUT_SECONDS,
                 interval=LOCK_CHECK_INTERVAL):
        self.on_lock = on_lock
        self.timeout = timeout
        self.interval = interval

        self._last = time.monotonic()
        self._armed = False           # следим только когда экран разблокирован
        self._is_dirty = None         # колбэк: есть ли несохранённые правки
        self._thread = None
        self._stop = threading.Event()

    # ==========================================
    # УПРАВЛЕНИЕ
    # ==========================================
    def set_dirty_check(self, callback):
        self._is_dirty = callback

    def touch(self):
        self._last = time.monotonic()

    def arm(self):
        """Включается после успешного ввода PIN."""
        self.touch()
        self._armed = True
        self._ensure_thread()

    def disarm(self):
        """Выключается на экране PIN, чтобы не срабатывать поверх него."""
        self._armed = False

    def expired(self):
        return (time.monotonic() - self._last) >= self.timeout

    # ==========================================
    # ФОНОВЫЙ КОНТРОЛЬ
    # ==========================================
    def _ensure_thread(self):
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self):
        while not self._stop.wait(self.interval):
            if not self._armed:
                continue
            if not self.expired():
                continue
            # Незаконченный ввод в модалке не выбрасываем: правки живут
            # до «Сохранить», блокировка потеряла бы их молча.
            if callable(self._is_dirty) and self._is_dirty():
                self.touch()
                continue
            self._armed = False
            try:
                self.on_lock()
            except Exception:
                pass

    def stop(self):
        self._armed = False
        self._stop.set()

    # ==========================================
    # ВОЗВРАТ ИЗ ФОНА
    # ==========================================
    def handle_app_state(self, state):
        """
        Событие жизненного цикла от Flet. Названия состояний отличаются
        между сборками, поэтому смотрим на подстроку.
        """
        text = str(state or "").lower()
        if "resume" in text or "show" in text:
            if self._armed and self.expired():
                if callable(self._is_dirty) and self._is_dirty():
                    self.touch()
                    return
                self._armed = False
                try:
                    self.on_lock()
                except Exception:
                    pass
            else:
                self.touch()
        elif "pause" in text or "hide" in text or "inactive" in text:
            # Метку не трогаем: именно по ней считается время в фоне.
            pass

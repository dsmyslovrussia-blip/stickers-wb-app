#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ЛОКАЛЬНЫЙ АГЕНТ WILDBERRIES — ФИНАЛЬНАЯ ВЕРСИЯ С МИНИ-ПРИЛОЖЕНИЕМ
✅ Токены загружаются из .env файла
✅ Исправлены все ошибки в коде (отступы, init_poolmanager → __init__)
✅ Стрелка направлена ВВЕРХ (↑) на первой странице БЕЗ текста
✅ Добавлена обработка данных из мини-приложения (web_app_data)
✅ Система авторизации настроек через бота
✅ Все предыдущие функции сохранены
"""
import os
import sys
import time
import logging
from pathlib import Path
from datetime import datetime, timedelta
import requests
import urllib3
from threading import Thread, Event
import ctypes
from ctypes import wintypes
import re
import json
import subprocess
from dotenv import load_dotenv  # ← НОВОЕ: загрузка .env

# ============ ЗАГРУЗКА .ENV ============
load_dotenv()  # ← Загружаем переменные из .env файла

# ============ ИСПРАВЛЕНИЕ SSL ============
import ssl

ssl._create_default_https_context = ssl._create_unverified_context
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============ ГЛОБАЛЬНЫЙ ИМПОРТ PYAUTOGUI (ИСПРАВЛЕНЫ ОТСТУПЫ) ============
try:
    import pyautogui

    pyautogui.FAILSAFE = False
except ImportError:
    pyautogui = None


def create_session():
    """Создаёт сессию requests с обходом SSL"""
    session = requests.Session()
    session.verify = False
    session.trust_env = False
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    return session


# ============ НАСТРОЙКИ ИЗ .ENV ============
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WB_TOKEN = os.getenv("WB_TOKEN")
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID", "-1003709985985"))
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "5021035612"))

# Дата создания токена (формат: YYYY-MM-DD)
WB_TOKEN_CREATION_DATE = os.getenv("WB_TOKEN_CREATION_DATE", "2026-08-07")
WB_TOKEN_EXPIRY_DAYS = int(os.getenv("WB_TOKEN_EXPIRY_DAYS", "182"))

# ============ КОНФИГУРАЦИЯ ПЕЧАТИ ============
DEFAULT_PRINTER = os.getenv("DEFAULT_PRINTER", "Xprinter XP-365B")
AUTO_PRINT_ENABLED = os.getenv("AUTO_PRINT_ENABLED", "True").lower() == "true"
AUTO_START_ENABLED = os.getenv("AUTO_START_ENABLED", "False").lower() == "false"

# ============ ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ============
RUN_LOCK = False
STOP_CURRENT_TASK = False
AGENT_SHUTDOWN = False
CONFIRMED = False
PROCESS_CANCELLED = False
CURRENT_MODE = None
AUTHORIZED_USERS = set()
PROCESSED_ORDERS = set()

# Глобальные флаги для ожидания ввода
WAITING_FOR_PRINTER_NAME = False
WAITING_FOR_WB_TOKEN = False

# ============ СИСТЕМА АВТОРИЗАЦИИ НАСТРОЕК МИНИ-ПРИЛОЖЕНИЯ ============
settings_access_requests = {}  # session_id: user_id

# ============ ПУТИ ============
SCRIPT_PATH = Path(__file__).resolve()
SCRIPT_DIR = SCRIPT_PATH.parent
DOWNLOADS_DIR = Path(os.path.expanduser("~/Desktop/вб"))
DOWNLOADS_DIR.mkdir(exist_ok=True)
CONFIG_FILE = SCRIPT_DIR / "config.json"
AUTHORIZED_FILE = SCRIPT_DIR / "authorized_users.txt"


def setup_logger():
    logger = logging.getLogger("WB_Final_Version")
    logger.setLevel(logging.INFO)
    if logger.handlers:
        logger.handlers.clear()
    formatter = logging.Formatter('%(asctime)s | %(levelname)-8s | %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    return logger


logger = setup_logger()


# ============ АДАПТИВНАЯ ЗАДЕРЖКА ============
def adaptive_sleep(seconds: float):
    """Увеличивает паузы в рабочем режиме для стабильности"""
    if CURRENT_MODE == "production":
        time.sleep(seconds * 1.5)  # На 50% дольше в автоматическом режиме
    else:
        time.sleep(seconds)


# ============ ЗАГРУЗКА КОНФИГУРАЦИИ ============
def load_configuration():
    """Загружает конфигурацию из файла"""
    global AUTHORIZED_USERS, PROCESSED_ORDERS, DEFAULT_PRINTER, AUTO_PRINT_ENABLED, AUTO_START_ENABLED
    global WB_TOKEN, TELEGRAM_BOT_TOKEN, GROUP_CHAT_ID, ADMIN_USER_ID, WB_TOKEN_CREATION_DATE

    # Загружаем авторизованных пользователей
    if AUTHORIZED_FILE.exists():
        try:
            with open(AUTHORIZED_FILE, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and line.isdigit():
                        AUTHORIZED_USERS.add(int(line))
            logger.info(f"Загружено {len(AUTHORIZED_USERS)} авторизованных пользователей")
        except Exception as e:
            logger.error(f"Ошибка загрузки авторизованных пользователей: {e}")

    # Загружаем основную конфигурацию
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
            WB_TOKEN = config.get('wb_token', WB_TOKEN)
            TELEGRAM_BOT_TOKEN = config.get('telegram_bot_token', TELEGRAM_BOT_TOKEN)
            GROUP_CHAT_ID = config.get('group_id', GROUP_CHAT_ID)
            ADMIN_USER_ID = config.get('admin_user_id', ADMIN_USER_ID)
            DEFAULT_PRINTER = config.get('printer_name', DEFAULT_PRINTER)
            AUTO_PRINT_ENABLED = config.get('auto_print_enabled', AUTO_PRINT_ENABLED)
            AUTO_START_ENABLED = config.get('auto_start_enabled', AUTO_START_ENABLED)
            WB_TOKEN_CREATION_DATE = config.get('wb_token_creation_date', WB_TOKEN_CREATION_DATE)
            logger.info("Конфигурация загружена")
        except Exception as e:
            logger.error(f"Ошибка загрузки конфигурации: {e}")

    # Добавляем админа
    AUTHORIZED_USERS.add(ADMIN_USER_ID)


def save_configuration():
    """Сохраняет текущую конфигурацию в файл"""
    try:
        config = {
            'wb_token': WB_TOKEN,
            'telegram_bot_token': TELEGRAM_BOT_TOKEN,
            'group_id': GROUP_CHAT_ID,
            'admin_user_id': ADMIN_USER_ID,
            'printer_name': DEFAULT_PRINTER,
            'auto_print_enabled': AUTO_PRINT_ENABLED,
            'auto_start_enabled': AUTO_START_ENABLED,
            'wb_token_creation_date': WB_TOKEN_CREATION_DATE
        }
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        logger.info("Конфигурация сохранена")
    except Exception as e:
        logger.error(f"Ошибка сохранения конфигурации: {e}")


def save_authorized_user(user_id: int):
    """Сохраняет пользователя в файл авторизованных"""
    try:
        with open(AUTHORIZED_FILE, 'a', encoding='utf-8') as f:
            f.write(f"{user_id}\n")
        logger.info(f"Пользователь {user_id} сохранён в файл авторизованных")
    except Exception as e:
        logger.error(f"Ошибка сохранения пользователя {user_id}: {e}")


def remove_authorized_user(user_id: int):
    """Удаляет пользователя из файла авторизованных"""
    try:
        if AUTHORIZED_FILE.exists():
            with open(AUTHORIZED_FILE, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            with open(AUTHORIZED_FILE, 'w', encoding='utf-8') as f:
                for line in lines:
                    if line.strip() != str(user_id):
                        f.write(line)
            logger.info(f"Пользователь {user_id} удалён из файла авторизованных")
    except Exception as e:
        logger.error(f"Ошибка удаления пользователя {user_id}: {e}")


# ============ ПОЛУЧЕНИЕ СПИСКА ПРИНТЕРОВ ============
def get_available_printers():
    """Получает список доступных принтеров в системе"""
    try:
        if sys.platform == "win32":
            import win32print
            printers = [printer[2] for printer in win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL)]
            return printers
        else:
            return ["Принтеры недоступны на этой ОС"]
    except Exception as e:
        logger.error(f"Ошибка получения списка принтеров: {e}")
        return ["Ошибка получения принтеров"]


# ============ БЕЗОПАСНАЯ СМЕНА ПРИНТЕРА ============
def set_printer_safely(printer_name: str) -> bool:
    """Безопасная смена принтера с проверкой существования"""
    try:
        available = set(get_available_printers())
        if printer_name in available:
            global DEFAULT_PRINTER
            DEFAULT_PRINTER = printer_name
            save_configuration()
            return True
        else:
            return False
    except Exception as e:
        logger.error(f"Ошибка проверки принтера: {e}")
        return False


# ============ АВТОМАТИЧЕСКАЯ ПЕЧАТЬ ============
def auto_print_pdf(pdf_path: Path):
    """Автоматическая печать PDF на указанный принтер"""
    global DEFAULT_PRINTER
    if not AUTO_PRINT_ENABLED:
        logger.info("Автоматическая печать отключена")
        return False

    try:
        if sys.platform == "win32":
            # Сначала попробуем найти конкретные программы
            specific_programs = [
                r"C:\Program Files\SumatraPDF\SumatraPDF.exe",
                r"C:\Program Files (x86)\SumatraPDF\SumatraPDF.exe",
                r"C:\Program Files\Foxit Software\Foxit Reader\FoxitReader.exe",
                r"C:\Program Files (x86)\Foxit Software\Foxit Reader\FoxitReader.exe",
                r"C:\Program Files\Adobe\Acrobat DC\Acrobat\Acrobat.exe",
                r"C:\Program Files (x86)\Adobe\Acrobat Reader DC\Reader\AcroRd32.exe"
            ]
            found_program = None
            for program_path in specific_programs:
                if os.path.exists(program_path):
                    found_program = program_path
                    break

            if found_program:
                # Используем найденную конкретную программу
                program_name = os.path.basename(found_program).lower()
                if "sumatrapdf" in program_name:
                    cmd = f'"{found_program}" -print-to "{DEFAULT_PRINTER}" "{pdf_path}"'
                elif "foxit" in program_name:
                    cmd = f'"{found_program}" /p "{pdf_path}" "{DEFAULT_PRINTER}"'
                else:  # Adobe
                    cmd = f'"{found_program}" /t "{pdf_path}" "{DEFAULT_PRINTER}"'

                logger.info(f"Печать через найденную программу: {found_program}")
                result = subprocess.run(cmd, shell=True, timeout=90, capture_output=True, text=True)
                if result.returncode == 0:
                    send_telegram_message(f"🖨️ <b>Печать запущена</b>\nПринтер: {DEFAULT_PRINTER}")
                    logger.info(f"✅ Успешно напечатано: {pdf_path.name}")
                    return True
                else:
                    logger.warning(f"Ошибка печати через {program_name}: {result.stderr}")

            # Если конкретные программы не найдены, используем ассоциацию Windows
            logger.info("Использую ассоциацию Windows для печати PDF")
            # Создаём временный .bat файл для печати
            bat_content = f'''@echo off
set PRINTER="{DEFAULT_PRINTER}"
set FILE="{pdf_path}"
REM Пытаемся напечатать через ассоциированную программу
start /wait "" "%FILE%"
REM Ждём немного чтобы программа успела запуститься
timeout /t 5 /nobreak >nul
REM Закрываем программу если она осталась открытой
taskkill /im AcroRd32.exe /f >nul 2>&1
taskkill /im FoxitReader.exe /f >nul 2>&1
taskkill /im SumatraPDF.exe /f >nul 2>&1
echo Печать завершена
'''
            bat_path = pdf_path.with_suffix('.bat')
            with open(bat_path, 'w', encoding='cp866') as f:
                f.write(bat_content)

            # Запускаем .bat файл
            result = subprocess.run(str(bat_path), shell=True, timeout=120, capture_output=True, text=True)
            # Удаляем временный файл
            try:
                bat_path.unlink()
            except:
                pass

            if result.returncode == 0:
                send_telegram_message(
                    f"🖨️ <b>Печать запущена</b>\nПринтер: {DEFAULT_PRINTER}\n(через ассоциацию Windows)")
                logger.info(f"✅ Печать через ассоциацию: {pdf_path.name}")
                return True
            else:
                error_msg = f"❌ Не удалось напечатать через ассоциацию Windows\nУстановите SumatraPDF для надёжной печати"
                send_telegram_message(error_msg)
                logger.error(f"Ошибка печати через ассоциацию: {result.stderr}")
                return False
        else:
            logger.warning("Авто-печать поддерживается только на Windows")
            return False
    except Exception as e:
        logger.error(f"Исключение при печати: {e}")
        send_telegram_message(f"❌ Ошибка печати: {str(e)[:200]}")
        return False


# ============ ПРОВЕРКА ТОКЕНА ============
def check_wb_token_expiry():
    """Проверяет оставшиеся дни до истечения токена (динамический расчёт)"""
    try:
        creation_date = datetime.strptime(WB_TOKEN_CREATION_DATE, "%Y-%m-%d")
        expiry_date = creation_date + timedelta(days=WB_TOKEN_EXPIRY_DAYS)
        current_date = datetime.now()
        days_left = (expiry_date - current_date).days

        if days_left <= 5 and days_left > 0:
            warning_msg = f"⚠️ <b>ВНИМАНИЕ!</b>\nДо окончания срока действия токена WB осталось <b>{days_left}</b> дней!\nНеобходимо обновить токен."
            send_telegram_message(warning_msg)
            logger.warning(f"Токен WB истекает через {days_left} дней")
        elif days_left <= 0:
            error_msg = "❌ <b>ТОКЕН WB ИСТЕК!</b>\nНемедленно обновите токен для продолжения работы."
            send_telegram_message(error_msg)
            logger.error("Токен WB истёк")
        else:
            logger.info(f"Токен WB действителен ещё {days_left} дней")

        return days_left
    except Exception as e:
        logger.error(f"Ошибка проверки токена: {e}")
        return None


# ============ СИСТЕМА ПОДТВЕРЖДЕНИЯ ============
confirmation_events = {}
current_step_id = 0


def wait_for_confirmation(step_id: str, description: str) -> bool:
    # В рабочем режиме всегда возвращаем True, но с задержкой для стабильности
    if CURRENT_MODE != "test":
        adaptive_sleep(1.5)
        return True

    print(f"\n🔍 ТРЕБУЕТСЯ ПОДТВЕРЖДЕНИЕ:")
    print(f"   Действие: {description}")
    print(f"   Нажмите 'Подтвердить ✅' в Telegram\n")

    global current_step_id
    current_step_id += 1
    step_key = f"step_{current_step_id}"
    confirmation_events[step_key] = Event()

    keyboard = {
        "inline_keyboard": [
            [{"text": "Подтвердить ✅", "callback_data": f"confirm_{step_key}"}],
            [{"text": "Отмена ❌", "callback_data": "cancel_process"}]
        ]
    }

    try:
        payload = {
            "chat_id": GROUP_CHAT_ID,
            "text": f"🔍 <b>Тестовый режим</b>\n<b>Действие:</b> {description}\nУспешно выполнено?",
            "parse_mode": "HTML",
            "reply_markup": keyboard
        }
        session = create_session()
        resp = session.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json=payload,
            timeout=20,
            verify=False
        )
        if resp.status_code == 200:
            logger.info(f"✅ Сообщение с кнопками отправлено: {description}")
        else:
            logger.error(f"❌ Ошибка отправки кнопок: {resp.status_code} - {resp.text}")
        return True
    except Exception as e:
        logger.error(f"❌ Исключение при отправке кнопок: {e}")
        return True

    logger.info(f"Ожидаю подтверждения: {description}")
    result = confirmation_events[step_key].wait(timeout=300)
    del confirmation_events[step_key]

    if result:
        print(f"✅ Подтверждено: {description}")
    else:
        print(f"⏰ Таймаут подтверждения: {description}")

    return result


def confirm_step(step_key: str):
    if step_key in confirmation_events:
        confirmation_events[step_key].set()
        logger.info(f"Действие подтверждено: {step_key}")


# ============ ОПТИМИЗИРОВАННАЯ ОТПРАВКА TELEGRAM ============
def send_telegram_message(text: str, reply_markup=None, important_only=False):
    """
    Отправляет сообщение в Telegram
    important_only=True — сообщение отправляется только в тестовом режиме
    """
    if important_only and CURRENT_MODE == "production":
        return True

    payload = {
        "chat_id": GROUP_CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup

    for attempt in range(5):
        try:
            session = create_session()
            resp = session.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json=payload,
                timeout=20,
                verify=False
            )
            if resp.status_code == 200:
                logger.info(f"✅ Сообщение отправлено: {text[:50]}...")
                return True
        except Exception as e:
            logger.error(f"Попытка {attempt + 1} не удалась: {e}")
            if attempt < 4:
                adaptive_sleep(2 ** attempt)
    else:
        print(f"❌ TELEGRAM: {text}")
        logger.error(f"Не удалось отправить сообщение: {text}")
        return False


def send_telegram_private_message(user_id: int, text: str, reply_markup=None):
    """Отправляет личное сообщение пользователю с обработкой ошибок 403"""
    try:
        payload = {
            "chat_id": user_id,
            "text": text,
            "parse_mode": "HTML"
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup

        session = create_session()
        resp = session.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json=payload,
            timeout=20,
            verify=False
        )
        if resp.status_code == 200:
            return True
        elif resp.status_code == 403:
            # Пользователь не начал диалог с ботом
            logger.warning(
                f"Невозможно отправить сообщение пользователю {user_id}: бот заблокирован или пользователь не написал первым")
            return False
        else:
            logger.error(f"Ошибка отправки ЛС: статус {resp.status_code}, ответ: {resp.text}")
            return False
    except Exception as e:
        logger.error(f"Исключение при отправке ЛС: {e}")
        return False


def send_telegram_document(file_path: Path):
    max_retries = 5
    for attempt in range(max_retries):
        try:
            session = create_session()
            with open(file_path, "rb") as f:
                files = {"document": f}
                data = {"chat_id": GROUP_CHAT_ID}
                resp = session.post(
                    f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument",
                    data=data,
                    files=files,
                    timeout=30,
                    verify=False
                )
            if resp.status_code == 200:
                logger.info(f"✅ Документ отправлен: {file_path.name}")
                return True
        except Exception as e:
            logger.error(f"Попытка отправки файла {attempt + 1}: {e}")
            if attempt < max_retries - 1:
                adaptive_sleep(2 ** attempt)
    else:
        print(f"❌ TELEGRAM FILE: {file_path.name}")
        logger.error(f"Не удалось отправить файл: {file_path}")
        return False


# ============ ПРИНУДИТЕЛЬНОЕ ОБНОВЛЕНИЕ СТРАНИЦЫ ============
def force_refresh_page():
    """Принудительно обновляет страницу для обхода кэша"""
    try:
        import pyautogui
        pyautogui.hotkey('ctrl', 'f5')
        adaptive_sleep(4)
        logger.info("Страница принудительно обновлена (Ctrl+F5)")
        return True
    except Exception as e:
        logger.error(f"Ошибка принудительного обновления: {e}")
        return False


# ============ ФУНКЦИИ УПРАВЛЕНИЯ МЫШЬЮ ============
def smooth_move_to_element(element_location, duration=1.0):
    """Плавное движение мыши к элементу (ускорено)"""
    if pyautogui is None:
        logger.error("pyautogui не установлен")
        return False

    try:
        if isinstance(element_location, tuple) and len(element_location) == 4:
            target_x = element_location[0] + element_location[2] // 2
            target_y = element_location[1] + element_location[3] // 2
        else:
            target_x = element_location.left + element_location.width // 2
            target_y = element_location.top + element_location.height // 2

        current_x, current_y = pyautogui.position()
        screen_width, screen_height = pyautogui.size()
        target_x = max(10, min(target_x, screen_width - 10))
        target_y = max(10, min(target_y, screen_height - 10))

        steps = int(duration * 10)
        for i in range(steps + 1):
            t = i / steps
            eased_t = t * t * (3 - 2 * t)
            new_x = current_x + (target_x - current_x) * eased_t
            new_y = current_y + (target_y - current_y) * eased_t
            pyautogui.moveTo(new_x, new_y, duration=0.01)
            adaptive_sleep(0.01)
        return True
    except Exception as e:
        logger.error(f"Ошибка плавного движения: {e}")
        return False


def find_and_click_element(image_path, description, confidence=0.8, timeout=10, scroll_if_needed=False):
    """Находит и плавно кликает по элементу (ускорено)"""
    if pyautogui is None:
        logger.error("pyautogui не установлен")
        send_telegram_message("❌ Ошибка: pyautogui не установлен", important_only=True)
        return False

    try:
        send_telegram_message(f"🔍 Ищу элемент: {description}...", important_only=True)
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                location = pyautogui.locateOnScreen(str(image_path), confidence=confidence)
                if location:
                    logger.info(f"✅ Найден элемент: {description}")
                    send_telegram_message(f"🖱️ Двигаю мышь к элементу: {description}...", important_only=True)
                    if smooth_move_to_element(location, duration=1.0):
                        adaptive_sleep(0.5)
                        if not wait_for_confirmation(f"move_to_{description}",
                                                     f"Мышь успешно наведена на '{description}'"):
                            return False
                        send_telegram_message(f"🖱️ Кликаю по элементу: {description}...", important_only=True)
                        pyautogui.click()
                        logger.info(f"🖱️ Кликнули по: {description}")
                        adaptive_sleep(1.0)
                        if not wait_for_confirmation(f"click_{description}", f"Успешно кликнули по '{description}'"):
                            return False
                        return True
                    else:
                        pyautogui.click(location)
                        logger.info(f"🖱️ Кликнули по: {description} (быстрый клик)")
                        if not wait_for_confirmation(f"quick_click_{description}",
                                                     f"Успешно кликнули по '{description}'"):
                            return False
                        return True
            except Exception:
                pass
            adaptive_sleep(0.5)

        if scroll_if_needed:
            send_telegram_message(f"🔄 Элемент '{description}' не найден, прокручиваю страницу...", important_only=True)
            pyautogui.scroll(-500)
            adaptive_sleep(1.0)
            location = pyautogui.locateOnScreen(str(image_path), confidence=confidence)
            if location:
                logger.info(f"✅ Найден элемент после прокрутки: {description}")
                if smooth_move_to_element(location, duration=1.0):
                    adaptive_sleep(0.5)
                    pyautogui.click()
                    adaptive_sleep(1.0)
                    return True

        logger.warning(f"⚠️ Не найден элемент: {description}")
        send_telegram_message(f"❌ Не найден элемент: {description}", important_only=True)
        return False
    except Exception as e:
        logger.error(f"Ошибка поиска элемента: {e}")
        return False


def wait_for_element(image_path, timeout=10, confidence=0.8):
    """Ждёт появления элемента на экране (ускорено)"""
    if pyautogui is None:
        return None
    try:
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                location = pyautogui.locateOnScreen(str(image_path), confidence=confidence)
                if location:
                    return pyautogui.center(location)
            except:
                pass
            adaptive_sleep(0.5)
        return None
    except Exception:
        return None


# ============ АКТИВАЦИЯ ОСНОВНОЙ ВКЛАДКИ ============
def activate_main_tab():
    """Активирует основную вкладку Wildberries"""
    try:
        if pyautogui is None:
            logger.error("pyautogui не установлен")
            return False

        target_x = 539
        target_y = 649

        send_telegram_message(f"🖱️ Активирую основную вкладку ({target_x}, {target_y})...", important_only=True)
        current_x, current_y = pyautogui.position()
        steps = 10
        for i in range(steps + 1):
            t = i / steps
            eased_t = t * t * (3 - 2 * t)
            new_x = current_x + (target_x - current_x) * eased_t
            new_y = current_y + (target_y - current_y) * eased_t
            pyautogui.moveTo(new_x, new_y, duration=0.01)
            adaptive_sleep(0.01)

        adaptive_sleep(0.3)
        pyautogui.click()
        adaptive_sleep(1.0)
        logger.info(f"✅ Основная вкладка активирована ({target_x}, {target_y})")
        return True
    except Exception as e:
        logger.error(f"Ошибка активации основной вкладки: {e}")
        return False


# ============ МЕДЛЕННАЯ ПЕЧАТЬ ЧИСЕЛ ============
def type_slowly_numbers(text: str, delay: float = 0.3):
    """Печатает текст медленно, символ за символом (только цифры и подчёркивания)"""
    try:
        import pyautogui
        for char in str(text):
            if char.isdigit() or char == '_':
                pyautogui.write(char)
                adaptive_sleep(delay)
            else:
                logger.warning(f"Пропущен недопустимый символ: {char}")
        logger.info(f"✅ Медленный ввод завершён: {text}")
    except Exception as e:
        logger.error(f"Ошибка медленного ввода: {e}")


# ============ ЗАКРЫТИЕ ВКЛАДКИ ПО КООРДИНАТАМ КРЕСТИКА ============
def close_download_tab_by_coordinates():
    """Закрывает вкладку скачивания по точным координатам крестика (X=501, Y=26)"""
    try:
        if pyautogui is None:
            logger.error("pyautogui не установлен")
            return False

        close_x, close_y = 501, 26

        send_telegram_message(f"🖱️ Навожу мышь на крестик закрытия ({close_x}, {close_y})...", important_only=True)
        current_x, current_y = pyautogui.position()
        steps = 10
        for i in range(steps + 1):
            t = i / steps
            eased_t = t * t * (3 - 2 * t)
            new_x = current_x + (close_x - current_x) * eased_t
            new_y = current_y + (close_y - current_y) * eased_t
            pyautogui.moveTo(new_x, new_y, duration=0.01)
            adaptive_sleep(0.01)

        adaptive_sleep(0.3)
        pyautogui.click()
        adaptive_sleep(1.0)
        logger.info(f"✅ Вкладка скачивания закрыта по координатам ({close_x}, {close_y})")
        return True
    except Exception as e:
        logger.error(f"Ошибка закрытия вкладки по координатам: {e}")
        return False


# ============ СКАЧИВАНИЕ СТИКЕРА С ЦИФРОВЫМ ИМЕНЕМ ============
def download_sticker_with_proper_name(filename: str, description: str):
    """Скачивает стикер с цифровым именем"""
    try:
        if not find_and_click_element(SCRIPT_DIR / "download_button.png", f"Кнопка 'Скачать' для {description}",
                                      timeout=8):
            return False

        adaptive_sleep(1.5)
        actual_filename = str(filename).strip()
        send_telegram_message(f"📝 Печатаю имя файла: '{actual_filename}'...", important_only=True)
        logger.info(f"DEBUG: Печатаю имя файла: '{actual_filename}'")

        if not actual_filename:
            logger.error("Пустое имя файла!")
            return False

        type_slowly_numbers(actual_filename, delay=0.3)
        adaptive_sleep(0.5)

        import pyautogui
        pyautogui.press('enter')
        adaptive_sleep(2.0)

        send_telegram_message("🔍 Жду ваш скриншот успешного скачивания...", important_only=True)
        success_found = wait_for_element(SCRIPT_DIR / "success_download_message.png", timeout=8)
        if success_found:
            send_telegram_message(f"✅ {description} '{actual_filename}' успешно скачан", important_only=True)
        else:
            send_telegram_message(f"❌ Не найден ваш скриншот успешного скачивания: '{actual_filename}'",
                                  important_only=True)
            return False

        adaptive_sleep(1.5)

        if not activate_main_tab():
            logger.warning("Не удалось активировать основную вкладку")

        adaptive_sleep(1.5)

        if not close_download_tab_by_coordinates():
            logger.warning("Не удалось закрыть вкладку скачивания по координатам")

        adaptive_sleep(1.5)
        return True
    except Exception as e:
        logger.error(f"Ошибка скачивания стикера {filename}: {e}")
        return False


# ============ УНИВЕРСАЛЬНЫЙ ПОИСК CHROME В ПАНЕЛИ ЗАДАЧ ============
def find_chrome_icon_in_taskbar():
    """Ищет иконку Chrome ТОЛЬКО в панели задач с точностью 0.9"""
    if pyautogui is None:
        logger.error("pyautogui не установлен")
        return None

    try:
        chrome_icon_path = SCRIPT_DIR / "chrome_icon.png"
        if not chrome_icon_path.exists():
            logger.error("Файл chrome_icon.png не найден")
            return None

        screen_width, screen_height = pyautogui.size()
        taskbar_region = (0, screen_height - 60, screen_width, 60)

        send_telegram_message(f"🔍 Ищу иконку Chrome в панели задач (точность 0.9)...", important_only=True)
        start_time = time.time()
        while time.time() - start_time < 10:
            try:
                location = pyautogui.locateOnScreen(
                    str(chrome_icon_path),
                    confidence=0.9,
                    region=taskbar_region
                )
                if location:
                    logger.info(f"✅ Иконка Chrome найдена в панели задач")
                    return location
            except Exception:
                pass
            adaptive_sleep(0.5)

        logger.warning("Иконка Chrome не найдена в панели задач")
        return None
    except Exception as e:
        logger.error(f"Ошибка поиска в панели задач: {e}")
        return None


def click_chrome_by_coordinates():
    """Кликает по Chrome по координатам как fallback"""
    if pyautogui is None:
        logger.error("pyautogui не установлен")
        return False

    try:
        screen_width, screen_height = pyautogui.size()
        chrome_x = min(300, screen_width // 4)
        chrome_y = screen_height - 10
        chrome_x = max(10, min(chrome_x, screen_width - 10))
        chrome_y = max(10, min(chrome_y, screen_height - 10))

        send_telegram_message(f"🖱️ Кликаю по координатам Chrome ({chrome_x}, {chrome_y})...", important_only=True)
        current_x, current_y = pyautogui.position()
        steps = 20
        for i in range(steps + 1):
            t = i / steps
            eased_t = t * t * (3 - 2 * t)
            new_x = current_x + (chrome_x - current_x) * eased_t
            new_y = current_y + (chrome_y - current_y) * eased_t
            new_x = max(10, min(new_x, screen_width - 10))
            new_y = max(10, min(new_y, screen_height - 10))
            pyautogui.moveTo(new_x, new_y, duration=0.01)
            adaptive_sleep(0.01)

        adaptive_sleep(0.5)
        pyautogui.click()
        adaptive_sleep(2.0)
        return True
    except Exception as e:
        logger.error(f"Ошибка клика по координатам: {e}")
        return False


# ============ НАДЁЖНОЕ СВОРАЧИВАНИЕ ОКОН ============
def minimize_all_windows():
    """Сворачиваем все окна через Windows API"""
    try:
        user32 = ctypes.windll.user32
        shell32 = ctypes.windll.shell32

        try:
            send_telegram_message("🖱️ Сворачиваю все окна (ShowDesktop)...", important_only=True)
            shell32.SHMinimizeAll()
            adaptive_sleep(1.5)
            logger.info("🖥️ Все окна свёрнуты (метод 1)")
            if not wait_for_confirmation("minimize_windows", "Все окна успешно свёрнуты"):
                return False
            return True
        except Exception as e1:
            logger.error(f"Метод 1 не сработал: {e1}")
            try:
                send_telegram_message("🖱️ Сворачиваю все окна (Win+D эмуляция)...", important_only=True)
                user32.keybd_event(0x5B, 0, 0, 0)
                user32.keybd_event(0x44, 0, 0, 0)
                adaptive_sleep(0.1)
                user32.keybd_event(0x44, 0, 2, 0)
                user32.keybd_event(0x5B, 0, 2, 0)
                adaptive_sleep(1.5)
                logger.info("🖥️ Все окна свёрнуты (метод 2)")
                if not wait_for_confirmation("minimize_windows", "Все окна успешно свёрнуты"):
                    return False
                return True
            except Exception as e2:
                error_msg = f"❌ Методы сворачивания не сработали:\n{e1}\n{e2}"
                send_telegram_message(error_msg, important_only=True)
                logger.error("Не удалось свернуть окна")
                return False
    except ImportError:
        send_telegram_message("❌ Ошибка: ctypes не доступен", important_only=True)
        return False


# ============ API КЛИЕНТ ============
class WBApiClient:
    def __init__(self, token: str):
        self.token = token
        self.base_url = "https://marketplace-api.wildberries.ru"
        self.headers = {"Authorization": token}
        self.session = create_session()

    def get_new_orders(self) -> list:
        max_retries = 3
        for attempt in range(max_retries):
            try:
                logger.info(
                    f"DEBUG: Запрашиваю новые заказы из {self.base_url}/api/v3/orders/new (попытка {attempt + 1})")
                resp = self.session.get(
                    f"{self.base_url}/api/v3/orders/new",
                    headers=self.headers,
                    timeout=45
                )
                logger.info(f"DEBUG: Статус ответа: {resp.status_code}")
                if resp.status_code == 200:
                    data = resp.json()
                    orders = data.get("orders", [])
                    logger.info(f"DEBUG: Получено {len(orders)} заказов")
                    return orders
                elif resp.status_code == 429:
                    logger.warning(f"DEBUG: Слишком много запросов (429), жду 30 сек...")
                    adaptive_sleep(30)
                    continue
                else:
                    logger.error(f"DEBUG: Ошибка API - статус {resp.status_code}, текст: {resp.text}")
                    if attempt < max_retries - 1:
                        adaptive_sleep(10 * (attempt + 1))
                        continue
            except requests.exceptions.Timeout:
                logger.error(f"DEBUG: Таймаут при получении заказов (попытка {attempt + 1})")
                if attempt < max_retries - 1:
                    adaptive_sleep(15 * (attempt + 1))
                    continue
            except Exception as e:
                logger.error(f"DEBUG: Исключение при получении заказов (попытка {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    adaptive_sleep(10 * (attempt + 1))
                    continue
        logger.error("DEBUG: Все попытки получения заказов исчерпаны")
        return []

    def create_supply(self, name: str) -> str:
        max_retries = 3
        for attempt in range(max_retries):
            try:
                resp = self.session.post(
                    f"{self.base_url}/api/v3/supplies",
                    json={"name": name},
                    headers=self.headers,
                    timeout=45
                )
                result = resp.json()
                supply_id = result["id"]
                logger.info(f"DEBUG: Создана поставка {supply_id}")
                return supply_id
            except requests.exceptions.Timeout:
                logger.error(f"DEBUG: Таймаут при создании поставки (попытка {attempt + 1})")
                if attempt < max_retries - 1:
                    adaptive_sleep(10 * (attempt + 1))
                    continue
            except Exception as e:
                logger.error(f"DEBUG: Ошибка создания поставки (попытка {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    adaptive_sleep(10 * (attempt + 1))
                    continue
        raise Exception("Не удалось создать поставку после всех попыток")

    def add_orders_to_supply(self, supply_id: str, order_ids: list):
        max_retries = 3
        for attempt in range(max_retries):
            try:
                url = f"{self.base_url}/api/marketplace/v3/supplies/{supply_id}/orders"
                self.session.patch(url, json={"orders": order_ids}, headers=self.headers, timeout=45)
                return
            except requests.exceptions.Timeout:
                logger.error(f"DEBUG: Таймаут при добавлении заказов (попытка {attempt + 1})")
                if attempt < max_retries - 1:
                    adaptive_sleep(10 * (attempt + 1))
                    continue
            except Exception as e:
                logger.error(f"DEBUG: Ошибка добавления заказов (попытка {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    adaptive_sleep(10 * (attempt + 1))
                    continue
        raise Exception("Не удалось добавить заказы после всех попыток")

    def deliver_supply(self, supply_id: str):
        max_retries = 3
        for attempt in range(max_retries):
            try:
                url = f"{self.base_url}/api/v3/supplies/{supply_id}/deliver"
                self.session.patch(url, headers=self.headers, timeout=45)
                return
            except requests.exceptions.Timeout:
                logger.error(f"DEBUG: Таймаут при передаче поставки (попытка {attempt + 1})")
                if attempt < max_retries - 1:
                    adaptive_sleep(10 * (attempt + 1))
                    continue
            except Exception as e:
                logger.error(f"DEBUG: Ошибка передачи поставки (попытка {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    adaptive_sleep(10 * (attempt + 1))
                    continue
        raise Exception("Не удалось передать поставку после всех попыток")


def switch_to_wb_tab():
    """Переключается на вкладку Wildberries (только поиск)"""
    max_attempts = 3
    for attempt in range(max_attempts):
        if PROCESS_CANCELLED:
            logger.info("Остановка: процесс отменён")
            return False

        if wait_for_element(SCRIPT_DIR / "ip_vashchuk.png", timeout=5):
            logger.info("✅ Уже на вкладке Wildberries")
            return True

        send_telegram_message(f"🔍 Попытка {attempt + 1}: Ищу вкладку Wildberries...", important_only=True)
        wb_tab_found = find_and_click_element(
            SCRIPT_DIR / "wb_tab_in_chrome.png",
            "Вкладка Wildberries в Chrome",
            timeout=8
        )
        if wb_tab_found:
            adaptive_sleep(3)
            if wait_for_element(SCRIPT_DIR / "ip_vashchuk.png", timeout=5):
                send_telegram_message("✅ Переключился на вкладку Wildberries", important_only=True)
                return True

        if attempt < max_attempts - 1:
            try:
                pyautogui.hotkey('alt', 'tab')
                adaptive_sleep(2)
            except:
                pass

    send_telegram_message("❌ Не удалось найти вкладку Wildberries", important_only=True)
    return False


def process_single_order(order: dict, order_index: int, session_dir: Path):
    """Обрабатывает один заказ с надёжным механизмом повторных попыток"""
    try:
        if PROCESS_CANCELLED:
            return []

        order_number = order_index + 1
        order_id = order["id"]
        quantity = order.get("quantity", 1)

        if order_id in PROCESSED_ORDERS:
            logger.info(f"Пропускаю уже обработанный заказ #{order_id}")
            return []

        supply_name = f"postavka_{order_number}_{order_id}"
        client = WBApiClient(WB_TOKEN)
        supply_id = client.create_supply(supply_name)
        client.add_orders_to_supply(supply_id, [order_id])

        send_telegram_message(f"📦 Создана поставка {supply_id} для заказа #{order_id}")
        if not wait_for_confirmation(f"create_supply_{order_id}", f"Поставка {supply_id} создана"):
            return []

        if PROCESS_CANCELLED:
            return []

        if not find_and_click_element(SCRIPT_DIR / "on_assembly_tab.png", "Кнопка 'На сборке'", timeout=8):
            return []

        adaptive_sleep(2)

        if PROCESS_CANCELLED:
            return []

        send_telegram_message("🖱️ Кликаю по координатам поставки (539, 649)...")
        target_x, target_y = 539, 649
        current_x, current_y = pyautogui.position()
        steps = 20
        for i in range(steps + 1):
            t = i / steps
            eased_t = t * t * (3 - 2 * t)
            new_x = current_x + (target_x - current_x) * eased_t
            new_y = current_y + (target_y - current_y) * eased_t
            pyautogui.moveTo(new_x, new_y, duration=0.01)
            adaptive_sleep(0.01)

        adaptive_sleep(0.5)
        pyautogui.click()
        adaptive_sleep(3.0)

        if PROCESS_CANCELLED:
            return []

        if not find_and_click_element(SCRIPT_DIR / "packaging_for_pvz.png", "Кнопка 'Упаковка для ПВЗ'", timeout=8):
            return []

        adaptive_sleep(2)

        if PROCESS_CANCELLED:
            return []

        create_box_found = False
        max_attempts = 5
        slow_mode = False

        for attempt in range(max_attempts):
            if PROCESS_CANCELLED:
                return []

            if attempt >= 3 and not slow_mode:
                send_telegram_message("🐢 Пробую снизить скорость обработки...")
                slow_mode = True

            send_telegram_message(f"🔍 Попытка {attempt + 1}: Ищу кнопку 'Создать коробку'...")
            create_box_found = find_and_click_element(
                SCRIPT_DIR / "create_box_button.png",
                "Кнопка 'Создать коробку'",
                scroll_if_needed=True,
                timeout=12 if slow_mode else 8
            )
            if create_box_found:
                break
            else:
                send_telegram_message("🔄 Прокручиваю страницу вверх...")
                pyautogui.scroll(500)
                adaptive_sleep(1.5)
                send_telegram_message("⬅️ Ищу кнопку 'Назад'...")
                back_found = find_and_click_element(
                    SCRIPT_DIR / "back_button.png",
                    "Кнопка 'Назад'",
                    timeout=8
                )
                if not back_found:
                    send_telegram_message("⚠️ Кнопка 'Назад' не найдена — пробую кликнуть по координатам")
                    current_x, current_y = pyautogui.position()
                    steps = 10
                    for i in range(steps + 1):
                        t = i / steps
                        eased_t = t * t * (3 - 2 * t)
                        new_x, new_y = 501, 26
                        pyautogui.moveTo(new_x, new_y, duration=0.01)
                        adaptive_sleep(0.01)
                    adaptive_sleep(0.3)
                    pyautogui.click()
                    adaptive_sleep(1.0)

                adaptive_sleep(3)
                send_telegram_message("🖱️ Снова кликаю по координатам поставки (539, 649)...")
                current_x, current_y = pyautogui.position()
                steps = 20
                for i in range(steps + 1):
                    t = i / steps
                    eased_t = t * t * (3 - 2 * t)
                    new_x = current_x + (target_x - current_x) * eased_t
                    new_y = current_y + (target_y - current_y) * eased_t
                    pyautogui.moveTo(new_x, new_y, duration=0.01)
                    adaptive_sleep(0.01)
                adaptive_sleep(0.5)
                pyautogui.click()
                adaptive_sleep(4 if slow_mode else 3)

                if not find_and_click_element(SCRIPT_DIR / "packaging_for_pvz.png", "Кнопка 'Упаковка для ПВЗ'",
                                              timeout=10 if slow_mode else 8):
                    send_telegram_message("❌ Не удалось вернуться в 'Упаковка для ПВЗ'")
                    continue

        if not create_box_found:
            send_telegram_message(
                f"❌ После {max_attempts} попыток не найдена кнопка 'Создать коробку'. Возможно, поставка пустая.")
            send_telegram_message(f"📋 Требуется вручную проверить поставку {supply_id} для заказа #{order_id}")
            send_telegram_message("⬅️ Выходим из поставки...")
            find_and_click_element(SCRIPT_DIR / "back_button.png", "Кнопка 'Назад'", timeout=8)
            adaptive_sleep(3)
            send_telegram_message("🏠 Переходим в раздел 'Новые'...")
            if not find_and_click_element(SCRIPT_DIR / "new_orders_tab.png", "Вкладка 'Новые'", timeout=8):
                logger.warning("Не вернулись в 'Новые'")
            adaptive_sleep(3)
            return []

        adaptive_sleep(4 if slow_mode else 3)

        if PROCESS_CANCELLED:
            return []

        if not find_and_click_element(SCRIPT_DIR / "printer_icon.png", "Значок принтера", timeout=8):
            return []

        adaptive_sleep(2)

        if PROCESS_CANCELLED:
            return []

        if PROCESS_CANCELLED:
            return []

        mp_filename = f"{order_number}_1"
        send_telegram_message(f"🖨️ Создаю стикер коробки: '{mp_filename}'")
        logger.info(f"DEBUG: Имя файла коробки: '{mp_filename}'")

        if not force_refresh_page():
            send_telegram_message("⚠️ Не удалось обновить страницу перед скачиванием стикера коробки")

        if not download_sticker_with_proper_name(mp_filename, "MP-sticker (коробка)"):
            return []

        adaptive_sleep(1.5)

        if PROCESS_CANCELLED:
            return []

        if not find_and_click_element(SCRIPT_DIR / "list_orders_button.png", "Кнопка 'Список заказов'", timeout=8):
            return []

        adaptive_sleep(2)
        if not wait_for_element(SCRIPT_DIR / "ip_vashchuk.png", timeout=5):
            send_telegram_message("❌ Не перешли в 'Список заказов'", important_only=True)
            return []

        downloaded_files = [session_dir / f"{mp_filename}.pdf"]
        sticker_names = [mp_filename]

        for item_num in range(quantity):
            if PROCESS_CANCELLED:
                return []

            file_suffix = item_num + 2
            product_filename = f"{order_number}_{file_suffix}"
            sticker_names.append(product_filename)

            send_telegram_message(f"🖨️ Создаю стикер товара: '{product_filename}'")
            logger.info(f"DEBUG: Имя файла стикера товара: '{product_filename}'")

            if not force_refresh_page():
                send_telegram_message(
                    f"⚠️ Не удалось обновить страницу перед скачиванием стикера товара {product_filename}")

            if not find_and_click_element(SCRIPT_DIR / "three_dots_vertical.png", f"Три точки товара {item_num + 1}",
                                          timeout=8):
                if item_num == 0:
                    break
                else:
                    continue

            adaptive_sleep(1.5)

            if PROCESS_CANCELLED:
                return []

            if not find_and_click_element(SCRIPT_DIR / "print_sticker_menu.png", "Пункт 'Печать стикера'", timeout=8):
                continue

            adaptive_sleep(2)

            if PROCESS_CANCELLED:
                return []

            if not download_sticker_with_proper_name(product_filename, f"Стикер товара"):
                continue

            adaptive_sleep(1.5)
            downloaded_files.append(session_dir / f"{product_filename}.pdf")

        if PROCESS_CANCELLED:
            return []

        try:
            client.deliver_supply(supply_id)
            send_telegram_message(f"✅ Заказ #{order_id} передан через API")
        except Exception as e:
            logger.warning(f"API недоступен для #{order_id}: {e}")
            if find_and_click_element(SCRIPT_DIR / "deliver_button.png", "Кнопка 'Передать в доставку'", timeout=8):
                adaptive_sleep(1.5)
                if PROCESS_CANCELLED:
                    return []
                if find_and_click_element(SCRIPT_DIR / "confirm_deliver_button.png", "Кнопка подтверждения", timeout=8):
                    send_telegram_message(f"✅ Заказ #{order_id} передан через интерфейс")
                    send_telegram_message("🔍 Жду ваш скриншот успешной передачи...", important_only=True)
                    success_found = wait_for_element(SCRIPT_DIR / "success_delivery_message.png", timeout=10)
                    if success_found:
                        send_telegram_message("✅ Подтверждено: поставка отправлена", important_only=True)
                    else:
                        send_telegram_message("❌ Не найден ваш скриншот успешной передачи", important_only=True)
                        return False
                else:
                    send_telegram_message("❌ Не найдена кнопка подтверждения", important_only=True)
            else:
                send_telegram_message(f"❌ Не удалось передать заказ #{order_id}", important_only=True)
                return []

        if PROCESS_CANCELLED:
            return []

        send_telegram_message("⬅️ Нажимаю кнопку 'Назад'...", important_only=True)
        if not find_and_click_element(SCRIPT_DIR / "back_button.png", "Кнопка 'Назад'", timeout=8):
            send_telegram_message("⚠️ Кнопка 'Назад' не найдена, продолжаю без неё", important_only=True)

        adaptive_sleep(2)
        if not find_and_click_element(SCRIPT_DIR / "new_orders_tab.png", "Вкладка 'Новые'", timeout=8):
            logger.warning("Не вернулись в 'Новые'")

        adaptive_sleep(2)
        send_telegram_message(f"✅ Обработан заказ #{order_id} ({', '.join(sticker_names)})")

        existing_files = [f for f in downloaded_files if f.exists() and f.stat().st_size > 10]
        if existing_files:
            PROCESSED_ORDERS.add(order_id)
            return existing_files
    except Exception as e:
        logger.error(f"Ошибка обработки заказа: {e}")
        return []


# ============ СОЗДАНИЕ ЗАГОЛОВОЧНОЙ СТРАНИЦЫ (СТРЕЛКА ВВЕРХ ↑ БЕЗ ТЕКСТА) ============
def create_header_page(output_path):
    """Создаёт заголовочную страницу в формате стикера (75×120 мм) с вертикальной стрелкой ВВЕРХ (↑) БЕЗ ТЕКСТА"""
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.units import mm

        # Размеры стикера: 75×120 мм
        sticker_width = 75 * mm
        sticker_height = 120 * mm

        c = canvas.Canvas(str(output_path), pagesize=(sticker_width, sticker_height))

        # === СТРЕЛКА ВВЕРХ (↑) БЕЗ ТЕКСТА ===
        arrow_x = sticker_width / 2  # Центр по горизонтали
        arrow_bottom = 30 * mm
        arrow_top = 90 * mm

        c.setLineWidth(3)
        # Ствол стрелки
        c.line(arrow_x, arrow_bottom, arrow_x, arrow_top)
        # Наконечник стрелки (левая часть)
        c.line(arrow_x, arrow_top, arrow_x - 8, arrow_top - 8)
        # Наконечник стрелки (правая часть)
        c.line(arrow_x, arrow_top, arrow_x + 8, arrow_top - 8)

        c.save()
        logger.info(f"✅ Создана заголовочная страница (75×120 мм): {output_path.name}")
        return True
    except Exception as e:
        logger.error(f"Ошибка создания заголовочной страницы: {e}")
        return False


# ============ ОБЪЕДИНЕНИЕ PDF ============
def merge_pdfs_by_order(all_stickers, session_dir):
    """Объединяет PDF-файлы с заголовочной страницей"""
    try:
        from pypdf import PdfWriter, PdfReader

        if not all_stickers:
            return None

        def sort_key(filename):
            name = filename.stem
            parts = name.split('_')
            if len(parts) == 2:
                order_num = int(parts[0])
                sticker_num = int(parts[1])
                return (order_num, sticker_num)
            return (999, 999)

        sorted_files = sorted(all_stickers, key=sort_key)

        header_path = session_dir / "header_temp.pdf"
        if not create_header_page(header_path):
            logger.warning("Не удалось создать заголовочную страницу")
            header_path = None

        merger = PdfWriter()

        if header_path and header_path.exists():
            try:
                with open(header_path, 'rb') as f:
                    reader = PdfReader(f)
                    for page in reader.pages:
                        merger.add_page(page)
            except Exception as e:
                logger.warning(f"Не удалось добавить заголовочную страницу: {e}")

        for pdf_file in sorted_files:
            if pdf_file.exists() and pdf_file.stat().st_size > 10:
                try:
                    with open(pdf_file, 'rb') as f:
                        reader = PdfReader(f)
                        for page in reader.pages:
                            merger.add_page(page)
                except Exception as e:
                    logger.warning(f"Не удалось добавить страницу из {pdf_file}: {e}")
                    continue

        if len(merger.pages) > 0:
            merged_path = session_dir / "все_стикеры_объединенные.pdf"
            with open(merged_path, 'wb') as output_file:
                merger.write(output_file)

            if header_path and header_path.exists():
                try:
                    header_path.unlink()
                except:
                    pass

            logger.info(f"✅ Объединено {len(sorted_files)} файлов в {merged_path.name} (с заголовком)")
            return merged_path
        else:
            logger.warning("Нет PDF-файлов для объединения")
            return None
    except ImportError:
        logger.error("pypdf не установлен, пропускаю объединение")
        return None
    except Exception as e:
        logger.error(f"Ошибка объединения PDF: {e}")
        return None


# ============ НАДЁЖНАЯ ОТПРАВКА СТИКЕРОВ ============
def send_stickers_in_batches(pdf_files, batch_size=5):
    """Отправляет стикеры пакетами с проверкой полноты отправки"""
    sent_count = 0
    total_files = len(pdf_files)

    if total_files == 0:
        return 0

    for i in range(0, total_files, batch_size):
        batch = pdf_files[i:i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (total_files + batch_size - 1) // batch_size

        send_telegram_message(f"📤 Пакет {batch_num}/{total_batches}: отправляю {len(batch)} файлов...")
        batch_sent = 0

        for pdf_file in batch:
            max_retries = 3
            file_sent = False

            for attempt in range(max_retries):
                try:
                    if pdf_file.exists() and pdf_file.stat().st_size > 10:
                        if send_telegram_document(pdf_file):
                            batch_sent += 1
                            sent_count += 1
                            file_sent = True
                            logger.info(f"✅ Отправлен: {pdf_file.name}")
                            adaptive_sleep(1.0)
                            break
                    else:
                        logger.warning(f"Попытка {attempt + 1}: Не удалось отправить {pdf_file.name}")
                except Exception as e:
                    logger.error(f"Ошибка отправки {pdf_file.name} (попытка {attempt + 1}): {e}")
                    if attempt < max_retries - 1:
                        adaptive_sleep(2 ** attempt)

            if not file_sent:
                send_telegram_message(f"⚠️ Файл {pdf_file.name} не был отправлен после {max_retries} попыток")

        send_telegram_message(f"✅ Пакет {batch_num}/{total_batches} завершён ({batch_sent}/{len(batch)})")
        adaptive_sleep(2)

    if sent_count != total_files:
        send_telegram_message(
            f"⚠️ <b>ВНИМАНИЕ!</b>\n"
            f"Должно быть отправлено: {total_files} файлов\n"
            f"Успешно отправлено: {sent_count} файлов\n"
            f"Пропущено: {total_files - sent_count} файлов\n"
            f"Проверьте подключение к интернету и повторите попытку."
        )
        logger.warning(f"Не все файлы отправлены: {sent_count}/{total_files}")
    else:
        logger.info(f"Все файлы успешно отправлены: {sent_count}/{total_files}")

    return sent_count


# ============ ФИНАЛЬНЫЙ ОТЧЁТ ============
def generate_final_report(orders_processed: int, stickers_sent: int, start_time: float):
    """Генерирует финальный отчёт"""
    end_time = time.time()
    processing_time = end_time - start_time
    days_left = check_wb_token_expiry()

    report_lines = [
        "📊 <b>ФИНАЛЬНЫЙ ОТЧЁТ</b>",
        f"📦 Обработано заказов: {orders_processed}",
        f"📤 Отправлено стикеров: {stickers_sent}",
        f"⏱️ Время обработки: {processing_time:.1f} сек",
    ]

    if days_left is not None:
        if days_left <= 5 and days_left > 0:
            report_lines.append(f"⚠️ Токен WB истекает через: {days_left} дней")
        elif days_left <= 0:
            report_lines.append("❌ Токен WB истёк!")
        else:
            report_lines.append(f"✅ Токен WB действителен ещё: {days_left} дней")

    report_text = "\n".join(report_lines)
    send_telegram_message(report_text)
    logger.info("Финальный отчёт отправлен")


# ============ ОБРАБОТКА НОВЫХ УЧАСТНИКОВ ============
def handle_new_chat_member(update):
    """Обрабатывает добавление нового участника в группу"""
    try:
        new_member = update["message"]["new_chat_member"]
        user_id = new_member["id"]
        username = new_member.get("username", f"user_{user_id}")
        first_name = new_member.get("first_name", "Unknown")

        request_text = (
            f"🔔 <b>Новый участник в группе!</b>\n"
            f"ID: <code>{user_id}</code>\n"
            f"Имя: {first_name}\n"
            f"Username: @{username}\n"
            f"Чтобы разрешить использование бота, отправьте в этот чат:\n"
            f"<code>/allow {user_id}</code> — разрешить\n"
            f"<code>/deny {user_id}</code> — запретить"
        )
        send_telegram_private_message(ADMIN_USER_ID, request_text)
        logger.info(f"Запрос на авторизацию для пользователя {user_id} отправлен админу")
    except Exception as e:
        logger.error(f"Ошибка обработки нового участника: {e}")


# ============ МЕНЮ НАСТРОЕК ============
def show_settings_menu():
    """Показывает меню настроек с inline-кнопками в ЛС администратора"""
    try:
        # Получаем список принтеров
        printers = get_available_printers()
        printer_list = "\n".join([f"• {p}" for p in printers[:5]])

        settings_text = (
            "⚙️ <b>МЕНЮ НАСТРОЕК</b>\n"
            f"🖨️ <b>Текущий принтер:</b> {DEFAULT_PRINTER}\n"
            f"📄 <b>Авто-печать:</b> {'✅ Включена' if AUTO_PRINT_ENABLED else '❌ Отключена'}\n"
            f"⏰ <b>Авто-запуск:</b> {'✅ Включён' if AUTO_START_ENABLED else '❌ Отключён'}\n"
            "<b>Доступные принтеры:</b>\n"
            f"{printer_list}"
        )

        # Создаём inline-кнопки
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "🖨️ Сменить принтер", "callback_data": "settings_change_printer"},
                    {"text": "🖨️ Авто-печать", "callback_data": "settings_toggle_print"}
                ],
                [
                    {"text": "⏰ Авто-запуск", "callback_data": "settings_toggle_auto"},
                    {"text": "🔑 Токен WB", "callback_data": "settings_wb_token"}
                ],
                [
                    {"text": "❌ Закрыть", "callback_data": "settings_close"}
                ]
            ]
        }

        # === ПОПЫТКА ОТПРАВИТЬ В ЛИЧНЫЕ СООБЩЕНИЯ ===
        success = send_telegram_private_message(ADMIN_USER_ID, settings_text, reply_markup=keyboard)
        if not success:
            # Если не получилось — отправляем в группу как fallback
            logger.warning("Не удалось отправить меню в ЛС, отправляю в группу")
            send_telegram_message(
                f"👤 <b>Настройки для администратора</b> (ID: {ADMIN_USER_ID})\n{settings_text}",
                reply_markup=keyboard
            )
        else:
            logger.info("Меню настроек отправлено в личные сообщения")
    except Exception as e:
        logger.error(f"Ошибка показа меню настроек: {e}")
        # Всегда отправляем в группу при ошибке
        send_telegram_message("❌ Ошибка отображения меню настроек", important_only=False)


# ============ ОБРАБОТКА CALLBACK-ОВ НАСТРОЕК ============
def handle_settings_callback(callback_data):
    """Обрабатывает нажатия в меню настроек"""
    try:
        if callback_data == "settings_change_printer":
            # Запрашиваем имя принтера
            request_text = "Введите имя принтера из списка выше:"
            send_telegram_private_message(ADMIN_USER_ID, request_text)
            # Устанавливаем флаг ожидания ввода
            global WAITING_FOR_PRINTER_NAME
            WAITING_FOR_PRINTER_NAME = True

        elif callback_data == "settings_toggle_print":
            global AUTO_PRINT_ENABLED
            AUTO_PRINT_ENABLED = not AUTO_PRINT_ENABLED
            save_configuration()
            status = "включена" if AUTO_PRINT_ENABLED else "отключена"
            send_telegram_private_message(ADMIN_USER_ID, f"✅ Автоматическая печать {status}")
            show_settings_menu()

        elif callback_data == "settings_toggle_auto":
            global AUTO_START_ENABLED
            AUTO_START_ENABLED = not AUTO_START_ENABLED
            save_configuration()
            status = "включён" if AUTO_START_ENABLED else "отключён"
            send_telegram_private_message(ADMIN_USER_ID, f"✅ Автоматический запуск {status}")
            show_settings_menu()

        elif callback_data == "settings_wb_token":
            request_text = "Введите новый токен Wildberries (начинается с 'eyJhbGci...'):"
            send_telegram_private_message(ADMIN_USER_ID, request_text)
            global WAITING_FOR_WB_TOKEN
            WAITING_FOR_WB_TOKEN = True

        elif callback_data == "settings_close":
            send_telegram_private_message(ADMIN_USER_ID, "Меню настроек закрыто")

    except Exception as e:
        logger.error(f"Ошибка обработки настроек: {e}")


# ============ СИСТЕМА АВТОРИЗАЦИИ НАСТРОЕК МИНИ-ПРИЛОЖЕНИЯ ============
def handle_settings_access_request(update):
    """Обрабатывает запрос доступа к настройкам из мини-приложения"""
    try:
        if "message" in update and "web_app_data" in update["message"]:
            data_str = update["message"]["web_app_data"]["data"]
            data = json.loads(data_str)

            if data.get("action") == "request_settings_access":
                user = data.get("user", {})
                session_id = data.get("session_id")
                requesting_user_id = user.get("id")
                first_name = user.get("first_name", "Unknown")
                username = user.get("username", "")

                # Сохраняем запрос
                settings_access_requests[session_id] = requesting_user_id

                # Отправляем уведомление админу
                keyboard = {
                    "inline_keyboard": [
                        [
                            {
                                "text": "✅ Разрешить",
                                "callback_data": f"settings_allow_{session_id}"
                            },
                            {
                                "text": "❌ Запретить",
                                "callback_data": f"settings_deny_{session_id}"
                            }
                        ]
                    ]
                }

                admin_message = (
                    f"🔐 <b>Запрос доступа к настройкам</b>\n\n"
                    f"👤 <b>Пользователь:</b> {first_name}\n"
                    f"🆔 <b>ID:</b> <code>{requesting_user_id}</code>\n"
                    f"{'@' + username if username else ''}\n\n"
                    f"Разрешить доступ к настройкам?"
                )

                send_telegram_private_message(ADMIN_USER_ID, admin_message, reply_markup=keyboard)

                # Подтверждение пользователю
                user_message = "⏳ Запрос отправлен администратору.\nПожалуйста, подождите подтверждения..."
                send_telegram_message(user_message)

                logger.info(f"Запрос доступа к настройкам от пользователя {requesting_user_id} (сессия: {session_id})")

    except Exception as e:
        logger.error(f"Ошибка обработки запроса настроек: {e}")


def handle_settings_access_callback(callback_data):
    """Обрабатывает ответ админа на запрос доступа к настройкам"""
    try:
        if callback_data.startswith("settings_allow_"):
            session_id = callback_data.replace("settings_allow_", "")

            if session_id in settings_access_requests:
                user_id = settings_access_requests[session_id]

                # Отправляем разрешение в мини-приложение
                settings_data = {
                    "printer": DEFAULT_PRINTER,
                    "auto_print": AUTO_PRINT_ENABLED,
                    "auto_start": AUTO_START_ENABLED,
                    "printers": get_available_printers()
                }

                import urllib.parse
                params_str = urllib.parse.urlencode({
                    'data': json.dumps({
                        "settings_auth": {
                            "approved": True,
                            "settings": settings_data
                        }
                    }, ensure_ascii=False)
                })

                keyboard = {
                    "inline_keyboard": [
                        [{
                            "text": "🖥️ Открыть интерфейс",
                            "web_app": {
                                "url": f"https://dsmyslovrussia-blip.github.io/stickers-wb-app/?{params_str}"
                            }
                        }]
                    ]
                }

                send_telegram_private_message(user_id, "✅ Доступ к настройкам разрешён!", reply_markup=keyboard)
                send_telegram_private_message(ADMIN_USER_ID, f"✅ Доступ разрешён пользователю {user_id}")

                logger.info(f"Доступ к настройкам разрешён пользователю {user_id}")

                # Удаляем запрос из памяти
                del settings_access_requests[session_id]

        elif callback_data.startswith("settings_deny_"):
            session_id = callback_data.replace("settings_deny_", "")

            if session_id in settings_access_requests:
                user_id = settings_access_requests[session_id]

                # Отправляем отказ в мини-приложение
                import urllib.parse
                params_str = urllib.parse.urlencode({
                    'data': json.dumps({
                        "settings_auth": {
                            "denied": True
                        }
                    }, ensure_ascii=False)
                })

                keyboard = {
                    "inline_keyboard": [
                        [{
                            "text": "🖥️ Открыть интерфейс",
                            "web_app": {
                                "url": f"https://dsmyslovrussia-blip.github.io/stickers-wb-app/?{params_str}"
                            }
                        }]
                    ]
                }

                send_telegram_private_message(user_id, "❌ Доступ к настройкам запрещён!", reply_markup=keyboard)
                send_telegram_private_message(ADMIN_USER_ID, f"❌ Доступ запрещён пользователю {user_id}")

                logger.info(f"Доступ к настройкам запрещён пользователю {user_id}")

                # Удаляем запрос из памяти
                del settings_access_requests[session_id]

    except Exception as e:
        logger.error(f"Ошибка обработки ответа настроек: {e}")


def handle_get_settings(update):
    """Отправляет текущие настройки в мини-приложение"""
    try:
        if "message" in update and "web_app_data" in update["message"]:
            data_str = update["message"]["web_app_data"]["data"]
            data = json.loads(data_str)

            if data.get("action") == "get_settings":
                user_id = update["message"]["from"]["id"]

                settings_data = {
                    "printer": DEFAULT_PRINTER,
                    "auto_print": AUTO_PRINT_ENABLED,
                    "auto_start": AUTO_START_ENABLED,
                    "printers": get_available_printers()
                }

                import urllib.parse
                params_str = urllib.parse.urlencode({
                    'data': json.dumps({
                        "settings_auth": {
                            "approved": True,
                            "settings": settings_data
                        }
                    }, ensure_ascii=False)
                })

                keyboard = {
                    "inline_keyboard": [
                        [{
                            "text": "🖥️ Открыть интерфейс",
                            "web_app": {
                                "url": f"https://dsmyslovrussia-blip.github.io/stickers-wb-app/?{params_str}"
                            }
                        }]
                    ]
                }

                send_telegram_private_message(user_id, "🔄 Настройки обновлены", reply_markup=keyboard)

    except Exception as e:
        logger.error(f"Ошибка отправки настроек: {e}")


# ============ ОБРАБОТКА ДАННЫХ ИЗ МИНИ-ПРИЛОЖЕНИЯ ============
def handle_webapp_data(update):
    """Обрабатывает данные из мини-приложения"""
    # ✅ ВСЕ global объявления в самом начале функции!
    global CURRENT_MODE, CONFIRMED, PROCESS_CANCELLED, RUN_LOCK

    try:
        if "message" in update and "web_app_data" in update["message"]:
            data_str = update["message"]["web_app_data"]["data"]
            data = json.loads(data_str)
            user_id = update["message"]["from"]["id"]

            # Проверка авторизации
            if user_id not in AUTHORIZED_USERS and user_id != ADMIN_USER_ID:
                send_telegram_message("❌ У вас нет доступа к этому агенту")
                return

            action = data.get("action")

            if action == "start_process":
                mode = data.get("mode", "test")

                if RUN_LOCK:
                    send_telegram_message("⚠️ Агент уже занят!")
                    return

                CURRENT_MODE = mode
                CONFIRMED = True
                PROCESS_CANCELLED = False
                RUN_LOCK = True

                # Запускаем обработку в отдельном потоке
                Thread(target=main_workflow).start()

                mode_text = "тестовый" if mode == "test" else "рабочий"
                send_telegram_message(f"🚀 Запущена обработка в {mode_text} режиме")

            elif action == "check_status":
                status = "busy" if RUN_LOCK else "ready"
                mode_info = CURRENT_MODE if CURRENT_MODE else "none"
                status_text = "🟡 Занят" if status == "busy" else "🟢 Готов"

                send_telegram_message(
                    f"📊 Статус: {status_text}\n"
                    f"Режим: {mode_info}\n"
                    f"Обработано заказов: {len(PROCESSED_ORDERS)}"
                )

            elif action == "cancel_process":
                PROCESS_CANCELLED = True
                send_telegram_message("✅ Обработка отменена")

            elif action == "get_logs":
                # Отправляем последние логи
                try:
                    log_file = SCRIPT_DIR / "bot.log"
                    if log_file.exists():
                        with open(log_file, 'r', encoding='utf-8') as f:
                            lines = f.readlines()[-20:]

                        logs_text = "📜 Последние логи:\n" + "".join(lines[-10:])
                        send_telegram_message(f"<pre>{logs_text}</pre>")
                    else:
                        send_telegram_message("📄 Лог-файл не найден")
                except Exception as e:
                    send_telegram_message(f"❌ Ошибка чтения логов: {e}")

            else:
                send_telegram_message(f"❌ Неизвестное действие: {action}")

    except Exception as e:
        logger.error(f"Ошибка обработки web_app_data: {e}")
        send_telegram_message(f"❌ Ошибка: {str(e)[:100]}")


# ============ ОБРАБОТКА КОМАНД ============
def handle_commands():
    """Обработка команд из Telegram + новые участники + авторизация + мини-приложение"""
    global CONFIRMED, RUN_LOCK, PROCESS_CANCELLED, STOP_CURRENT_TASK, CURRENT_MODE, AUTHORIZED_USERS, PROCESSED_ORDERS
    global WAITING_FOR_PRINTER_NAME, WAITING_FOR_WB_TOKEN

    last_update_id = None

    while not AGENT_SHUTDOWN:
        try:
            session = create_session()
            params = {"timeout": 30}
            if last_update_id:
                params["offset"] = last_update_id + 1

            resp = session.get(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates",
                params=params,
                timeout=35,
                verify=False
            )

            if resp.status_code == 200:
                updates = resp.json().get("result", [])
                for update in updates:
                    last_update_id = update.get("update_id")

                    # Обработка новых участников
                    if "message" in update and "new_chat_member" in update["message"]:
                        handle_new_chat_member(update)
                        continue

                    # Обработка callback-запросов (настройки, подтверждения)
                    if "callback_query" in update:
                        callback = update["callback_query"]
                        callback_data = callback["data"]

                        # Обработка авторизации настроек мини-приложения
                        if callback_data.startswith("settings_allow_") or callback_data.startswith("settings_deny_"):
                            handle_settings_access_callback(callback_data)
                            continue

                        # Обработка настроек
                        if callback_data.startswith("settings_"):
                            handle_settings_callback(callback_data)
                            continue

                        # Обработка выбора режима
                        if callback_data == "select_test_mode":
                            CURRENT_MODE = "test"
                            CONFIRMED = True
                            PROCESS_CANCELLED = False
                            send_telegram_message("🧪 Выбран тестовый режим\nНачинаю обработку заказов...")
                            Thread(target=main_workflow).start()

                        elif callback_data == "select_production_mode":
                            CURRENT_MODE = "production"
                            CONFIRMED = True
                            PROCESS_CANCELLED = False
                            send_telegram_message("🚀 Выбран рабочий режим\nНачинаю обработку заказов...")
                            Thread(target=main_workflow).start()

                        elif callback_data == "cancel_process":
                            PROCESS_CANCELLED = True
                            RUN_LOCK = False
                            send_telegram_message("❌ Обработка отменена")

                        elif callback_data.startswith("confirm_"):
                            step_key = callback_data.replace("confirm_", "")
                            confirm_step(step_key)
                            send_telegram_message("✅ Действие подтверждено, продолжаю...")
                            continue

                    # === ОБРАБОТКА ДАННЫХ ИЗ МИНИ-ПРИЛОЖЕНИЯ ===
                    if "message" in update and "web_app_data" in update["message"]:
                        data_str = update["message"]["web_app_data"]["data"]
                        data = json.loads(data_str)
                        action = data.get("action")

                        if action == "request_settings_access":
                            handle_settings_access_request(update)
                            continue
                        elif action == "get_settings":
                            handle_get_settings(update)
                            continue
                        else:
                            handle_webapp_data(update)
                            continue

                    if "message" not in update or "text" not in update["message"]:
                        continue

                    msg = update["message"]
                    chat_id = msg.get("chat", {}).get("id", 0)
                    text = msg.get("text", "").strip()

                    # === ОБРАБОТКА КОМАНДЫ /settings ИЗ ГРУППЫ ===
                    if chat_id == GROUP_CHAT_ID:
                        user_id = msg.get("from", {}).get("id", 0)
                        if user_id == ADMIN_USER_ID and text == "/settings":
                            show_settings_menu()
                            continue

                    # === ОБРАБОТКА КОМАНД В ЛИЧНЫХ СООБЩЕНИЯХ ===
                    if chat_id == ADMIN_USER_ID and "text" in msg:
                        # Обработка ввода после запроса принтера
                        if WAITING_FOR_PRINTER_NAME:
                            if set_printer_safely(text):
                                send_telegram_private_message(ADMIN_USER_ID, f"✅ Принтер изменён на: {text}")
                            else:
                                send_telegram_private_message(ADMIN_USER_ID, f"❌ Принтер '{text}' не найден в системе")
                            WAITING_FOR_PRINTER_NAME = False
                            show_settings_menu()
                            continue

                        # Обработка ввода токена WB
                        if WAITING_FOR_WB_TOKEN:
                            if text.startswith("eyJhbGci"):
                                global WB_TOKEN, WB_TOKEN_CREATION_DATE
                                WB_TOKEN = text
                                # Автоматически обновляем дату создания токена на сегодня
                                WB_TOKEN_CREATION_DATE = datetime.now().strftime("%Y-%m-%d")
                                save_configuration()
                                send_telegram_private_message(ADMIN_USER_ID,
                                                              "✅ Токен Wildberries обновлён\n📅 Дата создания обновлена на сегодня")
                            else:
                                send_telegram_private_message(ADMIN_USER_ID, "❌ Неверный формат токена")
                            WAITING_FOR_WB_TOKEN = False
                            show_settings_menu()
                            continue

                        # Остальные команды (/allow, /deny)
                        if text.startswith("/allow ") or text.startswith("/deny "):
                            parts = text.split(maxsplit=1)
                            if len(parts) < 2:
                                send_telegram_private_message(ADMIN_USER_ID,
                                                              "❌ Неверный формат. Пример: /allow 123456789")
                                continue

                            cmd, arg = parts[0], parts[1]
                            try:
                                user_id = int(arg)
                                if cmd == "/allow":
                                    AUTHORIZED_USERS.add(user_id)
                                    save_authorized_user(user_id)
                                    send_telegram_private_message(ADMIN_USER_ID,
                                                                  f"✅ Пользователь {user_id} авторизован!")
                                    logger.info(f"Пользователь {user_id} авторизован через /allow")
                                elif cmd == "/deny":
                                    AUTHORIZED_USERS.discard(user_id)
                                    remove_authorized_user(user_id)
                                    send_telegram_private_message(ADMIN_USER_ID,
                                                                  f"❌ Пользователь {user_id} заблокирован!")
                                    logger.info(f"Пользователь {user_id} заблокирован через /deny")
                                else:
                                    send_telegram_private_message(ADMIN_USER_ID, "❌ Неизвестная команда")
                            except ValueError:
                                send_telegram_private_message(ADMIN_USER_ID, "❌ ID должен быть числом")
                            continue

                    # Пропускаем сообщения не из группы
                    if chat_id != GROUP_CHAT_ID:
                        continue

                    user_id = msg.get("from", {}).get("id", 0)

                    # Проверка авторизации
                    if user_id not in AUTHORIZED_USERS and user_id != ADMIN_USER_ID:
                        send_telegram_message(
                            "❌ Вы не можете использовать этого агента без подтверждения администратора группы.")
                        logger.warning(f"Неавторизованная попытка использования бота: user_id={user_id}")
                        continue

                    # Убираем упоминание бота из команды
                    if "@" in text:
                        text = text.split("@")[0]

                    # === ОБРАБОТКА КОМАНД ===
                    if text == "/process":
                        if RUN_LOCK:
                            send_telegram_message("⚠️ Агент занят!")
                        else:
                            RUN_LOCK = True
                            CONFIRMED = False
                            PROCESS_CANCELLED = False
                            CURRENT_MODE = None

                            keyboard = {
                                "inline_keyboard": [
                                    [
                                        {"text": "Тестовый режим 🧪", "callback_data": "select_test_mode"},
                                        {"text": "Рабочий режим 🚀", "callback_data": "select_production_mode"}
                                    ],
                                    [
                                        {"text": "Отмена ❌", "callback_data": "cancel_process"}
                                    ]
                                ]
                            }

                            send_telegram_message(
                                "⚠️ Выберите режим работы:\n"
                                "• <b>Тестовый</b> — подтверждение каждого действия\n"
                                "• <b>Рабочий</b> — полная автоматизация",
                                reply_markup=keyboard
                            )

                    elif text == "/status":
                        if RUN_LOCK:
                            status = "🟡 Занят"
                            mode_info = f" ({'тестовый' if CURRENT_MODE == 'test' else 'рабочий'} режим)"
                        else:
                            status = "🟢 Готов"
                            mode_info = ""

                        send_telegram_message(f"📊 Статус: {status}{mode_info}")

            else:
                logger.warning(f"Ошибка получения обновлений: {resp.status_code}")

        except Exception as e:
            logger.error(f"Ошибка: {e}")
            adaptive_sleep(5)


# ============ ОСНОВНОЙ WORKFLOW ============
def main_workflow():
    """Основной workflow обработки заказов с финальным отчётом"""
    global RUN_LOCK, CONFIRMED, PROCESS_CANCELLED, STOP_CURRENT_TASK, CURRENT_MODE, PROCESSED_ORDERS

    start_time = time.time()

    try:
        while not CONFIRMED and not PROCESS_CANCELLED and RUN_LOCK:
            adaptive_sleep(0.1)

        if PROCESS_CANCELLED:
            send_telegram_message("❌ Обработка отменена")
            return

        send_telegram_message("🧹 Очищаю папку от старых стикеров...")
        for file_path in DOWNLOADS_DIR.glob("*.pdf"):
            try:
                file_path.unlink()
                logger.info(f"🗑️ Удалён файл: {file_path.name}")
            except Exception as e:
                logger.error(f"❌ Не удалось удалить {file_path.name}: {e}")

        if not minimize_all_windows():
            return

        send_telegram_message("🔍 Ищу иконку Chrome в панели задач...", important_only=True)
        chrome_icon_location = find_chrome_icon_in_taskbar()

        if not chrome_icon_location:
            send_telegram_message("⚠️ Иконка Chrome не найдена, использую координаты...", important_only=True)
            if not click_chrome_by_coordinates():
                error_msg = "❌ Не удалось активировать Chrome"
                send_telegram_message(error_msg, important_only=True)
                logger.error("Не удалось активировать Chrome")
                return
        else:
            send_telegram_message("🖱️ Двигаю мышь к иконке Chrome...", important_only=True)
            if smooth_move_to_element(chrome_icon_location, duration=1.0):
                adaptive_sleep(0.5)
                if not wait_for_confirmation("move_to_chrome", "Мышь наведена на иконку Chrome"):
                    return
                send_telegram_message("🖱️ Кликаю по иконке Chrome...", important_only=True)
                pyautogui.click()
                adaptive_sleep(2.0)
                if not wait_for_confirmation("click_chrome", "Успешно кликнул по иконке Chrome"):
                    return
            else:
                pyautogui.click(chrome_icon_location)
                adaptive_sleep(2.0)
                if not wait_for_confirmation("quick_click_chrome", "Успешно кликнул по иконке Chrome"):
                    return

        if not switch_to_wb_tab():
            return

        client = WBApiClient(WB_TOKEN)
        orders = client.get_new_orders()

        if not orders:
            send_telegram_message("📭 Нет новых заказов")
            return

        filtered_orders = []
        for order in orders:
            order_id = order["id"]
            if order_id in PROCESSED_ORDERS:
                logger.info(f"Пропускаю уже обработанный заказ #{order_id}")
                continue
            filtered_orders.append(order)

        if not filtered_orders:
            send_telegram_message("📭 Все заказы уже обработаны")
            return

        orders = filtered_orders

        if CURRENT_MODE == "production":
            send_telegram_message(f"🚀 <b>Рабочий режим</b>\n📦 Найдено {len(orders)} заказов\n⏱️ Начинаю обработку...")
        else:
            send_telegram_message(f"🧪 <b>Тестовый режим</b>\n📦 Найдено {len(orders)} заказов\n⏱️ Начинаю обработку...")

        logger.info(f"📥 Найдено {len(orders)} заказов ({CURRENT_MODE} режим)")

        all_stickers = []
        session_dir = DOWNLOADS_DIR
        orders_processed = 0

        for idx, order in enumerate(orders):
            if PROCESS_CANCELLED:
                send_telegram_message("✅ Обработка прервана")
                return

            order_id = order["id"]

            if CURRENT_MODE == "production":
                send_telegram_message(f"🔄 Обрабатываю заказ #{order_id}...")
            else:
                send_telegram_message(f"🔄 <b>Тест:</b> Обрабатываю заказ #{order_id}...")

            order_files = process_single_order(order, idx, session_dir)

            if order_files:
                orders_processed += 1
                logger.info(f"✅ Заказ #{order_id} успешно обработан")
            else:
                logger.warning(f"⚠️ Заказ #{order_id} не был обработан")

            all_stickers.extend(order_files)
            adaptive_sleep(1.5)

        if CURRENT_MODE == "test":
            if not wait_for_confirmation("send_stickers", "Готов отправить все стикеры"):
                send_telegram_message("📤 Отправка отменена")
                return

        # === СНАЧАЛА ОТПРАВЛЯЕМ ОБЪЕДИНЁННЫЙ PDF ===
        merged_pdf = merge_pdfs_by_order(all_stickers, DOWNLOADS_DIR)
        if merged_pdf:
            if CURRENT_MODE == "production":
                send_telegram_message("📄 Отправляю объединённый PDF со всеми стикерами...")
                send_telegram_document(merged_pdf)
                adaptive_sleep(2)
                if AUTO_PRINT_ENABLED:
                    auto_print_pdf(merged_pdf)
            else:
                send_telegram_message("📄 <b>Тест:</b> Отправляю объединённый PDF со всеми стикерами...")
                send_telegram_document(merged_pdf)
                adaptive_sleep(1.0)

        # === ЗАТЕМ ОТПРАВЛЯЕМ ОТДЕЛЬНЫЕ ФАЙЛЫ ===
        pdf_files = list(DOWNLOADS_DIR.glob("*.pdf"))

        def sort_key(filename):
            name = filename.stem
            parts = name.split('_')
            if len(parts) == 2:
                return (int(parts[0]), int(parts[1]))
            return (999, 999)

        sorted_pdf_files = sorted(pdf_files, key=sort_key)
        sent_count = send_stickers_in_batches(sorted_pdf_files, batch_size=5)

        generate_final_report(orders_processed, sent_count, start_time)
        logger.info("✅ Обработка завершена")

    except Exception as e:
        error_msg = f"🔥 Ошибка: {str(e)}"
        send_telegram_message(error_msg)
        logger.error(error_msg)

    finally:
        RUN_LOCK = False
        CONFIRMED = False
        PROCESS_CANCELLED = False
        STOP_CURRENT_TASK = False
        CURRENT_MODE = None


# ============ ОСНОВНАЯ ФУНКЦИЯ ============
def main():
    """Основная функция"""
    global AUTHORIZED_USERS

    # ✅ ПРОВЕРКА ЗАГРУЗКИ ТОКЕНОВ ИЗ .ENV
    if not TELEGRAM_BOT_TOKEN:
        logger.error("❌ TELEGRAM_BOT_TOKEN не найден в .env!")
        print("❌ Ошибка: TELEGRAM_BOT_TOKEN не найден в .env файле!")
        return

    if not WB_TOKEN:
        logger.error("❌ WB_TOKEN не найден в .env!")
        print("❌ Ошибка: WB_TOKEN не найден в .env файле!")
        return

    if not GROUP_CHAT_ID:
        logger.error("❌ GROUP_CHAT_ID не найден в .env!")
        print("❌ Ошибка: GROUP_CHAT_ID не найден в .env файле!")
        return

    if not ADMIN_USER_ID:
        logger.error("❌ ADMIN_USER_ID не найден в .env!")
        print("❌ Ошибка: ADMIN_USER_ID не найден в .env файле!")
        return

    logger.info(f"✅ Токены загружены из .env")
    logger.info(f"✅ Bot Token: {TELEGRAM_BOT_TOKEN[:20]}...")
    logger.info(f"✅ Group ID: {GROUP_CHAT_ID}")
    logger.info(f"✅ Admin ID: {ADMIN_USER_ID}")

    load_configuration()

    print("=" * 60)
    print("🤖 ЛОКАЛЬНЫЙ АГЕНТ WILDBERRIES — ГОТОВ К РАБОТЕ!")
    print("=" * 60)
    print("✅ Токены загружены из .env файла")
    print("Режим: локальный запуск")
    print("Зависимости: pip install requests pyautogui pywin32 opencv-python pillow pypdf reportlab python-dotenv")
    print(f"📁 Папка для скачивания: {DOWNLOADS_DIR}")
    print("❗ ВАЖНО: положите в папку агента:")
    print("   • back_button.png — скриншот кнопки 'Назад'")
    print("   • success_download_message.png — ваш скриншот успешного скачивания")
    print("   • success_delivery_message.png — ваш скриншот успешной передачи")
    print("   • wb_tab_in_chrome.png — скриншот вкладки Wildberries")
    print("   • chrome_icon.png — иконка Chrome для поиска в панели задач")
    print("=" * 60)

    send_telegram_message(
        "🟢 <b>Агент активен</b>\n"
        "Команды: /process, /status\n"
        "Админ: /settings"
    )

    logger.info("📱 Агент запущен")

    telegram_thread = Thread(target=handle_commands)
    telegram_thread.start()

    try:
        telegram_thread.join()
    except KeyboardInterrupt:
        print("\n🛑 Остановка...")
        global AGENT_SHUTDOWN
        AGENT_SHUTDOWN = True


if __name__ == "__main__":
    main()
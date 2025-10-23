"""
Общий модуль для настройки логирования webhook скриптов
ВАЖНО: Логи идут ТОЛЬКО в файлы, НЕ в stdout (чтобы не портить JSON ответы)
"""
import logging
from pathlib import Path

# Базовая директория для логов
LOG_DIR = Path('/home/asd/webhook_server/logs')

# Формат логов
LOG_FORMAT = '%(asctime)s - %(levelname)s - %(message)s'
LOG_LEVEL = logging.INFO


def setup_logger(script_name):
    """
    Настройка логгера для конкретного скрипта
    
    Args:
        script_name: имя скрипта (например, 'manufacturing', 'sale', и т.д.)
    
    Returns:
        logger: настроенный объект логгера
    """
    # Создаем директорию если её нет
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    
    # Путь к файлу лога
    log_file = LOG_DIR / f'{script_name}.log'
    
    # Создаем логгер
    logger = logging.getLogger(script_name)
    logger.setLevel(LOG_LEVEL)
    
    # Удаляем все существующие handlers (если есть)
    logger.handlers.clear()
    
    # Добавляем ТОЛЬКО FileHandler (без StreamHandler!)
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(LOG_LEVEL)
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    
    logger.addHandler(file_handler)
    
    return logger


# Предустановленные логгеры для всех скриптов
def get_manufacturing_logger():
    """Логгер для manufacturing.py"""
    return setup_logger('manufacturing')


def get_sale_logger():
    """Логгер для sale.py"""
    return setup_logger('sale')

def get_invent_logger():
    """Логгер для invent.py"""
    return setup_logger('invent')


def get_device_logger():
    """Логгер для get_device_by_serial.py"""
    return setup_logger('get_device_by_serial')


def get_devices_logger():
    """Логгер для get_devices.py"""
    return setup_logger('get_devices')


def get_check_device_logger():
    """Логгер для check_device.py"""
    return setup_logger('check_device')

def get_scan_sender_logger():
    """Логгер для read_and_send_scans.py"""
    return setup_logger('get_pending_scans')


# Пример использования:
if __name__ == '__main__':
    # Тест логирования
    logger = setup_logger('test')
    logger.info("Test log message")
    logger.warning("Test warning")
    logger.error("Test error")
    print("JSON response")  # Это пойдет в stdout, логи - в файл
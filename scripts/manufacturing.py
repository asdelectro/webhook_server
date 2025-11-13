#!/usr/bin/env python3
"""
Скрипт для обработки сканирования в производстве manufacturing.py
"""
import sys
import json
from datetime import datetime
from pathlib import Path
# Импорт InvenTreeStockManager больше не нужен, но мы его оставим как заглушку,
# если вы захотите его использовать для других целей в будущем.
# from aux.InvenTreeStockManager import InvenTreeStockManager 
import time
import requests # <-- ДОБАВЛЕНО: для выполнения HTTP-запросов

# Добавляем путь к AzureConnector
sys.path.insert(0, str(Path(__file__).parent.parent))

from AzureConnector import RadiacodeManager
from logger_config import get_manufacturing_logger

# Получаем настроенный логгер (без StreamHandler!)
logger = get_manufacturing_logger()

# ---------------- КОНФИГУРАЦИЯ FLASK-ОЧЕРЕДИ ----------------
# Укажите адрес и порт вашего Flask-сервера с очередью (например, на порту 5000)
FLASK_QUEUE_URL = "http://192.168.88.132:5000/add_serial"
# -------------------------------------------------------------

# Конфигурация сканирования
BARCODE_PREFIX = 'RC-'
MIN_BARCODE_LENGTH = 10
ALLOWED_TOPICS = ['production/ready']

# --- ИЗМЕНЕНА: ОТПРАВКА СЕРИЙНОГО НОМЕРА В FLASK-ОЧЕРЕДЬ ---
def process_new_device(serial_number: str):
    """
    Отправляет новый серийный номер в очередь Flask-сервера.
    """
    try:
        payload = {'serial': serial_number}
        
        logger.info(f"Sending {serial_number} to Flask queue: {FLASK_QUEUE_URL}")
        
        # Отправляем POST-запрос
        response = requests.post(
            FLASK_QUEUE_URL, 
            json=payload, 
            headers={'Content-Type': 'application/json'},
            timeout=5 # Таймаут для ожидания ответа от Flask-сервера
        )
        
        # Flask-сервер очереди должен вернуть 202 Accepted, если успешно
        if response.status_code == 202:
            logger.info(f"OK! Device {serial_number} successfully SENT to Flask queue.")
            return True, "Successfully sent to Flask queue."
        else:
            # Если Flask-сервер вернул ошибку или некорректный статус
            error_details = response.json() if response.text else response.status_code
            logger.error(f"ERROR {serial_number} not sent to Flask: Status {response.status_code}, Details: {error_details}")
            return False, f"Failed to send to Flask queue (Status: {response.status_code})"

    except requests.exceptions.RequestException as e:
        # Ошибка соединения (сервер не запущен, неверный адрес)
        logger.error(f"ERROR {serial_number} failed connection to Flask: {e}")
        return False, f"Failed to connect to Flask queue server: {e}"
    # -------------------------------------------------------------------------


def validate_barcode(barcode):
# ... (Эта функция остается без изменений) ...
    """Валидация штрихкода"""
    if not barcode:
        return False, "Barcode is required"
    
    if not barcode.startswith(BARCODE_PREFIX):
        return False, f"Invalid barcode format. Expected format: {BARCODE_PREFIX}XXXXXXXXX (min {MIN_BARCODE_LENGTH} chars)"
    
    if len(barcode) < MIN_BARCODE_LENGTH:
        return False, f"Invalid barcode format. Expected format: {BARCODE_PREFIX}XXXXXXXXX (min {MIN_BARCODE_LENGTH} chars)"
    
    return True, "OK"


def process_manufacturing(data):
    """
    Обработка данных производства
    """
    try:
        # ... (Проверка топика и парсинг payload остаются без изменений)
        logger.info(f"Получены данные: {data}")
        topic = data.get('topic', '')
        logger.info(f"Данные получены из топика: {topic}")
        
        topic_allowed = False
        for allowed_topic in ALLOWED_TOPICS:
            if topic == allowed_topic or topic.startswith(allowed_topic):
                topic_allowed = True
                break
        
        if not topic_allowed:
            logger.warning(f"Данные получены из неразрешенного топика: {topic}")
            result = {'error': 'Unauthorized topic', 'topic': topic, 'allowed_topics': ALLOWED_TOPICS}
            print(json.dumps(result))
            return 1

        payload_str = data.get('payload', '{}')
        payload_json = json.loads(payload_str)
        barcode = payload_json.get('msg', '').strip()
        logger.info(f"Парсинг: barcode={barcode}, topic={topic}")

        # Валидация штрихкода
        is_valid, error_msg = validate_barcode(barcode)
        if not is_valid:
            logger.warning(error_msg)
            print(json.dumps({'error': error_msg}))
            return 1
            
        # --- ИЗМЕНЕНА: Вызываем новую функцию отправки и убираем time.sleep(3) ---
        # time.sleep(3) # <-- Эту задержку теперь обрабатывает очередь на Flask-сервере
        success_send, send_message = process_new_device(barcode)
        
        if not success_send:
            # Если отправка в Flask-очередь не удалась, останавливаемся
            logger.error(f"Не удалось отправить серийный номер в Flask-очередь: {send_message}")
            print(json.dumps({'error': f'Failed to send to Flask queue: {send_message}'}))
            return 1
            
        # Записываем дату изготовления (логика RadiacodeManager)
        manager = RadiacodeManager()
        success = manager.WriteManufacturingDate(barcode)
        operation = 'manufacturing'
        date_field = 'manufacturing_date'
        
        if success:
            logger.info(f"Успешно записана {operation} дата для: {barcode} из топика: {topic}")
            response_data = {
                'status': 'success',
                'barcode': barcode,
                'topic': topic,
                'operation': operation,
                date_field: datetime.now().isoformat(),
                'message': f'{operation.capitalize()} date recorded successfully and sent to Flask queue' # Обновляем сообщение
            }
            print(json.dumps(response_data))
            return 0
        else:
            logger.error(f"Ошибка записи {operation} даты для: {barcode}")
            print(json.dumps({'error': f'Failed to record {operation} date'}))
            return 1
            
    except json.JSONDecodeError as e:
        logger.error(f"Ошибка парсинга JSON payload: {e}")
        print(json.dumps({'error': 'Invalid JSON payload'}))
        return 1
    except Exception as e:
        logger.error(f"Общая ошибка: {e}")
        print(json.dumps({'error': f'Server error: {str(e)}'}))
        return 1


if __name__ == '__main__':

    try:
        if len(sys.argv) > 1:
            data = json.loads(sys.argv[1])
        else:
            data = json.load(sys.stdin)
        
        exit_code = process_manufacturing(data)
        sys.exit(exit_code)
        
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        print(json.dumps({'success': False, 'error': str(e)}))
        sys.exit(1)
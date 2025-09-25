from flask import Flask, request, jsonify
import logging
import json
from datetime import datetime, timedelta
from AzureConnector import RadiacodeManager

app = Flask(__name__)

# Настройка логирования
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Конфигурация разрешенных топиков
MANUFACTURING_CONFIG = {
    'ALLOWED_TOPICS': [
        'production/ready',
        'sale/ready'
    ],
    'TOPIC_VALIDATION_ENABLED': True,  # Можно отключить для тестирования
    'BARCODE_PREFIX': 'RC-',
    'MIN_BARCODE_LENGTH': 10
}

# Создаем экземпляр менеджера
manager = RadiacodeManager()


class OrderTrackingManager:
    def __init__(self):
        self.pending_orders = {}  # {device_id: {'type': 'fedex'/'ups'/'non_fedex', 'timestamp': datetime, 'order_data': dict}}
        self.cleanup_timeout = 10  # 10 секунд на ожидание трек-кода
    
    def register_order(self, device_id, order_type, order_data):
        """Регистрирует заказ и ожидает трек-код"""
        self.pending_orders[device_id] = {
            'type': order_type,
            'timestamp': datetime.now(),
            'order_data': order_data
        }
        logger.info(f"Зарегистрирован заказ {order_type} для устройства {device_id}")
    
    def process_tracking_code(self, device_id, tracking_data):
        """Обрабатывает поступивший трек-код"""
        if device_id not in self.pending_orders:
            logger.warning(f"Получен трек-код для неизвестного устройства {device_id}")
            return False, "No pending order for this device"
        
        order_info = self.pending_orders.pop(device_id)
        
        # Проверяем таймаут
        if (datetime.now() - order_info['timestamp']).seconds > self.cleanup_timeout:
            logger.warning(f"Истек таймаут ожидания трек-кода для {device_id}")
            return False, "Tracking code timeout"
        
        # Извлекаем трек-код в зависимости от типа заказа
        msg = tracking_data.get('msg', '')
        
        if order_info['type'] in ['fedex_warehouse', 'non_fedex_warehouse']:
            # Для FedEx и Non-FedEx извлекаем последние 12 цифр как номер заказа
            order_number = msg[-12:] if len(msg) >= 12 else msg
            self.save_order_number(device_id, order_info['type'], order_number, order_info['order_data'])
            return True, f"Order number {order_number} saved for {order_info['type']}"
        
        elif order_info['type'] == 'ups_code':
            # Для UPS сохраняем весь msg как трек-номер
            tracking_number = msg
            self.save_tracking_number(device_id, 'ups', tracking_number, order_info['order_data'])
            return True, f"UPS tracking number {tracking_number} saved"
        
        return False, "Unknown order type"
    
    def save_order_number(self, device_id, order_type, order_number, original_data):
        """Сохраняет номер заказа в базу данных"""
        # Здесь ваша логика сохранения в БД
        logger.info(f"Сохранен номер заказа {order_number} типа {order_type} для устройства {device_id}")
        # manager.SaveOrderNumber(device_id, order_type, order_number, original_data)
    
    def save_tracking_number(self, device_id, carrier, tracking_number, original_data):
        """Сохраняет трек-номер в базу данных"""
        # Здесь ваша логика сохранения в БД
        logger.info(f"Сохранен трек-номер {tracking_number} перевозчика {carrier} для устройства {device_id}")
        # manager.SaveTrackingNumber(device_id, carrier, tracking_number, original_data)
    
    def cleanup_expired(self):
        """Очищает просроченные заказы"""
        current_time = datetime.now()
        expired_devices = [
            device_id for device_id, order_info in self.pending_orders.items()
            if (current_time - order_info['timestamp']).seconds > self.cleanup_timeout
        ]
        for device_id in expired_devices:
            logger.warning(f"Удален просроченный заказ для устройства {device_id}")
            del self.pending_orders[device_id]

# Глобальный менеджер
tracking_manager = OrderTrackingManager()

def clean_control_characters(s):
    """
    Удаляет управляющие символы из строки, заменяя их на пустую строку.
    """
    if not isinstance(s, str):
        return s
    # Удаляем управляющие символы (ASCII 0-31, кроме \n, \r, \t)
    return ''.join(c for c in s if ord(c) >= 32 or c in '\n\r\t')

def check_payload(payload_str):
    """
    Проверяет payload на соответствие формату RC-xxx-xxxxxx, UPS коду (421)84037040, 
    или JSON с FedEx/Non-FedEx логикой.
    Возвращает кортеж (status, payload_json, message).
    """
    logger.debug(f"Начало проверки payload: {payload_str}, тип: {type(payload_str)}")

    # Проверка типа входных данных
    if not isinstance(payload_str, str):
        logger.error(f"Некорректный тип payload: ожидалась строка, получено {type(payload_str)}")
        return "incorrect_format", None, f"Invalid payload type: expected str, got {type(payload_str)}"

    # Проверка на пустую строку
    if not payload_str:
        logger.warning("Получен пустой payload")
        return "incorrect_format", None, "Empty payload"

    # Очистка управляющих символов
    cleaned_payload = clean_control_characters(payload_str)
    logger.debug(f"Payload после очистки управляющих символов: {cleaned_payload}")

    # Проверка на UPS код (содержит 37040)
    if '37040' in cleaned_payload:
        logger.info(f"Обнаружен UPS код в payload: {cleaned_payload}")
        try:
            payload_json = json.loads(cleaned_payload)
            logger.info(f"UPS код успешно разобран как JSON: {payload_json}")
            return "ups_code", payload_json, "UPS code detected"
        except json.JSONDecodeError:
            logger.info(f"UPS код не является JSON: {cleaned_payload}")
            return "ups_code", None, f"UPS code detected: {cleaned_payload}"

    # Проверка формата RC-xxx-xxxxxx для самого payload
    logger.debug(f"Проверка формата RC-xxx-xxxxxx для payload: {cleaned_payload}")
    if len(cleaned_payload) == 39 and cleaned_payload.startswith('RC-'):
        logger.debug("Payload соответствует начальным условиям RC-xxx-xxxxxx")
        try:
            parts = cleaned_payload.split('-')
            logger.debug(f"Разделение payload на части: {parts}")
            if len(parts) == 3 and len(parts[1]) == 3 and len(parts[2]) == 6 and parts[1].isalnum() and parts[2].isalnum():
                logger.debug("Формат RC-xxx-xxxxxx корректен")
                try:
                    payload_json = json.loads(cleaned_payload)
                    logger.info(f"Успешно разобран JSON: {payload_json}")
                    return "valid_rc_format", payload_json, "Valid RC-xxx-xxxxxx format"
                except json.JSONDecodeError as e:
                    logger.warning(f"Ошибка разбора JSON в RC-xxx-xxxxxx: {str(e)}")
                    return "valid_rc_format", None, f"Valid RC-xxx-xxxxxx format but not JSON: {cleaned_payload}"
            else:
                logger.warning(f"Некорректный формат RC-xxx-xxxxxx: части={parts}, длина частей={len(parts)}")
                return "invalid_rc_format", None, f"Invalid RC-xxx-xxxxxx format: incorrect parts {parts}"
        except Exception as e:
            logger.error(f"Ошибка при разборе RC-xxx-xxxxxx: {str(e)}\n{traceback.format_exc()}")
            return "invalid_rc_format", None, f"Invalid RC-xxx-xxxxxx format: {str(e)}"

    # Проверка JSON строки
    logger.debug(f"Проверка payload как JSON: {cleaned_payload}")
    try:
        payload_json = json.loads(cleaned_payload)
        logger.debug(f"Успешно разобран JSON: {payload_json}")

        # Проверка на заказ FedEx склада или RC-xxx-xxxxxx в msg
        if isinstance(payload_json, dict):
            payload_msg = payload_json.get('msg', '')
            logger.debug(f"Извлечен msg из JSON: {payload_msg}, длина: {len(payload_msg)}")
            
            # Проверка на UPS код в msg
            if '37040' in payload_msg:
                logger.info(f"Обнаружен UPS код в msg: {payload_msg}")
                return "ups_code", payload_json, "UPS code detected in msg"
            
            # Проверка формата RC-xxx-xxxxxx в msg
            if len(payload_msg) == 13 and payload_msg.startswith('RC-'):
                try:
                    parts = payload_msg.split('-')
                    if len(parts) == 3 and len(parts[1]) == 3 and len(parts[2]) == 6 and parts[1].isalnum() and parts[2].isalnum():
                        logger.info("Обнаружен формат RC-xxx-xxxxxx в msg")
                        return "valid_rc_format", payload_json, "Valid RC-xxx-xxxxxx format in msg"
                    else:
                        logger.warning(f"Некорректный формат RC-xxx-xxxxxx в msg: части={parts}, длина частей={len(parts)}")
                        return "incorrect_format", None, f"Invalid RC-xxx-xxxxxx format in msg: incorrect parts {parts}"
                except Exception as e:
                    logger.error(f"Ошибка при разборе RC-xxx-xxxxxx в msg: {str(e)}\n{traceback.format_exc()}")
                    return "incorrect_format", None, f"Invalid RC-xxx-xxxxxx format in msg: {str(e)}"

            # Проверка на FedEx склад
            if 'FBA' in payload_msg and 'Coventry, West Midlands' in payload_msg and 'Lyons Park' in payload_msg:
                logger.info("Обнаружен заказ FedEx склада")
                return "fedex_warehouse", payload_json, "FedEx warehouse order"
            elif len(payload_msg) > 50:
                logger.info("Обнаружен заказ не FedEx склада")
                return "non_fedex_warehouse", payload_json, "Non-FedEx warehouse order"
            else:
                # ИСПРАВЛЕНИЕ: Проверяем, возможно это трек-код для уже зарегистрированного заказа
                device_id = payload_json.get('id', '')
                if device_id and device_id in tracking_manager.pending_orders:
                    logger.info(f"Найден ожидающий заказ для устройства {device_id}, обрабатываем как трек-код")
                    return "tracking_code", payload_json, "Potential tracking code for pending order"
                
                logger.warning(f"JSON корректен, но msg слишком короткий или не соответствует условиям: {payload_msg}")
                return "incorrect_format", None, "Incorrect format: msg too short or invalid"
        else:
            logger.warning(f"JSON не является словарем: {type(payload_json)}")
            return "incorrect_format", None, f"Invalid JSON format: expected dict, got {type(payload_json)}"

    except json.JSONDecodeError as e:
        logger.warning(f"Ошибка разбора JSON: {str(e)}")
        return "incorrect_format", None, f"Incorrect JSON format: {str(e)}"
    except Exception as e:
        logger.error(f"Неожиданная ошибка при обработке JSON: {str(e)}\n{traceback.format_exc()}")
        return "incorrect_format", None, f"Unexpected error: {str(e)}"
    
@app.route('/', methods=['GET'])
def health_check():
    """Проверка работоспособности сервера"""
    return jsonify({
        'status': 'OK',
        'service': 'Radiacode Manufacturing Server',
        'timestamp': datetime.now().isoformat()
    })


@app.route('/webhook/device', methods=['POST'])
def handle_device_scan():
    """Основной endpoint для обработки данных сканера"""
    try:
        # Получаем данные от EMQX
        data = request.get_json()
        logger.info(f"Получены данные: {data}")

        # Проверяем топик (если включена валидация)
        topic = data.get('topic', '')
        logger.info(f"Данные получены из топика: {topic}")
        
        if MANUFACTURING_CONFIG['TOPIC_VALIDATION_ENABLED']:
            allowed_topics = MANUFACTURING_CONFIG['ALLOWED_TOPICS']
            
            # Проверяем точное совпадение или по паттерну
            topic_allowed = False
            for allowed_topic in allowed_topics:
                if topic == allowed_topic or topic.startswith(allowed_topic):
                    topic_allowed = True
                    break
                    
            if not topic_allowed:
                logger.warning(f"Данные получены из неразрешенного топика: {topic}")
                return jsonify({
                    'error': 'Unauthorized topic',
                    'topic': topic,
                    'allowed_topics': allowed_topics
                }), 403

        # Парсим payload как JSON строку
        payload_str = data.get('payload', '{}')
        
        # Очищаем просроченные заказы перед обработкой
        tracking_manager.cleanup_expired()
        
        status, payload_json, message = check_payload(payload_str)
        logger.info(f"Результат проверки payload: status={status}, message={message}")
        
        match status:
            case "valid_rc_format":
                payload_json = json.loads(payload_str)
                # Извлекаем штрихкод (серийный номер)
                barcode = payload_json.get('msg', '').strip()
                
                logger.info(f"Парсинг: barcode={barcode}, topic={topic}")

                # Валидация штрихкода
                if not barcode:
                    logger.warning(f"Получен пустой штрихкод из payload: {payload_str}")
                    return jsonify({'error': 'Barcode is required'}), 400

                # Дополнительная валидация формата штрихкода Radiacode
                barcode_prefix = MANUFACTURING_CONFIG['BARCODE_PREFIX']
                min_length = MANUFACTURING_CONFIG['MIN_BARCODE_LENGTH']
                
                if not barcode.startswith(barcode_prefix) or len(barcode) < min_length:
                    logger.warning(f"Неверный формат штрихкода Radiacode: {barcode}")
                    return jsonify({
                        'error': f'Invalid barcode format. Expected format: {barcode_prefix}XXXXXXXXX (min {min_length} chars)'
                    }), 400

                # Выбираем действие в зависимости от топика
                if topic == 'production/ready':
                    # Записываем дату изготовления
                    success = manager.WriteManufacturingDate(barcode)
                    operation = 'manufacturing'
                    date_field = 'manufacturing_date'
                elif topic == 'sale/ready':
                    # Записываем дату продажи
                    success = manager.WriteSaleDate(barcode)
                    operation = 'sale'
                    date_field = 'sale_date'
                else:
                    # Этот случай не должен произойти из-за проверки топика выше
                    logger.error(f"Неизвестный топик: {topic}")
                    return jsonify({'error': 'Unknown topic'}), 500
                
                if success:
                    logger.info(f"Успешно записана {operation} дата для: {barcode} из топика: {topic}")
                    response_data = {
                        'status': 'success',
                        'barcode': barcode,
                        'topic': topic,
                        'operation': operation,
                        date_field: datetime.now().isoformat(),
                        'message': f'{operation.capitalize()} date recorded successfully'
                    }
                    return jsonify(response_data)
                else:
                    logger.error(f"Ошибка записи {operation} даты для: {barcode}")
                    return jsonify({'error': f'Failed to record {operation} date'}), 500

            case "fedex_warehouse":
                device_id = payload_json.get('id', '') if payload_json else ''
                tracking_manager.register_order(device_id, 'fedex_warehouse', payload_json)
                logger.info("Зарегистрирован заказ FedEx склада, ожидание трек-кода")
                return jsonify({
                    'status': 'pending', 
                    'message': 'FedEx warehouse order registered, waiting for tracking code',
                    'device_id': device_id,
                    'timeout_seconds': tracking_manager.cleanup_timeout
                }), 200

            case "non_fedex_warehouse":
                device_id = payload_json.get('id', '') if payload_json else ''
                tracking_manager.register_order(device_id, 'non_fedex_warehouse', payload_json)
                logger.info("Зарегистрирован заказ не FedEx склада, ожидание трек-кода")
                return jsonify({
                    'status': 'pending', 
                    'message': 'Non-FedEx warehouse order registered, waiting for tracking code',
                    'device_id': device_id,
                    'timeout_seconds': tracking_manager.cleanup_timeout
                }), 200

            case "ups_code":
                device_id = payload_json.get('id', '') if payload_json else ''
                
                # Проверяем, есть ли ожидающий заказ для этого устройства
                if device_id in tracking_manager.pending_orders:
                    success, result_message = tracking_manager.process_tracking_code(device_id, payload_json)
                    if success:
                        return jsonify({
                            'status': 'success', 
                            'message': result_message,
                            'device_id': device_id
                        }), 200
                    else:
                        return jsonify({
                            'status': 'error', 
                            'message': result_message,
                            'device_id': device_id
                        }), 400
                else:
                    # Если это первое сообщение с UPS кодом, регистрируем его
                    tracking_manager.register_order(device_id, 'ups_code', payload_json)
                    logger.info("Зарегистрирован UPS код, ожидание дополнительных данных")
                    return jsonify({
                        'status': 'pending', 
                        'message': 'UPS code registered, waiting for additional data',
                        'device_id': device_id,
                        'timeout_seconds': tracking_manager.cleanup_timeout
                    }), 200

            case "tracking_code":
                # ИСПРАВЛЕНИЕ: Новая обработка трек-кодов для уже зарегистрированных заказов
                device_id = payload_json.get('id', '') if payload_json else ''
                if device_id and device_id in tracking_manager.pending_orders:
                    success, result_message = tracking_manager.process_tracking_code(device_id, payload_json)
                    if success:
                        return jsonify({
                            'status': 'success', 
                            'message': result_message,
                            'device_id': device_id
                        }), 200
                    else:
                        return jsonify({
                            'status': 'error', 
                            'message': result_message,
                            'device_id': device_id
                        }), 400
                else:
                    logger.warning(f"Получен трек-код для неизвестного устройства: {device_id}")
                    return jsonify({
                        'status': 'error', 
                        'message': 'No pending order found for tracking code',
                        'device_id': device_id
                    }), 400

            case "incorrect_format":
                # ИСПРАВЛЕНИЕ: Проверяем, возможно это трек-код для уже зарегистрированного заказа
                if payload_json and isinstance(payload_json, dict):
                    device_id = payload_json.get('id', '')
                    if device_id and device_id in tracking_manager.pending_orders:
                        logger.info(f"Обрабатываем некорректный формат как трек-код для устройства {device_id}")
                        success, result_message = tracking_manager.process_tracking_code(device_id, payload_json)
                        if success:
                            return jsonify({
                                'status': 'success', 
                                'message': result_message,
                                'device_id': device_id
                            }), 200
                        else:
                            return jsonify({
                                'status': 'error', 
                                'message': result_message,
                                'device_id': device_id
                            }), 400
                
                logger.warning(f"Некорректный формат payload: {message}")
                return jsonify({'error': 'Invalid payload format', 'details': message}), 400

            case "invalid_rc_format":
                logger.warning(f"Некорректный формат RC-xxx-xxxxxx: {message}")
                return jsonify({'error': 'Invalid RC-xxx-xxxxxx format', 'details': message}), 400

            case _:
                logger.error(f"Неизвестный статус проверки payload: {status}")
                return jsonify({'error': 'Unknown payload status', 'details': message}), 400    

    except json.JSONDecodeError as e:
        logger.error(f"Ошибка парсинга JSON payload: {e}")
        return jsonify({'error': 'Invalid JSON payload'}), 400
    except Exception as e:
        logger.error(f"Общая ошибка: {e}")
        return jsonify({'error': f'Server error: {str(e)}'}), 500


@app.route('/api/device/<serial>', methods=['GET'])
def get_manufacturing_date(serial):
    """GET endpoint для получения даты изготовления по серийному номеру"""
    try:
        if not serial or not serial.strip():
            return jsonify({"success": False, "message": "Серийный номер пустой"})

        serial = serial.strip()
        logger.info(f"Запрос даты изготовления для: {serial}")

        # Читаем дату изготовления
        manufacturing_date = manager.ReadManufacturingDate(serial)
        
        if manufacturing_date is None:
            return jsonify({
                "success": False,
                "message": "Устройство не найдено",
                "serial": serial
            }), 404

        # Проверяем, что дата изготовления не старше 1 часа
        current_time = datetime.now()
        time_diff = current_time - manufacturing_date
        
        # Если разница меньше 1 часа (3600 секунд)
        is_fresh = time_diff.total_seconds() <= 3600
        
        return jsonify({
            "success": True,
            "serial": serial,
            "manufacturing_date": manufacturing_date.isoformat(),
            "is_fresh": is_fresh,
            "age_seconds": int(time_diff.total_seconds()),
            "age_minutes": int(time_diff.total_seconds() / 60),
            "status": "ready" if is_fresh else "expired"
        })

    except Exception as e:
        logger.error(f"Ошибка получения даты изготовления для {serial}: {e}")
        return jsonify({"success": False, "message": f"Ошибка: {str(e)}"}), 500


@app.route('/api/devices', methods=['GET'])
def get_devices():
    """Получение списка недавно изготовленных устройств"""
    try:
        # Получаем параметры из запроса
        limit = request.args.get('limit', 10, type=int)
        minutes = request.args.get('minutes', 30, type=int)
        
        # Используем новый UTC метод из RadiacodeManager
        devices_data = manager.GetRecentDevices(minutes=minutes, limit=limit)
        
        # Форматируем данные для совместимости с фронтендом
        devices = []
        for device in devices_data:
            device_info = {
                'barcode': device['serial'],
                'serial': device['serial'],
                'manufacturing_date': device['manufacturing_date'].isoformat() if device['manufacturing_date'] else None,
                'sale_date': device['sale_date'].isoformat() if device['sale_date'] else None,
                'status': device['status'],
                'age_minutes': device['age_minutes'],
                'age_seconds': device['age_seconds'],
                'scan_timestamp': device['manufacturing_date'].isoformat() if device['manufacturing_date'] else None,
                'timestamp': device['manufacturing_date'].strftime('%d.%m.%Y %H:%M') if device['manufacturing_date'] else 'Unknown',
                'scanner_id': 'manufacturing'
            }
            devices.append(device_info)

        logger.info(f"Найдено {len(devices)} устройств за последние {minutes} минут (UTC)")
        
        return jsonify({
            'success': True,
            'devices': devices,
            'count': len(devices),
            'message': f'Found {len(devices)} devices manufactured in last {minutes} minutes'
        })

    except Exception as e:
        logger.error(f"Ошибка получения устройств: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'devices': []
        }), 500
    

@app.route('/api/getalldevices/<serial>', methods=['GET'])
def get_device_by_serial(serial):
    """
    GET endpoint для получения ВСЕХ полей устройства по серийному номеру
    URL: localhost:3000/api/devices/RC-103G-001665
    """
    try:
        if not serial or not serial.strip():
            return jsonify({
                "success": False, 
                "message": "Серийный номер пустой",
                "serial": serial
            }), 400

        serial = serial.strip()
        logger.info(f"Запрос всех данных для устройства: {serial}")

        # Используем функцию ReadManufacturingDateAll
        device_data = manager.ReadManufacturingDateAll(serial)
        
        if device_data is None:
            return jsonify({
                "success": False,
                "message": "Устройство не найдено",
                "serial": serial
            }), 404

        return jsonify({
            "success": True,
            "serial": serial,
            "device_data": device_data,
            "message": f"Найдено устройство {serial}"
        })

    except Exception as e:
        logger.error(f"Ошибка получения данных для {serial}: {e}")
        return jsonify({
            "success": False,
            "message": f"Ошибка сервера: {str(e)}",
            "serial": serial
        }), 500    

@app.route('/api/check-status', methods=['POST'])
def check_device_status():
    """POST endpoint для проверки статуса устройства по штрихкоду (для совместимости)"""
    try:
        data = request.get_json()
        barcode = data.get("barcode", "").strip()

        if not barcode:
            return jsonify({"success": False, "message": "Штрихкод пустой"})

        # Читаем дату изготовления
        manufacturing_date = manager.ReadManufacturingDate(barcode)
        
        if manufacturing_date is None:
            return jsonify({
                "success": True,
                "scanned": False,
                "message": "Устройство не найдено или не отсканировано"
            })

        # Проверяем, что дата изготовления не старше 1 часа
        current_time = datetime.now()
        time_diff = current_time - manufacturing_date
        
        # Если разница меньше 1 часа (3600 секунд)
        if time_diff.total_seconds() <= 3600:
            return jsonify({
                "success": True,
                "scanned": True,
                "status": "ready",
                "manufacturing_date": manufacturing_date.isoformat(),
                "message": f"Устройство готово (отсканировано {int(time_diff.total_seconds())} секунд назад)"
            })
        else:
            return jsonify({
                "success": True,
                "scanned": True,
                "status": "expired",
                "manufacturing_date": manufacturing_date.isoformat(),
                "message": f"Устройство отсканировано более часа назад ({int(time_diff.total_seconds() / 60)} минут)"
            })

    except Exception as e:
        logger.error(f"Ошибка проверки статуса: {e}")
        return jsonify({"success": False, "message": f"Ошибка: {str(e)}"})


@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Получение статистики (упрощенная версия)"""
    try:
        return jsonify({
            'date': datetime.now().date().isoformat(),
            'service': 'Radiacode Manufacturing Server',
            'status': 'active'
        })
    except Exception as e:
        logger.error(f"Ошибка получения статистики: {e}")
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    logger.info("🚀 Запуск Radiacode Manufacturing сервера...")
    logger.info("📋 Доступные endpoints:")
    logger.info("   GET  /                      - Проверка здоровья")
    logger.info("   POST /webhook/device        - Прием данных от EMQX")
    logger.info("   GET  /api/device/<serial>   - Получение даты изготовления по серийнику")
    logger.info("   POST /api/check-status      - Проверка статуса (совместимость)")
    logger.info("   GET  /api/stats             - Статистика")
    logger.info("   GET  /api/devices           - Совместимость (возвращает пустой список)")

    # Проверка подключения к БД при запуске
    try:
        # Проверяем, что класс RadiacodeManager импортирован и работает
        logger.info("✅ RadiacodeManager успешно импортирован из AzureConnector")
        logger.info(f"✅ Manager создан: {type(manager).__name__}")
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации RadiacodeManager: {e}")

    app.run(host='0.0.0.0', port=3000, debug=False)
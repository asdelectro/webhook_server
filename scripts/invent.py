#!/usr/bin/env python3
import sys
import json
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from logger_config import get_invent_logger
from Digitkey_API import DigiKeyClient  # импортируем твой класс

logger = get_invent_logger()

RS = '\x1e'  # Record Separator
GS = '\x1d'  # Group Separator
EOT = '\x04' # End of Transmission

# ===== Настройка клиента Digi-Key =====
DIGIKEY_CLIENT_ID = "s72V1FevIthESyuv3HwWoG1ihutJcCdmfhnmwLjH6p1uAZ4J"
DIGIKEY_CLIENT_SECRET = "lXRuQUfdZvRDCOpqfTAnOjNUkjfIAudCg1f0xkTxbLcypSaXPCbuiGlcK9os62oR"
dk_client = DigiKeyClient(DIGIKEY_CLIENT_ID, DIGIKEY_CLIENT_SECRET)

def parse_digikey_payload(payload_str):
    payload_str = payload_str.replace(EOT, '')
    records = payload_str.split(RS)
    return [record for record in records if record.strip()]

def extract_part_qty(record):
    part_number = None
    quantity = None
    fields = record.split(GS)
    for field in fields:
        if field.startswith('P'):
            part_number = field[1:]
        elif field.startswith('Q'):
            quantity = field[1:]
    return part_number or 'N/A', quantity or 'N/A'

def process_sale(data):
    logger.info(f"Received data: {data}")

    try:
        raw_payload = data.get('payload', '{}')

        # Экранируем управляющие символы для json.loads
        safe_payload = re.sub(r'[\x00-\x1f]', lambda m: '\\u%04x' % ord(m.group()), raw_payload)
        payload = json.loads(safe_payload)
        msg = payload.get('msg', '')

        # Разделяем header и остальную часть
        if msg.startswith('[)>'):
            header, rest = msg.split('\x1e', 1)
        else:
            header, rest = '', msg

        records = parse_digikey_payload(rest)
        data_record = records[0] if records else ''
        part_number, quantity = extract_part_qty(data_record)

        # Получаем производитель и номинал через API
        if part_number != 'N/A':
            info = dk_client.get_basic_info(part_number)
            manufacturer = info.get("manufacturer") if info else "N/A"
            nominal = info.get("nominal") if info else "N/A"
        else:
            manufacturer = "N/A"
            nominal = "N/A"

        # Логируем всё в одну строку
        logger.info(f"Digi-Key Header: {header} | Part Number: {part_number} | Quantity: {quantity} | Manufacturer: {manufacturer} | Nominal: {nominal}")

        return records
    except Exception as e:
        logger.error(f"Error parsing payload: {e}")
        return []

if __name__ == '__main__':
    try:
        if len(sys.argv) > 1:
            data = json.loads(sys.argv[1])
        else:
            data = json.load(sys.stdin)

        process_sale(data)
    except Exception as e:
        logger.error(f"Fatal error: {e}")

import mysql.connector
from mysql.connector import Error
from datetime import datetime
import os
from dotenv import load_dotenv
import base64
import logging
from pathlib import Path
from datetime import datetime, timezone

load_dotenv()

# Настройка логирования - ТОЛЬКО в файл, БЕЗ StreamHandler
log_dir = Path('/home/asd/webhook_server/logs')
log_dir.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_dir / 'azure_connector.log', encoding='utf-8')
        # StreamHandler() УБРАН - логи НЕ идут в stdout
    ]
)
logger = logging.getLogger(__name__)


class RadiacodeManager:
    """
    Manager class for Radiacode device database operations
    """

    def __init__(self):
        self.MYSQL_HOST = os.getenv("MYSQL_HOST")
        self.MYSQL_PORT = int(os.getenv("MYSQL_PORT", 3306))
        self.MYSQL_USERNAME = os.getenv("MYSQL_USERNAME")
        self.MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD")
        self.MYSQL_DATABASE = os.getenv("MYSQL_DATABASE")

    def _get_connection(self):
        """Create and return database connection"""
        return mysql.connector.connect(
            host=self.MYSQL_HOST,
            port=self.MYSQL_PORT,
            user=self.MYSQL_USERNAME,
            password=self.MYSQL_PASSWORD,
            database=self.MYSQL_DATABASE,
            ssl_disabled=True,
            autocommit=True,
        )

    def _check_device_exists(self, serial):
        """
        Check if device with given serial number exists

        Args:
            serial: device serial number (str)

        Returns:
            bool: True if device exists, False otherwise
        """
        try:
            connection = self._get_connection()
            cursor = connection.cursor()

            query = """
            SELECT SerialNumber, ManufDate, SaleDate 
            FROM radiacode 
            WHERE SerialNumber = %s
            """

            cursor.execute(query, (serial,))
            result = cursor.fetchone()

            if result:
                serial_num, manuf_date, sale_date = result
                logger.info(f"Device found: {serial_num}")
                logger.info(f"Current ManufDate: {manuf_date.isoformat() if manuf_date else 'Not set'}")
                logger.info(f"Current SaleDate: {sale_date.isoformat() if sale_date else 'Not set'}")
                return True
            else:
                logger.warning(f"Device with serial number {serial} not found")
                return False

        except Error as e:
            logger.error(f"Database error: {e}")
            return False
        except Exception as e:
            logger.error(f"General error: {e}")
            return False
        finally:
            if "connection" in locals():
                if connection.is_connected():
                    cursor.close()
                    connection.close()

    def WriteManufacturingDate(self, serial):
        """
        Write current server time as manufacturing date for specified serial number

        Args:
            serial: device serial number (str)
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not self._check_device_exists(serial):
            return False

        current_time = datetime.now(timezone.utc).replace(tzinfo=None)
        logger.info(f"Will set ManufDate to: {current_time.isoformat()}")

        try:
            connection = self._get_connection()
            cursor = connection.cursor()

            query = """
            UPDATE radiacode 
            SET ManufDate = %s
            WHERE SerialNumber = %s
            """

            cursor.execute(query, (current_time, serial))

            if cursor.rowcount > 0:
                logger.info(f"Manufacturing date updated for {serial}: {current_time.isoformat()}")
                return True
            else:
                logger.warning(f"Update failed for {serial}")
                return False

        except Error as e:
            logger.error(f"Database error: {e}")
            return False
        except Exception as e:
            logger.error(f"General error: {e}")
            return False
        finally:
            if "connection" in locals():
                if connection.is_connected():
                    cursor.close()
                    connection.close()

    def WriteSaleDate(self, serial):
        """
        Write current server time as sale date for specified serial number

        Args:
            serial: device serial number (str)
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not self._check_device_exists(serial):
            return False

        current_time = datetime.now(timezone.utc).replace(tzinfo=None)
        logger.info(f"Will set SaleDate to: {current_time.isoformat()}")

        try:
            connection = self._get_connection()
            cursor = connection.cursor()

            query = """
            UPDATE radiacode 
            SET SaleDate = %s
            WHERE SerialNumber = %s
            """

            cursor.execute(query, (current_time, serial))

            if cursor.rowcount > 0:
                logger.info(f"Sale date updated for {serial}: {current_time.isoformat()}")
                return True
            else:
                logger.warning(f"Update failed for {serial}")
                return False

        except Error as e:
            logger.error(f"Database error: {e}")
            return False
        except Exception as e:
            logger.error(f"General error: {e}")
            return False
        finally:
            if "connection" in locals():
                if connection.is_connected():
                    cursor.close()
                    connection.close()

    def ReadManufacturingDate(self, serial):
        """
        Read manufacturing date for specified serial number

        Args:
            serial: device serial number (str)

        Returns:
            datetime or None: manufacturing date if found
        """
        try:
            connection = self._get_connection()
            cursor = connection.cursor()

            query = """
            SELECT ManufDate 
            FROM radiacode 
            WHERE SerialNumber = %s
            """

            cursor.execute(query, (serial,))
            result = cursor.fetchone()

            if result:
                manuf_date = result[0]
                logger.info(f"Manufacturing date for {serial}: {manuf_date.isoformat() if manuf_date else 'Not set'}")
                return manuf_date
            else:
                logger.warning(f"Device with serial number {serial} not found")
                return None

        except Error as e:
            logger.error(f"Database error: {e}")
            return None
        except Exception as e:
            logger.error(f"General error: {e}")
            return None
        finally:
            if "connection" in locals():
                if connection.is_connected():
                    cursor.close()
                    connection.close()

    def ReadManufacturingDateAll(self, serial):
        """
        Read ALL fields for specified serial number

        Args:
            serial: device serial number (str)

        Returns:
            dict or None: all device fields if found, None if not found
        """
        try:
            connection = self._get_connection()
            cursor = connection.cursor(dictionary=True)

            query = """
            SELECT * 
            FROM radiacode 
            WHERE SerialNumber = %s
            """

            cursor.execute(query, (serial,))
            result = cursor.fetchone()

            if result:
                logger.info(f"All data for {serial}: found {len(result)} fields")
                
                # Конвертируем все значения для JSON совместимости
                formatted_result = {}
                for key, value in result.items():
                    if isinstance(value, datetime):
                        formatted_result[key] = value.isoformat()
                        logger.debug(f"  {key}: {value.isoformat()}")
                    elif isinstance(value, bytes):
                        # Конвертируем bytes в base64 строку
                        formatted_result[key] = base64.b64encode(value).decode('utf-8')
                        logger.debug(f"  {key}: <bytes data, length: {len(value)}>")
                    elif value is None:
                        formatted_result[key] = None
                        logger.debug(f"  {key}: None")
                    else:
                        formatted_result[key] = value
                        logger.debug(f"  {key}: {value}")
                
                return formatted_result
            else:
                logger.warning(f"Device with serial number {serial} not found")
                return None

        except Error as e:
            logger.error(f"Database error: {e}")
            return None
        except Exception as e:
            logger.error(f"General error: {e}")
            return None
        finally:
            if "connection" in locals():
                if connection.is_connected():
                    cursor.close()
                    connection.close()

    def ReadSaleDate(self, serial):
        """
        Read sale date for specified serial number

        Args:
            serial: device serial number (str)

        Returns:
            datetime or None: sale date if found
        """
        try:
            connection = self._get_connection()
            cursor = connection.cursor()

            query = """
            SELECT SaleDate 
            FROM radiacode 
            WHERE SerialNumber = %s
            """

            cursor.execute(query, (serial,))
            result = cursor.fetchone()

            if result:
                sale_date = result[0]
                logger.info(f"Sale date for {serial}: {sale_date.isoformat() if sale_date else 'Not set'}")
                return sale_date
            else:
                logger.warning(f"Device with serial number {serial} not found")
                return None

        except Error as e:
            logger.error(f"Database error: {e}")
            return None
        except Exception as e:
            logger.error(f"General error: {e}")
            return None
        finally:
            if "connection" in locals():
                if connection.is_connected():
                    cursor.close()
                    connection.close()

    def GetRecentDevices(self, minutes=30, limit=30):
        """
        Get devices that were manufactured in the last N minutes (using UTC time)

        Args:
            minutes: number of minutes to look back (default: 30)
            limit: maximum number of devices to return (default: 30)

        Returns:
            list: List of dictionaries with device information, or empty list on error
        """
        try:
            connection = self._get_connection()
            cursor = connection.cursor()
            query = """
            SELECT SerialNumber, ManufDate, SaleDate
            FROM radiacode
            WHERE ManufDate >= UTC_TIMESTAMP() - INTERVAL %s MINUTE
            ORDER BY ManufDate DESC
            LIMIT %s
            """

            cursor.execute(query, (minutes, limit))
            results = cursor.fetchall()

            devices = []
            current_time_utc = datetime.now(timezone.utc).replace(tzinfo=None)
            
            for result in results:
                serial, manuf_date, sale_date = result
                
                if manuf_date:
                    time_diff = current_time_utc - manuf_date
                    age_minutes = int(time_diff.total_seconds() / 60)
                    age_seconds = int(time_diff.total_seconds())
                    
                    status = "ready" if time_diff.total_seconds() <= 3600 else "expired"
                    
                    device_info = {
                        'serial': serial,
                        'manufacturing_date': manuf_date,
                        'sale_date': sale_date,
                        'age_minutes': age_minutes,
                        'age_seconds': age_seconds,
                        'status': status
                    }
                    devices.append(device_info)

            logger.info(f"Found {len(devices)} devices manufactured in last {minutes} minutes (UTC)")
            return devices

        except Error as e:
            logger.error(f"Database error: {e}")
            return []
        except Exception as e:
            logger.error(f"General error: {e}")
            return []
        finally:
            if "connection" in locals():
                if connection.is_connected():
                    cursor.close()
                    connection.close()


# Example usage
if __name__ == "__main__":
    manager = RadiacodeManager()

    # Write manufacturing date
    manager.WriteManufacturingDate("RC-103G-001665")

    # Write sale date
    manager.WriteSaleDate("RC-103G-001665")

    # Read manufacturing date
    manager.ReadManufacturingDate("RC-103G-001665")

    # Read sale date
    manager.ReadSaleDate("RC-103G-001665")
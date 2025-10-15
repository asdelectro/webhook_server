import requests
import json
from typing import Optional, Dict, Any, Tuple

class InvenTreeStockManager:
    """
    Manages the addition of new devices to InvenTree, encapsulating all API logic.
    """

    def __init__(self):
        """
        Initializes the API client with fixed configuration.
        """
        self._INVENTREE_URL = "http://192.168.88.132:8080"
        self._API_TOKEN = "inv-3d1c37e2156c24a5af7e384099de32dfd12e522d-20251015"
        self._HEADERS = {
            "Authorization": f"Token {self._API_TOKEN}",
            "Content-Type": "application/json",
        }
        self._PARTS_URL = f"{self._INVENTREE_URL}/api/part/"
        self._STOCK_URL = f"{self._INVENTREE_URL}/api/stock/"
        self._LOCATIONS_URL = f"{self._INVENTREE_URL}/api/stock/location/"

    def _find_part_by_ipn(self, ipn: str) -> Optional[Dict[str, Any]]:
        """
        Internal method to find a part by its IPN.
        """
        params = {"IPN": ipn}
        try:
            r = requests.get(self._PARTS_URL, headers=self._HEADERS, params=params)
            r.raise_for_status()
            data = r.json()
            return data[0] if data else None
        except requests.exceptions.RequestException as e:
            print(f"Error finding part: {e}")
            return None

    def _get_location_id(self, name: str = "ReadyDevices") -> Optional[int]:
        """
        Internal method to get a location's ID by name.
        """
        try:
            r = requests.get(self._LOCATIONS_URL, headers=self._HEADERS, params={"name": name})
            r.raise_for_status()
            results = r.json()
            return results[0]["pk"] if results else None
        except requests.exceptions.RequestException as e:
            print(f"Error getting location: {e}")
            return None

    def _create_stock_item(
        self,
        part_id: int,
        serial: str,
        quantity: int = 1,
        location_name: str = "ReadyDevices",
    ) -> Tuple[bool, Any]:
        """
        Internal method to create a new stock item.
        """
        location_id = self._get_location_id(location_name)
        if location_id is None:
            return False, f"Could not find location '{location_name}'."

        payload = {
            "part": part_id,
            "quantity": quantity,
            "serial_numbers": serial,
            "status": 10,  # OK
            "location": location_id,
        }
        try:
            r = requests.post(self._STOCK_URL, headers=self._HEADERS, json=payload)
            if r.status_code in (200, 201):
                return True, r.json()
            else:
                return False, f"Error {r.status_code}: {r.text}"
        except requests.exceptions.RequestException as e:
            return False, str(e)

    def add_device_by_serial(self, serial: str) -> Tuple[bool, str]:
        """
        Adds a new device to InvenTree based on its serial number.

        This is the main public method. It handles all necessary steps:
        1. Extracts the IPN from the serial number.
        2. Finds the corresponding part in InvenTree.
        3. Creates a new stock item for the device.

        Args:
            serial (str): The serial number of the device (e.g., "RC-110-666667").

        Returns:
            Tuple[bool, str]: A tuple containing a boolean indicating success and a string
                              with either a success message or an error reason.
        """
        # 1. Extract IPN from the serial number
        parts = serial.split("-")
        ipn = "-".join(parts[:2]) if len(parts) > 1 else parts[0]
        if not ipn:
            return False, "Could not extract IPN from serial number."
        
        # 2. Find the part by IPN
        part = self._find_part_by_ipn(ipn)
        if not part:
            return False, f"Part with IPN '{ipn}' not found in InvenTree."

        # 3. Create a stock item
        success, result = self._create_stock_item(part_id=part["pk"], serial=serial)
        
        if success:
            return True, "Device successfully added."
        else:
            return False, f"Failed to add device: {result}"

# --- USAGE EXAMPLE ---

if __name__ == "__main__":
    manager = InvenTreeStockManager()

    # --- Test with a valid serial number ---
    test_serial_success = "RC-110-777778"
    print(f"Attempting to add device with serial: {test_serial_success}")
    success, message = manager.add_device_by_serial(test_serial_success)

    if success:
        print(f"✅ Success: {message}")
    else:
        print(f"❌ Failure: {message}")
        
    print("-" * 20)

    # --- Test with an invalid serial number (part does not exist) ---
    test_serial_fail = "XYZ-999-000000"
    print(f"Attempting to add device with serial: {test_serial_fail}")
    success, message = manager.add_device_by_serial(test_serial_fail)
    
    if success:
        print(f"✅ Success: {message}")
    else:
        print(f"❌ Failure: {message}")
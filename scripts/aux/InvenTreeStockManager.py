#!/usr/bin/env python3
"""
InvenTree Stock Manager - Creates ready devices using Build Orders
Replaces the old simple stock creation with full production automation
"""
from inventree.api import InvenTreeAPI
from inventree.part import Part
from inventree.build import Build
from inventree.stock import StockLocation, StockItem
from typing import Tuple
import time


class InvenTreeStockManager:
    """
    Manages the addition of new devices to InvenTree using Build Orders.
    All internal methods are private (prefixed with _).
    """

    def __init__(self, logger=None):
        """
        Initializes the API client with fixed configuration.
        
        Args:
            logger: Optional logger instance. If None, will use print statements.
        """
        self._INVENTREE_URL = "http://192.168.88.132:8080"
        self._API_TOKEN = "inv-3d1c37e2156c24a5af7e384099de32dfd12e522d-20251015"
        self._DEFECTIVE_LOCATION_ID = 32  # Exclude from allocation
        self._api = InvenTreeAPI(self._INVENTREE_URL, token=self._API_TOKEN)
        self._logger = logger
    
    def _log(self, message: str, level: str = 'info'):
        """Internal logging method"""
        if self._logger:
            getattr(self._logger, level)(message)
        else:
            print(message)

    def add_device_by_serial(self, serial: str, location: str = "ReadyDevices") -> Tuple[bool, str]:
        """
        Adds a new device to InvenTree based on its serial number.

        This is the main public method. It handles all necessary steps:
        1. Extracts the IPN from the serial number.
        2. Finds the corresponding part in InvenTree.
        3. Creates a Build Order and allocates components.
        4. Completes the build and creates the device in stock.

        Args:
            serial (str): The serial number of the device (e.g., "RC-102-011243").
            location (str): Target location name (default: "ReadyDevices").

        Returns:
            Tuple[bool, str]: A tuple containing a boolean indicating success and a string
                              with either a success message or an error reason.
        """
        try:
            self._log("=" * 60)
            self._log(f"Creating device: {serial}")
            self._log(f"Target location: {location}")
            self._log("=" * 60)

            # 1. Check if serial number already exists
            if self._serial_exists(serial):
                return True, f"Device with serial {serial} already exists in InvenTree. Skipping creation."

            # 2. Extract IPN from serial number
            ipn = self._extract_ipn_from_serial(serial)
            if not ipn:
                return False, "Could not extract IPN from serial number."
            self._log(f"Extracted IPN: {ipn}")

            # 3. Find part by IPN
            assembly_part = self._find_part(ipn)
            if not assembly_part:
                return False, f"Part with IPN '{ipn}' not found in InvenTree."

            # 4. Find target location
            target_location_id = self._find_location(location)
            if not target_location_id:
                return False, f"Could not find location '{location}'."

            # 4. Create and issue build
            build = self._create_build(assembly_part)
            if not build:
                return False, "Failed to create build order."

            # 5. Auto-allocate components
            if not self._auto_allocate(build, assembly_part):
                return False, "Failed to allocate components."

            # 6. Create output with serial number
            output_id = self._create_output(build, serial)
            if not output_id:
                return False, "Failed to create build output."

            # 7. Move to target location
            self._move_to_location(output_id, target_location_id, location)

            # 8. Complete and finish build
            if not self._complete_build(build, output_id, target_location_id):
                return False, "Failed to complete build."

            # 9. Verify success
            if self._verify_completion(build):
                return True, "Device successfully added."
            else:
                return False, "Build completed but status verification failed."

        except Exception as e:
            return False, f"Error: {str(e)}"

    def _extract_ipn_from_serial(self, serial: str) -> str:
        """Extract IPN from serial number (RC-102-011243 -> RC-102)"""
        parts = serial.split('-')
        if len(parts) >= 2:
            # Handle RC-103G case (3 parts before number)
            if len(parts) >= 3 and parts[2].isalpha():
                return f"{parts[0]}-{parts[1]}{parts[2]}"
            else:
                return f"{parts[0]}-{parts[1]}"
        return ""

    def _serial_exists(self, serial: str) -> bool:
        """
        Check if a stock item with this serial number already exists
        Returns True if exists, False otherwise
        """
        self._log(f"Checking if serial {serial} already exists...")
        try:
            # Search for stock items with this serial number
            stock_items = StockItem.list(self._api, serial=serial)
            
            if stock_items:
                self._log(f"✓ Serial {serial} already exists (Stock ID: {stock_items[0].pk})")
                return True
            
            self._log(f"✓ Serial {serial} is unique, proceeding with creation")
            return False
            
        except Exception as e:
            self._log(f"⚠ Warning: Could not check serial existence: {e}")
            # В случае ошибки проверки - продолжаем (безопаснее создать, чем пропустить)
            return False

    def _find_part(self, ipn: str) -> Part:
        """Find assembly part by IPN"""
        self._log(f"Searching for part by IPN: '{ipn}'...")
        parts = Part.list(self._api, IPN=ipn, assembly=True)

        if not parts:
            self._log(f"ERROR: Part with IPN '{ipn}' not found as assembly")
            return None

        part = parts[0]
        self._log(f"✓ Part found: {part.name} (IPN: {part.IPN}, ID: {part.pk})")
        return part

    def _find_location(self, location_name: str) -> int:
        """Find location ID by name"""
        self._log(f"Searching for location: '{location_name}'...")
        locations = StockLocation.list(self._api)

        for loc in locations:
            if loc.name == location_name:
                self._log(f"✓ Location found: {loc.name} (ID: {loc.pk})")
                return loc.pk

        self._log(f"ERROR: Location '{location_name}' not found")
        return None

    def _create_build(self, assembly_part: Part) -> Build:
        """Create and issue build order"""
        self._log(f"Creating build order for 1 unit...")
        build_data = {
            "part": assembly_part.pk,
            "quantity": 1,
            "title": f"Production of {assembly_part.name}",
        }

        build = Build.create(self._api, data=build_data)
        self._log(f"✓ Build created: ID {build.pk}")

        # Issue build
        self._log("Issuing build...")
        self._api.post(f"{self._api.base_url}/api/build/{build.pk}/issue/", data={})
        self._log("✓ Issued")

        return build

    def _auto_allocate(self, build: Build, assembly_part: Part) -> bool:
        """Auto-allocate components (excluding defective location)"""
        self._log("\nAuto-allocating components (excluding DefectiveParts)...")

        # Get BOM items
        bom_items = self._api.get(
            f"{self._api.base_url}/api/bom/",
            params={"part": assembly_part.pk, "sub_part_detail": "true"}
        )

        if not bom_items:
            self._log("⚠ No BOM items found")
            return False

        success = True
        for bom_item in bom_items:
            sub_part_id = bom_item["sub_part"]
            required_qty = bom_item["quantity"]
            bom_item_id = bom_item["pk"]

            # Get IPN for display
            sub_part_detail = bom_item.get("sub_part_detail")
            if sub_part_detail:
                ipn = sub_part_detail.get("IPN", "N/A")
            else:
                part_obj = Part(self._api, sub_part_id)
                ipn = part_obj.IPN if hasattr(part_obj, "IPN") else "N/A"

            # Find OK stock items (status=10), excluding DefectiveParts
            all_stock = StockItem.list(self._api, part=sub_part_id, in_stock=True)
            ok_stock = [
                item for item in all_stock
                if item.status == 10 and item.location != self._DEFECTIVE_LOCATION_ID
            ]

            if not ok_stock:
                self._log(f"  ✗ No OK stock found for {ipn}")
                success = False
                continue

            # Get build line
            build_lines = self._api.get(
                f"{self._api.base_url}/api/build/line/",
                params={"build": build.pk, "bom_item": bom_item_id}
            )

            if not build_lines:
                self._log(f"  ✗ No build line found for {ipn}")
                success = False
                continue

            build_line_id = build_lines[0]["pk"]
            stock_item = ok_stock[0]

            # Allocate
            alloc_data = {
                "build": build.pk,
                "build_line": build_line_id,
                "stock_item": stock_item.pk,
                "quantity": required_qty,
            }

            try:
                self._api.post(
                    f"{self._api.base_url}/api/build/item/",
                    data=alloc_data
                )
                self._log(f"  ✓ Allocated {ipn}: {required_qty} units from stock {stock_item.pk}")
            except Exception as e:
                self._log(f"  ✗ Failed to allocate {ipn}: {e}")
                success = False

        self._log("✓ Allocation completed")
        return success

    def _create_output(self, build: Build, serial: str) -> int:
        """Create build output with serial number"""
        self._log(f"Creating output with serial: {serial}...")

        output_payload = {
            "quantity": 1,
            "serial_numbers": serial
        }

        try:
            output_data = self._api.post(
                f"{self._api.base_url}/api/build/{build.pk}/create-output/",
                data=output_payload
            )

            output_id = (
                output_data[0]["pk"]
                if isinstance(output_data, list)
                else output_data["outputs"][0]["pk"]
            )

            self._log(f"✓ Output created: ID {output_id}")
            return output_id

        except Exception as e:
            self._log(f"✗ Failed to create output: {e}")
            return None

    def _move_to_location(self, output_id: int, location_id: int, location_name: str):
        """Move output to target location"""
        self._log(f"Moving to location '{location_name}'...")
        stock_item = StockItem(self._api, output_id)
        stock_item.location = location_id
        stock_item.save()
        self._log(f"✓ Moved to location (ID: {location_id})")
        time.sleep(1)

    def _complete_build(self, build: Build, output_id: int, location_id: int) -> bool:
        """Complete and finish build order"""
        # Step 1: Complete outputs
        self._log("\nStep 1: Completing outputs...")
        complete_data = {
            "outputs": [{"output": output_id}],
            "location": location_id,
            "accept_incomplete": False,
            "accept_unallocated": False,
        }

        try:
            self._api.post(
                f"{self._api.base_url}/api/build/{build.pk}/complete/",
                data=complete_data
            )
            self._log("✓ Outputs completed")
        except Exception as e:
            self._log(f"✗ Complete failed: {e}")
            return False

        time.sleep(1)

        # Step 2: Finish build
        self._log("\nStep 2: Finishing build...")
        try:
            self._api.post(
                f"{self._api.base_url}/api/build/{build.pk}/finish/",
                data={}
            )
            self._log("✓ Build finished")
        except Exception as e:
            self._log(f"✗ Finish failed: {e}")
            return False

        time.sleep(1)
        return True

    def _verify_completion(self, build: Build) -> bool:
        """Verify build completion"""
        build_final = Build(self._api, build.pk)

        self._log(f"" + "=" * 60)
        self._log(f"Build Status: {build_final.status}")
        self._log(f"Build Completed: {build_final.completed}")
        self._log("=" * 60)

        if build_final.status == 40:
            self._log(f"✓ SUCCESS: Build {build.pk} COMPLETE!")
            return True
        else:
            self._log(f"✗ Status: {build_final.status} (expected 40 for COMPLETE)")
            return False


# --- USAGE EXAMPLE ---

if __name__ == "__main__":
    # Option 1: Without logger (will use print)
    manager = InvenTreeStockManager()

    # Option 2: With logger (recommended for production)
    # from logger_config import get_manufacturing_logger
    # logger = get_manufacturing_logger()
    # manager = InvenTreeStockManager(logger=logger)

    # --- Test with a valid serial number ---
    test_serial_success = "RC-102-011243"
    print(f"Attempting to add device with serial: {test_serial_success}")
    success, message = manager.add_device_by_serial(test_serial_success)

    if success:
        print(f"✅ Success: {message}")
    else:
        print(f"❌ Failure: {message}")

    print("-" * 20)

    # --- Test with another serial number ---
    test_serial_success2 = "RC-110-777778"
    print(f"Attempting to add device with serial: {test_serial_success2}")
    success, message = manager.add_device_by_serial(test_serial_success2)

    if success:
        print(f"✅ Success: {message}")
    else:
        print(f"❌ Failure: {message}")
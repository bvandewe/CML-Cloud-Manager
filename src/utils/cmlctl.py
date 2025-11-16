#!/opt/cml/venv/bin/python
"""
CML Control Utility (cmlctl)

A general-purpose utility to control devices in Cisco Modeling Labs (CML).
Supports start, stop, wipe operations on one or multiple devices.

Usage:
    # Stop a device (auto-discover lab)
    cmlctl.py --cml-password cisco --device-name "ext-conn-0" --action stop

    # Start a device (auto-discover lab)
    cmlctl.py --cml-password cisco --device-name "rtr01" --action start

    # Wipe and restart a device
    cmlctl.py --cml-password cisco --device-name "rtr01" --action wipe

    # Control multiple devices
    cmlctl.py --cml-password cisco --device-name "rtr01,rtr02,sw01" --action stop

    # Specify lab name explicitly
    cmlctl.py --cml-password cisco --lab-name "My Lab" --device-name "rtr01" --action wipe

    # Custom CML server
    cmlctl.py --cml-server 10.1.1.100 --cml-password cisco --device-name "sw01" --action start

Logs: All operations are logged to /var/log/cmlctl.log
"""

import argparse
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

# Default CML Server (can be overridden)
DEFAULT_CML_SERVER = "192.168.255.1"
DEFAULT_CML_USER = "admin"
LOG_FILE = "/var/log/cmlctl.log"

# Ensure log directory and file exist
try:
    # Touch the file to ensure it exists
    with open(LOG_FILE, "a"):
        pass
except (PermissionError, FileNotFoundError):
    # Fallback to current directory if /var/log not writable
    LOG_FILE = "cmlctl.log"

# Disable warnings for insecure SSL
requests.packages.urllib3.disable_warnings()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def get_api_token(cml_server, username, password):
    """Authenticate and get API token."""
    logger.info(f"Authenticating with CML server: {cml_server}")
    url = f"https://{cml_server}/api/v0/authenticate"
    resp = requests.post(
        url, json={"username": username, "password": password}, verify=False
    )
    resp.raise_for_status()
    logger.info("Authentication successful")
    return resp.json()


def get_all_labs_id(cml_server, token):
    """Get all labs IDs."""
    logger.debug("Fetching all lab IDs")
    url = f"https://{cml_server}/api/v0/labs"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers, verify=False)
    response.raise_for_status()
    labs = response.json()
    logger.debug(f"Found {len(labs)} labs")
    return labs


def get_lab_id_by_name(cml_server, token, all_labs_ids, lab_name=None):
    """
    Find the lab ID by name, or find lab containing a device.

    If lab_name is None, returns None (for auto-discovery mode).
    """
    if lab_name is None:
        return None

    logger.info(f"Searching for lab: {lab_name}")
    for lab_id in all_labs_ids:
        url = f"https://{cml_server}/api/v0/labs/{lab_id}"
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.get(url, headers=headers, verify=False)
        resp.raise_for_status()
        if resp.json()["lab_title"] == lab_name:
            logger.info(f"Found lab '{lab_name}' with ID: {lab_id}")
            return lab_id
    raise Exception(f"Lab '{lab_name}' not found.")


def find_lab_by_device_name(cml_server, token, all_labs_ids, device_name):
    """
    Auto-discover which lab contains the specified device.

    Args:
        cml_server: CML server IP/hostname
        token: API authentication token
        all_labs_ids: List of all lab IDs
        device_name: Device name to search for

    Returns:
        tuple: (lab_id, lab_title) if found

    Raises:
        Exception: If device not found in any lab
    """
    logger.info(f"Auto-discovering lab for device: {device_name}")

    for lab_id in all_labs_ids:
        try:
            # Get lab title
            lab_url = f"https://{cml_server}/api/v0/labs/{lab_id}"
            headers = {"Authorization": f"Bearer {token}"}
            lab_resp = requests.get(lab_url, headers=headers, verify=False)
            lab_resp.raise_for_status()
            lab_title = lab_resp.json()["lab_title"]

            # Search for device in this lab
            nodes_url = f"https://{cml_server}/api/v0/labs/{lab_id}/nodes?data=true"
            nodes_resp = requests.get(nodes_url, headers=headers, verify=False)
            nodes_resp.raise_for_status()
            nodes = nodes_resp.json()

            for node in nodes:
                if node["label"] == device_name:
                    logger.info(
                        f"Found device '{device_name}' in lab '{lab_title}' "
                        f"(ID: {lab_id})"
                    )
                    return lab_id, lab_title
        except Exception as e:
            logger.debug(f"Error searching lab {lab_id}: {e}")
            continue

    raise Exception(
        f"Device '{device_name}' not found in any lab. "
        f"Searched {len(all_labs_ids)} lab(s)."
    )


def get_node_id_by_name(cml_server, token, lab_id, device_name):
    """Find the node ID for the target device in the specified lab."""
    logger.info(f"Searching for device: {device_name}")
    nodes_url = f"https://{cml_server}/api/v0/labs/{lab_id}/nodes?data=true"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(nodes_url, headers=headers, verify=False)
    resp.raise_for_status()
    nodes = resp.json()
    for node in nodes:
        if node["label"] == device_name:
            logger.info(f"Found device '{device_name}' with ID: {node['id']}")
            return node["id"]
    raise Exception(f"Device '{device_name}' not found in lab.")


def stop_node(cml_server, token, lab_id, node_id):
    """Stop the target node."""
    logger.info(f"Stopping node: {node_id}")
    url = f"https://{cml_server}/api/v0/labs/{lab_id}/nodes/{node_id}/state/stop"
    headers = {"Authorization": f"Bearer {token}"}
    requests.put(url, headers=headers, verify=False).raise_for_status()
    logger.info("Node stopped successfully")


def wipe_node(cml_server, token, lab_id, node_id):
    """Wipe the target node (factory reset)."""
    logger.info(f"Wiping disks for node: {node_id}")
    url = f"https://{cml_server}/api/v0/labs/{lab_id}/nodes/{node_id}/wipe_disks"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.put(url, headers=headers, verify=False)
    if resp.status_code != 204:
        raise Exception("Wipe operation failed.")
    logger.info("Node disks wiped successfully")


def start_node(cml_server, token, lab_id, node_id):
    """Start the target node."""
    logger.info(f"Starting node: {node_id}")
    url = f"https://{cml_server}/api/v0/labs/{lab_id}/nodes/{node_id}/state/start"
    headers = {"Authorization": f"Bearer {token}"}
    requests.put(url, headers=headers, verify=False).raise_for_status()
    logger.info("Node started successfully")


def wait_for_state(
    cml_server, token, lab_id, node_id, expected_state, max_attempts=60, poll_interval=2
):
    """
    Wait for a device to reach the expected state using CML API.

    Args:
        cml_server: CML server IP/hostname
        token: API authentication token
        lab_id: Lab ID
        node_id: Node ID
        expected_state: Expected state (e.g., 'STOPPED', 'STARTED', 'BOOTED')
        max_attempts: Maximum number of polling attempts (default: 60)
        poll_interval: Seconds between polling attempts (default: 2)

    Returns:
        True if device reaches expected state, False otherwise
    """
    url = f"https://{cml_server}/api/v0/labs/{lab_id}/nodes/{node_id}/state"
    headers = {"Authorization": f"Bearer {token}"}

    logger.info(f"Waiting for device to reach state: {expected_state}")
    for attempt in range(1, max_attempts + 1):
        try:
            resp = requests.get(url, headers=headers, verify=False)
            resp.raise_for_status()
            state = resp.json().get("state")

            logger.info(f"Attempt {attempt}/{max_attempts}: State = {state}")

            if state == expected_state:
                logger.info(f"Device has reached {expected_state} state")
                return True

            time.sleep(poll_interval)

        except Exception as e:
            logger.warning(f"Attempt {attempt}/{max_attempts}: API error - {e}")
            time.sleep(poll_interval)

    logger.error(f"Device could not reach {expected_state} state in time")
    return False


def perform_action(
    cml_server, token, lab_id, node_id, device_name, action, max_attempts=60
):
    """
    Perform the specified action on a device.

    Args:
        cml_server: CML server IP/hostname
        token: API authentication token
        lab_id: Lab ID
        node_id: Node ID
        device_name: Device name (for logging)
        action: Action to perform ('start', 'stop', 'wipe')
        max_attempts: Max polling attempts (derived from boot timeout)

    Returns:
        bool: True if action succeeded, False otherwise
    """
    try:
        if action == "stop":
            logger.info(f"Stopping device: {device_name}")
            stop_node(cml_server, token, lab_id, node_id)
            if wait_for_state(
                cml_server, token, lab_id, node_id, "STOPPED", max_attempts=30
            ):
                logger.info(f"[PASS] Device '{device_name}' stopped successfully")
                return True
            else:
                logger.error(f"[FAIL] Device '{device_name}' failed to stop")
                return False

        elif action == "start":
            logger.info(f"Starting device: {device_name}")
            start_node(cml_server, token, lab_id, node_id)
            if wait_for_state(
                cml_server, token, lab_id, node_id, "BOOTED", max_attempts=max_attempts
            ):
                logger.info(f"[PASS] Device '{device_name}' started successfully")
                return True
            else:
                logger.warning(f"[WARN] Device '{device_name}' started but not BOOTED")
                return True  # Still consider success if started

        elif action == "wipe":
            logger.info(f"Wiping device: {device_name}")

            # Stop the device
            stop_node(cml_server, token, lab_id, node_id)
            if not wait_for_state(
                cml_server, token, lab_id, node_id, "STOPPED", max_attempts=30
            ):
                logger.error(f"[FAIL] Failed to stop device '{device_name}'")
                return False

            # Wipe the device
            wipe_node(cml_server, token, lab_id, node_id)

            # Start the device
            start_node(cml_server, token, lab_id, node_id)

            # Verify device is at least started (BOOTED is ideal, STARTED is acceptable)
            if wait_for_state(
                cml_server, token, lab_id, node_id, "BOOTED", max_attempts=max_attempts
            ):
                logger.info(f"[PASS] Device '{device_name}' wiped and restarted")
                return True
            else:
                # Check if at least STARTED
                url = f"https://{cml_server}/api/v0/labs/{lab_id}/nodes/{node_id}/state"
                headers = {"Authorization": f"Bearer {token}"}
                resp = requests.get(url, headers=headers, verify=False)
                resp.raise_for_status()
                state = resp.json().get("state")

                if state == "STARTED":
                    logger.warning(
                        f"[WARN] Device '{device_name}' wiped and started (not fully BOOTED yet)"
                    )
                    return True
                else:
                    logger.error(
                        f"[FAIL] Device '{device_name}' did not start after wipe (state: {state})"
                    )
                    return False
        else:
            logger.error(f"Unknown action: {action}")
            return False

    except Exception as e:
        logger.error(f"[FAIL] Error performing {action} on '{device_name}': {e}")
        return False


def process_single_device(cml_server, token, lab_id, device_name, action, max_attempts):
    """
    Process a single device with the specified action.

    This function is designed to be called in parallel threads.

    Args:
        cml_server: CML server IP/hostname
        token: API authentication token
        lab_id: Lab ID (all devices must be in this lab)
        device_name: Device name
        action: Action to perform
        max_attempts: Max polling attempts (derived from boot timeout)

    Returns:
        tuple: (device_name, success: bool, error_message: str or None)
    """
    logger.info("=" * 60)
    logger.info(f"[Thread] Processing device: {device_name}")
    logger.info("=" * 60)

    try:
        # Find the node ID in the specified lab
        node_id = get_node_id_by_name(cml_server, token, lab_id, device_name)

        # Perform the action
        success = perform_action(
            cml_server, token, lab_id, node_id, device_name, action, max_attempts
        )

        if success:
            return (device_name, True, None)
        else:
            return (device_name, False, "Action failed")

    except Exception as e:
        error_msg = str(e)
        logger.error(f"[Thread] [FAIL] Error processing '{device_name}': {e}")
        return (device_name, False, error_msg)


def process_devices(
    cml_server,
    token,
    all_labs_ids,
    lab_name,
    device_names,
    action,
    max_workers=None,
    max_attempts=60,
):
    """
    Process one or more devices with the specified action in parallel.

    All devices must be in the same lab.

    Args:
        cml_server: CML server IP/hostname
        token: API authentication token
        all_labs_ids: List of all lab IDs
        lab_name: Lab name (optional, None for auto-discovery)
        device_names: List of device names
        action: Action to perform
        max_workers: Max parallel threads (default: min(devices, 10))
        max_attempts: Max polling attempts (derived from boot timeout)

    Returns:
        tuple: (success_count, total_count, results_dict)
    """
    success_count = 0
    total_count = len(device_names)
    results = {}

    # Default to number of devices, but cap at reasonable limit
    if max_workers is None:
        max_workers = min(len(device_names), 10)

    logger.info("=" * 60)
    logger.info(f"Processing {total_count} device(s) with {max_workers} workers")
    logger.info("=" * 60)

    # Step 1: Determine the lab_id
    if lab_name:
        # Use explicitly specified lab
        lab_id = get_lab_id_by_name(cml_server, token, all_labs_ids, lab_name)
        logger.info(f"Using specified lab: {lab_name} (ID: {lab_id})")
    else:
        # Auto-discover lab from first device
        first_device = device_names[0]
        lab_id, discovered_lab = find_lab_by_device_name(
            cml_server, token, all_labs_ids, first_device
        )
        logger.info(
            f"Auto-discovered lab: {discovered_lab} (ID: {lab_id}) "
            f"from device '{first_device}'"
        )

    # Step 2: Verify all devices exist in the same lab
    logger.info(f"Verifying all devices are in lab ID: {lab_id}")
    for device_name in device_names:
        try:
            get_node_id_by_name(cml_server, token, lab_id, device_name)
            logger.info(f"  ✓ Found device: {device_name}")
        except Exception as e:
            error_msg = (
                f"Device '{device_name}' not found in lab. "
                f"All devices must be in the same lab. Error: {e}"
            )
            logger.error(f"[FAIL] {error_msg}")
            # Return early with failure
            for dev in device_names:
                results[dev] = {
                    "success": False,
                    "error": "Not all devices in same lab",
                }
            return 0, total_count, results

    # Step 3: Process all devices in parallel
    logger.info("=" * 60)
    logger.info("Starting parallel device processing...")
    logger.info("=" * 60)

    # Use ThreadPoolExecutor for parallel processing
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_device = {
            executor.submit(
                process_single_device,
                cml_server,
                token,
                lab_id,
                device_name,
                action,
                max_attempts,
            ): device_name
            for device_name in device_names
        }

        # Collect results as they complete
        for future in as_completed(future_to_device):
            device_name, success, error_msg = future.result()
            results[device_name] = {"success": success, "error": error_msg}

            if success:
                success_count += 1
                logger.info(
                    f"[Main] Device '{device_name}' completed successfully "
                    f"({success_count}/{total_count})"
                )
            else:
                logger.error(
                    f"[Main] Device '{device_name}' failed: {error_msg} "
                    f"({success_count}/{total_count} succeeded so far)"
                )

    return success_count, total_count, results


def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(
        description="CML Control Utility - Control devices in Cisco Modeling Labs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Stop a device (auto-discover lab)
  cmlctl --cml-password cisco --device-name "ext-conn-0" --action stop

  # Start a device
  cmlctl --cml-password cisco --device-name "rtr01" --action start

  # Wipe and restart a device
  cmlctl --cml-password cisco --device-name "rtr01" --action wipe

  # Control multiple devices
  cmlctl --cml-password cisco --device-name "rtr01,rtr02,sw01" --action stop

  # Specify lab name explicitly
  cmlctl --cml-password cisco --lab-name "My Lab" \\
            --device-name "rtr01" --action wipe

  # Custom CML server
  cmlctl --cml-server 10.1.1.100 --cml-password cisco \\
            --device-name "sw01" --action start
        """,
    )
    parser.add_argument(
        "--cml-server",
        default=DEFAULT_CML_SERVER,
        help=f"CML server IP/hostname (default: {DEFAULT_CML_SERVER})",
    )
    parser.add_argument(
        "--cml-user",
        default=DEFAULT_CML_USER,
        help=f"CML username (default: {DEFAULT_CML_USER})",
    )
    parser.add_argument(
        "--cml-password",
        required=True,
        help="CML password (required)",
    )
    parser.add_argument(
        "--lab-name",
        help="CML lab name (optional, auto-discover if not specified)",
    )
    parser.add_argument(
        "--device-name",
        required=True,
        help="Device name(s) in CML (comma-separated for multiple)",
    )
    parser.add_argument(
        "--action",
        required=True,
        choices=["start", "stop", "wipe"],
        help="Action to perform: start, stop, or wipe",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        help="Maximum parallel workers (default: min(devices, 10))",
    )
    parser.add_argument(
        "--boot-timeout",
        type=int,
        default=120,
        help="Boot timeout in seconds for start/wipe (default: 120)",
    )
    args = parser.parse_args()

    # Parse device names (support comma-separated list)
    device_names = [name.strip() for name in args.device_name.split(",")]

    # Convert boot timeout (seconds) to polling attempts (2 seconds per attempt)
    max_attempts = max(1, round(args.boot_timeout / 2))

    logger.info("=" * 60)
    logger.info("CML Control Utility (cmlctl)")
    logger.info("=" * 60)
    logger.info(f"CML Server: {args.cml_server}")
    logger.info(f"Lab: {args.lab_name if args.lab_name else '(auto-discover)'}")
    logger.info(f"Device(s): {', '.join(device_names)}")
    logger.info(f"Action: {args.action}")
    logger.info("=" * 60)

    try:
        # Step 1: Authenticate
        token = get_api_token(args.cml_server, args.cml_user, args.cml_password)

        # Step 2: Get all labs
        all_labs_ids = get_all_labs_id(args.cml_server, token)

        # Step 3: Process devices
        success_count, total_count, results = process_devices(
            args.cml_server,
            token,
            all_labs_ids,
            args.lab_name,
            device_names,
            args.action,
            max_workers=args.max_workers,
            max_attempts=max_attempts,
        )

        # Step 4: Report detailed results
        logger.info("=" * 60)
        logger.info("[Main] Detailed results:")
        for device_name, result_info in results.items():
            if result_info["success"]:
                logger.info(f"[Main]   ✓ {device_name}: SUCCESS")
            else:
                error_msg = result_info["error"]
                logger.error(f"[Main]   ✗ {device_name}: FAILED - {error_msg}")

        logger.info("=" * 60)
        msg = f"[Main] Summary: {success_count}/{total_count} device(s) succeeded"
        logger.info(msg)
        logger.info("=" * 60)

        if success_count == total_count:
            sys.exit(0)
        else:
            sys.exit(1)

    except Exception as e:
        logger.error("=" * 60)
        logger.error(f"[FAIL] - ERROR: {e}")
        logger.error("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    main()

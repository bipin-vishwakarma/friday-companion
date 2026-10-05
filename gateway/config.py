"""Hermes Desk Buddy Gateway — Configuration"""

import os
import secrets
import json
from pathlib import Path

# Paths
HERMES_HOME = Path(os.environ.get("LOCALAPPDATA", r"C:\Users\Lenovo\AppData\Local")) / "hermes"
# Fallback to hardcoded user path when running as LocalSystem (NSSM service)
_state_file_candidate = HERMES_HOME / "gateway_state.json"
_state_file_hardcoded = Path(r"C:\Users\Lenovo\AppData\Local\hermes\gateway_state.json")
GATEWAY_STATE_FILE = _state_file_candidate if _state_file_candidate.exists() else _state_file_hardcoded
PROJECT_ROOT = Path(__file__).parent.parent
LOGS_DIR = PROJECT_ROOT / "logs"
CONFIG_FILE = PROJECT_ROOT / "gateway" / "desk_buddy_config.json"

# Network
GATEWAY_HOST = "0.0.0.0"
GATEWAY_PORT = 8765
OMNIROUTE_URL = "http://127.0.0.1:20128"
OMNIROUTE_HEALTH_ENDPOINT = "/api/health/ping"

# PC details
PC_LAN_IP = "192.168.1.11"
PC_MAC_WIFI = "00:45:E2:83:14:13"
PC_MAC_ETH = "00:E0:4C:36:00:DA"
PC_BROADCAST = "192.168.1.255"

# Health check intervals (seconds)
HEALTH_CHECK_INTERVAL = 5
HEARTBEAT_INTERVAL = 15
HEARTBEAT_TIMEOUT = 120

# Service restart limits
MAX_RESTART_ATTEMPTS = 5
RESTART_BACKOFF_BASE = 2  # seconds, exponential

# Auth - Fixed token for testing, use env override in production
AUTH_TOKEN = os.environ.get("DESK_BUDDY_TOKEN", "_dxFFVlMs9yCjR-EPZck3H9ywJ59smWbRAz_vLjXtAY")

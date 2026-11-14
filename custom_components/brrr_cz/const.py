"""Constants for the Brrr.cz integration."""
from typing import Final

DOMAIN: Final = "brrr_cz"
MANUFACTURER: Final = "Brrr.cz (Mgr. Zdeněk Macura)"

CONF_USER_ID: Final = "user_id"
CONF_HASH: Final = "hash"
CONF_SCAN_INTERVAL: Final = "scan_interval"

DEFAULT_SCAN_INTERVAL: Final = 180  # 3 minutes in seconds
MIN_SCAN_INTERVAL: Final = 60
MAX_SCAN_INTERVAL: Final = 3600

API_ENDPOINT: Final = "https://brrr.cz/brrr.php"

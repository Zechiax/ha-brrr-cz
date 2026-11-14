"""Constants for the Brrr.cz integration."""
from typing import Final

DOMAIN: Final = "brrr_cz"
MANUFACTURER: Final = "Brrr.cz (Mgr. Zdeněk Macura)"

CONF_API_URL: Final = "api_url"
CONF_DEVICES_LIST: Final = "devices_list"
CONF_SCAN_INTERVAL: Final = "scan_interval"

DEFAULT_SCAN_INTERVAL: Final = 180  # 3 minutes in seconds
MIN_SCAN_INTERVAL: Final = 60
MAX_SCAN_INTERVAL: Final = 3600

SINGLE_SENSOR_ENDPOINT: Final = (
    "https://brrr.cz/brrr.php?runpagephp=afterlogin"
    "&uloha=nacti_data_jen_posledni&ssid={ssid}&kod={kod}"
)

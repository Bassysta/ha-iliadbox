"""Constants for the Iliadbox integration."""

DOMAIN = "iliadbox"

DEFAULT_HOST = "192.168.1.254"
DEFAULT_PORT = 80
DEFAULT_SSL_PORT = 443

CONF_APP_TOKEN = "app_token"
CONF_USE_SSL = "use_ssl"
CONF_LOG_LEVEL = "log_level"

LOG_LEVELS = ["error", "info", "debug"]
DEFAULT_LOG_LEVEL = "info"

APP_ID = "ha.iliadbox"
APP_NAME = "Home Assistant"
APP_VERSION = "0.10.0"
DEVICE_NAME = "Home Assistant"

# LAN devices not seen for more than this many days are hidden (0 = keep all)
CONF_MAX_AGE_DAYS = "max_age_days"
DEFAULT_MAX_AGE_DAYS = 30
MAX_MAX_AGE_DAYS = 3650

# Polling interval in seconds, set in the options
DEFAULT_SCAN_INTERVAL = 60
MIN_SCAN_INTERVAL = 10
MAX_SCAN_INTERVAL = 3600

PLATFORMS = ["binary_sensor", "button", "device_tracker", "image", "sensor", "switch"]

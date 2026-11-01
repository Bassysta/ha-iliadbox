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
APP_VERSION = "0.8.0"
DEVICE_NAME = "Home Assistant"

# Polling interval in seconds, set in the options
DEFAULT_SCAN_INTERVAL = 60
MIN_SCAN_INTERVAL = 10
MAX_SCAN_INTERVAL = 3600

PLATFORMS = ["binary_sensor", "button", "device_tracker", "sensor", "switch"]

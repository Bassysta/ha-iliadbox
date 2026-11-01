"""Constants for the Iliadbox integration."""

from datetime import timedelta

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
APP_VERSION = "0.5.1"
DEVICE_NAME = "Home Assistant"

SCAN_INTERVAL = timedelta(seconds=30)

PLATFORMS = ["binary_sensor", "button", "device_tracker", "sensor", "switch"]

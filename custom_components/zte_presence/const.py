"""Constants for ZTE Wi-Fi presence."""

from datetime import timedelta
import os
import re
from urllib.parse import urlsplit

DOMAIN = "zte_presence"

CONF_URLS = "urls"
CONF_DEVICES = "devices"
CONF_CONSIDER_HOME = "consider_home"

DEFAULT_URLS = ["http://192.168.1.1"]
DEFAULT_CONSIDER_HOME = 180  # seconds a device may be missing before it counts as away
SCAN_INTERVAL = timedelta(seconds=30)

# Credentials come from the container environment, never from the UI or .storage.
# ZTE_USERNAME / ZTE_PASSWORD apply to every unit; a per-unit pair named after the
# host (ZTE_USERNAME_192_168_1_2) takes precedence.
ENV_USERNAME = "ZTE_USERNAME"
ENV_PASSWORD = "ZTE_PASSWORD"


def env_suffix(url: str) -> str:
    """Per-unit variable suffix, e.g. "192_168_1_2"."""
    return re.sub(r"\W", "_", urlsplit(url).hostname or url)


def credentials_from_env(url: str) -> tuple[str, str] | None:
    """Return (username, password) for one unit from the environment, or None if unset."""
    suffix = env_suffix(url)
    for username_var, password_var in (
        (f"{ENV_USERNAME}_{suffix}", f"{ENV_PASSWORD}_{suffix}"),
        (ENV_USERNAME, ENV_PASSWORD),
    ):
        username = os.environ.get(username_var)
        password = os.environ.get(password_var)
        if username and password:
            return username, password
    return None

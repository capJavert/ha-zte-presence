"""Constants for ZTE Wi-Fi presence."""

from datetime import timedelta
import json
import os
from urllib.parse import urlsplit

DOMAIN = "zte_presence"

CONF_URLS = "urls"
CONF_DEVICES = "devices"
CONF_CONSIDER_HOME = "consider_home"

DEFAULT_URLS = ["http://192.168.1.1"]
DEFAULT_CONSIDER_HOME = 180  # seconds a device may be missing before it counts as away
SCAN_INTERVAL = timedelta(seconds=30)

# Credentials come from the container environment, never from the UI or .storage.
# ZTE_USERNAME / ZTE_PASSWORD apply to every unit. Advanced: ZTE_CREDENTIALS is a JSON
# object of host -> {"username", "password"} for units with their own login, e.g.
# {"192.168.1.2": {"username": "user", "password": "other"}}; an entry there takes precedence.
ENV_USERNAME = "ZTE_USERNAME"
ENV_PASSWORD = "ZTE_PASSWORD"
ENV_CREDENTIALS = "ZTE_CREDENTIALS"


class CredentialsError(ValueError):
    """ZTE_CREDENTIALS is not valid; the message never contains its content."""


def _host(address: str) -> str:
    """Host of a URL or bare address, lowercase."""
    address = address.strip()
    return (urlsplit(address if "://" in address else f"//{address}").hostname or address).lower()


def credentials_from_env(url: str) -> tuple[str, str] | None:
    """Return (username, password) for one unit, or None if neither variable covers it."""
    if credentials := _credentials_entry(url):
        return credentials
    username = os.environ.get(ENV_USERNAME)
    password = os.environ.get(ENV_PASSWORD)
    return (username, password) if username and password else None


def _credentials_entry(url: str) -> tuple[str, str] | None:
    """The ZTE_CREDENTIALS entry for the unit's host."""
    raw = os.environ.get(ENV_CREDENTIALS)
    if not raw:
        return None
    try:
        entries = json.loads(raw)
    except ValueError:
        raise CredentialsError(f"{ENV_CREDENTIALS} is not valid JSON") from None
    if not isinstance(entries, dict) or not all(
        isinstance(entry, dict)
        and isinstance(entry.get("username"), str)
        and isinstance(entry.get("password"), str)
        and entry["username"]
        and entry["password"]
        for entry in entries.values()
    ):
        raise CredentialsError(
            f'{ENV_CREDENTIALS} must look like {{"host": {{"username": "...", "password": "..."}}}}'
        )
    host = _host(url)
    for address, entry in entries.items():
        if _host(address) == host:
            return entry["username"], entry["password"]
    return None

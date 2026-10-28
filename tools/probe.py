"""Log into a router or mesh unit once and print its Wi-Fi clients (names and addresses only).

Usage: ZTE_USERNAME=user ZTE_PASSWORD=... python3 tools/probe.py [access-point]
The access point (address or URL) comes from the argument, else ZTE_HOST, else 192.168.1.1.
Credentials are read from the environment like the integration does (ZTE_USERNAME /
ZTE_PASSWORD, or a ZTE_CREDENTIALS entry for the unit). If neither covers the unit, a
macOS keychain item is used (account = username, password = password), named by
ZTE_KEYCHAIN_SERVICE (default `zte-router`). Credentials are never printed.
"""

import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys

PACKAGE = Path(__file__).resolve().parent.parent / "custom_components" / "zte_presence"


def load(name: str):
    """Load one module on its own; the package __init__ needs Home Assistant."""
    spec = importlib.util.spec_from_file_location(f"zte_{name}", PACKAGE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def keychain_credentials() -> tuple[str, str] | None:
    """(username, password) from the macOS keychain, or None when unavailable."""
    if shutil.which("security") is None:
        return None
    service = os.environ.get("ZTE_KEYCHAIN_SERVICE", "zte-router")
    attributes = subprocess.run(["security", "find-generic-password", "-s", service], capture_output=True, text=True)
    if attributes.returncode != 0:
        return None
    username = next(
        (line.split("=", 1)[1].strip().strip('"') for line in attributes.stdout.splitlines() if '"acct"' in line), ""
    )
    password = subprocess.run(
        ["security", "find-generic-password", "-s", service, "-w"], capture_output=True, text=True
    ).stdout.strip()
    return (username, password) if username and password else None


zte = load("client")
const = load("const")

url = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("ZTE_HOST") or "192.168.1.1"
if "://" not in url:
    url = f"http://{url}"
try:
    credentials = const.credentials_from_env(url) or keychain_credentials()
except const.CredentialsError as err:
    sys.exit(f"failed: {err}")
if credentials is None:
    sys.exit(f"failed: set {const.ENV_USERNAME} and {const.ENV_PASSWORD}, or a keychain item (no login for {url})")
try:
    clients = zte.ZteClient(url, *credentials).fetch_clients()
except zte.ZteError as err:
    sys.exit(f"failed: {err}")
print(f"{len(clients)} Wi-Fi clients")
for client in sorted(clients.values(), key=lambda c: c.hostname.lower()):
    print(f"  {client.hostname or '?':30} {client.mac}  {client.ip}")

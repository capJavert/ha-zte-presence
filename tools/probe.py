"""Log into a router or mesh unit once and print its Wi-Fi clients (names and addresses only).

Usage: python3 tools/probe.py [access-point-url]
Credentials come from a macOS keychain item (account = router username,
password = router password), named by ZTE_KEYCHAIN_SERVICE (default
`zte-router`), and are never printed.
"""

import importlib.util
import os
from pathlib import Path
import subprocess
import sys

SERVICE = os.environ.get("ZTE_KEYCHAIN_SERVICE", "zte-router")
CLIENT = Path(__file__).resolve().parent.parent / "custom_components" / "zte_presence" / "client.py"

# Load client.py on its own; the package __init__ needs Home Assistant
spec = importlib.util.spec_from_file_location("zte_client", CLIENT)
zte = importlib.util.module_from_spec(spec)
sys.modules["zte_client"] = zte
spec.loader.exec_module(zte)


def keychain_credentials() -> tuple[str, str]:
    attributes = subprocess.run(
        ["security", "find-generic-password", "-s", SERVICE], capture_output=True, text=True, check=True
    ).stdout
    username = next(
        line.split("=", 1)[1].strip().strip('"') for line in attributes.splitlines() if '"acct"' in line
    )
    password = subprocess.run(
        ["security", "find-generic-password", "-s", SERVICE, "-w"], capture_output=True, text=True, check=True
    ).stdout.strip()
    return username, password


url = sys.argv[1] if len(sys.argv) > 1 else "http://192.168.1.1"
try:
    clients = zte.ZteClient(url, *keychain_credentials()).fetch_clients()
except zte.ZteError as err:
    sys.exit(f"failed: {err}")
print(f"{len(clients)} Wi-Fi clients")
for client in sorted(clients.values(), key=lambda c: c.hostname.lower()):
    print(f"  {client.hostname or '?':30} {client.mac}  {client.ip}")

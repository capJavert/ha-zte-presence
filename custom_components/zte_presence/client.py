"""Minimal client for the web interface of ZTE routers and mesh units (e.g. F8648P, H3601P).

Uses only the standard library, so it runs inside Home Assistant and on its own.
One fetch = log in, read the Wi-Fi client list, log out. Only Wi-Fi associations
are used: a LAN client list keeps devices for ~11 minutes after they leave, while
an access point drops a departed Wi-Fi client within ~30 s.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import http.client
import http.cookiejar
import json
import ssl
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET


class ZteError(Exception):
    """Router could not be reached or answered unexpectedly."""


class ZteAuthError(ZteError):
    """Login rejected or locked; retrying risks locking the router login."""

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        # Seconds until a temporary lock expires; None for a rejected login
        self.retry_after = retry_after


@dataclass(frozen=True)
class NetworkClient:
    """A device connected to an access point's Wi-Fi."""

    mac: str
    ip: str
    hostname: str
    access_point: str  # Host of the unit it is connected to, e.g. "192.168.1.2"


# Wi-Fi client list per model; a unit answers SessionTimeout for pages it lacks
# but keeps the session, so they are tried in order
WIFI_PAGES = ("wlan_client_stat_lua.lua", "accessdev_ssiddev_lua.lua")  # F8648P, H3601P


class ZteClient:
    """One login session against a router or mesh unit."""

    def __init__(self, url: str, username: str, password: str, timeout: float = 10) -> None:
        self._url = url.rstrip("/")
        self._host = urllib.parse.urlsplit(self._url).hostname or self._url
        self._username = username
        self._password = password
        self._timeout = timeout
        self._guid = int(time.time() * 1000)
        # Routers use self-signed certificates on https; skipping the CA bundle also
        # keeps construction free of disk I/O, so it is safe in the event loop
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
            urllib.request.HTTPSHandler(context=context),
        )

    def fetch_clients(self) -> dict[str, NetworkClient]:
        """Return connected Wi-Fi clients keyed by lowercase MAC address."""
        self._login()
        try:
            self._request(f"_type=menuView&_tag=localNetStatus&_={self._next_guid()}")
            error: ZteError | None = None
            for page in WIFI_PAGES:
                try:
                    clients = parse_clients(
                        self._request(f"_type=menuData&_tag={page}&_={self._next_guid()}"), self._host
                    )
                except ZteError as err:
                    error = err
                    continue
                return {client.mac: client for client in clients}
            raise error or ZteError("no Wi-Fi client list")
        finally:
            self._logout()

    def _login(self) -> None:
        entry = _json(self._request("_type=loginData&_tag=login_entry"))
        if locking := _locking_time(entry):
            raise ZteAuthError(f"router login is locked ({locking} s)", retry_after=locking)
        session_token = entry.get("sess_token")
        if not session_token:
            raise ZteError("router returned no session token")
        try:
            login_token = ET.fromstring(
                self._request(f"_type=loginData&_tag=login_token&_={self._next_guid()}")
            ).text
        except ET.ParseError as err:
            raise ZteError("router returned no login token") from err
        if not login_token:
            raise ZteError("router returned no login token")
        result = _json(
            self._request(
                "_type=loginData&_tag=login_entry",
                {
                    "action": "login",
                    "Password": hashlib.sha256((self._password + login_token).encode()).hexdigest(),
                    "Username": self._username,
                    "_sessionTOKEN": session_token,
                },
            )
        )
        if locking := _locking_time(result):
            raise ZteAuthError(f"router login is locked ({locking} s)", retry_after=locking)
        if result.get("loginErrMsg"):
            raise ZteAuthError(f"router login rejected: {result['loginErrMsg']}")

    def _logout(self) -> None:
        try:
            self._request("_type=loginData&_tag=logout_entry", {"IF_LogOff": "1"})
        except ZteError:
            pass  # The router expires the session on its own

    def _next_guid(self) -> int:
        self._guid += 1
        return self._guid

    def _request(self, query: str, form: dict[str, str] | None = None) -> str:
        request = urllib.request.Request(
            f"{self._url}/?{query}",
            data=urllib.parse.urlencode(form).encode() if form is not None else None,
            headers={"Referer": f"{self._url}/", "X-Requested-With": "XMLHttpRequest"},
        )
        try:
            with self._opener.open(request, timeout=self._timeout) as response:
                return response.read().decode("utf-8", "replace")
        except (OSError, http.client.HTTPException, ValueError) as err:
            raise ZteError(f"router request failed: {err}") from err


def parse_clients(text: str, access_point: str) -> list[NetworkClient]:
    """Parse a Wi-Fi client list; firmwares answer in XML or JSON."""
    try:
        if text.lstrip().startswith("{"):
            records = _json_records(json.loads(text))
        else:
            records = _xml_records(ET.fromstring(text))
    except (ValueError, ET.ParseError) as err:
        raise ZteError(f"unreadable client list: {err}") from err
    clients = []
    for record in records:
        mac = (record.get("MACAddress") or "").strip().lower()
        if mac:
            clients.append(
                NetworkClient(
                    mac=mac,
                    ip=record.get("IPAddress") or "",
                    hostname=record.get("HostName") or "",
                    access_point=access_point,
                )
            )
    return clients


def _xml_records(root: ET.Element) -> list[dict[str, str | None]]:
    error = root.findtext("IF_ERRORSTR")
    if error and error not in ("SUCC", "SUCCESS", "OK"):
        raise ZteError(f"router error: {error}")
    records = []
    for node in root:
        if node.tag == "OBJ_WLANAP_ID":  # Access points, not clients
            continue
        for instance in node.findall("Instance"):
            # Children alternate ParaName / ParaValue
            children = list(instance)
            records.append(
                {children[i].text or "": children[i + 1].text for i in range(0, len(children) - 1, 2)}
            )
    return records


def _json_records(data: dict) -> list[dict[str, str | None]]:
    records = []
    for key, node in data.items():
        if key == "OBJ_WLANAP_ID" or not isinstance(node, dict):
            continue
        instances = node.get("Instance") or []
        for instance in instances if isinstance(instances, list) else [instances]:
            if isinstance(instance, dict):
                params = instance.get("parameters")
                records.append(params if isinstance(params, dict) else instance)
    return records


def _locking_time(data: dict) -> int:
    """Seconds the login is locked for; firmwares send a number or a string."""
    try:
        return int(data.get("lockingTime") or 0)
    except (TypeError, ValueError):
        return 0


def _json(text: str) -> dict:
    try:
        data = json.loads(text)
    except ValueError as err:
        raise ZteError("router returned no JSON") from err
    if not isinstance(data, dict):
        raise ZteError("router returned unexpected JSON")
    return data

"""Polls every access point for its connected Wi-Fi clients."""

from __future__ import annotations

import asyncio
import logging
import time

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import NetworkClient, ZteAuthError, ZteClient, ZteError
from .const import CONF_DEVICES, CONF_URLS, DOMAIN, ENV_PASSWORD, ENV_USERNAME, SCAN_INTERVAL, credentials_from_env

_LOGGER = logging.getLogger(__name__)


class ZteCoordinator(DataUpdateCoordinator[dict[str, NetworkClient]]):
    """Fetches the client lists and remembers when each tracked MAC was last seen on each unit.

    data holds every connected client of all units (for the Configure list); a unit that
    fails keeps its last list until it answers again.
    """

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=SCAN_INTERVAL)
        # The container environment cannot change while HA runs, so read it once
        self._credentials: dict[str, tuple[str, str]] = {}
        for url in entry.data[CONF_URLS]:
            credentials = credentials_from_env(url)
            if credentials is None:
                raise ConfigEntryError(f"Set {ENV_USERNAME} and {ENV_PASSWORD} in the Home Assistant container")
            self._credentials[url] = credentials
        self._tracked: set[str] = set(entry.options.get(CONF_DEVICES, {}))
        # Monotonic times per unit; ages are measured against that unit's last successful
        # poll so an outage freezes presence instead of marking everyone away
        self.last_seen: dict[str, dict[str, float]] = {}
        self.last_poll: dict[str, float] = {}
        self._clients: dict[str, dict[str, NetworkClient]] = {}
        self._auth_failed: set[str] = set()
        self._locked_until: dict[str, float] = {}
        self._failing: set[str] = set()

    def is_connected(self, mac: str, consider_home: float) -> bool:
        """Seen on any unit within consider_home of that unit's last successful poll."""
        return any(
            self.last_poll[url] - seen < consider_home
            for url, seen in self.last_seen.get(mac, {}).items()
            if url in self.last_poll
        )

    async def _async_update_data(self) -> dict[str, NetworkClient]:
        results = await asyncio.gather(*(self._fetch(url) for url in self._credentials), return_exceptions=True)
        now = time.monotonic()
        errors: list[str] = []
        for url, result in zip(self._credentials, results):
            if isinstance(result, BaseException):
                if url not in self._failing:
                    _LOGGER.warning("%s: %s", url, result)
                    self._failing.add(url)
                errors.append(f"{url}: {result}")
                continue
            if url in self._failing:
                _LOGGER.info("%s answers again", url)
                self._failing.discard(url)
            self.last_poll[url] = now
            # All clients are kept for the Configure list; times only for tracked ones
            self._clients[url] = result
            for mac in result.keys() & self._tracked:
                self.last_seen.setdefault(mac, {})[url] = now
        if len(errors) == len(self._credentials):
            if self.data is None and self._auth_failed:
                raise ConfigEntryError("; ".join(errors))
            raise UpdateFailed("; ".join(errors))
        return self._merged()

    async def _fetch(self, url: str) -> dict[str, NetworkClient]:
        if url in self._auth_failed:
            # Stop logging in until reload, otherwise the unit locks the account
            raise ZteError("login was rejected; fix the credentials and reload the integration")
        if (locked_until := self._locked_until.get(url)) and time.monotonic() < locked_until:
            raise ZteError("login is locked; waiting for the lock to expire")
        try:
            return await self.hass.async_add_executor_job(ZteClient(url, *self._credentials[url]).fetch_clients)
        except ZteAuthError as err:
            if err.retry_after is not None:
                self._locked_until[url] = time.monotonic() + err.retry_after
                raise
            self._auth_failed.add(url)
            raise ZteAuthError(f"{err}; fix the credentials and reload the integration") from err

    def _merged(self) -> dict[str, NetworkClient]:
        """Each client as reported by the unit that saw it most recently."""
        newest: dict[str, tuple[float, NetworkClient]] = {}
        for url, clients in self._clients.items():
            for mac, client in clients.items():
                seen = self.last_poll[url]
                if mac not in newest or seen > newest[mac][0]:
                    newest[mac] = (seen, client)
        return {mac: client for mac, (_, client) in newest.items()}

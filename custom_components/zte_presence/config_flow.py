"""Config flow: access point addresses, then pick which Wi-Fi clients to track."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigEntryState, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .client import NetworkClient, ZteAuthError, ZteClient, ZteError
from .const import (
    CONF_CONSIDER_HOME,
    CONF_DEVICES,
    CONF_URLS,
    DEFAULT_CONSIDER_HOME,
    DEFAULT_URLS,
    DOMAIN,
    CredentialsError,
    credentials_from_env,
)


async def _probe(hass: HomeAssistant, urls: list[str]) -> tuple[dict[str, str], dict[str, NetworkClient]]:
    """Log in to each access point once and return (errors, connected clients of all that answered)."""
    clients: dict[str, NetworkClient] = {}
    for url in urls:
        try:
            credentials = credentials_from_env(url)
        except CredentialsError:
            return {"base": "invalid_env"}, {}
        if credentials is None:
            return {"base": "missing_env"}, {}
        try:
            clients |= await hass.async_add_executor_job(ZteClient(url, *credentials).fetch_clients)
        except ZteAuthError:
            return {"base": "invalid_auth"}, clients
        except ZteError:
            return {"base": "cannot_connect"}, clients
    return {}, clients


def _parse_urls(raw: list[str]) -> tuple[list[str], dict[str, str]]:
    """Normalise the entered addresses and return (urls, errors)."""
    urls = list(dict.fromkeys(url.strip().rstrip("/") for url in raw if url.strip()))
    if not urls:
        return urls, {"base": "no_urls"}
    for url in urls:
        parts = urlsplit(url)
        # No user:pass@ either, it would end up in the entry data and logs
        if parts.scheme not in ("http", "https") or not parts.hostname or "@" in parts.netloc:
            return urls, {CONF_URLS: "invalid_url"}
    return urls, {}


def _urls_schema(urls: list[str]) -> vol.Schema:
    return vol.Schema(
        {vol.Required(CONF_URLS, default=urls): TextSelector(TextSelectorConfig(type=TextSelectorType.URL, multiple=True))}
    )


def _devices_schema(clients: dict[str, NetworkClient], selected: dict[str, str], consider_home: int) -> vol.Schema:
    """Multi-select of connected clients plus already selected ones that are offline now."""
    options = [
        SelectOptionDict(value=mac, label=f"{client.hostname or 'Unknown'} ({mac}, {client.ip}, via {client.access_point})")
        for mac, client in sorted(clients.items(), key=lambda item: item[1].hostname.lower())
    ]
    options += [
        SelectOptionDict(value=mac, label=f"{name} ({mac}, not connected)")
        for mac, name in selected.items()
        if mac not in clients
    ]
    return vol.Schema(
        {
            vol.Required(CONF_DEVICES, default=list(selected)): SelectSelector(
                SelectSelectorConfig(options=options, multiple=True)
            ),
            vol.Required(CONF_CONSIDER_HOME, default=consider_home): NumberSelector(
                NumberSelectorConfig(min=30, max=1800, step=30, unit_of_measurement="s", mode=NumberSelectorMode.BOX)
            ),
        }
    )


def _options(user_input: dict[str, Any], clients: dict[str, NetworkClient], selected: dict[str, str]) -> dict[str, Any]:
    """Store selected MACs with a display name (router hostname, else the previous name)."""
    devices = {
        mac: selected.get(mac) or (clients[mac].hostname if mac in clients and clients[mac].hostname else mac)
        for mac in user_input[CONF_DEVICES]
    }
    return {CONF_DEVICES: devices, CONF_CONSIDER_HOME: int(user_input[CONF_CONSIDER_HOME])}


class ZteConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up ZTE Wi-Fi presence; one entry covers all access points."""

    VERSION = 1

    def __init__(self) -> None:
        self._urls = list(DEFAULT_URLS)
        self._clients: dict[str, NetworkClient] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        errors: dict[str, str] = {}
        if user_input is not None:
            self._urls, errors = _parse_urls(user_input[CONF_URLS])
            if not errors:
                errors, self._clients = await _probe(self.hass, self._urls)
            if not errors:
                return await self.async_step_devices()
        return self.async_show_form(step_id="user", data_schema=_urls_schema(self._urls), errors=errors)

    async def async_step_devices(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                title="ZTE Wi-Fi presence",
                data={CONF_URLS: self._urls},
                options=_options(user_input, self._clients, {}),
            )
        return self.async_show_form(
            step_id="devices", data_schema=_devices_schema(self._clients, {}, DEFAULT_CONSIDER_HOME)
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Change the access point addresses; tracked devices and their history stay."""
        entry = self._get_reconfigure_entry()
        urls: list[str] = entry.data[CONF_URLS]
        errors: dict[str, str] = {}
        if user_input is not None:
            urls, errors = _parse_urls(user_input[CONF_URLS])
            if not errors:
                errors, _ = await _probe(self.hass, urls)
            if not errors:
                return self.async_update_reload_and_abort(entry, data_updates={CONF_URLS: urls})
        return self.async_show_form(step_id="reconfigure", data_schema=_urls_schema(urls), errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return ZteOptionsFlow()


class ZteOptionsFlow(OptionsFlow):
    """Change tracked devices or the away delay."""

    def __init__(self) -> None:
        self._clients: dict[str, NetworkClient] = {}

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        selected = self.config_entry.options.get(CONF_DEVICES, {})
        if user_input is not None:
            return self.async_create_entry(data=_options(user_input, self._clients, selected))
        if self.config_entry.state is ConfigEntryState.LOADED:
            # Use the last poll; logging in again could end the poller's session
            errors, self._clients = {}, dict(self.config_entry.runtime_data.data or {})
        else:
            errors, self._clients = await _probe(self.hass, self.config_entry.data[CONF_URLS])
        return self.async_show_form(
            step_id="init",
            data_schema=_devices_schema(
                self._clients,
                selected,
                self.config_entry.options.get(CONF_CONSIDER_HOME, DEFAULT_CONSIDER_HOME),
            ),
            errors=errors,
        )

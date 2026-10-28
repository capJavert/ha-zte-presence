"""ZTE Wi-Fi presence: home/away from the Wi-Fi client lists of ZTE routers and mesh units."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import ZteCoordinator

PLATFORMS = [Platform.DEVICE_TRACKER]

type ZteConfigEntry = ConfigEntry[ZteCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: ZteConfigEntry) -> bool:
    """Set up from a config entry."""
    coordinator = ZteCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ZteConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload(hass: HomeAssistant, entry: ZteConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)

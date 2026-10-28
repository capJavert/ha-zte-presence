"""Device trackers for the selected network clients."""

from __future__ import annotations

from homeassistant.components.device_tracker import ScannerEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import ZteConfigEntry
from .const import CONF_CONSIDER_HOME, CONF_DEVICES, DEFAULT_CONSIDER_HOME
from .coordinator import ZteCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ZteConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    """Add one tracker per selected MAC address and remove trackers of deselected ones."""
    devices: dict[str, str] = entry.options.get(CONF_DEVICES, {})
    registry = er.async_get(hass)
    for registry_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if registry_entry.unique_id not in devices:
            registry.async_remove(registry_entry.entity_id)
    coordinator = entry.runtime_data
    async_add_entities(ZteTracker(coordinator, mac, name) for mac, name in devices.items())


class ZteTracker(CoordinatorEntity[ZteCoordinator], ScannerEntity):
    """Home while the device is connected to the Wi-Fi of any of the access points."""

    def __init__(self, coordinator: ZteCoordinator, mac: str, name: str) -> None:
        super().__init__(coordinator)
        self._mac = mac
        self._attr_name = name
        self._attr_unique_id = mac

    @property
    def entity_registry_enabled_default(self) -> bool:
        """ScannerEntity disables trackers of unknown MACs by default; selected ones are wanted."""
        return True

    @property
    def available(self) -> bool:
        """Available once any access point has answered."""
        return bool(self.coordinator.last_poll)

    @property
    def is_connected(self) -> bool:
        """Connected if seen within consider_home of an access point's last successful poll."""
        return self.coordinator.is_connected(
            self._mac, self.coordinator.config_entry.options.get(CONF_CONSIDER_HOME, DEFAULT_CONSIDER_HOME)
        )

    @property
    def mac_address(self) -> str:
        return self._mac

    @property
    def ip_address(self) -> str | None:
        client = (self.coordinator.data or {}).get(self._mac)
        return client.ip if client else None

    @property
    def hostname(self) -> str | None:
        client = (self.coordinator.data or {}).get(self._mac)
        return client.hostname if client else None

    @property
    def extra_state_attributes(self) -> dict[str, str] | None:
        """Which access point the device is connected to."""
        client = (self.coordinator.data or {}).get(self._mac)
        return {"access_point": client.access_point} if client else None

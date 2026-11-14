"""Binary sensor platform for Brrr.cz integration."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import BrrrDataUpdateCoordinator


@dataclass(frozen=True, kw_only=True)
class BrrrBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describes Brrr.cz binary sensor entity."""

    is_on_fn: Callable[[dict[str, Any]], bool | None]
    exists_fn: Callable[[dict[str, Any]], bool] = lambda _: True
    respect_online_state: bool = False


BINARY_SENSOR_TYPES: tuple[BrrrBinarySensorEntityDescription, ...] = (
    BrrrBinarySensorEntityDescription(
        key="cloud_connection",
        translation_key="cloud_connection",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        is_on_fn=lambda data: bool(data.get("online", False)),
        respect_online_state=False,  # Connectivity sensor itself stays available when offline
    ),
    BrrrBinarySensorEntityDescription(
        key="unpaid_invoice",
        translation_key="unpaid_invoice",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:cash-alert",
        is_on_fn=lambda data: bool(data.get("has_debt", False)),
        exists_fn=lambda data: data.get("device_kind") == "sensor",
        respect_online_state=False,
    ),
    BrrrBinarySensorEntityDescription(
        key="relay_state",
        translation_key="relay_state",
        device_class=BinarySensorDeviceClass.POWER,
        is_on_fn=lambda data: bool(data.get("relay_active", False)),
        exists_fn=lambda data: data.get("device_kind") == "relay",
        respect_online_state=True,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Brrr.cz binary sensors based on a config entry."""
    coordinator: BrrrDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[BrrrBinarySensorEntity] = []
    for ssid, device_data in coordinator.data.items():
        for description in BINARY_SENSOR_TYPES:
            if description.exists_fn(device_data):
                entities.append(BrrrBinarySensorEntity(coordinator, ssid, description))

    async_add_entities(entities)


class BrrrBinarySensorEntity(
    CoordinatorEntity[BrrrDataUpdateCoordinator], BinarySensorEntity
):
    """Representation of a Brrr.cz Binary Sensor."""

    _attr_has_entity_name = True
    entity_description: BrrrBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: BrrrDataUpdateCoordinator,
        ssid: str,
        description: BrrrBinarySensorEntityDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._ssid = ssid
        self.entity_description = description
        self._attr_unique_id = f"{ssid}_{description.key}"

        device_data = self._device_data
        connections = set()
        if mac := device_data.get("mac"):
            connections.add((dr.CONNECTION_NETWORK_MAC, mac))

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, ssid)},
            connections=connections,
            name=f"Brrr {device_data.get('name', ssid)}",
            manufacturer=MANUFACTURER,
            model=device_data.get("model", "Brrr.cz Sensor"),
            serial_number=ssid,
        )

    @property
    def _device_data(self) -> dict[str, Any]:
        """Return the current data dictionary for this device."""
        return self.coordinator.data.get(self._ssid, {})

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        if not super().available or not self._device_data:
            return False
        if self.entity_description.respect_online_state:
            return bool(self._device_data.get("online", False))
        return True

    @property
    def is_on(self) -> bool | None:
        """Return True if the binary sensor is on."""
        return self.entity_description.is_on_fn(self._device_data)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        data = self._device_data
        if self.entity_description.key == "unpaid_invoice":
            return {
                "unpaid_amount_czk": data.get("unpaid_amount", 0.0),
            }
        return {}

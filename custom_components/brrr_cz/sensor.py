"""Sensor platform for Brrr.cz integration."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricPotential,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import BrrrDataUpdateCoordinator


@dataclass(frozen=True, kw_only=True)
class BrrrSensorEntityDescription(SensorEntityDescription):
    """Describes Brrr.cz sensor entity."""

    value_fn: Callable[[dict[str, Any]], float | int | None]
    exists_fn: Callable[[dict[str, Any]], bool] = lambda _: True
    ignore_online_status: bool = False


SENSOR_TYPES: tuple[BrrrSensorEntityDescription, ...] = (
    BrrrSensorEntityDescription(
        key="temperature",
        translation_key="temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda data: data.get("temperature"),
        exists_fn=lambda data: data.get("device_kind") == "sensor"
        and (bool(data.get("has_temperature")) or data.get("temperature") is not None),
    ),
    BrrrSensorEntityDescription(
        key="humidity",
        translation_key="humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda data: data.get("humidity"),
        exists_fn=lambda data: data.get("device_kind") == "sensor"
        and (bool(data.get("has_humidity")) or data.get("humidity") is not None),
    ),
    BrrrSensorEntityDescription(
        key="voltage",
        translation_key="voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=2,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.get("voltage"),
        exists_fn=lambda data: data.get("device_kind") == "sensor"
        and data.get("voltage") is not None,
    ),
    BrrrSensorEntityDescription(
        key="age_minutes",
        translation_key="last_report_age",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:clock-outline",
        value_fn=lambda data: data.get("age_minutes"),
        exists_fn=lambda data: data.get("age_minutes") is not None,
        ignore_online_status=True,
    ),
    BrrrSensorEntityDescription(
        key="target_temperature",
        translation_key="target_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda data: data.get("target_temperature"),
        exists_fn=lambda data: data.get("device_kind") == "relay",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Brrr.cz sensors based on a config entry."""
    coordinator: BrrrDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    registered_entities: set[tuple[str, str]] = set()

    @callback
    def _async_discover_entities() -> None:
        """Discover and add new sensor entities when coordinator updates."""
        new_entities: list[BrrrSensorEntity] = []
        for ssid, device_data in coordinator.data.items():
            for description in SENSOR_TYPES:
                key = (ssid, description.key)
                if key not in registered_entities and description.exists_fn(device_data):
                    registered_entities.add(key)
                    new_entities.append(BrrrSensorEntity(coordinator, ssid, description))
        if new_entities:
            async_add_entities(new_entities)

    _async_discover_entities()
    entry.async_on_unload(coordinator.async_add_listener(_async_discover_entities))


class BrrrSensorEntity(CoordinatorEntity[BrrrDataUpdateCoordinator], SensorEntity):
    """Representation of a Brrr.cz Sensor."""

    _attr_has_entity_name = True
    entity_description: BrrrSensorEntityDescription

    def __init__(
        self,
        coordinator: BrrrDataUpdateCoordinator,
        ssid: str,
        description: BrrrSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
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
        """Return True if entity is available and not marked as 'tooold'."""
        if not super().available or not self._device_data:
            return False
        if self.entity_description.ignore_online_status:
            return True
        return bool(self._device_data.get("online", False))

    @property
    def native_value(self) -> float | int | None:
        """Return the state of the sensor."""
        return self.entity_description.value_fn(self._device_data)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        data = self._device_data
        attrs: dict[str, Any] = {
            "ssid": self._ssid,
            "last_cloud_update": data.get("last_update"),
        }
        if precision := data.get("precision"):
            attrs["precision"] = precision
        if linked := data.get("linked_sensor_ssid"):
            attrs["linked_sensor_ssid"] = linked
        return attrs

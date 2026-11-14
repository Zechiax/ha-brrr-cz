"""DataUpdateCoordinator for the Brrr.cz integration."""
from __future__ import annotations

import asyncio
from datetime import timedelta
import json
import logging
import re
from typing import Any
from urllib.parse import quote

from aiohttp import ClientError

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_API_URL,
    CONF_DEVICES_LIST,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    SINGLE_SENSOR_ENDPOINT,
)

_LOGGER = logging.getLogger(__name__)

# Regex to extract 'kod' hash from chartjs HTML link if present
KOD_REGEX = re.compile(r"kod=([a-fA-F0-9]{32})")


class BrrrDataUpdateCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Class to manage fetching Brrr.cz data from the cloud API."""

    config_entry: ConfigEntry | None

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry | None = None
    ) -> None:
        """Initialize the Brrr.cz coordinator."""
        self.entry = entry
        self.session = async_get_clientsession(hass)

        scan_interval = DEFAULT_SCAN_INTERVAL
        if entry is not None:
            scan_interval = entry.options.get(
                CONF_SCAN_INTERVAL,
                entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            )

        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        """Fetch data from Brrr.cz API and normalize it by device SSID."""
        if self.entry is None:
            raise ConfigEntryAuthFailed("No configuration entry available")

        api_url: str | None = self.entry.data.get(CONF_API_URL)
        devices_list: str | None = self.entry.data.get(CONF_DEVICES_LIST)
        return await self.async_fetch_data(api_url, devices_list)

    async def async_fetch_data(
        self, api_url: str | None, devices_list: str | None
    ) -> dict[str, dict[str, Any]]:
        """Fetch and normalize Brrr.cz data from API URL and/or individual sensor list."""
        api_url = (api_url or "").strip()
        devices_list = (devices_list or "").strip()

        if not api_url and not devices_list:
            raise ConfigEntryAuthFailed("No valid API URL or device list configured")

        try:
            async with asyncio.timeout(20):
                devices: dict[str, dict[str, Any]] = {}
                if api_url:
                    devices.update(await self._fetch_bulk_account_url(api_url))
                if devices_list:
                    individual = await self._fetch_individual_devices(devices_list)
                    for ssid, dev_data in individual.items():
                        if ssid not in devices:
                            devices[ssid] = dev_data
                return devices
        except TimeoutError as err:
            raise UpdateFailed("Timeout communicating with Brrr.cz server") from err
        except ClientError as err:
            raise UpdateFailed(f"Error communicating with Brrr.cz server: {err}") from err

    async def _fetch_bulk_account_url(self, url: str) -> dict[str, dict[str, Any]]:
        """Fetch the complete account JSON (ts, hs, relay) from a single URL."""
        async with self.session.get(url) as response:
            if response.status in (401, 403):
                raise ConfigEntryAuthFailed("Invalid authentication hash or URL")
            response.raise_for_status()
            text_data = await response.text()

        try:
            raw_data = json.loads(text_data)
        except json.JSONDecodeError as err:
            raise UpdateFailed(f"Invalid JSON received from Brrr.cz: {err}") from err

        if not isinstance(raw_data, dict) or not any(
            k in raw_data for k in ("ts", "hs", "relay", "ssid")
        ):
            raise UpdateFailed("Unexpected JSON structure from Brrr.cz")

        # Handle case where user pasted a single-sensor URL into the API URL field
        if "ssid" in raw_data and "posledni_zaznam_teplota" in raw_data:
            if raw_data.get("status_cislo") not in (0, "0", None):
                raise ConfigEntryAuthFailed(
                    f"Sensor {raw_data.get('ssid')} returned error status: {raw_data.get('status_cislo')}"
                )
            return self._normalize_single_sensor_payload([raw_data])

        return self._normalize_bulk_payload(raw_data)

    async def _fetch_individual_devices(
        self, devices_raw: str
    ) -> dict[str, dict[str, Any]]:
        """Fetch multiple individual sensors defined as SSID:kod pairs."""
        pairs: list[tuple[str, str]] = []
        for item in re.split(r"[\n,;]+", devices_raw):
            cleaned = item.strip()
            if not cleaned:
                continue
            if ":" not in cleaned:
                raise UpdateFailed(f"Invalid format '{cleaned}', expected SSID:kod")
            ssid, kod = cleaned.split(":", 1)
            ssid_clean, kod_clean = ssid.strip(), kod.strip()
            if not ssid_clean or not kod_clean:
                raise UpdateFailed(f"Invalid format '{cleaned}', expected SSID:kod")
            pairs.append((ssid_clean, kod_clean))

        if not pairs:
            raise UpdateFailed("No valid SSID:kod pairs found")

        results: list[dict[str, Any]] = []
        for ssid, kod in pairs:
            url = SINGLE_SENSOR_ENDPOINT.format(
                ssid=quote(ssid, safe=""),
                kod=quote(kod, safe=""),
            )
            async with self.session.get(url) as response:
                if response.status in (401, 403):
                    raise ConfigEntryAuthFailed(
                        f"Invalid authentication hash for sensor {ssid}"
                    )
                response.raise_for_status()
                text_data = await response.text()

            try:
                data = json.loads(text_data)
            except json.JSONDecodeError as err:
                raise UpdateFailed(
                    f"Invalid JSON received from Brrr.cz for sensor {ssid}: {err}"
                ) from err

            if not isinstance(data, dict) or not data.get("ssid"):
                raise UpdateFailed(
                    f"Unexpected JSON structure from Brrr.cz for sensor {ssid}"
                )
            if data.get("status_cislo") not in (0, "0", None):
                raise ConfigEntryAuthFailed(
                    f"Sensor {ssid} returned error status: {data.get('status_cislo')}"
                )
            results.append(data)

        return self._normalize_single_sensor_payload(results)

    def _normalize_bulk_payload(
        self, raw_data: dict[str, Any]
    ) -> dict[str, dict[str, Any]]:
        """Merge 'ts', 'hs', and 'relay' arrays into a unified dictionary keyed by SSID."""
        devices: dict[str, dict[str, Any]] = {}

        # 1. Process temperature sensors ('ts')
        for item in raw_data.get("ts", []):
            ssid = item.get("ssid")
            if not ssid:
                continue

            voltage_raw = item.get("voltage")
            voltage_v = self._parse_voltage(voltage_raw)

            has_debt_info = isinstance(item.get("dluh"), dict)
            dluh_obj = item.get("dluh") if has_debt_info else {}
            unpaid_amount = self._safe_float(dluh_obj.get("dluh"), 2) or 0.0
            has_debt = dluh_obj.get("je_dluh") == "ANO"

            kod_match = KOD_REGEX.search(item.get("chartjs", ""))
            extracted_kod = kod_match.group(1) if kod_match else None

            raw_temp = (
                item.get("value")
                if item.get("value") is not None
                else item.get("teplota")
            )

            devices[ssid] = {
                "ssid": ssid,
                "device_kind": "sensor",
                "name": (item.get("location") or ssid).strip(),
                "model": self._format_model(item.get("type"), item.get("pod_typ")),
                "mac": item.get("mac") or None,
                "online": item.get("tooold") == "no" and item.get("mereni_selhalo") != "1",
                "has_temperature": True,
                "has_humidity": False,
                "has_debt_info": has_debt_info,
                "temperature": self._safe_float(raw_temp),
                "humidity": None,
                "voltage": voltage_v,
                "last_update": item.get("date") or item.get("teplota_date"),
                "age_minutes": self._calculate_age_minutes(item.get("datediff")),
                "has_debt": has_debt,
                "unpaid_amount": unpaid_amount,
                "precision": item.get("prectext"),
                "kod": extracted_kod,
            }

        # 2. Process humidity sensors ('hs') and merge into existing SSID device
        for item in raw_data.get("hs", []):
            ssid = item.get("ssid")
            if not ssid:
                continue

            raw_humidity = (
                item.get("value")
                if item.get("value") is not None
                else item.get("humidity")
            )
            humidity_val = self._safe_float(raw_humidity)
            hs_online = item.get("tooold") == "no" and item.get("mereni_selhalo") != "1"

            if ssid in devices:
                devices[ssid]["humidity"] = humidity_val
                devices[ssid]["has_humidity"] = True
                # Keep online state True only if measurement did not fail and either ts or hs is fresh
                if item.get("mereni_selhalo") == "1":
                    devices[ssid]["online"] = False
                else:
                    devices[ssid]["online"] = devices[ssid]["online"] or hs_online
            else:
                has_debt_info = isinstance(item.get("dluh"), dict)
                dluh_obj = item.get("dluh") if has_debt_info else {}
                unpaid_amount = self._safe_float(dluh_obj.get("dluh"), 2) or 0.0
                has_debt = dluh_obj.get("je_dluh") == "ANO"

                devices[ssid] = {
                    "ssid": ssid,
                    "device_kind": "sensor",
                    "name": (item.get("location") or ssid).strip(),
                    "model": self._format_model(item.get("type"), item.get("pod_typ")),
                    "mac": item.get("mac") or None,
                    "online": hs_online,
                    "has_temperature": False,
                    "has_humidity": True,
                    "has_debt_info": has_debt_info,
                    "temperature": None,
                    "humidity": humidity_val,
                    "voltage": self._parse_voltage(item.get("voltage")),
                    "last_update": item.get("date") or item.get("teplota_date"),
                    "age_minutes": self._calculate_age_minutes(item.get("datediff")),
                    "has_debt": has_debt,
                    "unpaid_amount": unpaid_amount,
                    "precision": item.get("prectext"),
                    "kod": None,
                }

        # 3. Process thermostat relays ('relay')
        for item in raw_data.get("relay", []):
            ssid = item.get("ssid")
            if not ssid:
                continue

            devices[ssid] = {
                "ssid": ssid,
                "device_kind": "relay",
                "name": f"Termostat {(item.get('name') or ssid).strip()}",
                "model": self._format_model(item.get("type"), "TERMOSTAT"),
                "mac": None,
                "online": item.get("tooold") == "no",
                "has_temperature": False,
                "has_humidity": False,
                "has_debt_info": False,
                "relay_active": str(item.get("relaystatus")) == "1",
                "target_temperature": self._safe_float(item.get("issmallervalue")),
                "hysteresis": self._safe_float(item.get("hystereze")),
                "linked_sensor_ssid": item.get("teplomer_ssid"),
                "last_update": item.get("date_statuschecked"),
                "age_minutes": self._calculate_age_minutes(item.get("datediff")),
                "has_debt": False,
                "unpaid_amount": 0.0,
            }

        return devices

    def _normalize_single_sensor_payload(
        self, items: list[dict[str, Any]]
    ) -> dict[str, dict[str, Any]]:
        """Normalize output from the lightweight nacti_data_jen_posledni endpoint."""
        devices: dict[str, dict[str, Any]] = {}
        for item in items:
            ssid = item.get("ssid")
            if not ssid:
                continue

            is_ok = item.get("status_cislo") in (0, "0")
            humidity_val = self._safe_float(item.get("posledni_zaznam_vlhkost"))
            devices[ssid] = {
                "ssid": ssid,
                "device_kind": "sensor",
                "name": ssid,
                "model": "Brrr.cz Sensor",
                "mac": None,
                "online": is_ok,
                "has_temperature": True,
                "has_humidity": humidity_val is not None,
                "has_debt_info": False,
                "temperature": self._safe_float(item.get("posledni_zaznam_teplota")),
                "humidity": humidity_val,
                "voltage": self._parse_voltage(item.get("napeti_na_baterii")),
                "last_update": item.get("posledni_zaznam_cas"),
                "age_minutes": None,
                "has_debt": False,
                "unpaid_amount": 0.0,
                "precision": None,
                "kod": None,
            }
        return devices

    @staticmethod
    def _safe_float(value: Any, ndigits: int | None = None) -> float | None:
        """Convert string or number to float safely."""
        if value is None or value == "":
            return None
        try:
            val = float(value)
            return round(val, ndigits) if ndigits is not None else val
        except (ValueError, TypeError):
            return None

    @classmethod
    def _parse_voltage(cls, value: Any) -> float | None:
        """Normalize voltage (Brrr.cz returns either millivolts like '3517' or volts like '3.3')."""
        val = cls._safe_float(value)
        if val is None or val <= 0:
            return None
        if val > 20.0:
            return round(val / 1000.0, 3)
        return round(val, 3)

    @staticmethod
    def _format_model(hw_type: str | None, sub_type: str | None) -> str:
        """Create a human-readable model string."""
        base = (hw_type or "Brrr Sensor").strip()
        sub = (sub_type or "").strip()
        return f"{base} ({sub})" if sub else base

    @staticmethod
    def _calculate_age_minutes(datediff: dict[str, Any] | None) -> int | None:
        """Convert Brrr.cz PHP DateInterval JSON object into total minutes since last update."""
        if not isinstance(datediff, dict):
            return None
        try:
            days = int(datediff.get("days") or datediff.get("d") or 0)
            hours = int(datediff.get("h") or 0)
            minutes = int(datediff.get("i") or 0)
            return (days * 1440) + (hours * 60) + minutes
        except (ValueError, TypeError):
            return None

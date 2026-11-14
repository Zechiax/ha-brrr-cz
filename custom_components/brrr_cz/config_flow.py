"""Config flow for Brrr.cz integration."""
from __future__ import annotations

import hashlib
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed

from .const import (
    CONF_API_URL,
    CONF_DEVICES_LIST,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)
from .coordinator import BrrrDataUpdateCoordinator


class BrrrConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Brrr.cz."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._reauth_entry: config_entries.ConfigEntry | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            api_url = (user_input.get(CONF_API_URL) or "").strip()
            devices_list = (user_input.get(CONF_DEVICES_LIST) or "").strip()

            if not api_url and not devices_list:
                errors["base"] = "missing_credentials"
            elif api_url and not api_url.startswith(("http://", "https://")):
                errors[CONF_API_URL] = "invalid_url"
            else:
                unique_seed = f"{api_url}|{devices_list}" if (api_url and devices_list) else (api_url or devices_list)
                unique_hash = hashlib.md5(unique_seed.encode("utf-8")).hexdigest()[:12]
                await self.async_set_unique_id(f"brrr_{unique_hash}")
                self._abort_if_unique_id_configured()

                cleaned_data = {
                    CONF_NAME: user_input.get(CONF_NAME, "Brrr.cz Cloud"),
                    CONF_API_URL: api_url,
                    CONF_DEVICES_LIST: devices_list,
                    CONF_SCAN_INTERVAL: user_input.get(
                        CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                    ),
                }

                try:
                    await self._async_validate_input(cleaned_data)
                except ConfigEntryAuthFailed:
                    errors["base"] = "invalid_auth"
                except UpdateFailed:
                    errors["base"] = "cannot_connect"
                except Exception:  # noqa: BLE001
                    errors["base"] = "unknown"
                else:
                    return self.async_create_entry(
                        title=cleaned_data[CONF_NAME],
                        data=cleaned_data,
                    )

        schema = vol.Schema(
            {
                vol.Optional(CONF_NAME, default="Brrr.cz Cloud"): str,
                vol.Optional(CONF_API_URL, default=""): str,
                vol.Optional(CONF_DEVICES_LIST, default=""): str,
                vol.Optional(
                    CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
                ),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> FlowResult:
        """Handle initiation of re-authentication with Brrr.cz."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle re-authentication confirmation."""
        errors: dict[str, str] = {}
        entry = self._reauth_entry

        if user_input is not None and entry is not None:
            api_url = (user_input.get(CONF_API_URL) or "").strip()
            devices_list = (user_input.get(CONF_DEVICES_LIST) or "").strip()

            if not api_url and not devices_list:
                errors["base"] = "missing_credentials"
            elif api_url and not api_url.startswith(("http://", "https://")):
                errors[CONF_API_URL] = "invalid_url"
            else:
                updated_data = {
                    **entry.data,
                    CONF_API_URL: api_url,
                    CONF_DEVICES_LIST: devices_list,
                }
                try:
                    await self._async_validate_input(updated_data)
                except ConfigEntryAuthFailed:
                    errors["base"] = "invalid_auth"
                except UpdateFailed:
                    errors["base"] = "cannot_connect"
                except Exception:  # noqa: BLE001
                    errors["base"] = "unknown"
                else:
                    return self.async_update_reload_and_abort(
                        entry,
                        data=updated_data,
                    )

        current_api_url = entry.data.get(CONF_API_URL, "") if entry else ""
        current_devices = entry.data.get(CONF_DEVICES_LIST, "") if entry else ""

        schema = vol.Schema(
            {
                vol.Optional(CONF_API_URL, default=current_api_url): str,
                vol.Optional(CONF_DEVICES_LIST, default=current_devices): str,
            }
        )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=schema,
            errors=errors,
        )

    async def _async_validate_input(self, data: dict[str, Any]) -> None:
        """Validate the user input allows us to connect and fetch devices."""
        coordinator = BrrrDataUpdateCoordinator(self.hass)
        devices = await coordinator.async_fetch_data(
            data.get(CONF_API_URL),
            data.get(CONF_DEVICES_LIST),
        )
        if not devices:
            raise UpdateFailed("No devices returned from Brrr.cz API")

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return BrrrOptionsFlowHandler()


class BrrrOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Brrr.cz."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_interval = self.config_entry.options.get(
            CONF_SCAN_INTERVAL,
            self.config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL, default=current_interval
                    ): vol.All(
                        vol.Coerce(int),
                        vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
                    ),
                }
            ),
        )

"""Config flow for Brrr.cz integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed

from .const import (
    CONF_HASH,
    CONF_SCAN_INTERVAL,
    CONF_USER_ID,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)
from .coordinator import BrrrDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


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
            user_id = str(user_input.get(CONF_USER_ID) or "").strip()
            auth_hash = (user_input.get(CONF_HASH) or "").strip()

            if not user_id.isdigit():
                errors[CONF_USER_ID] = "invalid_user_id"
            elif not auth_hash:
                errors[CONF_HASH] = "invalid_hash"
            else:
                await self.async_set_unique_id(f"brrr_{user_id}")
                self._abort_if_unique_id_configured()

                data = {
                    CONF_NAME: user_input.get(CONF_NAME, "Brrr.cz Cloud"),
                    CONF_USER_ID: user_id,
                    CONF_HASH: auth_hash,
                    CONF_SCAN_INTERVAL: user_input.get(
                        CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                    ),
                }

                error = await self._async_validate(data)
                if error is None:
                    return self.async_create_entry(title=data[CONF_NAME], data=data)
                errors["base"] = error

        schema = vol.Schema(
            {
                vol.Optional(CONF_NAME, default="Brrr.cz Cloud"): str,
                vol.Required(CONF_USER_ID, default=""): str,
                vol.Required(CONF_HASH, default=""): str,
                vol.Optional(
                    CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
                ),
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> FlowResult:
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
            user_id = str(user_input.get(CONF_USER_ID) or "").strip()
            auth_hash = (user_input.get(CONF_HASH) or "").strip()

            if not user_id.isdigit():
                errors[CONF_USER_ID] = "invalid_user_id"
            elif not auth_hash:
                errors[CONF_HASH] = "invalid_hash"
            else:
                updated = {**entry.data, CONF_USER_ID: user_id, CONF_HASH: auth_hash}
                error = await self._async_validate(updated)
                if error is None:
                    return self.async_update_reload_and_abort(entry, data=updated)
                errors["base"] = error

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_USER_ID,
                    default=(entry.data.get(CONF_USER_ID, "") if entry else ""),
                ): str,
                vol.Required(CONF_HASH, default=""): str,
            }
        )

        return self.async_show_form(
            step_id="reauth_confirm", data_schema=schema, errors=errors
        )

    async def _async_validate(self, data: dict[str, Any]) -> str | None:
        """Try to fetch data; return an error key or None on success."""
        coordinator = BrrrDataUpdateCoordinator(self.hass)
        try:
            devices = await coordinator.async_fetch_data(
                data[CONF_USER_ID], data[CONF_HASH]
            )
        except ConfigEntryAuthFailed:
            return "invalid_auth"
        except UpdateFailed as err:
            _LOGGER.warning("Brrr.cz validation failed: %s", err)
            return "cannot_connect"
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Unexpected error validating Brrr.cz credentials")
            return "unknown"
        if not devices:
            return "no_devices"
        return None

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

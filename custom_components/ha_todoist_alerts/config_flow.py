"""Config flow for Todoist Alerts."""
from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_API_TOKEN, CONF_DEFAULT_PROJECT_ID, DOMAIN, TODOIST_API_BASE

_LOGGER = logging.getLogger(__name__)


class TodoistAlertsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the initial setup config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> config_entries.FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            token = user_input[CONF_API_TOKEN].strip()
            project_id = user_input.get(CONF_DEFAULT_PROJECT_ID, "").strip() or None

            valid = await self._validate_token(token)
            if valid:
                await self.async_set_unique_id(DOMAIN)
                self._abort_if_unique_id_configured()
                data = {CONF_API_TOKEN: token}
                if project_id:
                    data[CONF_DEFAULT_PROJECT_ID] = project_id
                return self.async_create_entry(title="Todoist Alerts", data=data)
            else:
                errors["base"] = "invalid_auth"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_API_TOKEN): str,
                vol.Optional(CONF_DEFAULT_PROJECT_ID): str,
            }),
            errors=errors,
        )

    async def _validate_token(self, token: str) -> bool:
        session = async_get_clientsession(self.hass)
        try:
            async with session.get(
                f"{TODOIST_API_BASE}/tasks",
                headers={"Authorization": f"Bearer {token}"},
            ) as resp:
                if resp.status == 200:
                    return True
                _LOGGER.warning(
                    "Todoist token validation failed: HTTP %s", resp.status
                )
                return False
        except Exception as err:
            _LOGGER.warning("Todoist token validation error: %s", err)
            return False

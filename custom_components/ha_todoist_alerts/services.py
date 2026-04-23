"""Service handlers for Todoist Alerts."""
from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
import homeassistant.helpers.config_validation as cv

from .const import (
    DOMAIN,
    SERVICE_CREATE_ALERT,
    SERVICE_RESOLVE_ALERT,
    SERVICE_SNOOZE_ALERT,
)
from .coordinator import TodoistCoordinator
from .sensor import TodoistAlertSensor

_LOGGER = logging.getLogger(__name__)


def _get_coordinator(hass: HomeAssistant) -> TodoistCoordinator:
    entries = hass.data.get(DOMAIN, {})
    if not entries:
        raise vol.Invalid("Todoist Alerts integration is not configured")
    return next(iter(entries.values()))


async def async_register_services(hass: HomeAssistant) -> None:
    """Register all service calls. Safe to call multiple times (checks first)."""

    if hass.services.has_service(DOMAIN, SERVICE_CREATE_ALERT):
        return

    # -------------------------------------------------------------------------
    # create_alert
    # -------------------------------------------------------------------------
    async def handle_create_alert(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass)
        name: str = call.data["name"]
        is_new = name not in coordinator.alerts

        task_id = await coordinator.async_create_alert(
            name=name,
            content=call.data["content"],
            description=call.data.get("description"),
            project_id=call.data.get("project_id"),
            priority=call.data.get("priority", 1),
            labels=call.data.get("labels"),
            due_string=call.data.get("due_string"),
            recreate_delay_minutes=call.data.get("recreate_delay_minutes", 30),
        )

        # Add sensor entity if this is a brand-new alert
        if is_new and coordinator.async_add_entities is not None:
            entity = TodoistAlertSensor(coordinator, name)
            coordinator.async_add_entities([entity], True)

    hass.services.async_register(
        DOMAIN,
        SERVICE_CREATE_ALERT,
        handle_create_alert,
        schema=vol.Schema({
            vol.Required("name"): cv.string,
            vol.Required("content"): cv.string,
            vol.Optional("description"): cv.string,
            vol.Optional("project_id"): cv.string,
            vol.Optional("priority", default=1): vol.All(
                vol.Coerce(int), vol.In([1, 2, 3, 4])
            ),
            vol.Optional("labels"): vol.All(cv.ensure_list, [cv.string]),
            vol.Optional("due_string"): cv.string,
            vol.Optional("recreate_delay_minutes", default=30): vol.All(
                vol.Coerce(int), vol.Range(min=0)
            ),
        }),
    )

    # -------------------------------------------------------------------------
    # resolve_alert
    # -------------------------------------------------------------------------
    async def handle_resolve_alert(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass)
        await coordinator.async_resolve_alert(call.data["name"])

    hass.services.async_register(
        DOMAIN,
        SERVICE_RESOLVE_ALERT,
        handle_resolve_alert,
        schema=vol.Schema({
            vol.Required("name"): cv.string,
        }),
    )

    # -------------------------------------------------------------------------
    # snooze_alert
    # -------------------------------------------------------------------------
    async def handle_snooze_alert(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass)
        await coordinator.async_snooze_alert(
            name=call.data["name"],
            duration_minutes=call.data.get("duration_minutes", 60),
        )

    hass.services.async_register(
        DOMAIN,
        SERVICE_SNOOZE_ALERT,
        handle_snooze_alert,
        schema=vol.Schema({
            vol.Required("name"): cv.string,
            vol.Optional("duration_minutes", default=60): vol.All(
                vol.Coerce(int), vol.Range(min=1)
            ),
        }),
    )

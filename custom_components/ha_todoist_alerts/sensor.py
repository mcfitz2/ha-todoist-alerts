"""Sensor platform for Todoist Alert entities."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import slugify

from .const import (
    ALERT_STATE_ACTIVE,
    ALERT_STATE_INACTIVE,
    ALERT_STATE_SNOOZED,
    ATTR_LAST_CREATED,
    ATTR_RECREATE_AT,
    ATTR_SNOOZE_UNTIL,
    ATTR_TASK_ID,
    ATTR_TASK_URL,
    DOMAIN,
)
from .coordinator import TodoistCoordinator

_LOGGER = logging.getLogger(__name__)

TODOIST_TASK_URL = "https://app.todoist.com/app/task/{task_id}"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: TodoistCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        TodoistAlertSensor(coordinator, name)
        for name in coordinator.alerts
    ]
    async_add_entities(entities, True)

    # Store callback for dynamic entity creation from service calls
    coordinator.async_add_entities = async_add_entities


class TodoistAlertSensor(RestoreEntity, SensorEntity):
    """Sensor entity representing a single Todoist alert."""

    _attr_should_poll = False
    _attr_has_entity_name = False

    def __init__(self, coordinator: TodoistCoordinator, name: str) -> None:
        self._coordinator = coordinator
        self._alert_name = name
        self._attr_unique_id = f"{DOMAIN}_{slugify(name)}"
        self._attr_name = name

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    async def async_added_to_hass(self) -> None:
        self._coordinator.register_entity(self._alert_name, self)

        # Subscribe to coordinator updates so polls refresh our state
        self.async_on_remove(
            self._coordinator.async_add_listener(self.async_write_ha_state)
        )

        # Restore previous state (handles HA restarts)
        last_state = await self.async_get_last_state()
        if last_state and last_state.state in (
            ALERT_STATE_ACTIVE, ALERT_STATE_INACTIVE, ALERT_STATE_SNOOZED
        ):
            # State is now driven by coordinator.alerts data, so we only need
            # to ensure the coordinator's in-memory state is consistent.
            # The store is loaded before entities are set up, so nothing to do.
            pass

    async def async_will_remove_from_hass(self) -> None:
        self._coordinator.unregister_entity(self._alert_name)

    # -------------------------------------------------------------------------
    # State
    # -------------------------------------------------------------------------

    @property
    def _alert(self) -> dict[str, Any]:
        return self._coordinator.alerts.get(self._alert_name, {})

    @property
    def native_value(self) -> str:
        alert = self._alert
        if not alert:
            return ALERT_STATE_INACTIVE

        snooze_until = alert.get("snooze_until")
        if snooze_until:
            from homeassistant.util import dt as dt_util
            snooze_dt = dt_util.parse_datetime(snooze_until)
            if snooze_dt and dt_util.utcnow() < snooze_dt:
                return ALERT_STATE_SNOOZED

        if alert.get("task_id") or alert.get("recreate_at"):
            return ALERT_STATE_ACTIVE

        return ALERT_STATE_INACTIVE

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        alert = self._alert
        task_id = alert.get("task_id")
        return {
            ATTR_TASK_ID: task_id,
            ATTR_TASK_URL: TODOIST_TASK_URL.format(task_id=task_id) if task_id else None,
            ATTR_LAST_CREATED: alert.get("last_created"),
            ATTR_SNOOZE_UNTIL: alert.get("snooze_until"),
            ATTR_RECREATE_AT: alert.get("recreate_at"),
        }

    @property
    def icon(self) -> str:
        state = self.native_value
        if state == ALERT_STATE_ACTIVE:
            return "mdi:alert-circle"
        if state == ALERT_STATE_SNOOZED:
            return "mdi:alarm-snooze"
        return "mdi:check-circle-outline"

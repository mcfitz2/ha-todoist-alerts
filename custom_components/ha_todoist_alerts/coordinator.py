"""Todoist API coordinator — manages task state, dedup, and storage."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_API_TOKEN,
    CONF_DEFAULT_PROJECT_ID,
    DOMAIN,
    POLL_INTERVAL_SECONDS,
    STORAGE_KEY,
    STORAGE_VERSION,
    TODOIST_API_BASE,
)

if TYPE_CHECKING:
    from .sensor import TodoistAlertSensor

_LOGGER = logging.getLogger(__name__)


class TodoistCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinates Todoist API calls and alert state persistence."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=POLL_INTERVAL_SECONDS),
        )
        self.api_token: str = entry.data[CONF_API_TOKEN]
        self.default_project_id: str | None = entry.data.get(CONF_DEFAULT_PROJECT_ID)
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)

        # name -> alert config dict (persisted)
        self.alerts: dict[str, dict[str, Any]] = {}
        # name -> live entity reference (not persisted)
        self._entities: dict[str, TodoistAlertSensor] = {}
        # set by sensor.async_setup_entry so services can add entities dynamically
        self.async_add_entities = None

    # -------------------------------------------------------------------------
    # Storage
    # -------------------------------------------------------------------------

    async def async_load(self) -> None:
        """Load persisted alert state from HA Store."""
        data = await self._store.async_load()
        if data:
            self.alerts = data.get("alerts", {})

    async def _async_save(self) -> None:
        await self._store.async_save({"alerts": self.alerts})

    # -------------------------------------------------------------------------
    # DataUpdateCoordinator polling
    # -------------------------------------------------------------------------

    async def _async_update_data(self) -> dict[str, Any]:
        """Poll Todoist for status of every tracked task."""
        now = dt_util.utcnow()
        changed: list[str] = []

        for name, alert in list(self.alerts.items()):
            task_id = alert.get("task_id")
            snooze_until = alert.get("snooze_until")
            recreate_at = alert.get("recreate_at")

            # --- snooze expiry ---
            if snooze_until:
                snooze_dt = dt_util.parse_datetime(snooze_until)
                if snooze_dt and now >= snooze_dt:
                    alert["snooze_until"] = None
                    changed.append(name)

            # --- recreate timer ---
            # When recreate_at is set, task_id is None by design — skip the
            # existence check below and just wait for the timer to fire.
            if recreate_at and not task_id:
                recreate_dt = dt_util.parse_datetime(recreate_at)
                if recreate_dt and now >= recreate_dt:
                    try:
                        new_task_id = await self._api_create_task(alert)
                        alert["task_id"] = new_task_id
                        alert["recreate_at"] = None
                        changed.append(name)
                    except Exception as err:
                        _LOGGER.error("Failed to recreate task for alert '%s': %s", name, err)
                continue  # task_id is intentionally None; nothing else to check

            # --- check if open task was externally completed ---
            if task_id:
                task = await self._api_get_task(task_id)
                if task is None:
                    # Task completed or deleted externally
                    alert["task_id"] = None
                    delay = alert.get("recreate_delay_minutes", 30)
                    if delay and delay > 0:
                        alert["recreate_at"] = (
                            now + timedelta(minutes=delay)
                        ).isoformat()
                    changed.append(name)

        if changed:
            await self._async_save()
            for name in changed:
                entity = self._entities.get(name)
                if entity:
                    entity.async_write_ha_state()

        return {"polled_at": now.isoformat()}

    # -------------------------------------------------------------------------
    # Todoist REST API helpers
    # -------------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

    async def _api_get_task(self, task_id: str) -> dict | None:
        """Return task dict if open, None if completed or missing.

        API v1 returns 200 with is_completed=true for completed tasks rather
        than 404, so we explicitly check the flag.
        """
        session = async_get_clientsession(self.hass)
        try:
            resp = await session.get(
                f"{TODOIST_API_BASE}/tasks/{task_id}",
                headers=self._headers(),
            )
            if resp.status == 200:
                data = await resp.json()
                if data.get("is_completed"):
                    return None
                return data
            if resp.status == 404:
                return None
            _LOGGER.warning("Unexpected status %s fetching task %s", resp.status, task_id)
            return None
        except Exception as err:
            _LOGGER.warning("Error fetching task %s: %s", task_id, err)
            return None

    async def _api_create_task(self, alert: dict[str, Any]) -> str:
        """Create a Todoist task from alert config. Returns task_id."""
        payload: dict[str, Any] = {"content": alert["content"]}
        if alert.get("description"):
            payload["description"] = alert["description"]
        project = alert.get("project_id") or self.default_project_id
        if project:
            payload["project_id"] = project
        if alert.get("priority"):
            payload["priority"] = alert["priority"]
        if alert.get("labels"):
            payload["labels"] = alert["labels"]
        if alert.get("due_string"):
            payload["due_string"] = alert["due_string"]

        _LOGGER.info("Creating Todoist task with payload: %s", payload)

        session = async_get_clientsession(self.hass)
        async with session.post(
            f"{TODOIST_API_BASE}/tasks",
            headers=self._headers(),
            json=payload,
        ) as resp:
            if not resp.ok:
                body = await resp.text()
                _LOGGER.error(
                    "Todoist task creation failed: HTTP %s — %s", resp.status, body
                )
                resp.raise_for_status()
            data = await resp.json()
            _LOGGER.info("Todoist task created: %s", data)
            return data["id"]

    async def _api_close_task(self, task_id: str) -> None:
        """Complete a Todoist task."""
        session = async_get_clientsession(self.hass)
        resp = await session.post(
            f"{TODOIST_API_BASE}/tasks/{task_id}/close",
            headers=self._headers(),
        )
        if resp.status not in (200, 204):
            resp.raise_for_status()

    async def _api_get_projects(self) -> list[dict]:
        """Fetch all projects (used during config flow validation)."""
        session = async_get_clientsession(self.hass)
        resp = await session.get(
            f"{TODOIST_API_BASE}/projects",
            headers=self._headers(),
        )
        resp.raise_for_status()
        return await resp.json()

    # -------------------------------------------------------------------------
    # Alert lifecycle (called by service handlers)
    # -------------------------------------------------------------------------

    def register_entity(self, name: str, entity: TodoistAlertSensor) -> None:
        self._entities[name] = entity

    def unregister_entity(self, name: str) -> None:
        self._entities.pop(name, None)

    async def async_create_alert(
        self,
        name: str,
        content: str,
        description: str | None = None,
        project_id: str | None = None,
        priority: int = 1,
        labels: list[str] | None = None,
        due_string: str | None = None,
        recreate_delay_minutes: int = 30,
    ) -> str | None:
        """Create alert and Todoist task if not already active. Returns task_id or None."""
        existing = self.alerts.get(name, {})
        existing_task_id = existing.get("task_id")
        _LOGGER.info("create_alert '%s': existing_task_id=%s", name, existing_task_id)

        # Check if existing task is still open
        if existing_task_id:
            task = await self._api_get_task(existing_task_id)
            if task:
                _LOGGER.info("Alert '%s' already has open task %s, skipping", name, existing_task_id)
                return existing_task_id
            _LOGGER.info("Alert '%s' task %s is completed/gone, will create new", name, existing_task_id)

        # Clear any pending recreate since we're explicitly creating now
        alert_config: dict[str, Any] = {
            "content": content,
            "description": description,
            "project_id": project_id,
            "priority": priority,
            "labels": labels or [],
            "due_string": due_string,
            "recreate_delay_minutes": recreate_delay_minutes,
            "task_id": None,
            "recreate_at": None,
            "snooze_until": existing.get("snooze_until"),  # preserve active snooze
        }

        # If currently snoozed, don't create a new task
        snooze_until = alert_config.get("snooze_until")
        if snooze_until:
            snooze_dt = dt_util.parse_datetime(snooze_until)
            if snooze_dt and dt_util.utcnow() < snooze_dt:
                _LOGGER.info("Alert '%s' is snoozed until %s, skipping task creation", name, snooze_until)
                self.alerts[name] = alert_config
                await self._async_save()
                return None

        try:
            task_id = await self._api_create_task(alert_config)
        except Exception as err:
            _LOGGER.error("Failed to create Todoist task for alert '%s': %s", name, err)
            raise

        alert_config["task_id"] = task_id
        alert_config["last_created"] = dt_util.utcnow().isoformat()
        self.alerts[name] = alert_config
        await self._async_save()

        _LOGGER.info("Created Todoist task %s for alert '%s'", task_id, name)
        return task_id

    async def async_resolve_alert(self, name: str) -> None:
        """Close task and remove alert entirely."""
        alert = self.alerts.get(name)
        if not alert:
            _LOGGER.warning("resolve_alert: no alert named '%s'", name)
            return

        task_id = alert.get("task_id")
        if task_id:
            try:
                await self._api_close_task(task_id)
            except Exception as err:
                _LOGGER.warning("Failed to close task %s for alert '%s': %s", task_id, name, err)

        self.alerts.pop(name, None)
        await self._async_save()

        # Remove entity
        entity = self._entities.pop(name, None)
        if entity:
            await entity.async_remove()

    async def async_snooze_alert(self, name: str, duration_minutes: int) -> None:
        """Close task and suppress recreation for duration_minutes."""
        alert = self.alerts.get(name)
        if not alert:
            _LOGGER.warning("snooze_alert: no alert named '%s'", name)
            return

        task_id = alert.get("task_id")
        if task_id:
            try:
                await self._api_close_task(task_id)
            except Exception as err:
                _LOGGER.warning("Failed to close task %s for snooze: %s", task_id, err)

        snooze_until = (dt_util.utcnow() + timedelta(minutes=duration_minutes)).isoformat()
        alert["task_id"] = None
        alert["recreate_at"] = None
        alert["snooze_until"] = snooze_until
        await self._async_save()

        entity = self._entities.get(name)
        if entity:
            entity.async_write_ha_state()

"""Todoist Alerts integration for Home Assistant."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import TodoistCoordinator
from .services import async_register_services

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Todoist Alerts from a config entry."""
    coordinator = TodoistCoordinator(hass, entry)

    # Load persisted alert state before setting up entities
    await coordinator.async_load()

    # Attempt first poll; don't block startup if Todoist is unreachable
    try:
        await coordinator.async_refresh()
    except Exception as err:
        _LOGGER.warning("Initial Todoist poll failed (will retry): %s", err)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await async_register_services(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded

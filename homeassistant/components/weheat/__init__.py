"""The Weheat integration."""

from __future__ import annotations

from http import HTTPStatus

import aiohttp
from weheat.abstractions.discovery import HeatPumpDiscovery
from weheat.exceptions import UnauthorizedException

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ACCESS_TOKEN, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.config_entry_oauth2_flow import (
    OAuth2Session,
    async_get_config_entry_implementation,
)

from .const import API_URL, LOGGER
from .coordinator import WeheatDataUpdateCoordinator

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]

type WeheatConfigEntry = ConfigEntry[list[WeheatDataUpdateCoordinator]]


async def async_setup_entry(hass: HomeAssistant, entry: WeheatConfigEntry) -> bool:
    """Set up Weheat from a config entry."""
    implementation = await async_get_config_entry_implementation(hass, entry)

    session = OAuth2Session(hass, entry, implementation)

    try:
        await session.async_ensure_token_valid()
    except aiohttp.ClientResponseError as ex:
        LOGGER.warning("API error: %s (%s)", ex.status, ex.message)
        if ex.status in (
            HTTPStatus.BAD_REQUEST,
            HTTPStatus.UNAUTHORIZED,
            HTTPStatus.FORBIDDEN,
        ):
            raise ConfigEntryAuthFailed("Token not valid, trigger renewal") from ex
        raise ConfigEntryNotReady from ex

    token = session.token[CONF_ACCESS_TOKEN]
    entry.runtime_data = []

    # fetch a list of the heat pumps the entry can access
    try:
        discovered_heat_pumps = await HeatPumpDiscovery.async_discover_active(
            API_URL, token, async_get_clientsession(hass)
        )
    except UnauthorizedException as error:
        raise ConfigEntryAuthFailed from error

    for pump_info in discovered_heat_pumps:
        LOGGER.debug("Adding %s", pump_info)
        # for each pump, add a coordinator
        new_coordinator = WeheatDataUpdateCoordinator(hass, session, pump_info)

        await new_coordinator.async_config_entry_first_refresh()

        entry.runtime_data.append(new_coordinator)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: WeheatConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.vacuum import (
    StateVacuumEntity,
    StateVacuumEntityDescription,
    VacuumEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.icon import icon_for_battery_level
from pymoebot import MoeBot

from . import BaseMoeBotEntity
from .const import DOMAIN

STATE_IDLE = "idle"
STATE_CLEANING = "cleaning"
STATE_DOCKED = "docked"
STATE_RETURNING = "returning"
STATE_ERROR = "error"

_STATUS_TO_HA: dict[str, str] = {
    "STANDBY":                    STATE_DOCKED,
    "MOWING":                     STATE_CLEANING,
    "CHARGING":                   STATE_DOCKED,
    "EMERGENCY":                  STATE_ERROR,
    "LOCKED":                     STATE_ERROR,
    "PAUSED":                     STATE_IDLE,
    "PARK":                       STATE_RETURNING,
    "CHARGING_WITH_TASK_SUSPEND": STATE_DOCKED,
    "FIXED_MOWING":               STATE_CLEANING,
    "ERROR":                      STATE_ERROR,
}

_log = logging.getLogger(__package__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    moebot = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([MoeBotVacuumEntity(moebot)])


class MoeBotVacuumEntity(BaseMoeBotEntity, StateVacuumEntity):
    entity_description: StateVacuumEntityDescription

    def __init__(self, moebot: MoeBot) -> None:
        super().__init__(moebot)
        self._attr_unique_id = f"{self._moebot.id}_vacuum"
        self._attr_name = "MoeBot"
        self._attr_icon = "mdi:robot-mower"
        self._attr_supported_features = (
            VacuumEntityFeature.PAUSE
            | VacuumEntityFeature.STOP
            | VacuumEntityFeature.RETURN_HOME
            | VacuumEntityFeature.BATTERY
            | VacuumEntityFeature.STATE
            | VacuumEntityFeature.START
        )

    @property
    def state(self) -> str:
        return _STATUS_TO_HA.get(self._moebot.state, STATE_ERROR)

    @property
    def battery_level(self) -> int:
        try:
            return round(self._moebot.battery)
        except (TypeError, ValueError):
            return 0

    @property
    def battery_icon(self) -> str:
        charging = self._moebot.state in {"CHARGING", "CHARGING_WITH_TASK_SUSPEND"}
        return icon_for_battery_level(
            battery_level=self.battery_level, charging=charging
        )

    # extra_state_attributes is inherited from BaseMoeBotEntity (cache-based, no polling)

    def start(self) -> None:
        self._moebot.start()

    def pause(self) -> None:
        self._moebot.pause()

    def stop(self, **kwargs: Any) -> None:
        self._moebot.cancel()

    def return_to_base(self, **kwargs: Any) -> None:
        self._moebot.dock()

    def clean_spot(self, **kwargs: Any) -> None:
        """Not implemented."""

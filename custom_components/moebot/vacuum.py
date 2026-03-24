from __future__ import annotations

import logging
from typing import Any

# Se eliminan las constantes STATE_ de aquí porque ya no existen en HA Core
from homeassistant.components.vacuum import (
    StateVacuumEntity, 
    StateVacuumEntityDescription, 
    VacuumEntityFeature
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.icon import icon_for_battery_level
from pymoebot import MoeBot

from . import BaseMoeBotEntity
from .const import DOMAIN

# Definición manual de estados para compatibilidad con HA moderno
STATE_IDLE = "idle"
STATE_CLEANING = "cleaning"
STATE_DOCKED = "docked"
STATE_RETURNING = "returning"
STATE_ERROR = "error"

_STATUS_TO_HA = {
    "STANDBY": STATE_DOCKED,
    "MOWING": STATE_CLEANING,
    "CHARGING": STATE_DOCKED,
    "EMERGENCY": STATE_ERROR,
    "LOCKED": STATE_ERROR,
    "PAUSED": STATE_IDLE,
    "PARK": STATE_RETURNING,
    "CHARGING_WITH_TASK_SUSPEND": STATE_DOCKED,
    "FIXED_MOWING": STATE_CLEANING,
    "ERROR": STATE_ERROR,
}

_log = logging.getLogger(__package__)


async def async_setup_entry(hass: HomeAssistant,
                            entry: ConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    """Set up MoeBot from a config entry."""
    moebot = hass.data[DOMAIN][entry.entry_id]

    moebot_entity = MoeBotVacuumEntity(moebot)
    async_add_entities([moebot_entity])


class MoeBotVacuumEntity(BaseMoeBotEntity, StateVacuumEntity):
    entity_description: StateVacuumEntityDescription

    def __init__(self, moebot: MoeBot):
        super().__init__(moebot)

        # ID único para la entidad
        self._attr_unique_id = f"{self._moebot.id}_vacuum"
        self._attr_name = f"MoeBot"
        self._attr_icon = "mdi:robot-mower"

        # Características soportadas (usando el nuevo formato de bits)
        self._attr_supported_features = (
            VacuumEntityFeature.PAUSE |
            VacuumEntityFeature.STOP |
            VacuumEntityFeature.RETURN_HOME |
            VacuumEntityFeature.BATTERY |
            VacuumEntityFeature.STATE |
            VacuumEntityFeature.START
        )

    @property
    def state(self) -> str | None:
        mb_state = self._moebot.state
        return _STATUS_TO_HA.get(mb_state, STATE_ERROR)

    @property
    def battery_icon(self) -> str:
        """Return the battery icon for the vacuum cleaner."""
        charging = bool(self._moebot.state in ["CHARGING", "CHARGING_WITH_TASK_SUSPEND"])

        return icon_for_battery_level(
            battery_level=self.battery_level, charging=charging
        )

    @property
    def battery_level(self) -> int | None:
        return round(self._moebot.battery)

    def start(self) -> None:
        """Start or resume the cleaning task."""
        self._moebot.start()

    def pause(self) -> None:
        """Pause the cleaning task."""
        self._moebot.pause()

    def stop(self, **kwargs: Any) -> None:
        self._moebot.cancel()

    def return_to_base(self, **kwargs: Any) -> None:
        self._moebot.dock()

    def clean_spot(self, **kwargs: Any) -> None:
        self._moebot.start(spiral=True)
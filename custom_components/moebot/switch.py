import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.entity import EntityCategory
from pymoebot import MoeBot

from . import BaseMoeBotEntity
from .const import DOMAIN

_log = logging.getLogger(__package__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    moebot = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities([
        HedgehogProtectionSwitch(moebot),
        BackwardBladeStopSwitch(moebot),
        ParkWhenRainingSwitch(moebot),
    ])


class ParkWhenRainingSwitch(BaseMoeBotEntity, SwitchEntity):
    def __init__(self, moebot: MoeBot) -> None:
        super().__init__(moebot)
        self._attr_unique_id = f"{self._moebot.id}_park_if_raining"
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_name = "Aparcar si Llueve"
        self._attr_icon = "mdi:weather-pouring"

    @property
    def is_on(self) -> bool:
        return bool(self._moebot.mow_in_rain)

    def turn_on(self, **kwargs: Any) -> None:
        self._moebot.mow_in_rain = True

    def turn_off(self, **kwargs: Any) -> None:
        self._moebot.mow_in_rain = False


class HedgehogProtectionSwitch(BaseMoeBotEntity, SwitchEntity):
    def __init__(self, moebot: MoeBot) -> None:
        super().__init__(moebot)
        self._attr_unique_id = f"{self._moebot.id}_hedgehog_protection"
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_name = "Protección de Erizos"
        self._attr_icon = "mdi:paw"

    @property
    def is_on(self) -> bool:
        return self._dp_cache.get("118") is True

    def turn_on(self, **kwargs: Any) -> None:
        _log.warning("DIAG turn_on 118: set_dp=%r, device=%r",
                     self._moebot.set_dp,
                     getattr(self._moebot, "_MoeBot__device", "NOT_FOUND"))
        result = self._moebot.set_dp({"118": True})
        _log.warning("DIAG set_dp({'118': True}) result: %r", result)
        self._dp_cache["118"] = True
        self.schedule_update_ha_state()

    def turn_off(self, **kwargs: Any) -> None:
        _log.warning("DIAG turn_off 118: set_dp=%r, device=%r",
                     self._moebot.set_dp,
                     getattr(self._moebot, "_MoeBot__device", "NOT_FOUND"))
        result = self._moebot.set_dp({"118": False})
        _log.warning("DIAG set_dp({'118': False}) result: %r", result)
        self._dp_cache["118"] = False
        self.schedule_update_ha_state()


class BackwardBladeStopSwitch(BaseMoeBotEntity, SwitchEntity):
    def __init__(self, moebot: MoeBot) -> None:
        super().__init__(moebot)
        self._attr_unique_id = f"{self._moebot.id}_backward_blade_stop"
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_name = "Parada Cuchilla Marcha Atrás"
        self._attr_icon = "mdi:saw-blade"

    @property
    def is_on(self) -> bool:
        return self._dp_cache.get("121") == 1

    def turn_on(self, **kwargs: Any) -> None:
        _log.warning("DIAG turn_on 121")
        result = self._moebot.set_dp({"121": 1})
        _log.warning("DIAG set_dp({'121': 1}) result: %r", result)
        self._dp_cache["121"] = 1
        self.schedule_update_ha_state()

    def turn_off(self, **kwargs: Any) -> None:
        _log.warning("DIAG turn_off 121")
        result = self._moebot.set_dp({"121": 0})
        _log.warning("DIAG set_dp({'121': 0}) result: %r", result)
        self._dp_cache["121"] = 0
        self.schedule_update_ha_state()

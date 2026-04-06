import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.entity import EntityCategory
from pymoebot import MoeBot

from . import BaseMoeBotEntity
from .const import DOMAIN

_log = logging.getLogger(__package__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Add switches for passed config_entry in HA."""
    moebot = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities([
        HedgehogProtectionSwitch(moebot),
        BackwardBladeStopSwitch(moebot),
        ParkWhenRainingSwitch(moebot),   # Last: groups naturally with RainDelayNumber
    ])


class ParkWhenRainingSwitch(BaseMoeBotEntity, SwitchEntity):
    """DP 104 – Park when rain sensor triggers (via pymoebot.mow_in_rain).

    Semantics: ON  = robot parks when rain is detected (rain mode active).
               OFF = robot ignores rain and keeps mowing.
    pymoebot exposes this as `mow_in_rain`; True means rain-parking IS enabled.
    """

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
        # Do NOT call schedule_update_ha_state() here.
        # pymoebot writes to the device; the push confirmation from the device
        # will trigger the listener which calls schedule_update_ha_state().
        # Calling it here AND from the listener causes the visible "bounce".

    def turn_off(self, **kwargs: Any) -> None:
        self._moebot.mow_in_rain = False


class HedgehogProtectionSwitch(BaseMoeBotEntity, SwitchEntity):
    """DP 118 – Small animal protection.

    State read from push cache (pre-populated at startup from status snapshot).
    Optimistic write: cache updated immediately; device confirmation via push.
    """

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
        self._moebot.set_dp({"118": True})
        self._dp_cache["118"] = True
        self.schedule_update_ha_state()

    def turn_off(self, **kwargs: Any) -> None:
        self._moebot.set_dp({"118": False})
        self._dp_cache["118"] = False
        self.schedule_update_ha_state()


class BackwardBladeStopSwitch(BaseMoeBotEntity, SwitchEntity):
    """DP 121 – Stop blade when reversing (valuereserved01 on Parkside).

    Parkside firmware: 1 = blade stops on reverse, 0 = blade keeps spinning.
    State read from push cache; optimistic write.
    """

    def __init__(self, moebot: MoeBot) -> None:
        super().__init__(moebot)
        self._attr_unique_id = f"{self._moebot.id}_backward_blade_stop"
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_name = "Parada Cuchilla Marcha Atrás"
        self._attr_icon = "mdi:saw-blade"

    @property
    def is_on(self) -> bool:
        # DP 121 is type 'value' (integer) on Parkside: 1 = ON, 0 = OFF.
        return self._dp_cache.get("121") == 1

    def turn_on(self, **kwargs: Any) -> None:
        self._moebot.set_dp({"121": 1})
        self._dp_cache["121"] = 1
        self.schedule_update_ha_state()

    def turn_off(self, **kwargs: Any) -> None:
        self._moebot.set_dp({"121": 0})
        self._dp_cache["121"] = 0
        self.schedule_update_ha_state()

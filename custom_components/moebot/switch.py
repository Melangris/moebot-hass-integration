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
        ParkWhenRainingSwitch(moebot),
        HedgehogProtectionSwitch(moebot),
        BackwardBladeStopSwitch(moebot)
    ])

class ParkWhenRainingSwitch(BaseMoeBotEntity, SwitchEntity):
    """Controla si el robot debe segar bajo la lluvia (DP 104)."""
    def __init__(self, moebot: MoeBot):
        super().__init__(moebot)

        # A unique_id for this entity within this domain.
        # Note: This is NOT used to generate the user visible Entity ID used in automations.
        self._attr_unique_id = f"{self._moebot.id}_park_if_raining"
        self._attr_entity_category = EntityCategory.CONFIG
        
        # Corregido: 'Mow in Rain' refleja fielmente el valor de self._moebot.mow_in_rain
        self._attr_name = "Mow in Rain"
        self._attr_icon = "mdi:weather-pouring"

    @property
    def is_on(self) -> bool:
        # Nota: pymoebot gestiona esto internamente con el DP 104
        return self._moebot.mow_in_rain

    def turn_on(self, **kwargs: Any) -> None:
        self._moebot.mow_in_rain = True
        self.schedule_update_ha_state()

    def turn_off(self, **kwargs: Any) -> None:
        self._moebot.mow_in_rain = False
        self.schedule_update_ha_state()

class HedgehogProtectionSwitch(BaseMoeBotEntity, SwitchEntity):
    """Entidad para el modo protección de erizos (DP 118)."""
    def __init__(self, moebot: MoeBot):
        super().__init__(moebot)
        self._attr_unique_id = f"{self._moebot.id}_hedgehog_protection"
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_name = "Protección de Erizos"
        self._attr_icon = "mdi:account-group"

    @property
    def is_on(self) -> bool:
        return self._moebot._device.status().get('118') is True

    def turn_on(self, **kwargs: Any) -> None:
        self._moebot._device.set_status({'118': True})
        self.schedule_update_ha_state()

    def turn_off(self, **kwargs: Any) -> None:
        self._moebot._device.set_status({'118': False})
        self.schedule_update_ha_state()

class BackwardBladeStopSwitch(BaseMoeBotEntity, SwitchEntity):
    """Control de parada de cuchilla al retroceder (DP 121)."""
    def __init__(self, moebot: MoeBot):
        super().__init__(moebot)
        self._attr_unique_id = f"{self._moebot.id}_backward_blade_stop"
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_name = "Parada Cuchilla Marcha Atrás"
        self._attr_icon = "mdi:saw-blade"

    @property
    def is_on(self) -> bool:
        # Según la plantilla Parkside: 1 es ON (parada activa), 0 es OFF
        val = self._moebot._device.status().get('121')
        return val == 1

    def turn_on(self, **kwargs: Any) -> None:
        # Enviamos el entero 1 para activar la parada (según plantilla de tuya-local)
        self._moebot._device.set_status({'121': 1})
        self.schedule_update_ha_state()

    def turn_off(self, **kwargs: Any) -> None:
        # Enviamos el entero 0 para permitir que gire al retroceder
        self._moebot._device.set_status({'121': 0})
        self.schedule_update_ha_state()

import logging
import base64
from dataclasses import dataclass
from enum import Enum

from homeassistant.components.number import NumberEntity, NumberMode, NumberDeviceClass
from homeassistant.helpers.entity import EntityCategory
from pymoebot import ZoneConfig, MoeBot

from . import BaseMoeBotEntity
from .const import DOMAIN

_log = logging.getLogger(__package__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Add sensors for passed config_entry in HA."""
    moebot = hass.data[DOMAIN][config_entry.entry_id]

    entities = [
            WorkingTimeNumber(moebot),
            RainDelayNumber(moebot)
    ]
    for zone in range(1, 6):
        for part in ZoneNumberType:
            entities.append(ZoneConfigNumber(moebot, zone, part))

    async_add_entities(entities)


class RainDelayNumber(BaseMoeBotEntity, NumberEntity):
    """Control del tiempo de espera tras lluvia (DP 139)."""

    def __init__(self, moebot: MoeBot):
        super().__init__(moebot)
        self._attr_unique_id = f"{self._moebot.id}_rain_delay_min"
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_name = "Tiempo Espera Lluvia"
        self._attr_native_min_value = 0
        self._attr_native_max_value = 720
        self._attr_native_step = 1
        self._attr_mode = NumberMode.BOX
        self._attr_native_unit_of_measurement = "min"
        self._attr_icon = "mdi:timer-sand"

    @property
    def native_value(self) -> float | None:
        # Obtenemos el valor Base64 (ej: 'AXg=' -> [0x01, 0x78] -> 120)
        b64_val = self._moebot._device.status().get('139')
        if not b64_val:
            return None
        try:
            decoded = base64.b64decode(b64_val)
            if len(decoded) >= 2:
                return float(decoded[1])
        except Exception as e:
            _log.error("Error decodificando rain_delay (DP 139): %s", e)
            return None
        return None

    def set_native_value(self, value: float) -> None:
        # Convertimos: 120 -> [0x01, 0x78] -> 'AXg='
        payload = bytes([0x01, int(value)])
        b64_value = base64.b64encode(payload).decode('utf-8')
        self._moebot._device.set_status({'139': b64_value})
        self.schedule_update_ha_state()


class WorkingTimeNumber(BaseMoeBotEntity, NumberEntity):
    """Control del tiempo de trabajo diario (DP 105)."""

    def __init__(self, moebot):
        super().__init__(moebot)

        # A unique_id for this entity within this domain.
        # Note: This is NOT used to generate the user visible Entity ID used in automations.
        self._attr_unique_id = f"{self._moebot.id}_mow_time_hrs"
        self._attr_entity_category = EntityCategory.CONFIG

        self._attr_name = "Mowing Time"

        self._attr_native_min_value = 1
        # Ajustado a 24 según la plantilla de tuya-local para Parkside
        self._attr_native_max_value = 24
        self._attr_native_step = 1
        self._attr_mode = NumberMode.SLIDER
        self._attr_device_class = NumberDeviceClass.DURATION
        self._attr_native_unit_of_measurement = "h"

    @property
    def native_value(self) -> float:
        return float(self._moebot.mow_time)

    def set_native_value(self, value: float) -> None:
        self._moebot.mow_time = int(value)
        self.schedule_update_ha_state()


@dataclass
class ZoneTypeDataMixin:
    type_name: str
    position: int


class ZoneNumberType(ZoneTypeDataMixin, Enum):
    DISTANCE = 'Distance', 0
    RATIO = 'Ratio', 1


class ZoneConfigNumber(BaseMoeBotEntity, NumberEntity):
    def __init__(self, moebot: MoeBot, zone: int, part: ZoneNumberType):
        super().__init__(moebot)
        self.zone = zone
        self.part = part

        # A unique_id for this entity within this domain.
        # Note: This is NOT used to generate the user visible Entity ID used in automations.
        self._attr_unique_id = f"{self._moebot.id}_zone{self.zone}_{self.part.value.type_name.lower()}"
        self._attr_entity_category = EntityCategory.CONFIG

        self._attr_name = f"Zone {self.zone} {self.part.value.type_name}"

        self._attr_native_min_value = 0
        self._attr_native_max_value = 100 if self.part == ZoneNumberType.RATIO else 200
        self._attr_native_step = 1
        self._attr_mode = NumberMode.BOX
        self._attr_native_unit_of_measurement = "%" if self.part == ZoneNumberType.RATIO else "m"
        self._attr_device_class = NumberDeviceClass.DISTANCE if self.part == ZoneNumberType.DISTANCE else None

        self._attr_entity_registry_enabled_default = False

    @classmethod
    def zone_config_to_list(cls, zc: ZoneConfig):
        return [int(zc.zone1[0]), int(zc.zone1[1]),
                int(zc.zone2[0]), int(zc.zone2[1]),
                int(zc.zone3[0]), int(zc.zone3[1]),
                int(zc.zone4[0]), int(zc.zone4[1]),
                int(zc.zone5[0]), int(zc.zone5[1]),
                ]

    @property
    def native_value(self) -> float:
        if not self._moebot.zones:
            _log.debug("Zone data hasn't been retrieved, can't provide values")
            return None

        zone_values = ZoneConfigNumber.zone_config_to_list(self._moebot.zones)
        return float(zone_values[(2 * (self.zone - 1)) + self.part.value.position])

    def set_native_value(self, value: float) -> None:
        new_zone_values = ZoneConfigNumber.zone_config_to_list(self._moebot.zones)
        new_zone_values[(2 * (self.zone - 1)) + self.part.value.position] = int(value)

        zc = ZoneConfig(*new_zone_values)
        self._moebot.zones = zc
        self.schedule_update_ha_state()

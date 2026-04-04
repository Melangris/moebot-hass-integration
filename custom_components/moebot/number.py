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
    """Add number entities for passed config_entry in HA."""
    moebot = hass.data[DOMAIN][config_entry.entry_id]

    entities: list = [WorkingTimeNumber(moebot), RainDelayNumber(moebot)]
    for zone in range(1, 6):
        for part in ZoneNumberType:
            entities.append(ZoneConfigNumber(moebot, zone, part))

    async_add_entities(entities)


class RainDelayNumber(BaseMoeBotEntity, NumberEntity):
    """DP 139 – Rain delay in minutes. Reads from push cache, never polls."""

    def __init__(self, moebot: MoeBot) -> None:
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
        """Decode Base64 DP 139 from push cache. e.g. 'AXg=' → [0x01,0x78] → 120."""
        b64_val = self._dp_cache.get("139")
        if not b64_val:
            return None
        try:
            decoded = base64.b64decode(b64_val)
            if len(decoded) >= 2:
                return float(decoded[1])
        except Exception as exc:
            _log.error("Error decoding rain_delay DP 139: %s", exc)
        return None

    def set_native_value(self, value: float) -> None:
        """Encode minutes as Base64 and send to device."""
        payload = bytes([0x01, int(value)])
        b64_value = base64.b64encode(payload).decode("utf-8")
        self._moebot.set_dp({"139": b64_value})
        # Optimistic update so the UI reflects immediately
        self._dp_cache["139"] = b64_value
        self.schedule_update_ha_state()


class WorkingTimeNumber(BaseMoeBotEntity, NumberEntity):
    """DP 105 – Daily mowing time (via pymoebot property)."""

    def __init__(self, moebot: MoeBot) -> None:
        super().__init__(moebot)
        self._attr_unique_id = f"{self._moebot.id}_mow_time_hrs"
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_name = "Mowing Time"
        self._attr_native_min_value = 1
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
    DISTANCE = "Distance", 0
    RATIO = "Ratio", 1


class ZoneConfigNumber(BaseMoeBotEntity, NumberEntity):
    def __init__(self, moebot: MoeBot, zone: int, part: ZoneNumberType) -> None:
        super().__init__(moebot)
        self.zone = zone
        self.part = part
        self._attr_unique_id = (
            f"{self._moebot.id}_zone{zone}_{part.value.type_name.lower()}"
        )
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_name = f"Zone {zone} {part.value.type_name}"
        self._attr_native_min_value = 0
        self._attr_native_max_value = 100 if part == ZoneNumberType.RATIO else 200
        self._attr_native_step = 1
        self._attr_mode = NumberMode.BOX
        self._attr_native_unit_of_measurement = (
            "%" if part == ZoneNumberType.RATIO else "m"
        )
        self._attr_device_class = (
            NumberDeviceClass.DISTANCE if part == ZoneNumberType.DISTANCE else None
        )
        self._attr_entity_registry_enabled_default = False

    @staticmethod
    def zone_config_to_list(zc: ZoneConfig) -> list[int]:
        return [
            int(zc.zone1[0]), int(zc.zone1[1]),
            int(zc.zone2[0]), int(zc.zone2[1]),
            int(zc.zone3[0]), int(zc.zone3[1]),
            int(zc.zone4[0]), int(zc.zone4[1]),
            int(zc.zone5[0]), int(zc.zone5[1]),
        ]

    @property
    def native_value(self) -> float | None:
        if not self._moebot.zones:
            _log.debug("Zone data not yet received")
            return None
        values = ZoneConfigNumber.zone_config_to_list(self._moebot.zones)
        return float(values[(2 * (self.zone - 1)) + self.part.value.position])

    def set_native_value(self, value: float) -> None:
        new_values = ZoneConfigNumber.zone_config_to_list(self._moebot.zones)
        new_values[(2 * (self.zone - 1)) + self.part.value.position] = int(value)
        self._moebot.zones = ZoneConfig(*new_values)
        self.schedule_update_ha_state()

import logging
import base64

from homeassistant.components.sensor import SensorEntity, SensorStateClass, SensorDeviceClass
from homeassistant.const import PERCENTAGE
from homeassistant.helpers.entity import EntityCategory

from . import BaseMoeBotEntity
from .const import DOMAIN

_log = logging.getLogger(__package__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Add sensors for passed config_entry in HA."""
    moebot = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities([
        MowingStateSensor(moebot),
        BatterySensor(moebot),
        EmergencyStateSensor(moebot),
        WorkModeSensor(moebot),
        DetailedStatusSensor(moebot),
        PyMoebotVersionSensor(moebot),
        TuyaVersionSensor(moebot),
    ])


class SensorBase(BaseMoeBotEntity, SensorEntity):
    def __init__(self, moebot):
        super().__init__(moebot)


class MowingStateSensor(SensorBase):
    def __init__(self, moebot):
        super().__init__(moebot)
        self._attr_unique_id = f"{self._moebot.id}_state"
        self._attr_name = "Mowing State"

    @property
    def native_value(self):
        return self._moebot.state


class DetailedStatusSensor(SensorBase):
    """Sensor for DP 103 (detailed error/status) – reads from push cache."""

    _STATUS_MAP = {
        "charge_done":       "Carga Completa",
        "charging":          "Cargando",
        "emergency":         "Emergencia (STOP)",
        "error":             "Error",
        "mowing":            "Segando",
        "no_loop_signal":    "Sin Señal de Cable",
        "outside_boundary":  "Fuera de Perímetro",
        "park":              "Aparcado",
        "pause":             "Pausado",
        "rain_park":         "Aparcado por Lluvia",
        "return_to_base":    "Regresando a Base",
        "standby":           "En Espera",
    }

    def __init__(self, moebot):
        super().__init__(moebot)
        self._attr_unique_id = f"{self._moebot.id}_detailed_status"
        self._attr_name = "Estado Detallado"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> str:
        """Return translated state from cached DP 103 – no network call."""
        raw = self._dp_cache.get("103")
        if raw is None:
            return "Unknown"
        return self._STATUS_MAP.get(str(raw), f"Desconocido ({raw})")


class EmergencyStateSensor(SensorBase):
    def __init__(self, moebot):
        super().__init__(moebot)
        self._attr_unique_id = f"{self._moebot.id}_emergency_state"
        self._attr_name = "Emergency State"

    @property
    def native_value(self):
        return self._moebot.emergency_state


class WorkModeSensor(SensorBase):
    def __init__(self, moebot):
        super().__init__(moebot)
        self._attr_unique_id = f"{self._moebot.id}_work_mode"
        self._attr_name = "Work Mode"

    @property
    def native_value(self):
        return self._moebot.work_mode


class BatterySensor(SensorBase):
    def __init__(self, moebot):
        super().__init__(moebot)
        self._attr_unique_id = f"{self._moebot.id}_battery"
        self._attr_name = "Battery Level"
        self._attr_device_class = SensorDeviceClass.BATTERY
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> int:
        try:
            return int(self._moebot.battery)
        except (TypeError, ValueError):
            return 0


class PyMoebotVersionSensor(SensorBase):
    def __init__(self, moebot):
        super().__init__(moebot)
        self._attr_unique_id = f"{self._moebot.id}_pymoebot_version"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_name = "pymoebot Version"

    @property
    def native_value(self):
        return self._moebot.pymoebot_version


class TuyaVersionSensor(SensorBase):
    def __init__(self, moebot):
        super().__init__(moebot)
        self._attr_unique_id = f"{self._moebot.id}_tuya_version"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_name = "Tuya Protocol Version"

    @property
    def native_value(self):
        return self._moebot.tuya_version

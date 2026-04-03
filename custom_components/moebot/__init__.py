"""The MoeBot integration."""
from __future__ import annotations

import logging
import base64
from datetime import datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform, EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.entity import Entity, DeviceInfo
from pymoebot import MoeBot

from .const import DOMAIN

PLATFORMS: list[Platform] = [
    Platform.VACUUM, 
    Platform.SENSOR, 
    Platform.NUMBER, 
    Platform.SWITCH, 
    Platform.BUTTON,
    Platform.LAWN_MOWER
]

_log = logging.getLogger(__package__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up MoeBot from a config entry."""
    moebot = await hass.async_add_executor_job(
        MoeBot, 
        entry.data["device_id"], 
        entry.data["ip_address"],
        entry.data["local_key"]
    )
    _log.info("Created a moebot: %r" % moebot)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = moebot
    
    await hass.async_add_executor_job(moebot.listen)

    # --- REGISTRO DE SERVICIOS PERSONALIZADOS ---

    async def handle_set_back_mowing(call: ServiceCall):
        """Servicio para Backward blade stop (DP 121). 0=False, 1=True."""
        enabled = call.data.get("enabled")
        # Según la plantilla Parkside, 1 detiene la cuchilla, 0 permite el giro
        val_121 = 1 if enabled else 0
        _log.debug("Llamando a set_status DP 121 con valor entero: %s", val_121)
        await hass.async_add_executor_job(moebot._device.set_status, {'121': val_121})

    async def handle_set_rain_delay(call: ServiceCall):
        """Servicio para configurar retraso de lluvia (DP 139)."""
        minutes = call.data.get("minutes")
        payload = bytes([0x01, int(minutes)])
        b64_value = base64.b64encode(payload).decode('utf-8')
        await hass.async_add_executor_job(moebot._device.set_status, {'139': b64_value})

    async def handle_set_hedgehog_protection(call: ServiceCall):
        """Servicio para protección de erizos (DP 118)."""
        enabled = call.data.get("enabled")
        await hass.async_add_executor_job(moebot._device.set_status, {'118': enabled})

    # Registro de servicios en el dominio moebot
    hass.services.async_register(DOMAIN, "set_back_mowing", handle_set_back_mowing)
    hass.services.async_register(DOMAIN, "set_rain_delay", handle_set_rain_delay)
    hass.services.async_register(DOMAIN, "set_hedgehog_protection", handle_set_hedgehog_protection)

    # --- FIN REGISTRO SERVICIOS ---

    def shutdown_moebot(event):
        """In the shutdown callback."""
        moebot.unlisten()

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, shutdown_moebot)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        moebot = hass.data[DOMAIN][entry.entry_id]
        moebot.unlisten()
        hass.data[DOMAIN].pop(entry.entry_id)
        
        # Eliminamos los servicios al descargar la integración
        for service in ["set_back_mowing", "set_rain_delay", "set_hedgehog_protection"]:
            hass.services.async_remove(DOMAIN, service)

    return unload_ok

class BaseMoeBotEntity(Entity):
    """The abstract base device for all MoeBot entities."""

    def __init__(self, moebot: MoeBot):
        self._moebot = moebot
        # MoeBot class is LOCAL PUSH, so we tell HA that it should not be polled
        self._attr_should_poll = False
        
        # Link this Entity under the MoeBot device. 
        # Refined with Parkside PMRDA specific info.
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._moebot.id)},
            name="Parkside PMRDA",
            manufacturer="Parkside",
            model="PMRDA 20-Li A1"
        )

    @property
    def extra_state_attributes(self):
        """Return entity specific state attributes."""
        attrs = {}
        if self._moebot.last_update is not None:
            attrs["last_message_received"] = datetime.fromtimestamp(self._moebot.last_update)
        
        # Monitorizamos solo los DPs confirmados por la plantilla del Parkside
        status = self._moebot._device.status()
        attrs["hedgehog_protection_118"] = status.get('118')
        attrs["backward_blade_stop_121"] = status.get('121')
        attrs["rain_delay_raw_139"] = status.get('139')
        attrs["status_detailed_103"] = status.get('103')
        
        return attrs

    async def async_added_to_hass(self) -> None:
        """Run when this Entity has been added to HA."""
        # The call back registration is done once this entity is registered with HA
        def listener(raw_msg):
            self.schedule_update_ha_state()

        self._moebot.add_listener(listener)

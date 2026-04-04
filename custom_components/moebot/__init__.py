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
    Platform.LAWN_MOWER,
]

_log = logging.getLogger(__package__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up MoeBot from a config entry."""
    moebot = await hass.async_add_executor_job(
        MoeBot,
        entry.data["device_id"],
        entry.data["ip_address"],
        entry.data["local_key"],
    )
    _log.info("Created a moebot: %r", moebot)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = moebot

    await hass.async_add_executor_job(moebot.listen)

    # --- CUSTOM SERVICES ---

    async def handle_set_back_mowing(call: ServiceCall) -> None:
        """DP 121 – Backward blade stop. 1=stop blade, 0=allow spin."""
        val = 1 if call.data.get("enabled") else 0
        _log.debug("set_back_mowing DP 121 → %s", val)
        await hass.async_add_executor_job(
            moebot._device.set_status, {"121": val}
        )

    async def handle_set_rain_delay(call: ServiceCall) -> None:
        """DP 139 – Rain delay in minutes, encoded as Base64."""
        minutes = int(call.data.get("minutes", 60))
        payload = bytes([0x01, minutes])
        b64_value = base64.b64encode(payload).decode("utf-8")
        _log.debug("set_rain_delay DP 139 → %s (%d min)", b64_value, minutes)
        await hass.async_add_executor_job(
            moebot._device.set_status, {"139": b64_value}
        )

    async def handle_set_hedgehog_protection(call: ServiceCall) -> None:
        """DP 118 – Hedgehog/small animal protection."""
        enabled = bool(call.data.get("enabled"))
        _log.debug("set_hedgehog_protection DP 118 → %s", enabled)
        await hass.async_add_executor_job(
            moebot._device.set_status, {"118": enabled}
        )

    for name, handler in (
        ("set_back_mowing", handle_set_back_mowing),
        ("set_rain_delay", handle_set_rain_delay),
        ("set_hedgehog_protection", handle_set_hedgehog_protection),
    ):
        hass.services.async_register(DOMAIN, name, handler)

    # --- END CUSTOM SERVICES ---

    def shutdown_moebot(event) -> None:
        """Stop listener on HA shutdown."""
        moebot.unlisten()

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, shutdown_moebot)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        moebot = hass.data[DOMAIN].pop(entry.entry_id)
        moebot.unlisten()
        for service in ("set_back_mowing", "set_rain_delay", "set_hedgehog_protection"):
            hass.services.async_remove(DOMAIN, service)
    return unload_ok


class BaseMoeBotEntity(Entity):
    """Abstract base entity for all MoeBot entities."""

    # DPs we want to track from push updates
    _TRACKED_DPS: tuple[str, ...] = ("103", "118", "121", "139")

    def __init__(self, moebot: MoeBot) -> None:
        self._moebot = moebot
        self._attr_should_poll = False
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._moebot.id)},
            name="Parkside PMRDA",
            manufacturer="Parkside",
            model="PMRDA 20-Li A1",
        )
        # DP cache populated by push listener – avoids blocking status() calls
        self._dp_cache: dict[str, object] = {}

    # ------------------------------------------------------------------
    # Availability
    # ------------------------------------------------------------------

    @property
    def available(self) -> bool:
        return self._moebot.online

    # ------------------------------------------------------------------
    # State attributes – reads ONLY from cache, never calls status()
    # ------------------------------------------------------------------

    @property
    def extra_state_attributes(self) -> dict:
        attrs: dict = {}
        if self._moebot.last_update is not None:
            attrs["last_message_received"] = datetime.fromtimestamp(
                self._moebot.last_update
            )
        attrs["hedgehog_protection_118"] = self._dp_cache.get("118")
        attrs["backward_blade_stop_121"] = self._dp_cache.get("121")
        attrs["rain_delay_raw_139"] = self._dp_cache.get("139")
        attrs["status_detailed_103"] = self._dp_cache.get("103")
        return attrs

    # ------------------------------------------------------------------
    # Listener registration
    # ------------------------------------------------------------------

    async def async_added_to_hass(self) -> None:
        """Register listener once entity is added to HA."""

        def listener(raw_msg: dict) -> None:
            _log.debug("%s update: %r", self.__class__.__name__, raw_msg)
            # raw_msg may contain a 'dps' key with updated datapoints
            if isinstance(raw_msg, dict):
                dps: dict = raw_msg.get("dps", {})
                for dp in self._TRACKED_DPS:
                    if dp in dps:
                        self._dp_cache[dp] = dps[dp]
            self.schedule_update_ha_state()

        self._moebot.add_listener(listener)

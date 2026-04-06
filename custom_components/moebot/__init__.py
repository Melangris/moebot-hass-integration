"""The MoeBot integration."""
from __future__ import annotations

import logging
import base64
from datetime import datetime
from typing import Any

import tinytuya

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

# Attribute names that pymoebot may use internally for its tinytuya Device.
_PYMOEBOT_TUYA_ATTRS = ("_d", "_device", "_tuya", "_tinytuya", "_client", "_mower_device")


def _find_tuya_device(moebot: MoeBot):
    """Return pymoebot's internal tinytuya Device if accessible, else None."""
    for attr in _PYMOEBOT_TUYA_ATTRS:
        candidate = getattr(moebot, attr, None)
        if candidate is not None and hasattr(candidate, "set_status"):
            _log.debug("Found pymoebot's tinytuya device at attribute '%s'", attr)
            return candidate
    _log.debug("pymoebot internal tinytuya device not found; will use ephemeral connections")
    return None


def _build_tuya_writer(device_id: str, ip: str, local_key: str, version: float):
    """Fallback write path: ephemeral tinytuya connection per write.

    Uses nowait=True to avoid racing with pymoebot's persistent listener socket.
    """
    def _send(dp_dict: dict[str, Any]) -> None:
        d = tinytuya.Device(device_id, ip, local_key)
        d.set_version(version)
        result = d.set_status(dp_dict, nowait=True)
        _log.debug("tinytuya ephemeral set_status %r → %r", dp_dict, result)

    return _send


def _fetch_initial_dps(device_id: str, ip: str, local_key: str, version: float) -> dict:
    """Query device for a full status snapshot before the listener starts."""
    try:
        d = tinytuya.Device(device_id, ip, local_key)
        d.set_version(version)
        result = d.status()
        if isinstance(result, dict):
            dps = result.get("dps", {})
            _log.debug("Initial DPS snapshot: %r", dps)
            return dps
    except Exception as exc:
        _log.warning("Could not fetch initial DPS snapshot: %s", exc)
    return {}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up MoeBot from a config entry."""
    device_id: str = entry.data["device_id"]
    ip_address: str = entry.data["ip_address"]
    local_key: str = entry.data["local_key"]

    moebot: MoeBot = await hass.async_add_executor_job(
        MoeBot, device_id, ip_address, local_key
    )
    _log.info("Created a moebot: %r", moebot)

    try:
        tuya_version = float(moebot.tuya_version)
    except (TypeError, ValueError):
        tuya_version = 3.3
        _log.warning("Could not read tuya_version from moebot, defaulting to 3.3")

    # Fetch initial DPS *before* starting the listener so the cache is
    # pre-populated for DPs 118, 121, 139 which are not pushed spontaneously.
    initial_dps: dict = await hass.async_add_executor_job(
        _fetch_initial_dps, device_id, ip_address, local_key, tuya_version
    )
    moebot._initial_dps = initial_dps  # consumed by BaseMoeBotEntity.async_added_to_hass

    # Inject write callable. Prefer pymoebot's own tinytuya device (same
    # socket) to avoid the concurrent-connection errors (Tuya 904/914).
    tuya_device = _find_tuya_device(moebot)
    if tuya_device is not None:
        moebot.set_dp = lambda dp_dict: tuya_device.set_status(dp_dict, nowait=True)
    else:
        moebot.set_dp = _build_tuya_writer(device_id, ip_address, local_key, tuya_version)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = moebot
    await hass.async_add_executor_job(moebot.listen)

    # --- CUSTOM SERVICES ---

    async def handle_set_back_mowing(call: ServiceCall) -> None:
        """DP 121 – Backward blade stop. 1=stop blade, 0=allow spin."""
        val = 1 if call.data.get("enabled") else 0
        _log.debug("set_back_mowing DP 121 → %s", val)
        await hass.async_add_executor_job(moebot.set_dp, {"121": val})

    async def handle_set_rain_delay(call: ServiceCall) -> None:
        """DP 139 – Rain delay in minutes, Base64-encoded."""
        minutes = int(call.data.get("minutes", 60))
        payload = bytes([0x01, minutes])
        b64_value = base64.b64encode(payload).decode("utf-8")
        _log.debug("set_rain_delay DP 139 → %s (%d min)", b64_value, minutes)
        await hass.async_add_executor_job(moebot.set_dp, {"139": b64_value})

    async def handle_set_hedgehog_protection(call: ServiceCall) -> None:
        """DP 118 – Hedgehog/small animal protection."""
        enabled = bool(call.data.get("enabled"))
        _log.debug("set_hedgehog_protection DP 118 → %s", enabled)
        await hass.async_add_executor_job(moebot.set_dp, {"118": enabled})

    for name, handler in (
        ("set_back_mowing", handle_set_back_mowing),
        ("set_rain_delay", handle_set_rain_delay),
        ("set_hedgehog_protection", handle_set_hedgehog_protection),
    ):
        hass.services.async_register(DOMAIN, name, handler)

    def shutdown_moebot(event) -> None:
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


def _parse_dps_from_raw_msg(raw_msg: Any) -> dict:
    """Extract DPS dict from whatever format pymoebot passes to listeners.

    pymoebot wraps tinytuya and may pass:
      - {'dps': {'101': 'MOWING', ...}}       (flat wrapper)
      - {'data': {'dps': {...}}}               (nested tinytuya format)
      - {'101': 'MOWING', ...}                (raw flat dict without wrapper)
    """
    if not isinstance(raw_msg, dict):
        return {}

    if "dps" in raw_msg and isinstance(raw_msg["dps"], dict):
        return raw_msg["dps"]

    data = raw_msg.get("data")
    if isinstance(data, dict) and "dps" in data:
        return data["dps"]

    # Raw flat dict with numeric-string keys
    if any(str(k).isdigit() for k in raw_msg):
        return {str(k): v for k, v in raw_msg.items()}

    return {}


class BaseMoeBotEntity(Entity):
    """Abstract base entity for all MoeBot entities."""

    # DPs not exposed by pymoebot as properties – we cache them ourselves.
    _TRACKED_DPS: tuple[str, ...] = ("118", "121", "139")

    def __init__(self, moebot: MoeBot) -> None:
        self._moebot = moebot
        self._attr_should_poll = False
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._moebot.id)},
            name="Parkside PMRDA",
            manufacturer="Parkside",
            model="PMRDA 20-Li A1",
        )
        self._dp_cache: dict[str, Any] = {}

    @property
    def available(self) -> bool:
        return self._moebot.online

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
        return attrs

    async def async_added_to_hass(self) -> None:
        """Register listener and pre-populate DP cache."""
        # Seed cache from the initial snapshot taken before the listener started.
        for dp, val in getattr(self._moebot, "_initial_dps", {}).items():
            if dp in self._TRACKED_DPS:
                self._dp_cache[dp] = val

        def listener(raw_msg: Any) -> None:
            _log.debug("%s push: %r", self.__class__.__name__, raw_msg)
            dps = _parse_dps_from_raw_msg(raw_msg)
            for dp in self._TRACKED_DPS:
                if dp in dps:
                    self._dp_cache[dp] = dps[dp]
            self.schedule_update_ha_state()

        self._moebot.add_listener(listener)

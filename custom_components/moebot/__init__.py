"""The MoeBot integration."""
from __future__ import annotations

import logging
import base64
from datetime import datetime
from typing import Any

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

# pymoebot 0.3.1 internal attributes (name-mangled)
_ATTR_DEVICE    = "_MoeBot__device"
_ATTR_QUEUE_CMD = "_MoeBot__queue_command"
_ATTR_LISTENERS = "_MoeBot__listeners"


def _make_set_dp(moebot: MoeBot):
    """Return the best available callable to write DPs to the device.

    pymoebot serialises all device writes through __queue_command, which
    is processed by its own listener thread — the same thread that owns
    the persistent TCP socket.  Using this mechanism is the only safe way
    to write DPs without racing against the listener's recv() loop.

    Direct set_status() calls on the shared Device object from a different
    thread (HA executor) result in the device silently dropping the command
    because the listener thread receives the ACK before set_status() can,
    leaving the operation with no confirmation and no effect.
    """
    queue_command = getattr(moebot, _ATTR_QUEUE_CMD, None)
    if callable(queue_command):
        _log.debug("set_dp will use pymoebot's internal __queue_command")
        return queue_command

    # Fallback: should never be reached with pymoebot 0.3.1, but log clearly.
    _log.error(
        "pymoebot.__queue_command not found — DP writes will not work. "
        "Available attrs: %r",
        [a for a in dir(moebot) if "queue" in a.lower() or "command" in a.lower()],
    )
    return lambda dp_dict: _log.error("set_dp unavailable: %r", dp_dict)


def _fetch_initial_dps(moebot: MoeBot) -> dict:
    """Snapshot current DPs before the listener starts.

    Uses pymoebot's own Device object (persist=False at this point, before
    listen() is called) so there is no concurrent socket conflict.
    """
    device = getattr(moebot, _ATTR_DEVICE, None)
    if device is None:
        _log.warning("Cannot fetch initial DPS: %s not found", _ATTR_DEVICE)
        return {}
    try:
        result = device.status()
        if isinstance(result, dict):
            dps = result.get("dps", {})
            _log.debug("Initial DPS snapshot: %r", dps)
            return dps
    except Exception as exc:
        _log.warning("Could not fetch initial DPS snapshot: %s", exc)
    return {}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up MoeBot from a config entry."""
    moebot: MoeBot = await hass.async_add_executor_job(
        MoeBot,
        entry.data["device_id"],
        entry.data["ip_address"],
        entry.data["local_key"],
    )
    _log.info("Created moebot: %r", moebot)

    # Snapshot DPs before listen() so the cache starts populated.
    initial_dps: dict = await hass.async_add_executor_job(
        _fetch_initial_dps, moebot
    )
    moebot._initial_dps = initial_dps

    # Inject thread-safe write callable using pymoebot's internal queue.
    moebot.set_dp = _make_set_dp(moebot)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = moebot
    await hass.async_add_executor_job(moebot.listen)

    # --- CUSTOM SERVICES ---

    async def handle_set_back_mowing(call: ServiceCall) -> None:
        """DP 121 – Backward blade stop. 1=stop blade, 0=allow spin."""
        val = 1 if call.data.get("enabled") else 0
        await hass.async_add_executor_job(moebot.set_dp, {"121": val})

    async def handle_set_rain_delay(call: ServiceCall) -> None:
        """DP 139 – Rain delay in minutes, Base64-encoded."""
        minutes = int(call.data.get("minutes", 60))
        payload = bytes([0x01, minutes])
        b64_value = base64.b64encode(payload).decode("utf-8")
        await hass.async_add_executor_job(moebot.set_dp, {"139": b64_value})

    async def handle_set_hedgehog_protection(call: ServiceCall) -> None:
        """DP 118 – Hedgehog/small animal protection."""
        enabled = bool(call.data.get("enabled"))
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
    """Extract DPS dict from whatever format pymoebot passes to listeners."""
    if not isinstance(raw_msg, dict):
        return {}
    if "dps" in raw_msg and isinstance(raw_msg["dps"], dict):
        return raw_msg["dps"]
    data = raw_msg.get("data")
    if isinstance(data, dict) and "dps" in data:
        return data["dps"]
    if any(str(k).isdigit() for k in raw_msg):
        return {str(k): v for k, v in raw_msg.items()}
    return {}


class BaseMoeBotEntity(Entity):
    """Abstract base entity for all MoeBot entities."""

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
        self._listener_fn = None

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
        """Register listener and pre-populate DP cache from initial snapshot."""
        for dp, val in getattr(self._moebot, "_initial_dps", {}).items():
            if str(dp) in self._TRACKED_DPS:
                self._dp_cache[str(dp)] = val

        def listener(raw_msg: Any) -> None:
            dps = _parse_dps_from_raw_msg(raw_msg)
            for dp in self._TRACKED_DPS:
                if dp in dps:
                    self._dp_cache[dp] = dps[dp]
            self.schedule_update_ha_state()

        self._listener_fn = listener
        self._moebot.add_listener(listener)

    async def async_will_remove_from_hass(self) -> None:
        """Deregister listener to prevent accumulation across reloads."""
        if self._listener_fn is not None:
            listeners: list = getattr(self._moebot, _ATTR_LISTENERS, [])
            try:
                listeners.remove(self._listener_fn)
            except ValueError:
                pass
            self._listener_fn = None

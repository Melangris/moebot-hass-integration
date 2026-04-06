import logging

from homeassistant.components.button import ButtonEntity, ButtonDeviceClass
from homeassistant.helpers.entity import EntityCategory

from . import BaseMoeBotEntity
from .const import DOMAIN

_log = logging.getLogger(__package__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Add sensors for passed config_entry in HA."""
    moebot = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities([
        PollDeviceButton(moebot),
        DiagnosticDumpButton(moebot),
    ])


class PollDeviceButton(BaseMoeBotEntity, ButtonEntity):

    def __init__(self, moebot):
        super().__init__(moebot)
        self._attr_unique_id = f"{self._moebot.id}_poll_device"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_device_class = ButtonDeviceClass.UPDATE
        self._attr_name = "Poll Device"

    def press(self) -> None:
        self._moebot.poll()


class DiagnosticDumpButton(BaseMoeBotEntity, ButtonEntity):
    """Temporary button: dumps pymoebot internals to the HA log at WARNING level.

    Press it once, then copy the resulting log lines here.
    Can be removed once the tinytuya attribute name is confirmed.
    """

    def __init__(self, moebot):
        super().__init__(moebot)
        self._attr_unique_id = f"{self._moebot.id}_debug_dump"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_name = "Debug Dump pymoebot"

    def press(self) -> None:
        _log.warning(
            "=== PYMOEBOT DIAGNOSTIC DUMP ===\n"
            "  type(moebot)   : %s\n"
            "  moebot.__dict__: %r\n"
            "  dir(moebot)    : %r",
            type(self._moebot),
            vars(self._moebot),
            [a for a in dir(self._moebot) if not a.startswith("__")],
        )

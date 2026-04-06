from homeassistant.components.button import ButtonEntity, ButtonDeviceClass
from homeassistant.helpers.entity import EntityCategory

from . import BaseMoeBotEntity
from .const import DOMAIN


async def async_setup_entry(hass, config_entry, async_add_entities):
    moebot = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities([PollDeviceButton(moebot)])


class PollDeviceButton(BaseMoeBotEntity, ButtonEntity):

    def __init__(self, moebot):
        super().__init__(moebot)
        self._attr_unique_id = f"{self._moebot.id}_poll_device"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_device_class = ButtonDeviceClass.UPDATE
        self._attr_name = "Poll Device"

    def press(self) -> None:
        self._moebot.poll()

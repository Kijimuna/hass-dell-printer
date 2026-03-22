"""The Dell printer component."""
from __future__ import annotations
from typing import Any
from datetime import timedelta

from dell_printer_parser.printer_parser import DellPrinterParser
from aiohttp.client_exceptions import ClientConnectorError

from .const import *

from homeassistant.core import HomeAssistant
from homeassistant.const import CONF_HOST, CONF_SCAN_INTERVAL
from homeassistant.config_entries import ConfigEntry, ConfigEntryNotReady
from homeassistant.helpers import entity_registry as er

from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, CoordinatorEntity, UpdateFailed

import logging

_LOGGER = logging.getLogger(__name__)
STORAGE_VERSION = 1


def _parse_int(value: Any, default: int = 0) -> int:
    """Parse integer-ish values safely."""
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _default_cached_data(serial_number: str) -> dict[str, Any]:
    """Return a safe baseline cache shape."""
    return {
        MODEL_NAME: DEFAULT_NAME,
        DELL_SERVICE_TAG_NUMBER: "",
        ASSET_TAG_NUMBER: "",
        PRINTER_SERIAL_NUMBER: serial_number,
        MEMORY_CAPACITY: "",
        PROCESSOR_SPEED: "",
        FIRMWARE_VERSION: "",
        NETWORK_FIRMWARE_VERSION: "",
        CYAN_LEVEL: 0,
        MAGENTA_LEVEL: 0,
        YELLOW_LEVEL: 0,
        BLACK_LEVEL: 0,
        MULTI_PURPOSE_FEEDER_STATUS: "Unknown",
        MULTI_PURPOSE_FEEDER_CAPACITY: 0,
        MULTI_PURPOSE_FEEDER_SIZE: "Unknown",
        OUTPUT_TRAY_STATUS: "Unknown",
        OUTPUT_TRAY_CAPACITY: 0,
        REAR_COVER_STATUS: "Unknown",
        ADF_COVER_STATUS: "Unknown",
        PRINTER_TYPE: "Unknown",
        PRINTING_SPEED: "",
        PRINTER_PAGE_COUNT: 0,
        PAPER_USED_LETTER: 0,
        PAPER_USED_A5: 0,
        PAPER_USED_B5: 0,
        PAPER_USED_A4: 0,
        PAPER_USED_EXECUTIVE: 0,
        PAPER_USED_FOLIO: 0,
        PAPER_USED_LEGAL: 0,
        PAPER_USED_ENVELOPE: 0,
        PAPER_USED_MONARCH: 0,
        PAPER_USED_DL: 0,
        PAPER_USED_C5: 0,
        PAPER_USED_OTHERS: 0,
        EVENT_LOCATION: "",
        EVENT_DETAILS: "Unknown",
    }


def _cached_data_from_restored_states(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any] | None:
    """Build cache data from HA-restored entity states for this config entry."""
    registry = er.async_get(hass)
    reg_entries = er.async_entries_for_config_entry(registry, entry.entry_id)
    if not reg_entries:
        return None

    serial_seed = entry.unique_id or entry.entry_id
    data = _default_cached_data(serial_seed)
    found = False

    for reg_entry in reg_entries:
        state = hass.states.get(reg_entry.entity_id)
        if state is None:
            continue

        found = True
        entity_id = reg_entry.entity_id
        attrs = state.attributes
        value = state.state
        unique_id = reg_entry.unique_id or ""
        unique_suffix = unique_id
        if "_" in unique_id:
            unique_prefix, unique_suffix = unique_id.split("_", 1)
            if unique_prefix:
                data[PRINTER_SERIAL_NUMBER] = unique_prefix

        if unique_suffix == "cyan":
            data[CYAN_LEVEL] = _parse_int(value)
        elif unique_suffix == "magenta":
            data[MAGENTA_LEVEL] = _parse_int(value)
        elif unique_suffix == "yellow":
            data[YELLOW_LEVEL] = _parse_int(value)
        elif unique_suffix == "black":
            data[BLACK_LEVEL] = _parse_int(value)
        elif unique_suffix == "print_volume":
            data[PRINTER_PAGE_COUNT] = _parse_int(value)
            data[PAPER_USED_LETTER] = _parse_int(attrs.get("letter"))
            data[PAPER_USED_A5] = _parse_int(attrs.get("a5"))
            data[PAPER_USED_B5] = _parse_int(attrs.get("b5"))
            data[PAPER_USED_A4] = _parse_int(attrs.get("a4"))
            data[PAPER_USED_EXECUTIVE] = _parse_int(attrs.get("executive"))
            data[PAPER_USED_FOLIO] = _parse_int(attrs.get("folio"))
            data[PAPER_USED_LEGAL] = _parse_int(attrs.get("legal"))
            data[PAPER_USED_ENVELOPE] = _parse_int(attrs.get("envelope"))
            data[PAPER_USED_MONARCH] = _parse_int(attrs.get("monarch"))
            data[PAPER_USED_DL] = _parse_int(attrs.get("dl"))
            data[PAPER_USED_C5] = _parse_int(attrs.get("c5"))
            data[PAPER_USED_OTHERS] = _parse_int(attrs.get("others"))
        elif entity_id.startswith("binary_sensor."):
            if unique_suffix == "rear_cover":
                data[REAR_COVER_STATUS] = value
            elif unique_suffix == "adf_cover":
                data[ADF_COVER_STATUS] = value
            elif unique_suffix == "output_tray":
                data[OUTPUT_TRAY_STATUS] = value
                data[OUTPUT_TRAY_CAPACITY] = _parse_int(attrs.get("capacity"))
            elif unique_suffix == "multi_purpose_feeder":
                data[MULTI_PURPOSE_FEEDER_STATUS] = value
                data[MULTI_PURPOSE_FEEDER_CAPACITY] = _parse_int(attrs.get("capacity"))
                data[MULTI_PURPOSE_FEEDER_SIZE] = attrs.get("size") or "Unknown"
            elif unique_suffix == "info":
                data[DELL_SERVICE_TAG_NUMBER] = attrs.get(DELL_SERVICE_TAG_NUMBER, "")
                data[ASSET_TAG_NUMBER] = attrs.get(ASSET_TAG_NUMBER, "")
                data[PRINTER_SERIAL_NUMBER] = attrs.get(PRINTER_SERIAL_NUMBER, data[PRINTER_SERIAL_NUMBER])
                data[MEMORY_CAPACITY] = attrs.get(MEMORY_CAPACITY, "")
                data[PROCESSOR_SPEED] = attrs.get(PROCESSOR_SPEED, "")
                data[FIRMWARE_VERSION] = attrs.get(FIRMWARE_VERSION, "")
                data[NETWORK_FIRMWARE_VERSION] = attrs.get(NETWORK_FIRMWARE_VERSION, "")
                data[PRINTER_TYPE] = attrs.get(PRINTER_TYPE, "Unknown")
                data[PRINTING_SPEED] = attrs.get(PRINTING_SPEED, "")
                data[EVENT_LOCATION] = attrs.get(EVENT_LOCATION, "")
                data[EVENT_DETAILS] = attrs.get(EVENT_DETAILS, "Unknown")
                data[MODEL_NAME] = attrs.get("friendly_name", DEFAULT_NAME)

    if not found:
        return None

    return data


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Setup a Dell printer from a config entry."""

    # get the host address
    host = entry.data[CONF_HOST]

    # setup the parser
    update_interval = entry.data.get(CONF_SCAN_INTERVAL, POLLING_INTERVAL)
    session = async_get_clientsession(hass)
    printer = DellPrinterParser(session, host)
    store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, f"{DOMAIN}_{entry.entry_id}")
    cached_data = await store.async_load()
    if not cached_data:
        cached_data = _cached_data_from_restored_states(hass, entry)

    # setup a coordinator
    coordinator = DellDataUpdateCoordinator(
        hass,
        _LOGGER,
        printer,
        timedelta(seconds=update_interval),
        store,
        cached_data,
    )

    # refresh coordinator for the first time to load initial data
    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryNotReady:
        if not cached_data:
            _LOGGER.debug("Printer at %s is currently unavailable, will retry setup", host)
            raise

        # Keep entities available with the last known values until the printer is reachable again.
        coordinator.async_set_updated_data(cached_data)
        await store.async_save(cached_data)
        _LOGGER.debug("Printer at %s is currently unavailable, using cached values until reconnect", host)

    # store coordinator
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # setup platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


class DellDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Dell data from the printer."""

    def __init__(
        self,
        hass: HomeAssistant,
        _LOGGER,
        printer: DellPrinterParser,
        update_interval: timedelta,
        store: Store[dict[str, Any]],
        cached_data: dict[str, Any] | None,
    ) -> None:
        """Initialize."""

        self.printer = printer
        self._store = store
        self._last_saved_data = cached_data
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=update_interval)


    async def _async_update_data(self) -> dict[str, Any]:
        """Update data via library."""

        try:
            """Ask the library to reload fresh data."""
            await self.printer.load_data()
        except (ConnectionError, ClientConnectorError) as error:
            raise UpdateFailed(error) from error

        """Stick the data into a dictionary and return this for further usage."""
        data = {}

        data[MODEL_NAME] = self.printer.information.modelName
        data[DELL_SERVICE_TAG_NUMBER] = self.printer.information.dellServiceTagNumber
        data[ASSET_TAG_NUMBER] = self.printer.information.assetTagNumber
        data[PRINTER_SERIAL_NUMBER] = self.printer.information.printerSerialNumber
        data[MEMORY_CAPACITY] = self.printer.information.memoryCapacity
        data[PROCESSOR_SPEED] = self.printer.information.processorSpeed
        data[FIRMWARE_VERSION] = self.printer.information.firmwareVersion
        data[NETWORK_FIRMWARE_VERSION] = self.printer.information.networkFirmwareVersion
        data[CYAN_LEVEL] = self.printer.status.cyanLevel
        data[MAGENTA_LEVEL] = self.printer.status.magentaLevel
        data[YELLOW_LEVEL] = self.printer.status.yellowLevel
        data[BLACK_LEVEL] = self.printer.status.blackLevel
        data[MULTI_PURPOSE_FEEDER_STATUS] = self.printer.status.multiPurposeFeederStatus
        data[MULTI_PURPOSE_FEEDER_CAPACITY] = self.printer.status.multiPurposeFeederCapacity
        data[MULTI_PURPOSE_FEEDER_SIZE] = self.printer.status.multiPurposeFeederSize
        data[OUTPUT_TRAY_STATUS] = self.printer.status.outputTrayStatus
        data[OUTPUT_TRAY_CAPACITY] = self.printer.status.outputTrayCapacity
        data[REAR_COVER_STATUS] = self.printer.status.rearCoverStatus
        data[ADF_COVER_STATUS] = self.printer.status.adfCoverStatus
        data[PRINTER_TYPE] = self.printer.status.printerType
        data[PRINTING_SPEED] = self.printer.status.printingSpeed
        data[PRINTER_PAGE_COUNT] = self.printer.printVolume.printerPageCount
        data[PAPER_USED_LETTER] = self.printer.printVolume.paperUsedLetter
        data[PAPER_USED_A5] = self.printer.printVolume.paperUsedA5
        data[PAPER_USED_B5] = self.printer.printVolume.paperUsedB5
        data[PAPER_USED_A4] = self.printer.printVolume.paperUsedA4
        data[PAPER_USED_EXECUTIVE] = self.printer.printVolume.paperUsedExecutive
        data[PAPER_USED_FOLIO] = self.printer.printVolume.paperUsedFolio
        data[PAPER_USED_LEGAL] = self.printer.printVolume.paperUsedLegal
        data[PAPER_USED_ENVELOPE] = self.printer.printVolume.paperUsedEnvelope
        data[PAPER_USED_MONARCH] = self.printer.printVolume.paperUsedMonarch
        data[PAPER_USED_DL] = self.printer.printVolume.paperUsedDL
        data[PAPER_USED_C5] = self.printer.printVolume.paperUsedC5
        data[PAPER_USED_OTHERS] = self.printer.printVolume.paperUsedOthers
        data[EVENT_LOCATION] = self.printer.events.eventLocation
        data[EVENT_DETAILS] = self.printer.events.eventDetails

        if data != self._last_saved_data:
            await self._store.async_save(data)
            self._last_saved_data = data.copy()

        return data


class DellPrinterEntity(CoordinatorEntity):

    def __init__(self, coordinator: DellDataUpdateCoordinator):
        super().__init__(coordinator)
        self._serialNumber = coordinator.data[PRINTER_SERIAL_NUMBER]
        self._modelName = coordinator.data[MODEL_NAME]
        self._firmware = coordinator.data[FIRMWARE_VERSION]
        self._name = self._serialNumber
        self._available = True

    @property
    def device_info(self):
        return {
            "identifiers": {
                (DOMAIN, self._serialNumber)
            },
            "name": self._name,
            "model": self._modelName,
            "manufacturer": "Dell",
            "sw_version": self._firmware,
        }

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._available

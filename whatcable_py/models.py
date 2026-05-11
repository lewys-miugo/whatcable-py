from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Endpoint(str, Enum):
    SOP = "SOP"
    SOP_PRIME = "SOP'"
    SOP_DOUBLE_PRIME = "SOP''"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class AdapterInfo:
    watts: int | None = None
    is_charging: bool | None = None
    source: str | None = None


@dataclass(frozen=True)
class PowerOption:
    voltage_mv: int
    max_current_ma: int
    max_power_mw: int

    @property
    def volts_label(self) -> str:
        return f"{self.voltage_mv / 1000:.0f}V"

    @property
    def amps_label(self) -> str:
        return f"{self.max_current_ma / 1000:.2f}A"

    @property
    def watts_label(self) -> str:
        return f"{self.max_power_mw / 1000:.0f}W"


@dataclass(frozen=True)
class PowerSource:
    id: int
    name: str
    parent_port_type: int
    parent_port_number: int
    options: tuple[PowerOption, ...] = ()
    winning: PowerOption | None = None

    @property
    def port_key(self) -> str:
        return f"{self.parent_port_type}/{self.parent_port_number}"

    @property
    def max_power_mw(self) -> int:
        values = [option.max_power_mw for option in self.options if option.max_power_mw > 0]
        if values:
            return max(values)
        return self.winning.max_power_mw if self.winning else 0


@dataclass(frozen=True)
class PDIdentity:
    id: int
    endpoint: Endpoint
    parent_port_type: int
    parent_port_number: int
    vendor_id: int
    product_id: int
    bcd_device: int
    vdos: tuple[int, ...] = ()
    spec_revision: int = 0

    @property
    def port_key(self) -> str:
        return f"{self.parent_port_type}/{self.parent_port_number}"


@dataclass(frozen=True)
class USBDevice:
    id: int
    location_id: int
    vendor_id: int
    product_id: int
    vendor_name: str | None = None
    product_name: str | None = None
    serial_number: str | None = None
    usb_version: str | None = None
    speed_raw: int | None = None
    bus_power_ma: int | None = None
    current_ma: int | None = None
    bus_index: int | None = None
    controller_port_name: str | None = None
    raw_properties: dict[str, str] = field(default_factory=dict)

    @property
    def speed_label(self) -> str:
        labels = {
            0: "Low Speed (1.5 Mbps)",
            1: "Full Speed (12 Mbps)",
            2: "High Speed (480 Mbps)",
            3: "SuperSpeed USB (5 Gbps)",
            4: "SuperSpeed USB 10 Gbps",
            5: "SuperSpeed USB 20 Gbps or faster",
        }
        return labels.get(self.speed_raw, "Unknown speed")


@dataclass(frozen=True)
class USBCPort:
    id: int
    service_name: str
    class_name: str
    port_description: str | None = None
    port_type_description: str | None = None
    port_number: int | None = None
    connection_active: bool | None = None
    active_cable: bool | None = None
    optical_cable: bool | None = None
    usb_active: bool | None = None
    super_speed_active: bool | None = None
    transports_supported: tuple[str, ...] = ()
    transports_active: tuple[str, ...] = ()
    transports_provisioned: tuple[str, ...] = ()
    plug_orientation: int | None = None
    power_current_limits: tuple[int, ...] = ()
    bus_index: int | None = None
    raw_properties: dict[str, str] = field(default_factory=dict)

    @property
    def label(self) -> str:
        return self.port_description or self.service_name

    @property
    def port_key(self) -> str | None:
        if self.port_number is None:
            return None
        return f"2/{self.port_number}"


@dataclass(frozen=True)
class CableSnapshot:
    ports: tuple[USBCPort, ...]
    power_sources: tuple[PowerSource, ...]
    identities: tuple[PDIdentity, ...]
    usb_devices: tuple[USBDevice, ...]
    adapter: AdapterInfo | None = None

    def to_comparable(self) -> dict[str, Any]:
        return {
            "ports": self.ports,
            "power_sources": self.power_sources,
            "identities": self.identities,
            "usb_devices": self.usb_devices,
            "adapter": self.adapter,
        }

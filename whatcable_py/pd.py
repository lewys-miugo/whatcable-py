from __future__ import annotations

from dataclasses import dataclass


PRODUCT_TYPES = {
    0: "Unspecified",
    1: "USB Hub",
    2: "USB Peripheral",
    3: "Passive cable",
    4: "Active cable",
    5: "Alternate Mode Adapter",
    6: "VCONN-powered device",
    7: "Other",
}

CABLE_SPEEDS = {
    0: ("USB 2.0 (480 Mbps)", 0.48),
    1: ("USB 3.2 Gen 1 (5 Gbps)", 5),
    2: ("USB 3.2 Gen 2 (10 Gbps)", 10),
    3: ("USB4 Gen 3 (20 / 40 Gbps)", 40),
    4: ("USB4 Gen 4 (80 Gbps)", 80),
}

CURRENTS = {
    0: ("USB default", 3.0),
    1: ("3 A", 3.0),
    2: ("5 A", 5.0),
}


@dataclass(frozen=True)
class IDHeader:
    usb_comm_host: bool
    usb_comm_device: bool
    modal_operation: bool
    ufp_product_type: int
    dfp_product_type: int
    vendor_id: int

    @property
    def product_label(self) -> str:
        product_type = self.ufp_product_type if self.ufp_product_type else self.dfp_product_type
        return PRODUCT_TYPES.get(product_type, "Unspecified")


@dataclass(frozen=True)
class CableVDO:
    speed_bits: int
    speed_label: str
    current_bits: int
    current_label: str
    max_volts: int
    max_watts: int
    cable_type: str
    warnings: tuple[str, ...]


def decode_id_header(vdo: int) -> IDHeader:
    return IDHeader(
        usb_comm_host=bool((vdo >> 31) & 1),
        usb_comm_device=bool((vdo >> 30) & 1),
        modal_operation=bool((vdo >> 26) & 1),
        ufp_product_type=(vdo >> 27) & 0b111,
        dfp_product_type=(vdo >> 23) & 0b111,
        vendor_id=vdo & 0xFFFF,
    )


def decode_cable_vdo(vdo: int, *, is_active: bool) -> CableVDO:
    speed_bits = vdo & 0b111
    speed_label, _ = CABLE_SPEEDS.get(speed_bits, CABLE_SPEEDS[0])
    current_bits = (vdo >> 5) & 0b11
    current_label, amps = CURRENTS.get(current_bits, CURRENTS[0])
    max_voltage_encoded = (vdo >> 9) & 0b11
    max_volts = {0: 20, 1: 30, 2: 40, 3: 50}.get(max_voltage_encoded, 20)
    latency_bits = (vdo >> 13) & 0b1111
    vdo_version_bits = (vdo >> 21) & 0b111
    termination_bits = (vdo >> 11) & 0b11
    epr_capable = bool((vdo >> 17) & 1)

    warnings: list[str] = []
    if speed_bits not in CABLE_SPEEDS:
        warnings.append(f"reserved speed encoding {speed_bits}")
    if current_bits not in CURRENTS:
        warnings.append(f"reserved current encoding {current_bits}")

    latency_invalid = latency_bits == 0 or (latency_bits >= 0b1011 if is_active else latency_bits >= 0b1001)
    if latency_invalid:
        warnings.append(f"reserved cable latency encoding {latency_bits}")

    if is_active:
        if vdo_version_bits not in {0, 0b010, 0b011}:
            warnings.append(f"invalid active-cable VDO version {vdo_version_bits}")
        if termination_bits < 0b10:
            warnings.append(f"invalid active-cable termination {termination_bits}")
    else:
        if vdo_version_bits != 0:
            warnings.append(f"invalid passive-cable VDO version {vdo_version_bits}")
        if termination_bits >= 0b10:
            warnings.append(f"invalid passive-cable termination {termination_bits}")
        if epr_capable and max_voltage_encoded == 0:
            warnings.append("EPR capable but max VBUS is 20V")

    return CableVDO(
        speed_bits=speed_bits,
        speed_label=speed_label,
        current_bits=current_bits,
        current_label=current_label,
        max_volts=max_volts,
        max_watts=round(max_volts * amps),
        cable_type="active" if is_active else "passive",
        warnings=tuple(warnings),
    )


def identity_header(vdos: tuple[int, ...]) -> IDHeader | None:
    if not vdos:
        return None
    return decode_id_header(vdos[0])


def cable_vdo(vdos: tuple[int, ...]) -> CableVDO | None:
    if len(vdos) < 4:
        return None
    header = identity_header(vdos)
    is_active = header.ufp_product_type == 4 if header else False
    return decode_cable_vdo(vdos[3], is_active=is_active)

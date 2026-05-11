from __future__ import annotations

from dataclasses import dataclass

from .models import PDIdentity, PowerSource, USBCPort
from .pd import cable_vdo


@dataclass(frozen=True)
class PortSummary:
    status: str
    headline: str
    subtitle: str
    bullets: tuple[str, ...]


@dataclass(frozen=True)
class ChargingDiagnostic:
    summary: str
    detail: str
    bottleneck: str
    is_warning: bool


def preferred_charging_source(sources: list[PowerSource]) -> PowerSource | None:
    return next((s for s in sources if s.name == "USB-PD"), None) or next((s for s in sources if s.name == "USB-C power"), None) or (sources[0] if sources else None)


def summary_for(port: USBCPort, sources: list[PowerSource], identities: list[PDIdentity]) -> PortSummary:
    connected = port.connection_active is True
    active = set(port.transports_active)
    supported = set(port.transports_supported)
    has_usb3 = "USB3" in active or port.super_speed_active is True
    has_usb2 = "USB2" in active or port.usb_active is True
    has_tb = "CIO" in active
    has_dp = "DisplayPort" in active
    pd_capable = "CC" in supported
    cable_identity = next((i for i in identities if i.endpoint.value in {"SOP'", "SOP''"}), None)
    has_emarker = cable_identity is not None

    if not connected:
        return PortSummary("empty", "Nothing connected", f"Plug a cable into {port.label} to see what it can do.", ())

    bullets: list[str] = []
    if has_tb:
        bullets.append("Thunderbolt / USB4 link active")
    elif has_usb3:
        bullets.append("SuperSpeed USB (5 Gbps or faster)")
    elif has_usb2:
        bullets.append("USB 2.0 only (480 Mbps), no high-speed data")
    if has_dp:
        bullets.append("Carrying DisplayPort video")

    if has_emarker:
        bullets.append("Cable has an e-marker chip (advertises its capabilities)")
    elif active and port.port_type_description == "USB-C":
        bullets.append("Cable does not advertise an e-marker (basic cable)" if pd_capable else "This port can't read cable details (USB-only port, no Power Delivery)")

    if cable_identity:
        decoded = cable_vdo(cable_identity.vdos)
        if decoded:
            bullets.append(f"Cable speed: {decoded.speed_label}")
            bullets.append(f"Cable rated for {decoded.current_label} at up to {decoded.max_volts}V (~{decoded.max_watts}W)")
        if cable_identity.vendor_id:
            from .vendor import label_for
            bullets.append(f"Cable made by {label_for(cable_identity.vendor_id)}")

    charging_source = preferred_charging_source(sources)
    charger_w = None
    if charging_source:
        max_w = round(charging_source.max_power_mw / 1000)
        if max_w > 0:
            charger_w = max_w
            bullets.append(f"Charger advertises up to {max_w}W")
        if charging_source.winning:
            win = charging_source.winning
            bullets.append(f"Currently negotiated: {win.volts_label} @ {win.amps_label} ({win.watts_label})")

    cable_suffix = ""
    if charger_w and cable_identity:
        decoded = cable_vdo(cable_identity.vdos)
        if decoded and 0 < decoded.max_watts < charger_w:
            cable_suffix = f" · {decoded.max_watts}W cable"

    power_suffix = f" · {charger_w}W charger" if charger_w else ""
    if has_tb:
        return PortSummary("thunderboltCable", f"Thunderbolt / USB4{power_suffix}{cable_suffix}", "High-speed data link is active.", tuple(bullets))
    if has_usb3 and has_dp:
        return PortSummary("displayCable", f"USB-C with video{power_suffix}{cable_suffix}", "Carrying both data and DisplayPort video.", tuple(bullets))
    if has_dp:
        return PortSummary("displayCable", f"Display connected{power_suffix}{cable_suffix}", "DisplayPort video over USB-C alt mode.", tuple(bullets))
    if has_usb3:
        return PortSummary("dataDevice", f"USB device{power_suffix}{cable_suffix}", "SuperSpeed data link is active.", tuple(bullets))
    if has_usb2:
        return PortSummary("dataDevice", f"Slow USB device or charge-only cable{power_suffix}{cable_suffix}", "Only USB 2.0 is active. If you expected high speed, the cable may not support it.", tuple(bullets))
    if charging_source:
        return PortSummary("charging", f"Charging{power_suffix}{cable_suffix}", "Power is flowing. No data connection.", tuple(bullets))
    return PortSummary("unknown", "Connected", "Couldn't determine cable type from this port.", tuple(bullets))


def charging_diagnostic(port: USBCPort, sources: list[PowerSource], identities: list[PDIdentity]) -> ChargingDiagnostic | None:
    source = preferred_charging_source(sources)
    if not source or port.connection_active is not True:
        return None
    charger_w = round(source.max_power_mw / 1000)
    negotiated_w = round(source.winning.max_power_mw / 1000) if source.winning else None
    if charger_w <= 0 and (negotiated_w or 0) <= 0:
        return None
    cable_identity = next((i for i in identities if i.endpoint.value in {"SOP'", "SOP''"}), None)
    decoded = cable_vdo(cable_identity.vdos) if cable_identity else None
    cable_w = decoded.max_watts if decoded else None
    if cable_w and cable_w < charger_w:
        return ChargingDiagnostic("Cable is limiting charging speed", f"Charger can deliver up to {charger_w}W, but this cable is only rated to carry {cable_w}W. Replace the cable to charge faster.", "cableLimit", True)
    if negotiated_w is not None and negotiated_w < charger_w - max(5, charger_w // 10) and (cable_w is None or negotiated_w < cable_w - max(5, cable_w // 10)):
        return ChargingDiagnostic(f"Charging at {negotiated_w}W (charger can do up to {charger_w}W)", "Both the charger and cable can do more, but the computer is currently asking for less. This is normal once the battery is mostly full, or when the system is idle.", "computerLimit", True)
    if negotiated_w is not None:
        return ChargingDiagnostic(f"Charging well at {negotiated_w}W", "Charger and cable are well-matched.", "fine", False)
    return ChargingDiagnostic(f"Charger advertises up to {charger_w}W", "Negotiation has not completed yet, or Linux did not expose the winning PDO.", "chargerLimit", True)


def trust_flags(identity: PDIdentity) -> tuple[str, ...]:
    flags: list[str] = []
    if identity.vendor_id == 0:
        flags.append("Vendor ID is zero; the cable did not report a real USB-IF vendor ID.")
    decoded = cable_vdo(identity.vdos)
    if decoded:
        flags.extend(decoded.warnings)
    return tuple(flags)

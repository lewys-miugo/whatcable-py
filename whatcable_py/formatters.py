from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import Any

from . import __version__
from .diagnostics import charging_diagnostic, summary_for, trust_flags
from .models import CableSnapshot, Endpoint, PDIdentity, PowerSource, USBCPort
from .pd import cable_vdo, identity_header
from .vendor import label_for, name_for

COLORS = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "gray": "\033[90m",
    "cyan": "\033[36m",
    "blue": "\033[34m",
    "yellow": "\033[33m",
    "green": "\033[32m",
    "magenta": "\033[35m",
}
STATUS_COLOR = {
    "empty": "gray",
    "charging": "yellow",
    "dataDevice": "blue",
    "thunderboltCable": "magenta",
    "displayCable": "cyan",
    "unknown": "yellow",
}


def color(text: str, *codes: str, enabled: bool = True) -> str:
    if not enabled:
        return text
    prefix = "".join(COLORS[c] for c in codes)
    return f"{prefix}{text}{COLORS['reset']}"


def render_text(snapshot: CableSnapshot, *, show_raw: bool = False, color_enabled: bool = True) -> str:
    if not snapshot.ports:
        return "No USB-C / removable USB ports were found on this system.\n"
    chunks: list[str] = []
    for port in snapshot.ports:
        sources = filter_sources(port, snapshot.power_sources)
        identities = filter_identities(port, snapshot.identities)
        chunks.append(render_port(port, sources, identities, show_raw=show_raw, color_enabled=color_enabled))
    return "\n".join(chunks)


def render_port(port: USBCPort, sources: list[PowerSource], identities: list[PDIdentity], *, show_raw: bool, color_enabled: bool) -> str:
    summary = summary_for(port, sources, identities)
    label = port.label
    suffix = f" ({port.port_type_description})" if port.port_type_description else ""
    lines = [color(f"=== {label}{suffix} ===", "bold", "cyan", enabled=color_enabled)]
    headline_color = STATUS_COLOR.get(summary.status, "yellow")
    lines.append(color(summary.headline, "bold", headline_color, enabled=color_enabled))
    lines.append(color(summary.subtitle, "dim", enabled=color_enabled))
    if summary.bullets:
        lines.append("")
        for bullet in summary.bullets:
            lines.append(f"  {color('•', 'gray', enabled=color_enabled)} {bullet}")
    diag = charging_diagnostic(port, sources, identities)
    if diag:
        diag_color = "yellow" if diag.is_warning else "green"
        lines.append("")
        lines.append(color("Charging: ", "bold", enabled=color_enabled) + color(diag.summary, diag_color, enabled=color_enabled))
        lines.append("  " + color(diag.detail, "dim", enabled=color_enabled))
    cable_identity = next((i for i in identities if i.endpoint in {Endpoint.SOP_PRIME, Endpoint.SOP_DOUBLE_PRIME}), None)
    if cable_identity:
        flags = trust_flags(cable_identity)
        if flags:
            lines.append("")
            lines.append(color("Cable trust signals:", "bold", "yellow", enabled=color_enabled))
            for flag in flags:
                lines.append(f"  {color('!', 'yellow', enabled=color_enabled)} {flag}")
    if show_raw:
        lines.append("")
        lines.append(color("Raw sysfs properties:", "bold", enabled=color_enabled))
        for key, value in sorted(port.raw_properties.items()):
            lines.append(f"  {color(key, 'gray', enabled=color_enabled)} = {value}")
    return "\n".join(lines) + "\n"


def render_json(snapshot: CableSnapshot, *, show_raw: bool = False) -> str:
    return json.dumps(snapshot_to_dict(snapshot, show_raw=show_raw), indent=2, sort_keys=True)


def snapshot_to_dict(snapshot: CableSnapshot, *, show_raw: bool = False) -> dict[str, Any]:
    return {
        "version": __version__,
        "ports": [port_to_dict(port, filter_sources(port, snapshot.power_sources), filter_identities(port, snapshot.identities), show_raw=show_raw) for port in snapshot.ports],
        "adapter": convert(snapshot.adapter),
    }


def port_to_dict(port: USBCPort, sources: list[PowerSource], identities: list[PDIdentity], *, show_raw: bool) -> dict[str, Any]:
    summary = summary_for(port, sources, identities)
    cable_identity = next((i for i in identities if i.endpoint in {Endpoint.SOP_PRIME, Endpoint.SOP_DOUBLE_PRIME}), None)
    partner = next((i for i in identities if i.endpoint == Endpoint.SOP), None)
    output: dict[str, Any] = {
        "name": port.label,
        "type": port.port_type_description,
        "className": port.class_name,
        "connectionActive": bool(port.connection_active),
        "pdCapable": "CC" in port.transports_supported,
        "status": summary.status,
        "headline": summary.headline,
        "subtitle": summary.subtitle,
        "bullets": list(summary.bullets),
        "transports": {
            "supported": list(port.transports_supported),
            "active": list(port.transports_active),
            "provisioned": list(port.transports_provisioned),
        },
        "powerSources": [power_source_to_dict(s) for s in sources],
        "cable": cable_to_dict(cable_identity) if cable_identity else None,
        "device": identity_to_dict(partner) if partner else None,
        "charging": convert(charging_diagnostic(port, sources, identities)),
    }
    if show_raw:
        output["rawProperties"] = dict(sorted(port.raw_properties.items()))
    return output


def power_source_to_dict(source: PowerSource) -> dict[str, Any]:
    return {
        "name": source.name,
        "maxPowerW": round(source.max_power_mw / 1000),
        "options": [power_option_to_dict(o) for o in source.options],
        "negotiated": power_option_to_dict(source.winning) if source.winning else None,
    }


def power_option_to_dict(option) -> dict[str, float]:
    return {
        "voltageV": option.voltage_mv / 1000,
        "currentA": option.max_current_ma / 1000,
        "powerW": option.max_power_mw / 1000,
    }


def cable_to_dict(identity: PDIdentity) -> dict[str, Any]:
    decoded = cable_vdo(identity.vdos)
    return {
        "endpoint": identity.endpoint.value,
        "vendorID": identity.vendor_id,
        "vendorName": name_for(identity.vendor_id),
        "productID": identity.product_id,
        "speed": decoded.speed_label if decoded else None,
        "currentRating": decoded.current_label if decoded else None,
        "maxVolts": decoded.max_volts if decoded else None,
        "maxWatts": decoded.max_watts if decoded else None,
        "type": decoded.cable_type if decoded else None,
        "trustFlags": list(trust_flags(identity)) or None,
        "vdos": [f"0x{v:08X}" for v in identity.vdos],
    }


def identity_to_dict(identity: PDIdentity) -> dict[str, Any]:
    header = identity_header(identity.vdos)
    return {
        "kind": header.product_label if header else None,
        "vendorID": identity.vendor_id,
        "vendorName": name_for(identity.vendor_id),
        "productID": identity.product_id,
        "pdRevision": {1: "PD 2.0", 2: "PD 3.0", 3: "PD 3.1"}.get(identity.spec_revision),
    }


def filter_sources(port: USBCPort, sources: tuple[PowerSource, ...]) -> list[PowerSource]:
    key = port.port_key
    return [source for source in sources if key and source.port_key == key]


def filter_identities(port: USBCPort, identities: tuple[PDIdentity, ...]) -> list[PDIdentity]:
    key = port.port_key
    return [identity for identity in identities if key and identity.port_key == key]


def convert(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {k: convert(v) for k, v in asdict(value).items()}
    if isinstance(value, tuple):
        return [convert(v) for v in value]
    if isinstance(value, list):
        return [convert(v) for v in value]
    if isinstance(value, dict):
        return {k: convert(v) for k, v in value.items()}
    return value


def cable_report(snapshot: CableSnapshot) -> str:
    cables = [identity for identity in snapshot.identities if identity.endpoint in {Endpoint.SOP_PRIME, Endpoint.SOP_DOUBLE_PRIME}]
    if not cables:
        return "No cable e-markers detected. Plug in an e-marked USB-C cable and try again.\n"
    blocks: list[str] = []
    for index, identity in enumerate(cables, start=1):
        decoded = cable_vdo(identity.vdos)
        lines = []
        if len(cables) > 1:
            lines.append(f"=== Cable {index} of {len(cables)} ===")
            lines.append("")
        lines.append("### Cable e-marker fingerprint")
        lines.append("")
        lines.append("| Field | Value |")
        lines.append("|---|---|")
        lines.append(f"| Vendor ID | `0x{identity.vendor_id:04X}` ({label_for(identity.vendor_id)}) |")
        lines.append(f"| Product ID | `0x{identity.product_id:04X}` |")
        if decoded:
            lines.append(f"| Cable speed | {decoded.speed_label} |")
            lines.append(f"| Current rating | {decoded.current_label} at up to {decoded.max_volts}V (~{decoded.max_watts}W) |")
            lines.append(f"| Type | {decoded.cable_type} |")
        lines.append("| Has e-marker | Yes |")
        if identity.vdos:
            lines.append("")
            lines.append("### Raw VDOs")
            lines.append("")
            lines.append("| Index | Value |")
            lines.append("|---|---|")
            for i, vdo in enumerate(identity.vdos):
                lines.append(f"| {i} | `0x{vdo:08X}` |")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) + "\n"

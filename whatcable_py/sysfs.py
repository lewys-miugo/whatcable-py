from __future__ import annotations

from pathlib import Path

from .models import AdapterInfo, CableSnapshot, Endpoint, PDIdentity, PowerOption, PowerSource, USBCPort, USBDevice
from .vendor import name_for

TYPEC_ROOT = Path("/sys/class/typec")
USB_ROOT = Path("/sys/bus/usb/devices")
POWER_ROOT = Path("/sys/class/power_supply")

TYPEC_PORT_ATTRS = (
    "data_role",
    "power_role",
    "port_type",
    "preferred_role",
    "vconn_source",
    "power_operation_mode",
    "usb_typec_revision",
    "usb_power_delivery_revision",
    "supports_usb_power_delivery",
    "orientation",
    "accessory_mode",
    "supported_accessory_modes",
)
TYPEC_IDENTITY_ATTRS = (
    "accessory_mode",
    "supports_usb_power_delivery",
    "usb_power_delivery_revision",
    "id_header",
    "cert_stat",
    "product",
    "product_type_vdo1",
    "product_type_vdo2",
    "product_type_vdo3",
    "product_type_vdo4",
    "product_type_vdo5",
)
TYPEC_CABLE_ATTRS = (
    "active",
    "plug_type",
    "type",
    "cable_type",
    "latency",
    "maximum_voltage",
    "current_capability",
) + TYPEC_IDENTITY_ATTRS
ALT_MODE_ATTRS = ("active", "svid", "mode", "description", "vdo")
USB_ATTRS = (
    "busnum",
    "devnum",
    "devpath",
    "idVendor",
    "idProduct",
    "manufacturer",
    "product",
    "serial",
    "version",
    "speed",
    "bMaxPower",
    "removable",
    "tx_lanes",
    "rx_lanes",
)
POWER_ATTRS = (
    "type",
    "online",
    "status",
    "scope",
    "usb_type",
    "voltage_now",
    "voltage_max",
    "current_now",
    "current_max",
    "input_current_limit",
    "power_now",
    "manufacturer",
    "model_name",
)


def snapshot() -> CableSnapshot:
    devices = tuple(read_usb_devices())
    ports = tuple(read_typec_ports(devices))
    identities = tuple(read_pd_identities())
    if not ports:
        ports = tuple(fallback_usb_ports(devices))
    return CableSnapshot(
        ports=ports,
        power_sources=tuple(read_power_sources(len(ports))),
        identities=identities,
        usb_devices=devices,
        adapter=read_adapter_info(),
    )


def read_typec_ports(devices: tuple[USBDevice, ...]) -> list[USBCPort]:
    names = sorted((p.name for p in TYPEC_ROOT.iterdir() if typec_port_index(p.name) is not None), key=lambda n: typec_port_index(n) or 0) if TYPEC_ROOT.exists() else []
    single_typec_port = len(names) == 1
    any_superspeed = any((device.speed_raw or 0) >= 3 for device in devices)
    return [make_typec_port(name, assume_superspeed=single_typec_port and any_superspeed) for name in names]


def make_typec_port(name: str, *, assume_superspeed: bool) -> USBCPort:
    url = TYPEC_ROOT / name
    partner_url = TYPEC_ROOT / f"{name}-partner"
    cable_url = TYPEC_ROOT / f"{name}-cable"
    index = typec_port_index(name) or 0
    port_number = index + 1

    raw = read_attrs(url, TYPEC_PORT_ATTRS)
    raw.update({f"partner.{k}": v for k, v in read_attrs(partner_url, TYPEC_IDENTITY_ATTRS).items()})
    raw.update({f"cable.{k}": v for k, v in read_attrs(cable_url, TYPEC_CABLE_ATTRS).items()})
    raw["linux.backend"] = "typec"
    raw["linux.sysfs"] = str(resolve(url))

    connected = partner_url.exists() or cable_url.exists()
    data_role = (raw.get("data_role") or "").lower()
    has_data_role = "host" in data_role or "device" in data_role
    active: list[str] = []
    if connected and has_data_role:
        active.append("USB2")
        if assume_superspeed:
            active.append("USB3")
    for transport in active_alt_modes(name):
        if transport not in active:
            active.append(transport)

    return USBCPort(
        id=stable_id(f"typec:{name}"),
        service_name=f"{name}@{port_number}",
        class_name="LinuxTypeCPort",
        port_description=f"USB-C Port {port_number}",
        port_type_description="USB-C",
        port_number=port_number,
        connection_active=connected,
        active_cable=parse_bool(raw.get("cable.active")),
        optical_cable="optical" in (raw.get("cable.type") or "").lower(),
        usb_active="USB2" in active,
        super_speed_active="USB3" in active,
        transports_supported=("CC", "USB2", "USB3"),
        transports_active=tuple(active),
        transports_provisioned=tuple(active),
        plug_orientation=orientation_value(raw.get("orientation")),
        power_current_limits=tuple(filter(None, [current_limit_ma(raw.get("power_operation_mode"))])),
        raw_properties=raw,
    )


def active_alt_modes(port_name: str) -> list[str]:
    transports: set[str] = set()
    if not TYPEC_ROOT.exists():
        return []
    for path in TYPEC_ROOT.iterdir():
        if not path.name.startswith(f"{port_name}-partner."):
            continue
        raw = read_attrs(path, ALT_MODE_ATTRS)
        if parse_bool(raw.get("active")) is not True:
            continue
        text = " ".join(raw.values()).lower()
        svid = parse_hex(raw.get("svid"))
        if svid == 0xFF01 or "displayport" in text:
            transports.add("DisplayPort")
        if svid == 0x8087 or "thunderbolt" in text or "usb4" in text:
            transports.add("CIO")
    return sorted(transports)


def read_pd_identities() -> list[PDIdentity]:
    identities: list[PDIdentity] = []
    if not TYPEC_ROOT.exists():
        return identities
    for path in TYPEC_ROOT.iterdir():
        index = typec_port_index(path.name)
        if index is None:
            continue
        port_number = index + 1
        candidates = (
            (TYPEC_ROOT / f"{path.name}-partner", Endpoint.SOP),
            (TYPEC_ROOT / f"{path.name}-cable", Endpoint.SOP_PRIME),
            (TYPEC_ROOT / f"{path.name}-plug0", Endpoint.SOP_PRIME),
            (TYPEC_ROOT / f"{path.name}-plug1", Endpoint.SOP_DOUBLE_PRIME),
        )
        for candidate, endpoint in candidates:
            identity = make_pd_identity(candidate, endpoint, port_number)
            if identity:
                identities.append(identity)
    return identities


def make_pd_identity(path: Path, endpoint: Endpoint, port_number: int) -> PDIdentity | None:
    if not path.exists():
        return None
    id_header = read_vdo(path, "id_header")
    cert_stat = read_vdo(path, "cert_stat")
    product = read_vdo(path, "product")
    product_vdos = [read_vdo(path, f"product_type_vdo{i}") for i in range(1, 6)]
    product_vdos = [v for v in product_vdos if v is not None]
    if id_header is None and cert_stat is None and product is None and not product_vdos:
        return None
    vdos = tuple([id_header or 0, cert_stat or 0, product or 0, *product_vdos])
    product_raw = product or 0
    return PDIdentity(
        id=stable_id(f"pd:{path.name}"),
        endpoint=endpoint,
        parent_port_type=2,
        parent_port_number=port_number,
        vendor_id=(id_header or 0) & 0xFFFF,
        product_id=product_raw & 0xFFFF,
        bcd_device=(product_raw >> 16) & 0xFFFF,
        vdos=vdos,
        spec_revision=pd_revision(read_text(path / "usb_power_delivery_revision")),
    )


def read_vdo(path: Path, name: str) -> int | None:
    for candidate in (path / name, path / "identity" / name):
        value = parse_hex(read_text(candidate))
        if value is not None:
            return value
    return None


def read_usb_devices() -> list[USBDevice]:
    if not USB_ROOT.exists():
        return []
    devices: list[USBDevice] = []
    for path in sorted(USB_ROOT.iterdir(), key=lambda p: p.name):
        if path.name.startswith("usb") or ":" in path.name or "-" not in path.name:
            continue
        vendor_id = parse_hex(read_text(path / "idVendor"))
        product_id = parse_hex(read_text(path / "idProduct"))
        if vendor_id is None or product_id is None:
            continue
        raw = read_attrs(path, USB_ATTRS)
        raw["linux.backend"] = "usb"
        raw["linux.sysfs"] = str(resolve(path))
        raw["linux.sysfsName"] = path.name
        busnum = parse_int(read_text(path / "busnum")) or usb_bus_number(path.name) or 0
        devnum = parse_int(read_text(path / "devnum")) or 0
        manufacturer = read_text(path / "manufacturer")
        devices.append(
            USBDevice(
                id=stable_id(f"usb:{path.name}"),
                location_id=(busnum << 24) | devnum,
                vendor_id=vendor_id,
                product_id=product_id,
                vendor_name=manufacturer or name_for(vendor_id),
                product_name=read_text(path / "product"),
                serial_number=read_text(path / "serial"),
                usb_version=read_text(path / "version"),
                speed_raw=usb_speed_raw(read_text(path / "speed")),
                bus_power_ma=current_ma(read_text(path / "bMaxPower")),
                bus_index=busnum or None,
                raw_properties=raw,
            )
        )
    return devices


def fallback_usb_ports(devices: tuple[USBDevice, ...]) -> list[USBCPort]:
    visible = [device for device in devices if (device.raw_properties.get("removable") or "").lower() != "fixed"]
    ports: list[USBCPort] = []
    for offset, device in enumerate(visible, start=1):
        superspeed = (device.speed_raw or 0) >= 3
        active = ("USB3",) if superspeed else ("USB2",)
        raw = dict(device.raw_properties)
        raw["linux.backend"] = "usb-device-fallback"
        ports.append(
            USBCPort(
                id=stable_id(f"fallback:{device.id}"),
                service_name=f"USB-Device@{offset}",
                class_name="LinuxUSBDevice",
                port_description=device.product_name or device.vendor_name or device.raw_properties.get("linux.sysfsName") or f"USB device {offset}",
                port_type_description="USB",
                port_number=offset,
                connection_active=True,
                usb_active=not superspeed,
                super_speed_active=superspeed,
                transports_supported=("USB2", "USB3") if superspeed else ("USB2",),
                transports_active=active,
                transports_provisioned=active,
                bus_index=device.bus_index,
                raw_properties=raw,
            )
        )
    return ports


def read_power_sources(port_count: int) -> list[PowerSource]:
    if not POWER_ROOT.exists():
        return []
    sources: list[PowerSource] = []
    for path in sorted(POWER_ROOT.iterdir(), key=lambda p: p.name):
        raw = read_attrs(path, POWER_ATTRS)
        typ = (raw.get("type") or "").lower()
        real_path = str(resolve(path)).lower()
        looks_usb_c = "usb" in typ or "ucsi" in path.name.lower() or "typec" in real_path or "ucsi" in real_path
        if not looks_usb_c or not is_online(raw):
            continue
        port_number = port_number_from_power_supply(path.name, real_path)
        if port_number is None and port_count == 1:
            port_number = 1
        if port_number is None:
            continue
        winning = power_option(raw.get("voltage_now"), raw.get("current_now") or raw.get("input_current_limit"), raw.get("power_now"))
        max_option = power_option(raw.get("voltage_max") or raw.get("voltage_now"), raw.get("current_max") or raw.get("input_current_limit") or raw.get("current_now"), raw.get("power_now"))
        options = tuple([option for option in [max_option or winning] if option])
        sources.append(
            PowerSource(
                id=stable_id(f"power:{path.name}"),
                name="USB-PD" if "pd" in (raw.get("usb_type") or "").lower() else "USB-C power",
                parent_port_type=2,
                parent_port_number=port_number,
                options=options,
                winning=winning,
            )
        )
    return sources


def read_adapter_info() -> AdapterInfo:
    online = False
    charging = False
    watts = None
    if POWER_ROOT.exists():
        for path in POWER_ROOT.iterdir():
            raw = read_attrs(path, POWER_ATTRS)
            typ = (raw.get("type") or "").lower()
            if typ == "battery" and (raw.get("status") or "").lower() == "charging":
                charging = True
            if is_online(raw) and ("mains" in typ or "usb" in typ):
                online = True
                option = power_option(raw.get("voltage_now"), raw.get("current_now") or raw.get("input_current_limit"), raw.get("power_now"))
                if option:
                    watts = round(option.max_power_mw / 1000)
    return AdapterInfo(watts=watts, is_charging=charging or online, source="AC" if online else "Battery")


def read_attrs(path: Path, names: tuple[str, ...]) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for name in names:
        value = read_text(path / name)
        if value is not None:
            values[name] = value
    identity = path / "identity"
    if identity.exists():
        for name in names:
            if name in values:
                continue
            value = read_text(identity / name)
            if value is not None:
                values[name] = value
    return values


def read_text(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    return text or None


def resolve(path: Path) -> Path:
    try:
        return path.resolve()
    except OSError:
        return path


def typec_port_index(name: str) -> int | None:
    if not name.startswith("port"):
        return None
    suffix = name[4:]
    return int(suffix) if suffix.isdigit() else None


def usb_bus_number(name: str) -> int | None:
    prefix = name.split("-", 1)[0]
    return int(prefix) if prefix.isdigit() else None


def usb_speed_raw(value: str | None) -> int | None:
    if not value:
        return None
    try:
        mbps = float(value.strip())
    except ValueError:
        return None
    if mbps <= 1.5:
        return 0
    if mbps <= 12:
        return 1
    if mbps <= 480:
        return 2
    if mbps <= 5000:
        return 3
    if mbps <= 10000:
        return 4
    return 5


def current_ma(value: str | None) -> int | None:
    if not value:
        return None
    digits = "".join(ch for ch in value if ch.isdigit())
    return int(digits) if digits else None


def current_limit_ma(mode: str | None) -> int | None:
    mode = (mode or "").lower()
    if "3.0" in mode or "3a" in mode:
        return 3000
    if "1.5" in mode or "1.5a" in mode:
        return 1500
    return None


def orientation_value(value: str | None) -> int | None:
    value = (value or "").lower()
    if value == "normal":
        return 0
    if value == "reverse":
        return 1
    return None


def power_option(voltage_uv: str | None, current_ua: str | None, power_uw: str | None) -> PowerOption | None:
    voltage_mv = (parse_int(voltage_uv) or 0) // 1000
    current_ma_value = (parse_int(current_ua) or 0) // 1000
    power_mw = (parse_int(power_uw) or 0) // 1000
    if current_ma_value <= 0 and voltage_mv > 0 and power_mw > 0:
        current_ma_value = power_mw * 1000 // voltage_mv
    if power_mw <= 0 and voltage_mv > 0 and current_ma_value > 0:
        power_mw = voltage_mv * current_ma_value // 1000
    if voltage_mv <= 0 or power_mw <= 0:
        return None
    return PowerOption(voltage_mv=voltage_mv, max_current_ma=current_ma_value, max_power_mw=power_mw)


def port_number_from_power_supply(name: str, path: str) -> int | None:
    for value in (name, path):
        lowered = value.lower()
        marker = "port"
        start = 0
        while True:
            index = lowered.find(marker, start)
            if index < 0:
                break
            pos = index + len(marker)
            digits = ""
            while pos < len(lowered) and lowered[pos].isdigit():
                digits += lowered[pos]
                pos += 1
            if digits:
                return int(digits) + 1
            start = pos
    if ":" in name:
        suffix = name.rsplit(":", 1)[1]
        if suffix.isdigit() and int(suffix) > 0:
            return int(suffix)
    return None


def is_online(raw: dict[str, str]) -> bool:
    if raw.get("online") == "0":
        return False
    if (raw.get("status") or "").lower() == "discharging":
        return False
    return True


def pd_revision(value: str | None) -> int:
    value = value or ""
    if "3.1" in value:
        return 3
    if "3.0" in value:
        return 2
    if "2.0" in value:
        return 1
    return 0


def parse_bool(value: str | None) -> bool | None:
    value = (value or "").lower()
    if value in {"1", "yes", "true", "y"}:
        return True
    if value in {"0", "no", "false", "n"}:
        return False
    return None


def parse_int(value: str | None) -> int | None:
    try:
        return int((value or "").strip())
    except ValueError:
        return None


def parse_hex(value: str | None) -> int | None:
    if not value:
        return None
    cleaned = value.strip().lower()
    if cleaned.startswith("0x"):
        cleaned = cleaned[2:]
    try:
        return int(cleaned, 16)
    except ValueError:
        return parse_int(value)


def stable_id(seed: str) -> int:
    value = 0xCBF29CE484222325
    for byte in seed.encode("utf-8"):
        value ^= byte
        value = (value * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return value

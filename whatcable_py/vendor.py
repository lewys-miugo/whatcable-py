# Small built-in map for common vendors. Unknown VIDs still render as hex.
VENDORS = {
    0x0000: None,
    0x05AC: "Apple",
    0x04B4: "Cypress Semiconductor",
    0x045E: "Microsoft",
    0x046D: "Logitech",
    0x04E8: "Samsung Electronics",
    0x057E: "Nintendo",
    0x0951: "Kingston Technology",
    0x0BDA: "Realtek Semiconductor",
    0x103C: "HP Inc.",
    0x17EF: "Lenovo",
    0x2109: "VIA Labs, Inc.",
    0x2357: "TP-Link",
    0x2BDA: "Anker Innovations Limited",
    0x8087: "Intel",
    0xFFFF: "No vendor ID assigned",
}


def name_for(vendor_id: int) -> str | None:
    return VENDORS.get(vendor_id)


def label_for(vendor_id: int) -> str:
    name = name_for(vendor_id)
    if name:
        return f"{name} (0x{vendor_id:04X})"
    return f"0x{vendor_id:04X}"

from whatcable_py.pd import decode_cable_vdo, decode_id_header


def test_decode_passive_cable_vdo():
    vdo = 0b011 | (2 << 5) | (1 << 13)
    decoded = decode_cable_vdo(vdo, is_active=False)
    assert decoded.speed_label.startswith("USB4")
    assert decoded.current_label == "5 A"
    assert decoded.max_watts == 100


def test_decode_id_header_vendor():
    header = decode_id_header((3 << 27) | 0x05AC)
    assert header.vendor_id == 0x05AC
    assert header.product_label == "Passive cable"

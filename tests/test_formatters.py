from whatcable_py.formatters import render_text
from whatcable_py.models import CableSnapshot, USBCPort


def test_empty_snapshot_message():
    output = render_text(CableSnapshot(ports=(), power_sources=(), identities=(), usb_devices=()), color_enabled=False)
    assert "No USB-C" in output


def test_port_headline_renders():
    port = USBCPort(
        id=1,
        service_name="port0@1",
        class_name="LinuxTypeCPort",
        port_description="USB-C Port 1",
        port_type_description="USB-C",
        port_number=1,
        connection_active=False,
        transports_supported=("CC", "USB2", "USB3"),
    )
    output = render_text(CableSnapshot(ports=(port,), power_sources=(), identities=(), usb_devices=()), color_enabled=False)
    assert "Nothing connected" in output

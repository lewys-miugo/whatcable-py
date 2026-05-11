# WhatCable Py

> What can this USB-C cable actually do on Ubuntu?

WhatCable Py is a Python implementation of the WhatCable experience for Ubuntu and Ubuntu-based distributions. It keeps the same product goal and interaction style: show every visible USB-C/USB connection in plain English, call out likely charging bottlenecks, expose e-marker identity when Linux makes it available, and provide JSON/raw/watch modes for engineers.

The app is read-only. It reads Linux kernel sysfs data from:

- `/sys/class/typec` for USB-C ports, partners, cables, identity VDOs, orientation, roles, and alternate modes.
- `/sys/bus/usb/devices` for attached USB devices and negotiated link speeds.
- `/sys/class/power_supply` for battery/charger hints.

Linux hardware support varies. If `/sys/class/typec` is empty, your kernel/firmware is not exposing USB-C controller state; WhatCable Py falls back to removable USB device speed and cannot read cable e-markers or USB-PD source options.

## Compatibility

WhatCable Py targets supported Ubuntu releases with Python 3.10 or newer:

- Ubuntu 22.04 LTS
- Ubuntu 24.04 LTS
- Ubuntu 26.04 LTS
- Current supported interim Ubuntu releases, such as Ubuntu 25.10

It should also work on Ubuntu flavours and Ubuntu-based distros that inherit those Python/kernel stacks, including Kubuntu, Xubuntu, Lubuntu, Ubuntu Budgie, Ubuntu MATE, Linux Mint, Pop!_OS, Zorin OS, elementary OS, and KDE neon.

Ubuntu 20.04 is not a primary target because its default Python is older than 3.10. It may work only if you install and use Python 3.10+ yourself.

Ubuntu release status changes over time; check the official list at <https://releases.ubuntu.com/>.


## Install Directly From GitHub

After publishing the repo, users can install it with pipx:

```bash
sudo apt update
sudo apt install pipx python3-tk
pipx ensurepath
pipx install git+https://github.com/lewys-miugo/whatcable-py.git

whatcable-py
whatcable-py.gui
```

If the shell cannot find `whatcable-py` after `pipx ensurepath`, close and reopen the terminal.

## CLI Commands

```bash
whatcable-py              # human-readable summary
whatcable-py --json       # structured JSON
whatcable-py --raw        # include raw sysfs values
whatcable-py --watch      # redraw when state changes
whatcable-py --report     # print cable e-marker report data when available
whatcable-py --version
```

## GUI Command

```bash
whatcable-py.gui
```

The GUI mirrors the WhatCable popover as a compact desktop window: one card per port/device, refresh controls, a raw-details toggle, a hide-empty toggle, and status colors for empty, charging, USB, display, Thunderbolt/USB4, and unknown states.

You can also launch the GUI from source without installing:

```bash
python3 -m whatcable_py.gui
```

## What It Shows

- At-a-glance headline: Thunderbolt / USB4, USB device, charging only, slow USB / charge-only cable, nothing connected.
- Charging diagnostics when USB-C power data is exposed.
- Cable e-marker details from Discover Identity VDOs when Linux exposes them.
- Cable trust signals for unusual vendor IDs or reserved cable VDO encodings.
- Connected USB devices and negotiated speed.
- Raw sysfs values via `--raw` or the GUI's Raw toggle.

## Quick Start From A Clone

```bash
git clone https://github.com/lewys-miugo/whatcable-py.git
cd whatcable-py
python3 -m whatcable_py
python3 -m whatcable_py --json
python3 -m whatcable_py.gui
```

## Install Commands

For a local editable install from the cloned repo:

```bash
cd whatcable-py
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .

whatcable-py
whatcable-py --json
whatcable-py --raw
whatcable-py --watch
whatcable-py.gui
```

The GUI uses Python's standard `tkinter` desktop toolkit, not PyGObject/GTK. On most desktop Python installs it is already available. If `whatcable-py.gui` says Tkinter is missing, install it with:

```bash
sudo apt update
sudo apt install python3-tk
```

If you use pyenv and Tkinter is missing, install `tk-dev` and rebuild/reinstall that pyenv Python version, or run WhatCable Py with Ubuntu's `/usr/bin/python3`.

## Troubleshooting

### `No module named 'gi'`

Older drafts of this project used GTK/PyGObject. The current GUI does not need `gi`. Pull the latest code and run:

```bash
python3 -m whatcable_py.gui
```

### `No USB-C / removable USB ports were found`

This usually means one of two things:

- No removable USB device is currently attached.
- Your machine/kernel does not expose Type-C controller state under `/sys/class/typec`.

Check with:

```bash
ls /sys/class/typec
```

If the directory is empty, WhatCable Py cannot read cable e-markers or USB-PD details on that machine. It will still show removable USB device speed when such devices are attached.

### No root required

Normal usage should not need `sudo`. The app only reads sysfs.

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
pytest
```

The project intentionally has no runtime Python dependencies.

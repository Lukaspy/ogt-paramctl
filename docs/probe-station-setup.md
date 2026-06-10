# Running the photo-IV campaign on another machine (probe station)

This sets up `paramctl` and the `paramctl-photoiv` campaign GUI on a fresh
machine. You can do the whole thing in **mock mode** with no instruments
attached, then point it at real hardware.

## 1. Prerequisites

- **Python 3.11+** and **git**.
- The **4155/4156** reachable over GPIB — either an NI USB-GPIB-HS or a
  XyphroLabs UsbGpib V2 (the latter enumerates as a USBTMC device and needs no
  extra driver).
- Only if driving **real light**: the 8-channel NI **PXI-7853R LED source**
  (the "Mightex") with its `led_driver` package, NI-RIO/`nifpga`, and the
  compiled `.lvbitx` bitfile.

## 2. Get the code

```bash
git clone <paramctl-remote-url> paramctl     # or copy the directory across
cd paramctl
```

## 3. Create the environment

```bash
python -m venv .venv
source .venv/bin/activate                     # Windows: .venv\Scripts\activate
pip install -e ".[dev]"                        # ".[dev]" adds pytest/ruff/mypy; plain -e . is fine for use
```

This pulls PyVISA, pyvisa-py, PyQt6, pyqtgraph, pydantic, PyYAML and installs
two console scripts: **`paramctl`** (single-sweep GUI) and
**`paramctl-photoiv`** (the campaign GUI).

Verify with the mock backend (no hardware needed):

```bash
paramctl-photoiv --mock
```

## 4. GPIB-over-USB backend for the 4155 (Ubuntu)

`pyvisa-py` (pure Python) is installed automatically. What else you need depends
on the adapter. First, identify it:

```bash
lsusb | grep -iE "national instruments|gpib|3923"
# "National Instruments" / ID 3923:... -> NI USB-GPIB-HS  (route B)
# a USBTMC device                       -> XyphroLabs UsbGpib V2 (route A)
```

### A) XyphroLabs UsbGpib V2 — simplest, no GPIB driver
It enumerates as a USBTMC device; `pyvisa-py` talks to it over USB.

```bash
sudo apt update && sudo apt install -y libusb-1.0-0
pip install pyusb            # in the project venv; pyvisa-py uses it for USB
```

Permissions so you don't need `sudo` (use the VID from `lsusb`):

```bash
echo 'SUBSYSTEM=="usb", ATTRS{idVendor}=="04d8", MODE="0666"' | \
  sudo tee /etc/udev/rules.d/99-usbtmc.rules
sudo udevadm control --reload-rules && sudo udevadm trigger   # then replug
```

### B) NI USB-GPIB-HS — `linux-gpib` (open source)

```bash
sudo apt install -y build-essential linux-headers-$(uname -r) \
    libncurses-dev tk-dev autoconf libtool flex bison
```

Download `linux-gpib-kernel` + `linux-gpib-user` from
<https://sourceforge.net/projects/linux-gpib/>, then build & install both:

```bash
cd linux-gpib-kernel-*  && make && sudo make install && sudo depmod -a
cd ../linux-gpib-user-* && ./bootstrap && ./configure && make && sudo make install && sudo ldconfig
```

Configure `/etc/gpib.conf` with `board_type "ni_usb_b"`, then bring it up
(this uploads the adapter firmware via `fxload`):

```bash
sudo modprobe ni_usb_gpib
sudo gpib_config
sudo usermod -aG gpib "$USER"      # device access without sudo; re-login after
pip install gpib-ctypes            # so pyvisa-py can use linux-gpib
```

> Alternative for an NI adapter: if your Ubuntu is an NI-supported LTS, install
> NI-488.2 + NI-VISA from NI's apt repo instead of building linux-gpib; PyVISA
> then uses the NI backend automatically (drop the `'@py'` below). Often less
> fiddly, but only on NI-supported releases.

### Confirm and find the resource string

```bash
python -c "import pyvisa; rm=pyvisa.ResourceManager('@py'); \
  r=rm.list_resources(); print(r); print(rm.open_resource(r[0]).query('*IDN?'))"
# NI:      ('GPIB0::17::INSTR',)    — 17 is the 4155's front-panel GPIB address
# Xyphro:  ('USB0::0x....::INSTR',)
```

Pass that string to the launcher, e.g. `--resource 'GPIB0::17::INSTR'`.

## 5. LED source (real hardware only)

Skip this entirely with `--led-mock` (or `--mock`) to develop without the FPGA.

```bash
git clone git@github.com:Lukaspy/PXI-AWG.git
pip install -e ../PXI-AWG          # into the SAME paramctl venv -> 'led_driver' importable
```

Also required on the LED machine: the NI-RIO / `nifpga` runtime, the compiled
`.lvbitx` bitfile, and the per-channel current-limit config at
`~/.config/led_driver/config.json` (copy it from the lab machine — it pins the
850=Ch0 … 385=Ch7 wiring and the 590 nm 700 mA limit).

The bitfile ships in the PXI-AWG repo root —
`leddriverfpga_FPGATarget_LEDDriverFPGA_gPdx1Ep2TLE.lvbitx`. **You must pass it
explicitly** with `--led-bitfile`: without it, `led_driver` would run its own
mock backend (no real light), so the launcher refuses to start a real-analyzer
run unless you give either `--led-bitfile` or `--led-mock`. The toolbar's
"LED:" label confirms the active mode (`FPGA RIO0` vs `mock`).

## 6. Launch

```bash
# Everything mock (no instruments):
paramctl-photoiv --mock

# Real 4155 + mock light (wiring up the analyzer first):
paramctl-photoiv --resource GPIB0::17::INSTR --led-mock

# Real 4155 + real LED:
paramctl-photoiv --resource GPIB0::17::INSTR --led-bitfile /path/to/led.lvbitx

# ...and apply the power calibration's equalization (optional, see §7):
paramctl-photoiv --resource GPIB0::17::INSTR --led-bitfile /path/to/led.lvbitx --led-use-cal
```

In the GUI: pick wavelengths → set intensities / settle / delays → choose
dual-polarity if wanted → **Generate sequence** → set the **Output folder** →
**Run campaign**. One CSV is written per curve.

## 7. Optical power calibration (optional)

The LED power calibration is recorded by the separate **`mfia-ledcal`** tool in
the MFIA-Ct repo and stored at `~/.config/led_driver/calibration.json`. Once it
exists on the machine:

- the photo-IV CSVs automatically carry an `optical_power_mw` per curve — this
  works **even with equalization off**, and
- `--led-use-cal` additionally *equalizes* commanded % to equal optical power
  across wavelengths. Leave it **off** if you want the raw per-channel drive %
  (which is the usual choice for an intensity series).

## Troubleshooting

- `led_driver is not importable` → you launched with real-LED flags but didn't
  `pip install -e ../PXI-AWG` into this venv. Use `--led-mock` or install it.
- No VISA resources found → check the GPIB backend (§4) and the cabling; try the
  `list_resources()` one-liner.
- Qt fails to start over SSH → run on the machine's display, or for headless
  checks set `QT_QPA_PLATFORM=offscreen` (tests do this automatically).

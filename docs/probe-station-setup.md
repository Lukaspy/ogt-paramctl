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

## 4. VISA backend for the 4155

- `pyvisa-py` (pure Python) is installed automatically — enough for the Xyphro
  USBTMC adapter with no extra software.
- **NI USB-GPIB-HS on Linux:** install `linux-gpib` (kernel module + userspace)
  and its Python bindings. On Windows/macOS install **NI-488.2 / NI-VISA**.
- Find your instrument's resource string:

  ```bash
  python -c "import pyvisa; print(pyvisa.ResourceManager().list_resources())"
  # e.g. ('GPIB0::17::INSTR',)
  ```

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

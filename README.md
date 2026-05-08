# paramctl

Python desktop control for **Keysight (Agilent/HP) 4155/4156 Semiconductor Parameter Analyzers** — a lighter-weight alternative to EasyEXPERT, focused on running and capturing measurements.

> **Status:** pre-alpha. The repository is being built up to Milestone 0 (first vertical slice). Nothing here works yet.

## What it does (planned for v1)

- Configures and runs **sweep**, **sampling**, and **spot** measurements.
- Live plots data as the instrument streams it back.
- Saves and loads test setups as YAML.
- Exports captured data as CSV (HDF5 deferred).
- Talks to the instrument over either an **NI USB-GPIB-HS** or a **XyphroLabs UsbGpib V2** adapter.

A `MockDriver` is built in so the entire stack — including the GUI — runs end-to-end without any instrument plugged in.

## Requirements

- Python 3.11+
- A VISA backend. `pyvisa-py` (pure Python) is the default and is pulled in automatically. NI-VISA is optional.
- For the NI USB-GPIB-HS on Linux: `linux-gpib` kernel module + userspace.
- For the XyphroLabs UsbGpib V2: nothing extra — it enumerates as a USBTMC device.

## Install (development)

```bash
git clone <this-repo>
cd 4155_python_control
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Run the tests

```bash
pytest                    # unit + integration against MockDriver
pytest -m hardware        # only hardware-bound tests (requires a real instrument)
```

## Project guidance

`CLAUDE.md` is the source of truth for architectural decisions, conventions, and milestones. Read it before contributing.

## License

GPL-3.0-or-later. See `LICENSE`.

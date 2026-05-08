# CLAUDE.md

> Project guidance for Claude Code working on this repository.
> Read this first. Treat it as the source of truth for architectural decisions and conventions.

---

## Project mission

A Python desktop application for remote control of Keysight (Agilent/HP) **4155/4156 Semiconductor Parameter Analyzers**, in the spirit of EasyEXPERT but lighter weight.

Package name: **`paramctl`**. License: **GPL-3.0**. Docstring style: **Google**. Primary instrument: **4155B** (4155C / 4156B / 4156C variants are in-scope; variant-specific command divergence is handled inside the driver, not above it).

**In scope (v1):**
- Configure and run sweep, sampling, and spot measurements on the 4155/4156
- Live plotting of measurement data during sweeps
- Save and load test setups (YAML)
- Export measurement data (CSV, optionally HDF5)
- Support both **NI USB-GPIB-HS** and **XyphroLabs UsbGpib V2** USB-GPIB adapters

**Future / aspirational** (do NOT build for v1; architecture must not preclude):
- Keysight **B1500A** Semiconductor Device Parameter Analyzer support (different command set, similar conceptual model — drops in as a new driver implementation)
- HP/Agilent **4145B** support (very different page-mode HP-IB syntax — also a new driver implementation, will exercise the abstraction harder)
- Additional GPIB adapters as users report them

The driver abstraction (`AnalyzerDriver` ABC) is the seam where new instrument support gets added later. Keep instrument-specific logic inside concrete driver classes; do **not** bake 4155/4156 assumptions into the models or engine layers.

**Explicitly out of scope** (do not build, do not pre-architect for):
- Project/workspace library (à la EasyEXPERT projects)
- Built-in parameter extraction (Vth, mobility, lifetime, etc.)
- Reliability/stress testing modes
- Multi-user / networked operation

If you find yourself building something on the "out of scope" list, stop and ask.

---

## Tech stack

| Concern             | Choice                                         |
|---------------------|------------------------------------------------|
| Language            | Python 3.11+                                   |
| Instrument I/O      | PyVISA (backend: pyvisa-py default, NI-VISA optional) |
| GUI                 | PyQt6 (do not mix in PySide6)                  |
| Plotting            | pyqtgraph (live), matplotlib (offline export only) |
| Data models         | Pydantic v2                                    |
| Setup file format   | YAML (PyYAML)                                  |
| Tests               | pytest, pytest-qt                              |
| Lint / format       | ruff                                           |
| Type checking       | mypy (`--strict` on `src/`)                    |
| Packaging           | `pyproject.toml`, hatchling                    |
| Version control     | git (mandatory — see below)                    |

Pin everything in `pyproject.toml`. No floating versions.

---

## Version control

This project lives in git from commit zero. No "I'll add git later."

- **Initial commit** sets up `pyproject.toml`, `README.md`, `CLAUDE.md`, `.gitignore`, `LICENSE` (TBD), and an empty `src/paramctl/__init__.py`. Nothing else.
- **`.gitignore`** must exclude at minimum: `__pycache__/`, `*.pyc`, `.venv/`, `venv/`, `dist/`, `build/`, `.mypy_cache/`, `.pytest_cache/`, `.ruff_cache/`, `*.egg-info/`, IDE folders (`.vscode/`, `.idea/`), OS junk (`.DS_Store`, `Thumbs.db`), and **measurement output** (`*.csv`, `*.h5`, `*.hdf5` outside `tests/fixtures/` and `examples/`).
- **Branches**: `main` is always shippable. Feature work on `feat/<short-slug>`. Fixes on `fix/<short-slug>`. Refactors on `refactor/<short-slug>`. No long-lived branches.
- **Commits**: Conventional Commits (`feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`, `build:`, `ci:`). Subject line ≤ 72 chars. Body explains *why*, not *what*. One logical change per commit. No "WIP" commits in `main` history — squash before merging.
- **Merges**: squash-merge feature branches into `main`. Keep `main` history linear and meaningful.
- **Tags**: semantic versioning (`vMAJOR.MINOR.PATCH`). M0 ships as `v0.1.0`. Pre-1.0, breaking changes bump MINOR.
- **`CHANGELOG.md`** in Keep-a-Changelog format. Updated in the same commit as the change.
- **Architectural decisions** of any size live in `docs/decisions/` as lightweight ADRs (one markdown file per decision, numbered). When you (Claude Code) make a non-obvious call, write the ADR in the same commit.
- **Never commit**: secrets, API keys, instrument calibration data, real measurement output outside fixtures, or generated artifacts.

---

## Architecture

Strict top-down layering. Higher layers may import from lower; lower layers must not import from higher.

```
ui/         (PyQt — main window, panels, plot widget, workers)
   │
engine/     (measurement orchestration, no Qt imports)
   │
models/     (Pydantic models — channels, setups, results)
   │
driver/     (PyVISA — talks to the instrument)
```

Plus `persistence/` (sits beside engine, depends on models only).

### Layer responsibilities

**`driver/`** — Pure I/O. Abstract `AnalyzerDriver` base class. Concrete `FlexDriver` implements the FLEX command set for the 4155/4156. `MockDriver` implements the same interface and returns physically plausible synthetic data. Driver code must not import Qt, must not import models, and must not contain measurement orchestration logic. Future B1500A and 4145B drivers will live alongside `FlexDriver` as additional concrete implementations.

**`models/`** — Pydantic v2 models for channel configuration, measurement modes, full setups, and results. These are the lingua franca between layers. UI- and driver-agnostic. Models must describe *what* a measurement is, not *how* a specific instrument runs it. If a field only makes sense for the 4155/4156, that's a smell — push it down into the driver.

**`engine/`** — Takes a `Setup` model + an `AnalyzerDriver` and runs the measurement. Emits results via a callback or queue interface. No Qt imports. Must be testable from a plain pytest function with a `MockDriver`.

**`persistence/`** — YAML for setups, CSV (and later HDF5) for measurement data. Setup files are versioned (`schema_version: 1`); migrations are mandatory when the schema bumps.

**`ui/`** — PyQt only. The UI talks to the engine via a `QThread`-based worker. The UI never makes a VISA call directly.

### Threading rules (non-negotiable)

- No VISA call ever runs on the Qt main thread.
- The engine runs on a worker `QThread`. Communication uses Qt signals.
- The driver itself stays Qt-free; the worker wraps it.
- Cancellation must propagate within ~1 second of the user clicking Stop.

---

## Supported transports

The driver layer must work with at least these two USB-GPIB adapters, with no special-case logic above the driver layer:

| Adapter                       | Resource string                       | VISA backend                                          | Notes |
|-------------------------------|---------------------------------------|-------------------------------------------------------|-------|
| NI USB-GPIB-HS                | `GPIB0::N::INSTR`                     | NI-VISA on Win/Mac; linux-gpib + pyvisa-py on Linux   | Full GPIB controller; can address multiple devices on one bus |
| XyphroLabs UsbGpib V2         | `USB0::0xVID::0xPID::SERIAL::INSTR`   | pyvisa-py on any OS — USBTMC class device             | Auto-detects connected instrument; one instrument per adapter |

### Rules

- **Never hardcode a resource string.** Setups store the chosen resource; defaults come from `ResourceManager.list_resources()`.
- **Don't rely on GPIB-only control-plane operations** (fine-grained IFC/REN sequencing, parallel poll, etc.). The 4155/4156 FLEX surface doesn't need them, and the Xyphro USBTMC adapter doesn't expose them.
- **Connection dialog** lists all VISA resources discovered, lets the user pick, performs `*IDN?` confirmation before enabling output, and remembers the last choice per setup.
- **Hardware tests** must cover both adapters before tagging a release (see Release checklist).
- A third adapter (Prologix, AR488, Keysight 82357B, …) is fine to add later — but evaluate whether it's USBTMC-class (drop-in via PyVISA) or serial-protocol (Prologix-style: needs a custom transport shim). Discuss before implementing.

---

## Domain concepts

### Channels

The 4155/4156 has:

- **4× SMU** (Source/Measure Unit) — can source V or I, measure the other; configurable compliance
- **2× VSU** (Voltage Source Unit) — voltage out, no measurement
- **2× VMU** (Voltage Monitor Unit) — voltage measurement, differential or single-ended
- **GNDU** — ground unit

Each measurement channel has:
- A **function** in the measurement: `VAR1`, `VAR2`, `VAR1'` (linked to VAR1 by ratio/offset), or `CONST`
- A **mode**: V-source, I-source, COMMON, or DISABLED
- **Compliance** (current limit when V-sourcing, voltage limit when I-sourcing)
- **Range** settings: auto, fixed, or limited-auto

Model these as Pydantic dataclasses: `ChannelConfig`, `SweepConfig`, `Setup`, etc.

### Measurement modes (for v1)

- **Sweep** — one VAR1 axis, optional VAR2 for families of curves (e.g. ID-VDS at multiple VGS)
- **Sampling** — time-based capture for transient measurements
- **Spot** — single-point DC measurement

Stress / reliability modes are out of scope.

### FLEX command set

Use **FLEX**, not the 4145B compatibility syntax. Common commands you'll touch: `*RST`, `*IDN?`, `US`, `FMT`, `MM`, `DV`, `DI`, `WV`, `WI`, `XE`, plus data-buffer reads.

**The 4155B/4156B Programmer's Guide is the source of truth** for the primary target (`manuals/4155and4156b_progguide.pdf`). The 4155C-specific guide (`manuals/4155c_progguide.pdf`) is consulted when supporting C-series variants. When unsure of a command's exact syntax or argument order, look it up — do not guess. If a command isn't documented in either guide, do not use it.

---

## Coding conventions

- Type hints on every function signature. CI runs `mypy --strict` on `src/`.
- Pydantic models for anything that gets serialized or crosses a layer boundary.
- Module-level loggers (`logger = logging.getLogger(__name__)`). No `print()` in library code.
- Public functions and classes get docstrings (Google or NumPy style — pick one in the first PR and stick to it).
- One non-trivial class per file.
- `__all__` declared in `__init__.py` for any package meant to be imported from.
- No bare `except:`. Catch specific exceptions.
- File naming: snake_case. Class naming: PascalCase. Constants: UPPER_SNAKE.

---

## Mock-first development

The whole stack — including the GUI — must run end-to-end without a real instrument plugged in. To enforce this:

- `MockDriver` implements the full `AnalyzerDriver` interface.
- It returns physically plausible data: simple BSIM-ish or EKV-ish MOSFET model, diode Shockley equation, linear resistor, etc. — enough to look right on a plot, not enough to be accurate.
- All unit and integration tests run against the mock.
- Tests that require real hardware are marked `@pytest.mark.hardware` and skipped by default in CI.

Mock-first is not optional. Hardware time is expensive; development time on a laptop is cheap.

---

## Safety

- Each `Setup` carries per-channel software compliance limits in addition to whatever compliance is sent to the instrument.
- Each project (or the application as a whole) has a configurable ceiling for max V and max I per channel. Setups that exceed the ceiling are rejected at load time with a clear error.
- The Stop button is always reachable, always enabled while a measurement is running, and aborts within ~1s.
- Connecting to a real instrument shows a confirmation dialog with the instrument's `*IDN?` string before any output is enabled.

---

## Project layout

```
.
├── .git/
├── .gitignore
├── pyproject.toml
├── README.md
├── CLAUDE.md                  # this file
├── CHANGELOG.md
├── LICENSE
├── docs/
│   └── decisions/             # ADRs for significant choices
├── src/paramctl/
│   ├── __init__.py
│   ├── driver/
│   │   ├── base.py            # AnalyzerDriver ABC
│   │   ├── flex.py            # 4155/4156 FLEX implementation
│   │   └── mock.py            # MockDriver
│   │                          # (future: b1500.py, hp4145.py)
│   ├── models/
│   │   ├── channel.py
│   │   ├── measurement.py
│   │   ├── setup.py
│   │   └── results.py
│   ├── engine/
│   │   ├── runner.py
│   │   └── events.py
│   ├── persistence/
│   │   ├── setups.py          # YAML
│   │   └── data.py            # CSV / HDF5
│   └── ui/
│       ├── main_window.py
│       ├── widgets/
│       │   ├── channel_panel.py
│       │   ├── sweep_panel.py
│       │   └── plot_view.py
│       └── workers.py         # QThread wrappers
├── tests/
│   ├── unit/
│   ├── integration/           # against MockDriver
│   ├── hardware/              # marked, skipped by default
│   ├── fixtures/
│   └── conftest.py
└── examples/
    └── scripts/               # headless usage examples
```

The package is named `paramctl`. CLI entry-point name is also TBD — defer until a CLI is actually needed (M0 is GUI-only).

---

## Milestone 0 — first vertical slice

Definition of done:

1. **Repo initialized** with `pyproject.toml`, `.gitignore`, `README.md`, `CLAUDE.md`, `CHANGELOG.md`, `LICENSE`, and a clean Conventional-Commits initial commit.
2. Connect to a 4155/4156 via VISA — both NI USB-GPIB-HS and Xyphro V2 paths exercised — or to `MockDriver`. Show `*IDN?` on connect.
3. Configure SMU1 as `VAR1` voltage sweep, SMU2 as `CONST` voltage. Compliance configurable.
4. Run a single sweep. Plot I(SMU1) vs V(SMU1) **live** as data streams in.
5. Stop button cancels mid-sweep cleanly (no leftover state on the instrument).
6. Save the current setup to YAML. Load it back and reproduce the same measurement.
7. Export the result to CSV with a header containing the setup metadata.

Ship M0 as tag `v0.1.0` when all seven work against the mock **and** at least one full sweep has been verified on real hardware against at least one adapter, with the other adapter's status documented in the release notes.

Resist the urge to build VAR2, sampling mode, HDF5 export, B1500A driver, or 4145B driver until M0 is shipped.

---

## Release checklist

Before tagging a release:

- [ ] All unit + integration tests pass against the mock.
- [ ] Hardware tests pass against at least one real adapter.
- [ ] Hardware tests pass against the *other* adapter type (NI ↔ Xyphro), or the gap is documented in the release notes.
- [ ] `mypy --strict` clean on `src/`.
- [ ] `ruff check` clean.
- [ ] `CHANGELOG.md` updated under the new version heading.
- [ ] Version bumped in `pyproject.toml`.
- [ ] Tag created and pushed: `git tag vX.Y.Z && git push --tags`.

---

## Things to avoid

- Don't bake instrument quirks into UI code. Quirks live in the driver.
- Don't bake 4155/4156-specific assumptions into `models/` or `engine/`. Future B1500A and 4145B drivers must slot in cleanly behind the same abstraction.
- Don't store transient state on widgets. State lives in models; widgets render and edit models.
- Don't `time.sleep()` on the GUI thread. Ever.
- Don't mix pyqtgraph and matplotlib in the live UI.
- Don't skip the mock driver "to save time." It always pays back faster than expected.
- Don't depend on NI-VISA being installed. pyvisa-py must work as the default backend.
- Don't hardcode VISA resource strings. They live in setups; defaults come from discovery.
- Don't use GPIB-only bus operations (parallel poll, etc.). USBTMC adapters won't expose them.
- Don't add new dependencies without updating `pyproject.toml` and noting the reason in the PR/commit.
- Don't write code that requires hardware to test unless it's behind `@pytest.mark.hardware`.
- Don't commit measurement data, secrets, or generated artifacts.
- Don't merge to `main` without updating `CHANGELOG.md` for user-visible changes.

---

## References

- *Agilent 4155B/4156B Semiconductor Parameter Analyzer Programmer's Guide* — `manuals/4155and4156b_progguide.pdf` (primary source of truth)
- *Agilent 4155C/4156C Semiconductor Parameter Analyzer Programmer's Guide* — `manuals/4155c_progguide.pdf` (variant reference)
- *Keysight B1500A Programming Guide* (for future driver work — not present in repo)
- *HP 4145B Operator's / Programmer's Manual* (for future driver work — not present in repo)
- XyphroLabs UsbGpib project: https://github.com/xyphro/UsbGpib
- PyVISA documentation: https://pyvisa.readthedocs.io
- pyqtgraph documentation: https://pyqtgraph.readthedocs.io
- Pydantic v2 documentation: https://docs.pydantic.dev
- Conventional Commits: https://www.conventionalcommits.org
- Keep a Changelog: https://keepachangelog.com

---

## Open questions for the project owner

These are not decided yet — flag in PRs, do not silently pick:

- CLI entry-point name (defer until first CLI is needed — M0 is GUI-only)
- HDF5 schema (defer until after M0)
- Whether to support remote (LAN) connection to 4156C in v1

### Resolved

- **Package name**: `paramctl`
- **License**: GPL-3.0
- **Docstring style**: Google
- **Remote git hosting**: none (local-only for now)
- **Primary instrument**: 4155B; 4155C / 4156B / 4156C variants supported, divergence handled in driver

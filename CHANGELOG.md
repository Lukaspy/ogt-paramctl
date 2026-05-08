# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial repository scaffold: `pyproject.toml` (hatchling build, pinned dependencies, ruff/mypy/pytest configuration), `README.md`, `.gitignore`, `LICENSE` (GPL-3.0-or-later), `CLAUDE.md` project guidance, and an empty `src/paramctl/__init__.py`.
- `CHANGELOG.md` (this file).
- ADR 0001: choice of GPL-3.0-or-later as the license version.
- Driver layer scaffold:
  - `paramctl.driver.AnalyzerDriver` — synchronous abstract base class with `connect`, `disconnect`, `idn`, `reset`, `is_connected`, plus context-manager protocol.
  - `paramctl.driver.MockDriver` — synthetic implementation returning a 4155B-flavored IDN with `MOCK` markers in the serial and firmware fields, plus a `reset_count` counter for testability.
  - `paramctl.driver.FlexDriver` — VISA-backed implementation for the 4155/4156 family, supporting any USBTMC- or GPIB-class adapter that PyVISA can open. Currently exposes connect / IDN / reset / disconnect; measurement methods come in the next slice.
  - `paramctl.driver.list_resources()` — wrapper around `pyvisa.ResourceManager().list_resources()`, used by the headless example script and (later) the GUI connection dialog.
  - Driver-layer exception hierarchy: `DriverError`, `NotConnectedError`, `CommunicationError`.
- Test infrastructure:
  - `tests/conftest.py` exposes a `--resource` CLI option and a `visa_resource` fixture that skips hardware tests when no resource is supplied.
  - `tests/unit/` covers the ABC contract and `MockDriver` end-to-end (14 tests).
  - `tests/hardware/` is registered behind the `hardware` marker; skipped by default.
- `examples/scripts/connect_and_idn.py` — headless smoke test exercising discovery, connect, `*IDN?`, and disconnect against either a real instrument or the mock.
- Pydantic v2 models layer (`paramctl.models`):
  - `ChannelId` enum (SMU1..SMU4, VSU1..VSU2, VMU1..VMU2, GNDU) plus `is_smu` / `is_vsu` / `is_vmu` helpers.
  - `ChannelMode` (V_SOURCE / I_SOURCE / COMMON / DISABLED) and `ChannelFunction` (VAR1 / VAR2 / VAR1_PRIME / CONST) enums.
  - `ChannelConfig` — frozen, extra-forbidden, with `model_validator` enforcing hardware-shaped rules: GNDU is always COMMON, VMU cannot source, VSU cannot I-source, sweep functions require a source mode, SMU sources require positive compliance, DISABLED channels cannot have a sweep function.
  - `ChannelLimits` — per-channel safety ceilings (max voltage, max current).
  - `SweepRange` (start / stop / points / scale / direction) with log-sweep zero-crossing rejection; `SweepScale` (LINEAR, LOG10/25/50) and `SweepDirection` (SINGLE, DOUBLE) enums; `Var1PrimeLink`.
  - `MeasurementMode` discriminated union over `SweepMeasurement` / `SamplingMeasurement` / `SpotMeasurement` (sampling and spot are shells; sweep is fully populated for M0).
  - `Setup` — top-level model: schema_version (pinned to 1), channels list, measurement, optional safety_ceilings dict, optional last-used resource_string. Cross-channel validation: unique channel_id, exactly-one VAR1/VAR2/VAR1' pairing with the measurement, ceiling enforcement on source values and compliance.
  - `Sample` and `MeasurementResult` shells for the engine layer to populate later.
- 52 model tests covering the rules above plus YAML-style round-trip via `model_dump`/`model_validate`.
- Driver measurement surface and synthesis:
  - `AnalyzerDriver.measure(setup) -> Iterator[Sample]` and `AnalyzerDriver.abort()` lifted to the abstract base. Drivers own the full measurement lifecycle; the engine just iterates and forwards.
  - `MockDriver.measure()` synthesises plausible sweep data via `paramctl.driver.synth`: square-law NMOS Id when a companion V-source is present (treated as gate bias), Shockley diode otherwise; channel-length modulation, compliance clamping, and small Gaussian noise. Honours `hold_time` / `delay_time` / per-sample interval; aborts within ~50 ms via an internal `threading.Event`.
  - `FlexDriver.measure()` / `abort()` raise `NotImplementedError` with a clear pointer to the upcoming FLEX commit; existing IDN/connect path unaffected.
  - New module `paramctl.driver.synth` exposes `sweep_points()` (linear / log-decade / single / double-direction) and `synth_readings()`.
- Engine layer (`paramctl.engine`):
  - `run_sweep(driver, setup, abort_event=None) -> Iterator[SweepEvent]` — Qt-free generator that emits `SweepStarted` -> `SampleReady`* -> terminal `SweepCompleted` or `SweepFailed`. Driver exceptions are captured into `SweepFailed` so the ui can show them; `KeyboardInterrupt` and `SystemExit` propagate.
  - Frozen-dataclass event types (`SweepStarted`, `SampleReady`, `SweepCompleted`, `SweepFailed`) and the `SweepEvent` union.
- `examples/scripts/connect_and_idn.py` gains `--sweep`: runs an ID-VDS sweep at `V_GS = 1.5 V`, prints a tabular trace, and reports completion. Headless smoke test for the engine path.
- 27 new tests across mock measurement, engine orchestration, synthesis math, and the M0 vertical-slice integration test (`test_id_vds_sweep_against_mock_produces_plottable_curve`). 93 unit + integration tests overall.
- FlexDriver: real-hardware sweep implementation (`measure()` / `abort()`):
  - `paramctl.driver.flex_protocol` — pure command-builder + FMT 1,1 response parser, isolated from PyVISA so the parser is unit-tested without an instrument. Captures the 18-char-per-field FLEX wire format (`<3-char status><1-char channel A..D><1-char type V/I/v/i><13-char number>`) decoded from a real probe of the 4155B.
  - `FlexDriver.measure()` translates a `Setup` into the documented FLEX sequence (`US`, `FMT 1,1`, `CN`, `WV`/`WI`, `DV`/`DI`, `WT`, `MM 2`, `XE`), polls `NUB?` until the buffer holds the expected data, reads with `RMD?`, and yields `Sample`s in acquisition order. SMU1..SMU4 only for now; VSU/VMU support is a follow-up.
  - `FlexDriver.abort()` sets the abort flag and issues a GPIB Device Clear so an in-flight sweep is interrupted promptly. The polling loop honours the flag between `NUB?` polls.
  - Sweep modes (1/2/3/4) and direction (SINGLE/DOUBLE) round-trip through the command builder; log scales (LOG10/25/50) map to FLEX modes 3 (single) and 4 (double).
- 26 new unit tests for the FLEX command builder and parser (against a real captured response). 4 hardware tests now passing on a 4155B (firmware 03.10) — IDN, context manager, open-circuit V-sweep with exact source-data check, and the M0 step-3 ID-VDS setup end-to-end.
- `examples/scripts/connect_and_idn.py --resource '<visa>' --sweep` runs the same sweep on real hardware and prints the trace.
- UI thin slice (`paramctl.ui`):
  - `SweepWorker` (QObject) — moves onto a `QThread`, iterates `run_sweep`, re-emits engine events as Qt signals (`started`/`sample`/`completed`/`failed`/`finished`). Driver calls never run on the Qt main thread, per CLAUDE.md §100.
  - `PlotView` widget — pyqtgraph-backed; one curve per measured channel, X axis is the VAR1 source value, Y axis is the channel reading. `configure_for(setup)` rebuilds curves at the start of each run; `add_sample(sample)` appends incrementally so plots fill in live.
  - `MainWindow` — Run / Stop buttons, status bar, embedded `PlotView`. Spawns a worker thread per run, ties Stop to `abort_event.set()` plus `driver.abort()` for prompt cancellation, and emits public `sweep_completed(count, aborted)` and `sweep_failed(exception, count)` signals so tests and external listeners can observe outcomes without poking internals.
  - `paramctl.ui.app.main` — argparse-driven launcher (`--mock`, `--resource`, `--verbose`); auto-selects a single discovered VISA resource. `python -m paramctl` is the entry point.
- Engine refinement: `run_sweep` now reports `aborted=True` when either the in-loop check fires *or* the driver self-terminates due to its own abort signal (e.g. `FlexDriver._wait_for_data` returning early on `abort_event`). Previously a driver-side abort was reported as `aborted=False` because the iterator exhausted "naturally" from the engine's view.
- FlexDriver: `_wait_for_data` swallows `VisaIOError` raised by an in-flight `NUB?` query when the abort flag is set — Device Clear sent by `abort()` no longer surfaces as `SweepFailed`.
- pytest-qt config: tests force `QT_QPA_PLATFORM=offscreen` via conftest, so they run without a display server (CI-friendly). 8 new UI tests (4 worker + 4 main-window). 126 tests pass on the laptop, 4 hardware tests pass on the 4155B.
- End-to-end validated on real hardware: offscreen `MainWindow` driving the real 4155B at GPIB0::15 produced a 21-point ID-VDS plot through the same code path users will use.
- UI editor + multi-trace plot:
  - `ChannelPanel` — one row per SMU (SMU1..SMU4) with enable / mode / function / source value / compliance / label fields. Compliance and source fields auto-disable for non-source modes (COMMON / DISABLED). VSU/VMU/GNDU rows are deliberately not surfaced until FlexDriver supports those channels.
  - `SweepPanel` — start, stop, points, scale (LINEAR / LOG10 / LOG25 / LOG50), direction (SINGLE / DOUBLE), integration time (SHORT / MEDIUM / LONG), hold time, delay time. Backed by `SweepRange` and `SweepMeasurement` round-trip.
  - `SetupEditor` — combines name field + ChannelPanel + SweepPanel; `current_setup()` constructs a fully-validated `Setup` (Pydantic validation runs at build time and propagates errors to the caller).
  - `FloatEdit` helper — `QLineEdit` with `QDoubleValidator` in scientific notation so values like `1e-3` work alongside `0.001`.
  - `PlotView` rewrite for multi-trace history: `begin_run(setup)` demotes the active curves to history (recoloured + dimmed, age-fade alpha), `add_sample(sample)` appends to the active run, `clear_history()` removes everything. Active run gets a bright primary colour and thicker line; history runs cycle through a six-hue palette.
  - `MainWindow` integrates the editor in a left-side scroll area (with `QSplitter`), the plot on the right, and a Run / Stop / Clear-traces toolbar on top. `Run` re-reads the editor each time so changes take effect without reopening the window. Invalid setups land in the status bar with the failing field name; a sweep cannot be aborted while a run is in flight.
- 9 new UI tests cover panel round-trip, setup-editor validation, plot history demotion, Clear-traces behaviour, and an invalid-setup-status-bar case. 135 unit + integration tests in total; 4 hardware tests still pass on the real 4155B. Smoke test: two consecutive real-hardware sweeps via `MainWindow` correctly show one history trace + one active trace at the second run's completion.
- SI-prefix input + dynamic unit labels:
  - `paramctl.util.units` exposes `format_si` and `parse_si` — pure-Python helpers covering 9 prefixes (`f` … `G`). Case-sensitive (`m` is milli, `M` is mega); accepts both `u` and `µ` for micro. The parser is permissive (`"100 u"`, `"100u"`, `"100 uA"`, `"100µA"` all parse to 1e-4); the formatter picks the prefix that keeps the mantissa in `[1, 1000)`.
  - `SiFloatEdit` widget replaces the old plain-float input. Compliance values now read as `"10 mA"` / `"1 uA"` instead of `0.01` / `1e-6`; users can type either form. Invalid input restores the previous good value on edit-finished.
  - Live unit propagation: changing SMU1's mode from V_SOURCE to I_SOURCE flips the row's source/compliance unit suffixes (V↔A) and the sweep panel's start/stop suffixes simultaneously. `ChannelPanel` emits `channels_changed` on structural edits (enable / mode / function); `SetupEditor` listens and pushes the VAR1 unit into `SweepPanel.set_var1_unit()`.
  - Hold time / delay time show `"0 s"` / `"50 ms"` etc., independent of VAR1 mode (they are always seconds).
- 57 new tests cover the SI formatter/parser (parametrised at 14 input forms), the `SiFloatEdit` widget (initial render, set_value, set_unit, parse on edit-finished, invalid input restoration, value_changed signal semantics), and dynamic unit propagation across the editor. 192 unit + integration tests in total.
- Plot quality of life:
  - Axis labels reflect the active VAR1 channel's label and source mode: V_SOURCE → "<label> voltage" (V) on X, "<label> current" (A) on Y; I_SOURCE swaps them.
  - `set_log_y` toggle on `PlotView` plus a Log-Y toolbar checkbox in `MainWindow`. When enabled, the cursor readout converts the displayed log value back to linear so the status bar shows real units.
  - Mouse-hover cursor: a dashed vertical line tracks the pointer; `cursor_changed` emits a pre-formatted `"X: 1.5 V    Y: 200 uA"` string that the main window pins to a permanent right-side status-bar widget.
- 12 new tests across `PlotView` (axis units, log-Y toggle, cursor formatting, log-Y persistence across runs) and `MainWindow` (Log-Y checkbox, cursor label updates from signal). 204 unit + integration tests in total; 4 hardware tests still pass.

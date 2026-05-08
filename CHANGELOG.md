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

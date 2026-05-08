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

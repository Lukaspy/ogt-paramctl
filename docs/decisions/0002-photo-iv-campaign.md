# ADR 0002 — Photo-IV campaign lives inside `paramctl`

- **Status:** accepted
- **Date:** 2026-06-10

## Context

The project owner needs to take IV curves at each wavelength with varying
intensity, staging a batch of measurements that runs automatically, with a
dark-pre / lit / dark-post pattern at each point and a settable delay between
measurements. The light source is the same 8-channel NI PXI-7853R LED driver
(`led_driver`) already used by the sister MFIA C-f/C-t tools (the owner calls
it "the Mightex"; the FPGA drives a Mightex unit through analog inputs).

`paramctl` already drives the 4155/4156 end-to-end: an `AnalyzerDriver`
abstraction with a `FlexDriver` + `MockDriver`, a Qt-free `run_sweep` engine,
Pydantic models, CSV/YAML persistence, and a PyQt6 multi-trace plot. The
question was whether to build the photo-IV tool as a separate program or as a
capability within `paramctl`.

## Decision

Build the photo-IV campaign **as a feature inside `paramctl`**, reusing the
analyzer stack, and add a second GUI entry point `paramctl-photoiv` (the
single-sweep GUI remains `paramctl` / `python -m paramctl`).

New pieces, each slotting into an existing layer:

- `paramctl.light` — a `LightSource` ABC beside `driver/` (pure I/O), with
  `PxiLightSource` (lazy `led_driver` import) and `MockLightSource`.
- `models/illumination.py` and `models/campaign.py` — the light "plan" and the
  `PhotoIvCampaign` that pairs it with a base IV `Setup` + inter-step delay.
- `engine/campaign.py` (`run_campaign`) — a Qt-free generator that loops the
  sequence, delegating each IV sweep to the existing `run_sweep`.
- `persistence/photoiv.py` — one standard trace CSV per step, plus a backward-
  compatible `extra_metadata` header on `write_run_csv`.
- `ui/photoiv_window.py` + `ui/photoiv_workers.py` — a campaign window and
  QThread worker reusing the existing `PlotView` and `SetupEditor`.

## Rationale

- ~90% reuse: the analyzer driver, engine, models, persistence, plot, and
  threading discipline already exist and are tested. A separate program would
  duplicate all of it or take a hard dependency on an unpublished package.
- Mirrors the proven decision in the sister MFIA tool, where C-V was added as
  a mode inside the existing C-f tool rather than as a new program.
- The light source fits the existing seam: it is "another driver," modelled
  with the same ABC + mock-first pattern as `AnalyzerDriver`. No layering rule
  is bent — `light/` is pure I/O, the engine stays Qt-free, models stay
  instrument-agnostic.
- The single-sweep GUI is untouched: campaign code is additive.

## Consequences

- `led_driver` is an optional, lazily-imported runtime dependency (only when
  real LED hardware is selected); the mock path and the whole test suite run
  without it. Added to the mypy `ignore_missing_imports` overrides.
- `run_campaign` owns the light-source lifecycle (connect / all-off +
  disconnect) but reuses the caller-connected analyzer driver, matching
  `run_sweep`'s contract.
- A future B1500A/4145B analyzer driver and any future LED source drop in
  behind their respective ABCs without touching the campaign engine.

## Alternatives considered

- **Separate program importing `paramctl`** — `paramctl` is not published, so a
  sibling package would need a path/editable install and would still duplicate
  the GUI shell. No benefit over an in-tree feature.
- **Generalising the engine to an arbitrary instrument-pairing framework** —
  over-engineered for one auxiliary source; rejected in favour of a concrete
  `LightSource` ABC.

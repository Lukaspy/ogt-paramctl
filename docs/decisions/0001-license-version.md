# ADR 0001 — License: GPL-3.0-or-later

- **Status:** accepted
- **Date:** 2026-05-08

## Context

The project owner specified "GPL is fine" without naming a specific version. GPL has two living versions in common use (GPL-2.0 and GPL-3.0), each with `-only` and `-or-later` SPDX variants.

## Decision

Use **`GPL-3.0-or-later`** (SPDX identifier).

## Rationale

- GPL-3.0 is the modern default. It closes the patent-grant and tivoization loopholes that GPL-2.0 left ambiguous, both of which are relevant to a tool that may eventually be redistributed alongside instrument firmware tooling.
- The `-or-later` suffix permits future GPL versions to apply at the licensee's option — keeps the door open without committing the project today.
- Compatible with the dependency stack we are pinning: PyVISA (MIT), PyQt6 (GPL-3 / commercial), pyqtgraph (MIT), Pydantic (MIT), PyYAML (MIT). PyQt6's GPL-3 licensing is the binding constraint — using GPL-3.0-or-later avoids any compatibility friction there.

## Consequences

- The project, including any redistribution, must comply with GPL-3.0-or-later terms (source availability, copyleft propagation through linked GPL-3 dependencies).
- If a future requirement surfaces a need to drop down to GPL-2.0-only (e.g. integration with a strictly v2 codebase), revisit this ADR; relicensing requires contributor sign-off but is not blocked by `-or-later`.

## Alternatives considered

- **GPL-2.0-only** — older, narrower compatibility set. PyQt6 being GPL-3 makes this awkward.
- **GPL-2.0-or-later** — workable but no concrete reason to prefer it over GPL-3.0-or-later.
- **LGPL-3.0** — would allow proprietary linking, but the project is an end-user application not a library, so the LGPL relaxation buys nothing.

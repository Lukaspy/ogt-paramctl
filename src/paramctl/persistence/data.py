"""CSV export of measurement runs with the originating ``Setup`` in the header.

Format::

    # paramctl trace export
    # exported_at: 2026-05-08T13:42:01Z
    # ----- setup begin -----
    # schema_version: 1
    # name: ID-VDS at VGS=1.5 V
    # channels:
    # - channel_id: SMU1
    # ...
    # ----- setup end -----
    index,var1_value,SMU1,compliance_hit,timestamp
    0,0.0,7.5e-14,False,0.012
    1,0.1,1.234e-7,False,0.034
    ...

Setup metadata sits in ``#``-prefixed comment lines so it does not collide
with CSV column data; round-trip is YAML-compatible. Tools that ignore
comments (Excel, pandas with ``comment='#'``) read the data straight away.

Reading back: :func:`read_run_csv` parses both halves and returns a
``(Setup, list[Sample])`` tuple — useful for replays, regression checks,
and analysis pipelines.
"""
from __future__ import annotations

import csv
import datetime as _dt
import io
import logging
from pathlib import Path

from ..models.channel import ChannelId
from ..models.results import Sample
from ..models.setup import Setup
from .setups import dump_setup_yaml, load_setup_yaml

logger = logging.getLogger(__name__)


_SETUP_BEGIN = "# ----- setup begin -----"
_SETUP_END = "# ----- setup end -----"


class TraceFileError(Exception):
    """Raised for any structural problem reading a trace CSV."""


def write_run_csv(
    path: Path | str,
    setup: Setup,
    samples: list[Sample],
) -> None:
    """Write a measurement run to ``path`` as comment-prefixed CSV."""
    Path(path).write_text(dump_run_csv(setup, samples))


def dump_run_csv(setup: Setup, samples: list[Sample]) -> str:
    """Render the same payload as :func:`write_run_csv` to a string."""
    buf = io.StringIO()
    buf.write("# paramctl trace export\n")
    buf.write(f"# exported_at: {_now_iso()}\n")
    buf.write(f"{_SETUP_BEGIN}\n")
    for line in dump_setup_yaml(setup).splitlines():
        buf.write(f"# {line}\n")
    buf.write(f"{_SETUP_END}\n")

    columns = _column_names(samples)
    writer = csv.writer(buf)
    writer.writerow(columns)
    for sample in samples:
        writer.writerow(_row_for_sample(sample, columns))
    return buf.getvalue()


def read_run_csv(path: Path | str) -> tuple[Setup, list[Sample]]:
    """Parse a paramctl trace CSV back into ``(Setup, list[Sample])``."""
    return parse_run_csv(Path(path).read_text())


def parse_run_csv(text: str) -> tuple[Setup, list[Sample]]:
    """Parse a string in the same format as :func:`write_run_csv` produces."""
    setup_yaml_lines: list[str] = []
    in_setup = False
    body_lines: list[str] = []
    for line in text.splitlines():
        if line == _SETUP_BEGIN:
            in_setup = True
            continue
        if line == _SETUP_END:
            in_setup = False
            continue
        if in_setup:
            stripped = line.lstrip("# ").rstrip()
            if line.startswith("# "):
                stripped = line[2:]
            elif line.startswith("#"):
                stripped = line[1:]
            setup_yaml_lines.append(stripped)
            continue
        if line.startswith("#"):
            continue
        body_lines.append(line)

    if not setup_yaml_lines:
        raise TraceFileError("trace file is missing the embedded setup block")
    setup = load_setup_yaml("\n".join(setup_yaml_lines))

    if not body_lines:
        raise TraceFileError("trace file has a setup block but no CSV body")

    reader = csv.reader(body_lines)
    columns = next(reader, None)
    if columns is None:
        raise TraceFileError("trace CSV body is missing the header row")

    samples = [_sample_from_row(columns, row) for row in reader if row]
    return setup, samples


def _column_names(samples: list[Sample]) -> list[str]:
    channel_ids: list[str] = []
    seen: set[ChannelId] = set()
    for sample in samples:
        for channel_id in sample.readings:
            if channel_id not in seen:
                seen.add(channel_id)
                channel_ids.append(channel_id.value)
    return ["index", "var1_value", *channel_ids, "compliance_hit", "timestamp"]


def _row_for_sample(sample: Sample, columns: list[str]) -> list[str]:
    row: list[str] = []
    for column in columns:
        if column == "index":
            row.append(str(sample.index))
        elif column == "var1_value":
            row.append("" if sample.var1_value is None else repr(sample.var1_value))
        elif column == "compliance_hit":
            row.append(str(sample.compliance_hit))
        elif column == "timestamp":
            row.append("" if sample.timestamp is None else repr(sample.timestamp))
        else:
            try:
                channel_id = ChannelId(column)
            except ValueError:
                row.append("")
                continue
            value = sample.readings.get(channel_id)
            row.append("" if value is None else repr(value))
    return row


def _sample_from_row(columns: list[str], row: list[str]) -> Sample:
    if len(row) != len(columns):
        raise TraceFileError(
            f"row length {len(row)} does not match header {len(columns)}: {row!r}"
        )
    cells = dict(zip(columns, row, strict=True))
    readings: dict[ChannelId, float] = {}
    for column, raw in cells.items():
        if column in {"index", "var1_value", "compliance_hit", "timestamp"}:
            continue
        if not raw:
            continue
        try:
            channel_id = ChannelId(column)
        except ValueError:
            continue
        readings[channel_id] = float(raw)

    var1_str = cells.get("var1_value", "")
    timestamp_str = cells.get("timestamp", "")
    return Sample(
        index=int(cells["index"]),
        var1_value=float(var1_str) if var1_str else None,
        readings=readings,
        timestamp=float(timestamp_str) if timestamp_str else None,
        compliance_hit=cells.get("compliance_hit", "False").lower() == "true",
    )


def _now_iso() -> str:
    return _dt.datetime.now(tz=_dt.UTC).isoformat(timespec="seconds")


__all__ = [
    "TraceFileError",
    "dump_run_csv",
    "parse_run_csv",
    "read_run_csv",
    "write_run_csv",
]

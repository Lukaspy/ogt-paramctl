"""Driver for the Keysight 4155B/4156B (and C variants) using the FLEX command set.

This module is the only place in ``paramctl`` that imports PyVISA. Higher
layers depend on the ``AnalyzerDriver`` interface and remain transport-agnostic.

Why FLEX rather than the 4145B-compatible page mode: FLEX is the modern,
documented API for the 4155/4156 family and is what the Programmer's Guide
in ``manuals/4155and4156b_progguide.pdf`` covers in depth.
"""
from __future__ import annotations

import logging
import threading
import time
from collections.abc import Iterator

import pyvisa
import pyvisa.errors
from pyvisa.resources import MessageBasedResource

from ..models.measurement import SweepMeasurement
from ..models.results import Sample
from ..models.setup import Setup
from .base import AnalyzerDriver, CommunicationError, NotConnectedError
from .flex_protocol import (
    FlexField,
    FlexProtocolError,
    build_setup_commands,
    expected_value_count,
    parse_response,
)

logger = logging.getLogger(__name__)


class FlexDriver(AnalyzerDriver):
    """Synchronous driver for the 4155/4156 family.

    The driver opens a VISA resource on ``connect()`` and closes it on
    ``disconnect()``. It does not assume any particular transport — both
    NI USB-GPIB-HS (``GPIB0::N::INSTR``) and XyphroLabs UsbGpib V2
    (``USB0::VID::PID::SERIAL::INSTR``) are supported as long as PyVISA can
    open the resource.
    """

    DEFAULT_TIMEOUT_MS: int = 5000

    def __init__(
        self,
        resource: str,
        *,
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
        resource_manager: pyvisa.ResourceManager | None = None,
    ) -> None:
        """Construct a driver bound to a specific VISA resource string.

        Args:
            resource: VISA resource string returned by
                ``pyvisa.ResourceManager().list_resources()``.
            timeout_ms: I/O timeout applied to the opened resource.
            resource_manager: Optional pre-existing ``ResourceManager``. When
                provided, the caller retains ownership and the driver will
                not close it on ``disconnect()``. When omitted, the driver
                creates and owns its own manager.
        """
        self._resource_string = resource
        self._timeout_ms = timeout_ms
        self._external_rm = resource_manager is not None
        self._rm: pyvisa.ResourceManager | None = resource_manager
        self._instr: MessageBasedResource | None = None
        self._abort_event = threading.Event()

    @property
    def resource_string(self) -> str:
        """The VISA resource string this driver is bound to."""
        return self._resource_string

    def connect(self) -> None:
        if self._instr is not None:
            return
        if self._rm is None:
            self._rm = pyvisa.ResourceManager()
        try:
            opened = self._rm.open_resource(self._resource_string)
        except pyvisa.errors.VisaIOError as exc:
            self._teardown_rm_on_failure()
            raise CommunicationError(
                f"Failed to open VISA resource {self._resource_string!r}"
            ) from exc

        if not isinstance(opened, MessageBasedResource):
            opened.close()
            self._teardown_rm_on_failure()
            raise CommunicationError(
                f"Resource {self._resource_string!r} is not message-based; "
                "FLEX requires a SCPI-style transport."
            )

        opened.timeout = self._timeout_ms
        self._instr = opened
        logger.info("Connected to %s (timeout %d ms)", self._resource_string, self._timeout_ms)

    def disconnect(self) -> None:
        if self._instr is not None:
            try:
                self._instr.close()
            except pyvisa.errors.VisaIOError:
                logger.exception("Error while closing %s; continuing", self._resource_string)
            finally:
                self._instr = None
                logger.info("Disconnected from %s", self._resource_string)
        if self._rm is not None and not self._external_rm:
            try:
                self._rm.close()
            except pyvisa.errors.VisaIOError:
                logger.exception("Error while closing ResourceManager; continuing")
            finally:
                self._rm = None

    def idn(self) -> str:
        instr = self._require_instr()
        try:
            return instr.query("*IDN?").strip()
        except pyvisa.errors.VisaIOError as exc:
            raise CommunicationError("*IDN? query failed") from exc

    def reset(self) -> None:
        instr = self._require_instr()
        try:
            instr.write("*RST")
        except pyvisa.errors.VisaIOError as exc:
            raise CommunicationError("*RST write failed") from exc

    @property
    def is_connected(self) -> bool:
        return self._instr is not None

    def measure(self, setup: Setup) -> Iterator[Sample]:
        """Run the sweep on the 4155/4156 and yield samples in acquisition order.

        Translates the ``Setup`` to a FLEX command sequence (``US``, ``FMT 1,1``,
        ``CN``, ``WV``/``WI``, ``DV``/``DI``, ``WT``, ``MM 2``), executes ``XE``,
        polls ``NUB?`` until the buffer holds the expected number of values, and
        reads the result with ``RMD?``. The 4155 does not stream individual
        samples in this mode; the driver therefore reads the full sweep at the
        end. Live UI updates are still possible — the driver yields samples
        one-at-a-time after the read, and the engine emits them as
        ``SampleReady`` events as it iterates.

        Raises:
            NotConnectedError: If ``connect()`` has not been called.
            CommunicationError: For VISA-level failures.
            NotImplementedError: For non-sweep measurement modes.
        """
        instr = self._require_instr()
        if not isinstance(setup.measurement, SweepMeasurement):
            raise NotImplementedError(
                "FlexDriver currently only supports sweep measurements; "
                f"got {type(setup.measurement).__name__}."
            )
        return self._run_sweep(instr, setup, setup.measurement)

    def abort(self) -> None:
        """Mark the in-flight sweep cancelled and clear it from the bus.

        The flag is honoured by the polling loop in ``_run_sweep``. As a
        belt-and-braces measure we also send a GPIB Device Clear via
        ``visalib.clear`` so any in-progress instrument I/O is reset.
        """
        self._abort_event.set()
        instr = self._instr
        if instr is None:
            return
        try:
            instr.clear()
        except pyvisa.errors.VisaIOError:
            logger.exception("FlexDriver.abort: GPIB clear failed; continuing")

    _NUB_POLL_INTERVAL_S: float = 0.1

    def _run_sweep(
        self,
        instr: MessageBasedResource,
        setup: Setup,
        sweep: SweepMeasurement,
    ) -> Iterator[Sample]:
        self._abort_event.clear()
        try:
            commands = build_setup_commands(setup)
        except FlexProtocolError as exc:
            raise CommunicationError(str(exc)) from exc

        for cmd in commands:
            self._write(instr, cmd)
        self._write(instr, "XE")

        expected = expected_value_count(sweep)
        if not self._wait_for_data(instr, expected):
            self._safe_disable_channels(instr)
            return

        try:
            response = instr.query(f"RMD? {expected}").strip()
        except pyvisa.errors.VisaIOError as exc:
            raise CommunicationError("RMD? query failed") from exc

        try:
            fields = parse_response(response)
        except FlexProtocolError as exc:
            raise CommunicationError(
                f"could not parse FLEX response: {exc}"
            ) from exc

        if len(fields) != expected:
            raise CommunicationError(
                f"FLEX response field count mismatch: expected {expected}, got {len(fields)}"
            )

        try:
            yield from self._samples_from_fields(fields)
        finally:
            self._safe_disable_channels(instr)

    def _wait_for_data(self, instr: MessageBasedResource, expected: int) -> bool:
        """Block until ``NUB?`` reports >= ``expected`` values, or abort.

        Returns ``True`` when the data is ready, ``False`` if the abort flag
        was set before the buffer filled.

        ``abort()`` issues a GPIB Device Clear which can cause an in-flight
        ``NUB?`` query to fail with ``VisaIOError``. When that happens *and*
        the abort flag is set, swallow the error and exit cleanly — the
        engine reports ``aborted=True`` instead of ``failed``.
        """
        while not self._abort_event.is_set():
            try:
                nub = int(instr.query("NUB?").strip())
            except pyvisa.errors.VisaIOError as exc:
                if self._abort_event.is_set():
                    return False
                raise CommunicationError("NUB? poll failed") from exc
            if nub >= expected:
                return True
            time.sleep(self._NUB_POLL_INTERVAL_S)
        return False

    def _samples_from_fields(self, fields: list[FlexField]) -> Iterator[Sample]:
        # FMT 1,1 layout: per sweep point, a measurement field followed by a
        # source-data field. Group into pairs; carry through any extra
        # measurement-side channels in the future by extending this loop.
        if len(fields) % 2 != 0:
            raise CommunicationError(
                f"FMT 1,1 expects measurement+source pairs but got {len(fields)} fields"
            )

        for index, pair_start in enumerate(range(0, len(fields), 2)):
            measured = fields[pair_start]
            source = fields[pair_start + 1]

            if measured.is_source:
                # Some setups echo source first; swap.
                measured, source = source, measured
            if not source.is_source:
                raise CommunicationError(
                    f"expected one source field per pair at index {index}; "
                    f"got two measurement fields"
                )

            yield Sample(
                index=index,
                var1_value=source.value,
                readings={measured.channel: measured.value},
                timestamp=None,
            )

    def _write(self, instr: MessageBasedResource, command: str) -> None:
        try:
            instr.write(command)
        except pyvisa.errors.VisaIOError as exc:
            raise CommunicationError(f"FLEX write failed: {command!r}") from exc

    def _safe_disable_channels(self, instr: MessageBasedResource) -> None:
        try:
            instr.write("CL")
        except pyvisa.errors.VisaIOError:
            logger.exception("FlexDriver: CL (channel disable) failed; continuing")

    def _require_instr(self) -> MessageBasedResource:
        if self._instr is None:
            raise NotConnectedError(
                f"FlexDriver({self._resource_string!r}) is not connected; call connect() first."
            )
        return self._instr

    def _teardown_rm_on_failure(self) -> None:
        if self._rm is not None and not self._external_rm:
            try:
                self._rm.close()
            except pyvisa.errors.VisaIOError:
                logger.exception("Error while closing ResourceManager during failure cleanup")
            self._rm = None

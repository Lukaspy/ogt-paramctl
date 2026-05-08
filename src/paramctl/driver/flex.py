"""Driver for the Keysight 4155B/4156B (and C variants) using the FLEX command set.

This module is the only place in ``paramctl`` that imports PyVISA. Higher
layers depend on the ``AnalyzerDriver`` interface and remain transport-agnostic.

Why FLEX rather than the 4145B-compatible page mode: FLEX is the modern,
documented API for the 4155/4156 family and is what the Programmer's Guide
in ``manuals/4155and4156b_progguide.pdf`` covers in depth.
"""
from __future__ import annotations

import logging
from collections.abc import Iterator

import pyvisa
import pyvisa.errors
from pyvisa.resources import MessageBasedResource

from ..models.results import Sample
from ..models.setup import Setup
from .base import AnalyzerDriver, CommunicationError, NotConnectedError

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
        """Run the sweep on the instrument. Pending implementation.

        FLEX command-set translation (``*RST``, ``US``, ``FMT``, ``MM 1``,
        ``DV``/``DI``, ``WV``/``WI``, ``XE``, data-buffer reads) lands in
        a follow-up commit so this slice can be reviewed against the mock
        first.
        """
        del setup  # silence unused-arg until the implementation lands
        raise NotImplementedError(
            "FlexDriver.measure() is not yet implemented; FLEX command-set "
            "translation is the next driver-layer commit."
        )

    def abort(self) -> None:
        """Send the FLEX abort. Pending implementation."""
        raise NotImplementedError(
            "FlexDriver.abort() is not yet implemented; pairs with measure()."
        )

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

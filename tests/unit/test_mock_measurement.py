"""Tests for ``MockDriver.measure`` end-to-end behaviour."""
from __future__ import annotations

import threading
import time
from itertools import pairwise

import pytest

from paramctl.driver import MockDriver, NotConnectedError
from paramctl.models import (
    ChannelConfig,
    ChannelFunction,
    ChannelId,
    ChannelMode,
    Setup,
    SpotMeasurement,
    SweepMeasurement,
    SweepRange,
)


def _id_vds_setup(points: int = 11) -> Setup:
    return Setup(
        channels=[
            ChannelConfig(
                channel_id=ChannelId.SMU1,
                mode=ChannelMode.V_SOURCE,
                function=ChannelFunction.VAR1,
                compliance=1e-3,
            ),
            ChannelConfig(
                channel_id=ChannelId.SMU2,
                mode=ChannelMode.V_SOURCE,
                function=ChannelFunction.CONST,
                source_value=1.5,
                compliance=1e-3,
            ),
        ],
        measurement=SweepMeasurement(
            var1=SweepRange(start=0.0, stop=1.0, points=points)
        ),
    )


def test_measure_yields_one_sample_per_point() -> None:
    drv = MockDriver()
    drv.connect()
    samples = list(drv.measure(_id_vds_setup(points=11)))
    assert len(samples) == 11


def test_measure_samples_have_increasing_index_and_var1_values() -> None:
    drv = MockDriver()
    drv.connect()
    samples = list(drv.measure(_id_vds_setup(points=5)))
    assert [s.index for s in samples] == [0, 1, 2, 3, 4]
    var1_vals = [s.var1_value for s in samples]
    assert var1_vals[0] == pytest.approx(0.0)
    assert var1_vals[-1] == pytest.approx(1.0)
    assert all(
        a is not None and b is not None and a <= b
        for a, b in pairwise(var1_vals)
    )


def test_measure_includes_channel_readings() -> None:
    drv = MockDriver()
    drv.connect()
    samples = list(drv.measure(_id_vds_setup(points=3)))
    for sample in samples:
        assert ChannelId.SMU1 in sample.readings
        assert ChannelId.SMU2 in sample.readings


def test_measure_before_connect_raises() -> None:
    drv = MockDriver()
    with pytest.raises(NotConnectedError):
        list(drv.measure(_id_vds_setup()))


def test_measure_rejects_unsupported_mode() -> None:
    drv = MockDriver()
    drv.connect()
    setup = Setup(
        channels=[
            ChannelConfig(
                channel_id=ChannelId.SMU1,
                mode=ChannelMode.V_SOURCE,
                function=ChannelFunction.CONST,
                compliance=1e-3,
            ),
        ],
        measurement=SpotMeasurement(),
    )
    with pytest.raises(NotImplementedError, match="sweep"):
        list(drv.measure(setup))


def test_abort_stops_iteration() -> None:
    drv = MockDriver(inter_sample_delay_s=0.05)
    drv.connect()

    samples_seen: list[int] = []

    def consumer() -> None:
        for s in drv.measure(_id_vds_setup(points=200)):
            samples_seen.append(s.index)

    t = threading.Thread(target=consumer)
    t.start()
    time.sleep(0.15)
    drv.abort()
    t.join(timeout=2.0)

    assert not t.is_alive()
    # Some samples were produced, but well short of the full 200-point sweep.
    assert 0 < len(samples_seen) < 200


def test_disconnect_during_measure_aborts() -> None:
    drv = MockDriver(inter_sample_delay_s=0.05)
    drv.connect()

    samples_seen: list[int] = []

    def consumer() -> None:
        for s in drv.measure(_id_vds_setup(points=200)):
            samples_seen.append(s.index)

    t = threading.Thread(target=consumer)
    t.start()
    time.sleep(0.1)
    drv.disconnect()
    t.join(timeout=2.0)

    assert not t.is_alive()
    assert len(samples_seen) < 200


def test_consecutive_measures_are_independent() -> None:
    drv = MockDriver()
    drv.connect()

    first = list(drv.measure(_id_vds_setup(points=5)))
    second = list(drv.measure(_id_vds_setup(points=7)))

    assert len(first) == 5
    assert len(second) == 7
    assert second[0].index == 0  # index resets per run

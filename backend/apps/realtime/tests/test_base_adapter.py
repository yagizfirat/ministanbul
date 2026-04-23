from datetime import datetime, timezone

import pytest

from apps.realtime.adapters.base import BaseAdapter
from apps.realtime.schemas import VehiclePosition


class NullAdapter(BaseAdapter):
    name = "null-adapter"
    source = "null"
    mode = "test"

    def fetch(self) -> list[VehiclePosition]:
        return []


def test_base_adapter_cannot_instantiate():
    with pytest.raises(TypeError):
        BaseAdapter()  # type: ignore[abstract]


def test_null_adapter_fetch_returns_empty_list():
    adapter = NullAdapter()
    assert adapter.fetch() == []


def test_null_adapter_health_default():
    adapter = NullAdapter()
    assert adapter.health() == {"adapter": "null-adapter", "healthy": True}


def test_null_adapter_yields_vehicleposition_compatible():
    class OneVehicleAdapter(NullAdapter):
        def fetch(self) -> list[VehiclePosition]:
            return [
                VehiclePosition(
                    vehicle_id="X1",
                    latitude=41.0,
                    longitude=29.0,
                    timestamp=datetime(2026, 4, 22, 12, tzinfo=timezone.utc),
                    source=self.source,
                    mode=self.mode,
                )
            ]

    adapter = OneVehicleAdapter()
    vehicles = adapter.fetch()

    assert len(vehicles) == 1
    assert isinstance(vehicles[0], VehiclePosition)
    assert vehicles[0].source == "null"
    assert vehicles[0].mode == "test"
    assert vehicles[0].vehicle_id == "X1"

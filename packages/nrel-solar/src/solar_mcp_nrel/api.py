"""Thin typed layer over the two NREL endpoints this server wraps."""

from dataclasses import dataclass

from solar_mcp_core.errors import SourceUnavailable
from solar_mcp_core.http import FetchedResponse, SolarHttpClient

from solar_mcp_nrel.models import PVWattsRequest, PVWattsResponse, SolarResourceResponse

PVWATTS_PATH = "/api/pvwatts/v8.json"
SOLAR_RESOURCE_PATH = "/api/solar/solar_resource/v1.json"


@dataclass
class PVWattsResult:
    response: PVWattsResponse
    fetched: FetchedResponse


@dataclass
class SolarResourceResult:
    response: SolarResourceResponse
    fetched: FetchedResponse


async def pvwatts(client: SolarHttpClient, request: PVWattsRequest) -> PVWattsResult:
    fetched = await client.get_json(PVWATTS_PATH, request.to_params())
    _raise_on_body_errors(client.config.name, fetched)
    return PVWattsResult(PVWattsResponse.model_validate(fetched.data), fetched)


async def solar_resource(client: SolarHttpClient, lat: float, lon: float) -> SolarResourceResult:
    fetched = await client.get_json(SOLAR_RESOURCE_PATH, {"lat": lat, "lon": lon})
    _raise_on_body_errors(client.config.name, fetched)
    return SolarResourceResult(SolarResourceResponse.model_validate(fetched.data), fetched)


def _raise_on_body_errors(source: str, fetched: FetchedResponse) -> None:
    errors = fetched.data.get("errors")
    if errors:
        raise SourceUnavailable(source, "; ".join(str(e) for e in errors))

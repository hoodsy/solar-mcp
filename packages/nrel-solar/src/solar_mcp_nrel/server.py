"""FastMCP server exposing the four nrel-solar tools over stdio.

Shims here are deliberately thin: all logic lives in plain typed functions
under tools/ (they get direct tests; the FastMCP decorator erases signatures
for mypy). One SolarHttpClient is shared for the server's lifetime via the
lifespan context, so the cache and rate limiter are shared across tools.
"""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession
from solar_mcp_core.config import NREL
from solar_mcp_core.envelope import ToolResult
from solar_mcp_core.http import SolarHttpClient

from solar_mcp_nrel import resources
from solar_mcp_nrel.tools.compare_orientations import compare_orientations as _compare
from solar_mcp_nrel.tools.estimate_production import estimate_production as _estimate
from solar_mcp_nrel.tools.get_solar_resource import get_solar_resource as _resource
from solar_mcp_nrel.tools.size_system_for_target import size_system_for_target as _size


@dataclass
class AppContext:
    client: SolarHttpClient


ToolContext = Context[ServerSession, AppContext]


def create_server(
    client_factory: Callable[[], SolarHttpClient] | None = None,
) -> FastMCP:
    factory = client_factory if client_factory is not None else lambda: SolarHttpClient(NREL)

    @asynccontextmanager
    async def lifespan(_server: FastMCP) -> AsyncIterator[AppContext]:
        client = factory()
        try:
            yield AppContext(client=client)
        finally:
            await client.aclose()

    mcp = FastMCP(
        "nrel-solar",
        instructions=(
            "US solar data from NREL: PVWatts v8 production modeling and NSRDB "
            "irradiance. Every tool returns data + units + source + assumptions "
            "+ warnings; read the assumptions before quoting numbers."
        ),
        lifespan=lifespan,
    )

    @mcp.tool()
    async def estimate_production(
        lat: float,
        lon: float,
        system_capacity_kw: float,
        ctx: ToolContext,
        tilt_deg: float | None = None,
        azimuth_deg: float = 180.0,
        array_type: str = "fixed_roof",
        module_type: str = "standard",
        losses_pct: float = 14.0,
        bifacial: bool = False,
        albedo: float | None = None,
        dc_ac_ratio: float = 1.2,
    ) -> ToolResult:
        """Estimate annual and monthly AC production for a PV system (PVWatts v8).

        Use this when the user describes a specific system at a location. Use
        get_solar_resource for raw irradiance without a system, compare_orientations
        to sweep tilt/azimuth options, size_system_for_target to go from a kWh
        goal to a system size.

        Example: estimate_production(lat=33.42, lon=-111.83, system_capacity_kw=8,
        tilt_deg=25) -> ~14,700 kWh/yr for Mesa, AZ.

        Units: ac_annual_kwh in kWh AC/year; ac_monthly in kWh AC per month;
        capacity_factor in percent; solrad_annual in kWh/m2/day. tilt_deg and
        azimuth_deg in degrees (azimuth 180 = south); losses_pct in percent.
        """
        return await _estimate(
            ctx.request_context.lifespan_context.client,
            lat=lat,
            lon=lon,
            system_capacity_kw=system_capacity_kw,
            tilt_deg=tilt_deg,
            azimuth_deg=azimuth_deg,
            array_type=array_type,
            module_type=module_type,
            losses_pct=losses_pct,
            bifacial=bifacial,
            albedo=albedo,
            dc_ac_ratio=dc_ac_ratio,
        )

    @mcp.tool()
    async def get_solar_resource(lat: float, lon: float, ctx: ToolContext) -> ToolResult:
        """Get annual/monthly solar irradiance (GHI, DNI) for a location (NSRDB).

        Use this for "how sunny is it there" questions with no specific system.
        Use estimate_production when a system size is known — it already folds
        irradiance in.

        Example: get_solar_resource(lat=39.74, lon=-105.18) -> ghi_annual ~4.8.

        Units: ghi_*/dni_* in kWh/m2/day; resolved_cell_lat/lon in degrees
        (center of the 0.1-degree NSRDB cell actually answering the query).
        """
        return await _resource(ctx.request_context.lifespan_context.client, lat=lat, lon=lon)

    @mcp.tool()
    async def compare_orientations(
        lat: float,
        lon: float,
        system_capacity_kw: float,
        ctx: ToolContext,
        tilts: list[float] | None = None,
        azimuths: list[float] | None = None,
        array_type: str = "fixed_roof",
        module_type: str = "standard",
        losses_pct: float = 14.0,
        dc_ac_ratio: float = 1.2,
    ) -> ToolResult:
        """Rank tilt x azimuth combinations by annual production for one system.

        Use this for "how bad is my north-facing roof really" or "is 10 vs 25
        degrees of tilt worth it". Use estimate_production for a single known
        orientation. The sweep is capped at 25 combinations per call.

        Example: compare_orientations(lat=33.42, lon=-111.83,
        system_capacity_kw=8, tilts=[10, 25], azimuths=[180]) -> ranked table
        with pct_delta_vs_best.

        Units: tilt/azimuth in degrees (azimuth 90=E, 180=S, 270=W);
        ac_annual_kwh in kWh AC/year; pct_delta_vs_best in percent (0 = best).
        """
        return await _compare(
            ctx.request_context.lifespan_context.client,
            lat=lat,
            lon=lon,
            system_capacity_kw=system_capacity_kw,
            tilts=tilts,
            azimuths=azimuths,
            array_type=array_type,
            module_type=module_type,
            losses_pct=losses_pct,
            dc_ac_ratio=dc_ac_ratio,
        )

    @mcp.tool()
    async def size_system_for_target(
        lat: float,
        lon: float,
        target_annual_kwh: float,
        ctx: ToolContext,
        tilt_deg: float | None = None,
        azimuth_deg: float = 180.0,
        array_type: str = "fixed_roof",
        module_type: str = "standard",
        losses_pct: float = 14.0,
        dc_ac_ratio: float = 1.2,
    ) -> ToolResult:
        """Find the system size (kW) that produces a target annual kWh.

        Use this to size a system from a consumption goal ("my home uses 9,000
        kWh/yr"). Use estimate_production when the size is already known.
        Solves to within 2% using at most 6 PVWatts calls.

        Example: size_system_for_target(lat=39.74, lon=-105.18,
        target_annual_kwh=6000, tilt_deg=25) -> required_kw ~5.8.

        Units: required_kw in kW DC; achieved_annual_kwh in kWh AC/year;
        pct_error in percent (achieved vs target).
        """
        return await _size(
            ctx.request_context.lifespan_context.client,
            lat=lat,
            lon=lon,
            target_annual_kwh=target_annual_kwh,
            tilt_deg=tilt_deg,
            azimuth_deg=azimuth_deg,
            array_type=array_type,
            module_type=module_type,
            losses_pct=losses_pct,
            dc_ac_ratio=dc_ac_ratio,
        )

    resources.register(mcp)
    return mcp


def main() -> None:
    create_server().run()


if __name__ == "__main__":
    main()

# solar-data-mcp-forecast

MCP server wrapping the open [Quartz Solar Forecast](https://github.com/openclimatefix/quartz-solar-forecast)
model (Open Climate Fix) — the forecast domain of
[solar-data-mcp](https://github.com/hoodsy/solar-data-mcp). No API key needed.

| Tool | Answers |
|---|---|
| `forecast_generation` | "What will my array generate tomorrow?" (hourly, ≤48 h) |
| `compare_forecast_to_model` | "Is today unusually sunny?" (forecast vs PVWatts typical-year) |

Run standalone: `uvx --from solar-data-mcp-forecast solar-forecast-mcp` — but see the
model-install note below; most users want the combined
[`solar-data-mcp`](https://github.com/hoodsy/solar-data-mcp/blob/main/packages/solar-data-mcp/README.md)
server, which adds the other three domains plus the skill and report layer.

## Installing the model

`quartz-solar-forecast` pins `pydantic==2.6.2`, which conflicts with the MCP SDK,
so it is not a declared dependency. Install it alongside (it runs fine on newer
pydantic; the pin is conservative). **Python 3.11 is required** —
`pv-site-prediction` does not support 3.12+:

```console
$ uv venv --python 3.11 --seed .venv && source .venv/bin/activate
$ pip install solar-data-mcp-forecast
$ pip install --no-deps quartz-solar-forecast
$ pip install pv-site-prediction xarray xgboost openmeteo-requests requests-cache retry-requests huggingface_hub async_timeout
```

On macOS, xgboost also needs the OpenMP runtime: `brew install libomp`.

Without the model installed, the server still starts and its tools return an
error containing these instructions.

Model note: Quartz is trained on sites ≤ 4 kWp; larger arrays are modeled at
4 kWp and linearly scaled (the library prints a notice when it does this).

## Using forecasts with the combined `solar-data-mcp` server

An ephemeral `uvx` environment cannot hold the side-install above. Use a
persistent venv and point your agent at its entry point:

```console
$ uv venv --python 3.11 --seed ~/.venvs/solar-data-mcp
$ ~/.venvs/solar-data-mcp/bin/pip install solar-data-mcp
$ ~/.venvs/solar-data-mcp/bin/pip install --no-deps quartz-solar-forecast
$ ~/.venvs/solar-data-mcp/bin/pip install pv-site-prediction xarray xgboost openmeteo-requests requests-cache retry-requests huggingface_hub async_timeout
```

Then in the agent config, replace `"command": "uvx", "args": ["solar-data-mcp"]`
with `"command": "~/.venvs/solar-data-mcp/bin/solar-data-mcp"`.

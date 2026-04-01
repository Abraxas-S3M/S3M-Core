# OpenWeatherMap Provider Runbook

## Registration and Credentials
1. Register at `https://openweathermap.org/`.
2. Generate API key.
3. Set `S3M_OPENWEATHERMAP_API_KEY`.

## Endpoints Used
- Current weather: `/data/2.5/weather`
- 5-day forecast: `/data/2.5/forecast`
- Air pollution: `/data/2.5/air_pollution`
- One Call alerts: `/data/3.0/onecall`

## Tactical Usage
OpenWeatherMap serves as model-diversity cross-validation against Open-Meteo,
with AQI + PM10 proxy to infer dust stress when direct dust concentration is unavailable.

## Mapping Notes
- Wind speed in metric mode is already m/s (no conversion).
- Visibility converted from meters to kilometers.
- PM10 is used as `dust_proxy` in normalized air quality output.
- AQI labels: 1 good, 2 fair, 3 moderate, 4 poor, 5 very_poor.

## Air-Gapped Operations
Cache representative current/forecast/AQ/alert payloads and run in `airgapped` mode.

## Smoke Test
```bash
python3 -m pytest packages/providers/weather-owm/tests/ -v
```

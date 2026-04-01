# Open-Meteo Provider Runbook

## Registration and Access
Open-Meteo requires no account registration and no API key.

## Endpoints Used
- Forecast: `https://api.open-meteo.com/v1/forecast`
- Archive: `https://api.open-meteo.com/v1/archive`
- Marine: `https://api.open-meteo.com/v1/marine`
- Air Quality: `https://api.open-meteo.com/v1/air-quality`

## Parameters and Units
- Hourly: `temperature_2m`, `relative_humidity_2m`, `wind_speed_10m`, `wind_direction_10m`, `visibility`, `precipitation`, `cloud_cover`, `uv_index`, `dust`, `surface_pressure`
- Daily: max/min temperature, precipitation sum, max wind
- Marine: wave height/period/direction, swell, current velocity
- Air quality: PM10, PM2.5, dust, AOD, UV

### Unit Conversions
- Wind: km/h to m/s = `value / 3.6`
- Visibility: m to km = `value / 1000`

## Saudi Location Catalog
The adapter includes 12 preconfigured Saudi tactical locations:
Riyadh, Jeddah, Dhahran, Tabuk, Najran, Jubail, NEOM, Sharurah, King Khalid Military City,
Strait of Hormuz, Bab el-Mandeb, Gulf of Aden.

## Operational Thresholds (Military Context)
- Flight visibility minimum: 1600m (VFR threshold)
- Ground operations minimum visibility: 500m
- UAV max wind: 40 km/h
- Helicopter max wind: 65 km/h
- Max operating temperature: 52C (heat casualty risk)
- Dust warning: 200 ug/m3
- Severe dust stop threshold: 500 ug/m3
- USV wave max: 2.5m
- Patrol boat wave max: 4.0m

## Sandstorm Risk Classification
- none: < 50 ug/m3
- moderate: 50-200 ug/m3
- severe: 200-500 ug/m3
- extreme: > 500 ug/m3

## S3M Integration
- Phase 8 navigation: weather-aware routing overlays (visibility, winds, dust)
- Phase 15 sensor analytics: schedule SAR and EO windows around sandstorm fronts
- Phase 17 maintenance: trigger filter and optics protection actions during high dust/heat
- Tactical COP: fused weather layer for command decision support

## Air-Gapped Operations
- Capture periodic forecast snapshots while connected.
- Store snapshots under integration data directories and run adapter in `airgapped` mode.

## Smoke Test
```bash
python3 -m pytest packages/providers/weather-openmeteo/tests/ -v
```

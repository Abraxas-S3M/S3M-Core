# Copernicus Open Access Hub (ESA Sentinel)

## Provider Info
- **Provider ID:** geoint-copernicus
- **Category:** GEOINT (Satellite Imagery)
- **Tier:** Free
- **Official Docs:** https://documentation.dataspace.copernicus.eu/APIs/OData.html

## Authentication
OAuth2 client credentials against the Copernicus Data Space Ecosystem (CDSE).

1. Register at https://dataspace.copernicus.eu
2. Create OAuth2 client in your account settings
3. Set environment variables:
   ```
   S3M_COPERNICUS_CLIENT_ID=your_client_id
   S3M_COPERNICUS_CLIENT_SECRET=your_client_secret
   ```

## Required Environment Variables
| Variable | Description | Required |
|----------|-------------|----------|
| S3M_COPERNICUS_CLIENT_ID | CDSE OAuth2 client ID | Yes (online mode) |
| S3M_COPERNICUS_CLIENT_SECRET | CDSE OAuth2 client secret | Yes (online mode) |

## Rate Limits
- No published hard limit for search queries
- Recommended: 30 requests/minute
- Download: concurrent downloads may be limited

## Supported Collections
| Collection | Type | Resolution | S3M Usage |
|-----------|------|-----------|-----------|
| SENTINEL-1 | C-band SAR | 10m | Maritime ship detection, all-weather surveillance |
| SENTINEL-2 | Multispectral optical | 10m | Land monitoring, infrastructure change detection |
| SENTINEL-3 | Ocean/land | 300m | Sea surface temperature, ocean color |
| SENTINEL-5P | Atmospheric | 7km | Dust/sandstorm monitoring, air quality |

## Normalized Schema
Outputs: `NormalizedGeoObservation`

## Pre-defined Saudi AOIs
8 pre-configured areas of interest covering: Persian Gulf, Red Sea (full + north), Bab el-Mandeb, Strait of Hormuz, Gulf of Aden, Full Saudi Arabia, Jubail Coast.

## Air-Gapped Operation
In air-gapped mode, reads from `data/integrations/geoint-copernicus/` directory.
Data is populated during online ingestion and transferred via secure USB.
Health degrades if cached data is older than 7 days.

## S3M Integration Points
- **Phase 15 (Sensor Analytics):** Sentinel-1 SAR feeds SARDetector for maritime ship detection
- **Phase 19 (Intel):** Satellite imagery feeds OSINT geospatial intelligence
- **Phase 5 (Threat Detection):** Change detection for infrastructure monitoring

## Smoke Test
```bash
# Set credentials
export S3M_COPERNICUS_CLIENT_ID=your_id
export S3M_COPERNICUS_CLIENT_SECRET=your_secret

# Run adapter tests
python -m pytest packages/providers/geoint-copernicus/tests/ -v

# Test live search (online mode)
python -c "
from packages.providers.geoint_copernicus import CopernicusAdapter
adapter = CopernicusAdapter()
if adapter.validate_credentials():
    results = adapter.fetch_sentinel1_sar(aoi='persian_gulf', days_back=3)
    print(f'Found {results[\"total_results\"]} Sentinel-1 products')
    normalized = adapter.normalize(results)
    print(f'Normalized {len(normalized)} observations')
"
```

## Known Limitations
- Download of actual imagery files (multi-GB) not implemented — only search/catalog metadata
- Sentinel-1 near-real-time products may have 3–6 hour latency from acquisition
- Cloud cover filter only applicable to Sentinel-2 (SAR penetrates clouds)

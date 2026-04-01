# Label Studio Provider Runbook

## Purpose
Label Studio delivers self-hosted annotation workflows for S3M model retraining.

## Self-hosted setup (Docker)
```bash
docker run -d --name s3m-labelstudio -p 8081:8080 heartexlabs/label-studio:latest
```

## Authentication
- Generate a user token in Label Studio account settings.
- Export for S3M:
  - `S3M_LABELSTUDIO_URL=http://localhost:8081`
  - `S3M_LABELSTUDIO_TOKEN=<token>`

## S3M project templates
- `sar_ship_detection` (sensor_analytics): SAR ship, oil platform, buoy, debris boxes.
- `military_vehicle_detection` (threat_detection): aerial vehicle classes for YOLO updates.
- `arabic_ner` (comms_nlp): UNIT/LOCATION/WEAPON/PERSON/THREAT labels.
- `threat_classification` (threat_detection): threat type and severity labeling.

## Annotation workflow
1. Create project from template with `create_project(template_name)`.
2. Import tasks via `import_tasks(project_id, data)`.
3. Monitor with `get_labeling_progress(project_id)`.
4. Export annotations using `export_for_training`.

## Export formats for training
- YOLO: class and normalized box coordinates.
- COCO: JSON images/annotations/categories.
- CoNLL: token-label format for NER pipelines.

## Air-gapped notes
- Deploy Label Studio on the same trusted local network as Jetson operators.
- Exported training files are written under `data/training/<project>/`.

## Smoke test
```bash
pytest -q packages/providers/ml-labelstudio/tests/test_labelstudio_adapter.py
```

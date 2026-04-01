"""Label Studio provider configuration for S3M ML data annotation workflows."""

from __future__ import annotations

from dataclasses import dataclass, field


PROJECT_TEMPLATES: dict[str, dict[str, str]] = {
    "sar_ship_detection": {
        "title": "SAR Ship Detection Training Data",
        "description": "Bounding box annotation for ships in Sentinel-1 SAR imagery",
        "label_config": '<View><Image name="image" value="$image"/><RectangleLabels name="label" toName="image"><Label value="ship"/><Label value="oil_platform"/><Label value="buoy"/><Label value="debris"/></RectangleLabels></View>',
        "s3m_layer": "sensor_analytics",
    },
    "military_vehicle_detection": {
        "title": "Military Vehicle Detection",
        "description": "Vehicle classification from aerial/drone imagery",
        "label_config": '<View><Image name="image" value="$image"/><RectangleLabels name="label" toName="image"><Label value="tank"/><Label value="apc"/><Label value="truck"/><Label value="helicopter"/><Label value="fighter_jet"/><Label value="uav"/><Label value="patrol_boat"/></RectangleLabels></View>',
        "s3m_layer": "threat_detection",
    },
    "arabic_ner": {
        "title": "Arabic Military NER",
        "description": "Named entity recognition for Arabic military text",
        "label_config": '<View><Labels name="label" toName="text"><Label value="UNIT"/><Label value="LOCATION"/><Label value="WEAPON"/><Label value="PERSON"/><Label value="THREAT"/></Labels><Text name="text" value="$text"/></View>',
        "s3m_layer": "comms_nlp",
    },
    "threat_classification": {
        "title": "Threat Indicator Classification",
        "description": "Classify threat indicators by type and severity",
        "label_config": '<View><Text name="text" value="$text"/><Choices name="threat_type" toName="text"><Choice value="malware"/><Choice value="phishing"/><Choice value="apt"/><Choice value="botnet"/><Choice value="ransomware"/></Choices><Choices name="severity" toName="text"><Choice value="critical"/><Choice value="high"/><Choice value="medium"/><Choice value="low"/></Choices></View>',
        "s3m_layer": "threat_detection",
    },
}


@dataclass
class LabelStudioConfig:
    base_url: str = "http://localhost:8081"
    rate_limit_rpm: int = 30
    s3m_project_templates: dict[str, dict[str, str]] = field(default_factory=lambda: PROJECT_TEMPLATES.copy())

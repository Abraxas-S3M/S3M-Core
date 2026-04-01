"""Federation Object Model helpers for simulation-only HLA integration."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from packages.providers.sim_hla.config import HLA_INTERACTIONS, HLA_OBJECT_CLASSES


class FOMManager:
    """Load, generate, and validate S3M HLA FOM XML definitions."""

    def __init__(self, fom_path: str | None = None):
        self.fom_path = fom_path or "configs/interop/s3m_fom.xml"

    def load_fom(self, path: str) -> dict[str, Any]:
        root = ET.parse(path).getroot()
        objects: dict[str, Any] = {}
        interactions: dict[str, Any] = {}
        for obj in root.findall(".//objects/objectClass"):
            name = str(obj.attrib.get("name", ""))
            attrs = [str(attr.attrib.get("name", "")) for attr in obj.findall("./attribute")]
            if name:
                objects[name] = {"attributes": attrs}
        for inter in root.findall(".//interactions/interactionClass"):
            name = str(inter.attrib.get("name", ""))
            params = [str(param.attrib.get("name", "")) for param in inter.findall("./parameter")]
            if name:
                interactions[name] = {"parameters": params}
        return {
            "federation": str(root.attrib.get("name", "S3M_Federation")),
            "objects": objects,
            "interactions": interactions,
        }

    def generate_s3m_fom(self) -> str:
        root = ET.Element("fom", attrib={"name": "S3M_Federation", "rprVersion": "2.0"})
        objects_node = ET.SubElement(root, "objects")
        for class_name, details in HLA_OBJECT_CLASSES.items():
            obj = ET.SubElement(objects_node, "objectClass", attrib={"name": class_name, "sharing": "PublishSubscribe"})
            for attr_name in details.get("attributes", []):
                ET.SubElement(obj, "attribute", attrib={"name": str(attr_name), "dataType": "HLAunicodeString"})

        inter_node = ET.SubElement(root, "interactions")
        for class_name, details in HLA_INTERACTIONS.items():
            inter = ET.SubElement(inter_node, "interactionClass", attrib={"name": class_name, "sharing": "PublishSubscribe"})
            for param_name in details.get("parameters", []):
                ET.SubElement(inter, "parameter", attrib={"name": str(param_name), "dataType": "HLAunicodeString"})

        xml_text = ET.tostring(root, encoding="unicode")
        target = Path(self.fom_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(xml_text, encoding="utf-8")
        return xml_text

    def validate_fom(self, fom_xml: str) -> tuple[bool, list[str]]:
        errors: list[str] = []
        try:
            root = ET.fromstring(fom_xml)
        except ET.ParseError as exc:
            return (False, [f"invalid_xml: {exc}"])

        object_names = {str(node.attrib.get("name", "")) for node in root.findall(".//objects/objectClass")}
        interaction_names = {str(node.attrib.get("name", "")) for node in root.findall(".//interactions/interactionClass")}
        for required in HLA_OBJECT_CLASSES:
            if required not in object_names:
                errors.append(f"missing_object_class:{required}")
        for required in HLA_INTERACTIONS:
            if required not in interaction_names:
                errors.append(f"missing_interaction_class:{required}")
        return (len(errors) == 0, errors)

    def get_object_class_handles(self, fom: dict[str, Any]) -> dict[str, int]:
        classes = sorted((fom.get("objects") or {}).keys())
        return {name: idx for idx, name in enumerate(classes, start=1)}

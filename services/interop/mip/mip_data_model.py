"""Core MIP data model subset for tactical Object/Action exchange."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4
from xml.etree import ElementTree as ET


_VALID_OBJECT_CATEGORIES = {"unit", "equipment", "facility", "feature", "materiel"}
_VALID_HOSTILITY = {"friend", "hostile", "neutral", "unknown"}
_VALID_OPERATIONAL_STATUS = {"operational", "degraded", "destroyed"}
_VALID_OIG_CATEGORIES = {"operations", "intelligence", "logistics", "plans", "cop"}


@dataclass
class MIPObjectItem:
    object_item_id: str  # UUID
    name: str
    category: str  # "unit" | "equipment" | "facility" | "feature" | "materiel"
    hostility_status: str  # "friend" | "hostile" | "neutral" | "unknown"
    symbol_id: str  # APP-6 SIDC
    operational_status: str  # "operational" | "degraded" | "destroyed"


@dataclass
class MIPLocation:
    object_item_id: str  # references ObjectItem
    latitude: float
    longitude: float
    altitude: float
    bearing: float  # degrees true north
    speed: float  # m/s
    datetime: str  # ISO-8601


@dataclass
class MIPActionTask:
    action_id: str
    action_type: str  # "advance" | "defend" | "patrol" | "attack" | ...
    responsible_unit: str  # ObjectItem ID
    start_time: str
    end_time: str
    objective_location: Optional[MIPLocation] = None
    order_text: str = ""


@dataclass
class MIPOperationalInfoGroup:
    oig_id: str
    category: str  # "operations" | "intelligence" | "logistics" | "plans" | "cop"
    owning_unit: str
    items: list[str] = field(default_factory=list)  # list of ObjectItem/ActionTask/Location IDs


class MIPDataModel:
    """Minimal MIM subset used for tactical CWIX-style interoperability exchanges."""

    def __init__(self) -> None:
        self.object_items: dict[str, MIPObjectItem] = {}
        self.locations: dict[str, MIPLocation] = {}
        self.action_tasks: dict[str, MIPActionTask] = {}
        self.oigs: dict[str, MIPOperationalInfoGroup] = {}

    @staticmethod
    def _iso_now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _normalized(value: str) -> str:
        return str(value or "").strip().lower()

    def create_object_item(
        self,
        name: str,
        category: str,
        hostility: str,
        sidc: str,
    ) -> MIPObjectItem:
        category_val = self._normalized(category)
        hostility_val = self._normalized(hostility)
        if category_val not in _VALID_OBJECT_CATEGORIES:
            category_val = "feature"
        if hostility_val not in _VALID_HOSTILITY:
            hostility_val = "unknown"
        item = MIPObjectItem(
            object_item_id=str(uuid4()),
            name=str(name or "Unknown Object"),
            category=category_val,
            hostility_status=hostility_val,
            symbol_id=str(sidc or "00000000000000000000"),
            operational_status="operational",
        )
        self.object_items[item.object_item_id] = item
        return item

    def create_location(
        self,
        object_item_id: str,
        lat: float,
        lon: float,
        alt: float,
        bearing: float,
        speed: float,
    ) -> MIPLocation:
        location = MIPLocation(
            object_item_id=str(object_item_id),
            latitude=float(lat),
            longitude=float(lon),
            altitude=float(alt),
            bearing=float(bearing),
            speed=float(speed),
            datetime=self._iso_now(),
        )
        self.locations[location.object_item_id] = location
        return location

    def create_action_task(
        self,
        action_type: str,
        unit_id: str,
        start: str,
        end: str,
        objective: Optional[MIPLocation] = None,
    ) -> MIPActionTask:
        task = MIPActionTask(
            action_id=str(uuid4()),
            action_type=str(action_type or "advance").strip().lower(),
            responsible_unit=str(unit_id),
            start_time=str(start),
            end_time=str(end),
            objective_location=objective,
        )
        self.action_tasks[task.action_id] = task
        return task

    def create_oig(self, category: str, unit_id: str) -> MIPOperationalInfoGroup:
        category_val = self._normalized(category)
        if category_val not in _VALID_OIG_CATEGORIES:
            category_val = "operations"
        oig = MIPOperationalInfoGroup(
            oig_id=str(uuid4()),
            category=category_val,
            owning_unit=str(unit_id),
            items=[],
        )
        self.oigs[oig.oig_id] = oig
        return oig

    @staticmethod
    def _tag(node: ET.Element) -> str:
        return node.tag.rsplit("}", 1)[-1]

    def to_xml(self, objects: list) -> str:
        root = ET.Element(
            "MIPExchange",
            {
                "baseline": "4.3",
                "dataModel": "MIM",
                "generatedAt": self._iso_now(),
            },
        )
        for obj in list(objects or []):
            if isinstance(obj, MIPObjectItem):
                node = ET.SubElement(root, "ObjectItem")
                ET.SubElement(node, "ObjectItemID").text = obj.object_item_id
                ET.SubElement(node, "Name").text = obj.name
                ET.SubElement(node, "Category").text = obj.category
                ET.SubElement(node, "HostilityStatus").text = obj.hostility_status
                ET.SubElement(node, "SymbolID").text = obj.symbol_id
                ET.SubElement(node, "OperationalStatus").text = obj.operational_status
            elif isinstance(obj, MIPLocation):
                node = ET.SubElement(root, "Location")
                ET.SubElement(node, "ObjectItemID").text = obj.object_item_id
                ET.SubElement(node, "Latitude").text = str(obj.latitude)
                ET.SubElement(node, "Longitude").text = str(obj.longitude)
                ET.SubElement(node, "Altitude").text = str(obj.altitude)
                ET.SubElement(node, "Bearing").text = str(obj.bearing)
                ET.SubElement(node, "Speed").text = str(obj.speed)
                ET.SubElement(node, "DateTime").text = obj.datetime
            elif isinstance(obj, MIPActionTask):
                node = ET.SubElement(root, "ActionTask")
                ET.SubElement(node, "ActionID").text = obj.action_id
                ET.SubElement(node, "ActionType").text = obj.action_type
                ET.SubElement(node, "ResponsibleUnit").text = obj.responsible_unit
                ET.SubElement(node, "StartTime").text = obj.start_time
                ET.SubElement(node, "EndTime").text = obj.end_time
                ET.SubElement(node, "OrderText").text = obj.order_text
                if obj.objective_location is not None:
                    objective = ET.SubElement(node, "ObjectiveLocation")
                    ET.SubElement(objective, "ObjectItemID").text = obj.objective_location.object_item_id
                    ET.SubElement(objective, "Latitude").text = str(obj.objective_location.latitude)
                    ET.SubElement(objective, "Longitude").text = str(obj.objective_location.longitude)
                    ET.SubElement(objective, "Altitude").text = str(obj.objective_location.altitude)
                    ET.SubElement(objective, "Bearing").text = str(obj.objective_location.bearing)
                    ET.SubElement(objective, "Speed").text = str(obj.objective_location.speed)
                    ET.SubElement(objective, "DateTime").text = obj.objective_location.datetime
            elif isinstance(obj, MIPOperationalInfoGroup):
                node = ET.SubElement(root, "OperationalInfoGroup")
                ET.SubElement(node, "OIGID").text = obj.oig_id
                ET.SubElement(node, "Category").text = obj.category
                ET.SubElement(node, "OwningUnit").text = obj.owning_unit
                items_node = ET.SubElement(node, "Items")
                for item_id in obj.items:
                    ET.SubElement(items_node, "ItemRef").text = str(item_id)
        return ET.tostring(root, encoding="unicode")

    def from_xml(self, xml_str: str) -> list:
        parsed: list = []
        root = ET.fromstring(xml_str)
        for node in root:
            tag = self._tag(node)
            if tag == "ObjectItem":
                item = MIPObjectItem(
                    object_item_id=node.findtext(".//{*}ObjectItemID", default=""),
                    name=node.findtext(".//{*}Name", default=""),
                    category=node.findtext(".//{*}Category", default="feature"),
                    hostility_status=node.findtext(".//{*}HostilityStatus", default="unknown"),
                    symbol_id=node.findtext(".//{*}SymbolID", default=""),
                    operational_status=node.findtext(".//{*}OperationalStatus", default="operational"),
                )
                self.object_items[item.object_item_id] = item
                parsed.append(item)
            elif tag == "Location":
                loc = MIPLocation(
                    object_item_id=node.findtext(".//{*}ObjectItemID", default=""),
                    latitude=float(node.findtext(".//{*}Latitude", default="0")),
                    longitude=float(node.findtext(".//{*}Longitude", default="0")),
                    altitude=float(node.findtext(".//{*}Altitude", default="0")),
                    bearing=float(node.findtext(".//{*}Bearing", default="0")),
                    speed=float(node.findtext(".//{*}Speed", default="0")),
                    datetime=node.findtext(".//{*}DateTime", default=self._iso_now()),
                )
                self.locations[loc.object_item_id] = loc
                parsed.append(loc)
            elif tag == "ActionTask":
                objective_node = node.find(".//{*}ObjectiveLocation")
                objective = None
                if objective_node is not None:
                    objective = MIPLocation(
                        object_item_id=objective_node.findtext(".//{*}ObjectItemID", default=""),
                        latitude=float(objective_node.findtext(".//{*}Latitude", default="0")),
                        longitude=float(objective_node.findtext(".//{*}Longitude", default="0")),
                        altitude=float(objective_node.findtext(".//{*}Altitude", default="0")),
                        bearing=float(objective_node.findtext(".//{*}Bearing", default="0")),
                        speed=float(objective_node.findtext(".//{*}Speed", default="0")),
                        datetime=objective_node.findtext(".//{*}DateTime", default=self._iso_now()),
                    )
                task = MIPActionTask(
                    action_id=node.findtext(".//{*}ActionID", default=""),
                    action_type=node.findtext(".//{*}ActionType", default="advance"),
                    responsible_unit=node.findtext(".//{*}ResponsibleUnit", default=""),
                    start_time=node.findtext(".//{*}StartTime", default=""),
                    end_time=node.findtext(".//{*}EndTime", default=""),
                    objective_location=objective,
                    order_text=node.findtext(".//{*}OrderText", default=""),
                )
                self.action_tasks[task.action_id] = task
                parsed.append(task)
            elif tag == "OperationalInfoGroup":
                items = [x.text or "" for x in node.findall(".//{*}ItemRef")]
                oig = MIPOperationalInfoGroup(
                    oig_id=node.findtext(".//{*}OIGID", default=""),
                    category=node.findtext(".//{*}Category", default="operations"),
                    owning_unit=node.findtext(".//{*}OwningUnit", default=""),
                    items=items,
                )
                self.oigs[oig.oig_id] = oig
                parsed.append(oig)
        return parsed

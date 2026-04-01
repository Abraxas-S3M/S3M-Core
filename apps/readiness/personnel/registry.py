"""Personnel registry for S3M Phase 20 readiness layer."""

from __future__ import annotations

import base64
import json
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

from apps.readiness.models import (
    Branch,
    ClearanceLevel,
    MedicalStatus,
    MilitaryStatus,
    Rank,
    ServiceMember,
)
from src.security.crypto import DataEncryptor, SecureAuditLog


class PersonnelRegistry:
    """Authoritative military personnel registry with bilingual Saudi context."""

    def __init__(self, max_personnel: int = 100000):
        self.max_personnel = int(max_personnel)
        self._members: Dict[str, ServiceMember] = {}
        self._service_number_idx: Dict[str, str] = {}
        self._encryptor = DataEncryptor()
        self._audit = SecureAuditLog(log_dir="data/readiness_audit/")
        if "readiness" not in self._encryptor.list_keys():
            self._encryptor.generate_key("readiness")

    def _mk_member_id(self) -> str:
        return f"mem-{uuid.uuid4().hex[:12]}"

    def _mk_service_number(self) -> str:
        return f"KSA-{datetime.now(timezone.utc).strftime('%Y')}-{uuid.uuid4().hex[:8].upper()}"

    def _encrypt_contact(self, contact: dict) -> dict:
        if not contact:
            return {}
        blob = json.dumps(contact, ensure_ascii=False).encode("utf-8")
        encrypted = self._encryptor.encrypt_data(blob, key_id="readiness")
        return {"ciphertext_b64": base64.b64encode(encrypted).decode("ascii"), "encrypted": True}

    def _decrypt_contact(self, contact_payload: dict) -> dict:
        if not contact_payload or not contact_payload.get("encrypted"):
            return dict(contact_payload or {})
        raw = self._encryptor.decrypt_data(
            base64.b64decode(contact_payload["ciphertext_b64"].encode("ascii")),
            key_id="readiness",
        )
        return json.loads(raw.decode("utf-8"))

    def register(
        self,
        name_en,
        name_ar,
        rank,
        branch,
        mos,
        mos_description_en,
        mos_description_ar,
        unit_id,
        unit_name_en,
        unit_name_ar,
        service_number=None,
        clearance=ClearanceLevel.CONFIDENTIAL,
        medical=MedicalStatus.FIT_FOR_DUTY,
        languages=None,
        specializations=None,
    ) -> ServiceMember:
        if len(self._members) >= self.max_personnel:
            raise ValueError("personnel registry capacity reached")

        service_number = service_number or self._mk_service_number()
        if service_number in self._service_number_idx:
            raise ValueError(f"service number already exists: {service_number}")

        now = datetime.now(timezone.utc)
        member = ServiceMember(
            member_id=self._mk_member_id(),
            service_number=service_number,
            name_en=name_en,
            name_ar=name_ar,
            rank=Rank(rank),
            branch=Branch(branch),
            mos=mos,
            mos_description_en=mos_description_en,
            mos_description_ar=mos_description_ar,
            status=MilitaryStatus.ACTIVE_DUTY,
            clearance=ClearanceLevel(clearance),
            medical=MedicalStatus(medical),
            unit_id=unit_id,
            unit_name_en=unit_name_en,
            unit_name_ar=unit_name_ar,
            date_of_rank=now,
            service_start_date=now - timedelta(days=365 * 4),
            years_of_service=4.0,
            certifications=[],
            deployments=[],
            training_score=None,
            eligible_for_deployment=True,
            next_evaluation_date=now + timedelta(days=180),
            languages=list(languages or ["ar", "en"]),
            specializations=list(specializations or []),
            contact={},
        )
        self._members[member.member_id] = member
        self._service_number_idx[service_number] = member.member_id
        self._audit.log(
            action="personnel_registered",
            details={
                "member_id": member.member_id,
                "service_number": service_number,
                "rank": member.rank.value,
                "branch": member.branch.value,
                "unit_id": member.unit_id,
            },
            source="readiness.personnel_registry",
        )
        return member

    def get_member(self, member_id) -> Optional[ServiceMember]:
        return self._members.get(member_id)

    def get_by_service_number(self, service_number) -> Optional[ServiceMember]:
        member_id = self._service_number_idx.get(service_number)
        if not member_id:
            return None
        return self._members.get(member_id)

    def get_members(
        self,
        unit_id=None,
        rank=None,
        branch=None,
        status=None,
        mos=None,
        deployable_only=False,
    ) -> List[ServiceMember]:
        rows = list(self._members.values())
        if unit_id is not None:
            rows = [m for m in rows if m.unit_id == unit_id]
        if rank is not None:
            rank_value = Rank(rank)
            rows = [m for m in rows if m.rank == rank_value]
        if branch is not None:
            branch_value = Branch(branch)
            rows = [m for m in rows if m.branch == branch_value]
        if status is not None:
            status_value = MilitaryStatus(status)
            rows = [m for m in rows if m.status == status_value]
        if mos is not None:
            rows = [m for m in rows if m.mos == mos]
        if deployable_only:
            rows = [m for m in rows if m.is_deployable()]
        return rows

    def update_member(self, member_id, **kwargs):
        member = self._members.get(member_id)
        if member is None:
            raise KeyError(f"member not found: {member_id}")
        for key, value in kwargs.items():
            if key == "contact":
                setattr(member, key, self._encrypt_contact(value))
                continue
            if key == "rank":
                value = Rank(value)
            if key == "branch":
                value = Branch(value)
            if key == "status":
                value = MilitaryStatus(value)
            if key == "clearance":
                value = ClearanceLevel(value)
            if key == "medical":
                value = MedicalStatus(value)
            if hasattr(member, key):
                setattr(member, key, value)
        self._audit.log(
            action="personnel_updated",
            details={"member_id": member_id, "updated_fields": sorted(list(kwargs.keys()))},
            source="readiness.personnel_registry",
        )
        return member

    def promote(self, member_id, new_rank: Rank):
        member = self._members.get(member_id)
        if member is None:
            raise KeyError(f"member not found: {member_id}")
        new_rank = Rank(new_rank)
        if Rank.rank_level(new_rank) <= Rank.rank_level(member.rank):
            raise ValueError("new rank must be higher than current rank")
        member.rank = new_rank
        member.date_of_rank = datetime.now(timezone.utc)
        self._audit.log(
            action="personnel_promoted",
            details={"member_id": member_id, "new_rank": new_rank.value},
            source="readiness.personnel_registry",
        )
        return member

    def update_status(self, member_id, status: MilitaryStatus):
        return self.update_member(member_id, status=MilitaryStatus(status))

    def update_medical(self, member_id, medical: MedicalStatus):
        return self.update_member(member_id, medical=MedicalStatus(medical))

    def update_clearance(self, member_id, clearance: ClearanceLevel):
        return self.update_member(member_id, clearance=ClearanceLevel(clearance))

    def assign_to_unit(self, member_id, unit_id, unit_name_en, unit_name_ar):
        return self.update_member(
            member_id,
            unit_id=unit_id,
            unit_name_en=unit_name_en,
            unit_name_ar=unit_name_ar,
        )

    def get_unit_roster(self, unit_id) -> List[ServiceMember]:
        return [m for m in self._members.values() if m.unit_id == unit_id]

    def get_officers(self, unit_id=None, branch=None) -> List[ServiceMember]:
        rows = self.get_members(unit_id=unit_id, branch=branch)
        return [m for m in rows if m.is_officer()]

    def search(self, query: str) -> List[ServiceMember]:
        q = query.strip().lower()
        if not q:
            return []
        out = []
        for m in self._members.values():
            hay = [m.name_en.lower(), m.name_ar.lower(), m.service_number.lower(), m.mos.lower()]
            if any(q in chunk for chunk in hay):
                out.append(m)
        return out

    def get_statistics(self) -> dict:
        rows = list(self._members.values())
        by_rank = Counter(m.rank.value for m in rows)
        by_branch = Counter(m.branch.value for m in rows)
        by_status = Counter(m.status.value for m in rows)
        officers = len([m for m in rows if Rank.is_officer(m.rank)])
        ncos = len([m for m in rows if Rank.is_nco(m.rank)])
        enlisted = len([m for m in rows if Rank.is_enlisted(m.rank)])
        deployable = len([m for m in rows if m.is_deployable()])
        total = len(rows)
        return {
            "total": total,
            "by_rank": dict(by_rank),
            "by_branch": dict(by_branch),
            "by_status": dict(by_status),
            "officers": officers,
            "ncos": ncos,
            "enlisted": enlisted,
            "deployable": deployable,
            "deployable_pct": round((deployable / total) * 100.0, 2) if total else 0.0,
        }

    def create_saudi_battalion_template(self) -> List[ServiceMember]:
        names = [
            ("Fahad Al-Harbi", "فهد الحربي"),
            ("Saad Al-Qahtani", "سعد القحطاني"),
            ("Nasser Al-Dosari", "ناصر الدوسري"),
            ("Abdullah Al-Otaibi", "عبدالله العتيبي"),
            ("Khalid Al-Mutairi", "خالد المطيري"),
            ("Majed Al-Anzi", "ماجد العنزي"),
            ("Turki Al-Shammari", "تركي الشمري"),
            ("Mansour Al-Zahrani", "منصور الزهراني"),
            ("Rakan Al-Ghamdi", "راكان الغامدي"),
            ("Yousef Al-Amri", "يوسف العمري"),
            ("Sultan Al-Hazmi", "سلطان الحازمي"),
            ("Badr Al-Rashidi", "بدر الرشيدي"),
            ("Hamad Al-Shehri", "حمد الشهري"),
            ("Mishari Al-Harthi", "مشاري الحارثي"),
            ("Tariq Al-Farhan", "طارق الفرحان"),
            ("Nawaf Al-Sudairi", "نواف السديري"),
            ("Waleed Al-Salem", "وليد السالم"),
            ("Riyad Al-Saif", "رياض السيف"),
            ("Adel Al-Saqr", "عادل الصقر"),
            ("Ammar Al-Ajmi", "عمار العجمي"),
            ("Faisal Al-Malki", "فيصل المالكي"),
            ("Ibrahim Al-Mutlaq", "إبراهيم المطلق"),
            ("Omar Al-Tamimi", "عمر التميمي"),
            ("Hassan Al-Yami", "حسن اليامي"),
            ("Ziad Al-Qarni", "زياد القرني"),
            ("Rashed Al-Mansour", "راشد المنصور"),
            ("Nayef Al-Bishi", "نايف البيشي"),
            ("Samer Al-Khathlan", "سامر الخثلان"),
            ("Fawaz Al-Nahdi", "فواز النهدي"),
            ("Talal Al-Subaie", "طلال السبيعي"),
            ("Mohannad Al-Ruwais", "مهند الرويس"),
            ("Raed Al-Hussain", "رائد الحسين"),
            ("Sami Al-Saadi", "سامي السعدي"),
            ("Karem Al-Maghrabi", "كريم المغربي"),
            ("Nabil Al-Qaedi", "نبيل القائدي"),
            ("Basil Al-Rabeea", "باسل الربيعة"),
            ("Hadi Al-Hamdan", "هادي الحمدان"),
            ("Mazen Al-Masri", "مازن المصري"),
            ("Ayman Al-Khalaf", "أيمن الخلف"),
            ("Shaher Al-Qaidi", "شاهر القائدي"),
            ("Yahya Al-Juhani", "يحيى الجهني"),
            ("Fares Al-Sobhi", "فارس الصبحي"),
            ("Saeed Al-Sharif", "سعيد الشريف"),
            ("Muteb Al-Dawood", "متعب الداوود"),
            ("Ziyad Al-Turki", "زياد التركي"),
        ]
        rank_plan = (
            [Rank.LIEUTENANT_COLONEL]
            + [Rank.MAJOR] * 3
            + [Rank.CAPTAIN] * 6
            + [Rank.FIRST_LIEUTENANT] * 6
            + [Rank.SECOND_LIEUTENANT] * 6
            + [Rank.FIRST_SERGEANT] * 4
            + [Rank.STAFF_SERGEANT] * 4
            + [Rank.SERGEANT] * 8
            + [Rank.CORPORAL] * 7
        )
        assert len(rank_plan) == 45
        statuses = (
            [MilitaryStatus.ACTIVE_DUTY] * 38
            + [MilitaryStatus.DEPLOYED] * 3
            + [MilitaryStatus.TRAINING] * 2
            + [MilitaryStatus.MEDICAL_LEAVE]
            + [MilitaryStatus.ADMINISTRATIVE_LEAVE]
        )
        assert len(statuses) == 45
        mos_catalog = [
            ("11A", "Armor Officer", "ضابط مدرعات"),
            ("11B", "Infantry Officer", "ضابط مشاة"),
            ("13F", "Fire Support", "إسناد نيراني"),
            ("25U", "Signals Operator", "مشغل إشارات"),
            ("35F", "Intelligence Analyst", "محلل استخبارات"),
            ("68W", "Combat Medic", "مسعف قتالي"),
            ("15W", "UAV Operator", "مشغل طائرات بدون طيار"),
            ("17C", "Cyber Operations", "عمليات سيبرانية"),
            ("19K", "Armor Crewman", "طاقم مدرعة"),
            ("92A", "Logistics Specialist", "أخصائي لوجستي"),
        ]
        specs = [
            "armor_crewman",
            "uav_operator",
            "cyber_analyst",
            "signals_operator",
            "intel_fusion",
            "combat_medic",
            "fire_support",
        ]

        unit_id = "unit-1st-armored-bn"
        unit_name_en = "1st Armored Battalion"
        unit_name_ar = "كتيبة المدرعات الأولى"
        created: List[ServiceMember] = []
        now = datetime.now(timezone.utc)
        for idx in range(45):
            en, ar = names[idx]
            mos, mos_en, mos_ar = mos_catalog[idx % len(mos_catalog)]
            member = self.register(
                name_en=en,
                name_ar=ar,
                rank=rank_plan[idx],
                branch=Branch.ARMY,
                mos=mos,
                mos_description_en=mos_en,
                mos_description_ar=mos_ar,
                unit_id=unit_id,
                unit_name_en=unit_name_en,
                unit_name_ar=unit_name_ar,
                service_number=f"KSA-BN-{uuid.uuid4().hex[:8].upper()}",
                clearance=ClearanceLevel.SECRET if idx < 12 else ClearanceLevel.CONFIDENTIAL,
                medical=MedicalStatus.FIT_FOR_DUTY if statuses[idx] != MilitaryStatus.MEDICAL_LEAVE else MedicalStatus.LIMITED_DUTY,
                languages=["ar", "en"] if idx % 5 else ["ar", "en", "fr"],
                specializations=[specs[idx % len(specs)]],
            )
            member.status = statuses[idx]
            member.years_of_service = float(3 + (idx % 12))
            member.date_of_rank = now - timedelta(days=30 * (3 + (idx % 36)))
            member.certifications = ["S3M_WARGAMING_L1"] if idx < 30 else []
            member.training_score = 88.0 - (idx % 7)
            created.append(member)

        self._audit.log(
            action="saudi_battalion_template_created",
            details={"count": len(created), "unit_id": unit_id},
            source="readiness.personnel_registry",
        )
        return created

    def export(self, filepath: str):
        rows = []
        for member in self._members.values():
            row = member.to_dict()
            row["contact"] = row.get("contact") or {}
            if row["contact"] and not row["contact"].get("encrypted"):
                row["contact"] = self._encrypt_contact(row["contact"])
            rows.append(row)
        out = Path(filepath)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as handle:
            json.dump(rows, handle, ensure_ascii=False, indent=2)
        self._audit.log(
            action="personnel_exported",
            details={"filepath": filepath, "count": len(rows)},
            source="readiness.personnel_registry",
        )


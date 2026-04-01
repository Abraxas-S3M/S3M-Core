"""Procurement request lifecycle and auto-generation logic."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import uuid4

from services.maintenance.models import (
    ProcurementRequest,
    ProcurementStatus,
    SparePartInventory,
    WorkOrder,
    WorkOrderPriority,
)


class ProcurementTracker:
    """Track spare-part acquisition requests supporting fleet availability."""

    def __init__(self):
        self.requests: Dict[str, ProcurementRequest] = {}

    def create_request(
        self,
        part_name,
        part_number,
        quantity,
        urgency,
        asset_id=None,
        work_order_id=None,
        supplier_id=None,
        estimated_cost=0,
        requested_by="system",
    ) -> ProcurementRequest:
        request = ProcurementRequest(
            request_id=f"pr-{uuid4().hex[:10]}",
            asset_id=asset_id,
            work_order_id=work_order_id,
            part_name=str(part_name),
            part_number=str(part_number),
            quantity=int(quantity),
            urgency=WorkOrderPriority(urgency),
            status=ProcurementStatus.REQUESTED,
            supplier_id=supplier_id,
            estimated_cost=float(estimated_cost),
            requested_by=str(requested_by),
            requested_at=datetime.now(timezone.utc),
            notes="",
        )
        self.requests[request.request_id] = request
        return request

    def approve(self, request_id, approved_by: str):
        req = self.get_request(request_id)
        if req is None:
            raise KeyError(f"Request not found: {request_id}")
        req.status = ProcurementStatus.APPROVED
        req.approved_at = datetime.now(timezone.utc)
        req.notes = (req.notes + "\n" if req.notes else "") + f"Approved by {approved_by}"

    def update_status(self, request_id, status: ProcurementStatus, notes: str = ""):
        req = self.get_request(request_id)
        if req is None:
            raise KeyError(f"Request not found: {request_id}")
        req.status = ProcurementStatus(status)
        if notes:
            req.notes = (req.notes + "\n" if req.notes else "") + notes

    def get_request(self, request_id) -> Optional[ProcurementRequest]:
        return self.requests.get(request_id)

    def get_requests(self, status=None, urgency=None, asset_id=None) -> List[ProcurementRequest]:
        rows = list(self.requests.values())
        if status is not None:
            st = ProcurementStatus(status)
            rows = [r for r in rows if r.status == st]
        if urgency is not None:
            ug = WorkOrderPriority(urgency)
            rows = [r for r in rows if r.urgency == ug]
        if asset_id is not None:
            rows = [r for r in rows if r.asset_id == asset_id]
        return rows

    def get_pending(self) -> List[ProcurementRequest]:
        return [req for req in self.requests.values() if req.is_pending()]

    def auto_generate_from_work_orders(self, work_orders: List[WorkOrder]) -> List[ProcurementRequest]:
        generated: List[ProcurementRequest] = []
        for wo in work_orders:
            for part in wo.parts_required:
                if bool(part.get("in_stock", True)):
                    continue
                qty = int(part.get("quantity", 1))
                generated.append(
                    self.create_request(
                        part_name=part.get("name", "Unknown Part"),
                        part_number=part.get("part_id", "UNKNOWN"),
                        quantity=qty,
                        urgency=wo.priority,
                        asset_id=wo.asset_id,
                        work_order_id=wo.work_order_id,
                        estimated_cost=float(part.get("unit_cost", 0.0)) * qty,
                        requested_by="maintenance_scheduler",
                    )
                )
        return generated

    def auto_generate_from_inventory(self, spare_parts: List[SparePartInventory]) -> List[ProcurementRequest]:
        generated: List[ProcurementRequest] = []
        for part in spare_parts:
            if not part.needs_reorder():
                continue
            generated.append(
                self.create_request(
                    part_name=part.part_name,
                    part_number=part.part_number,
                    quantity=part.reorder_quantity,
                    urgency=WorkOrderPriority.ROUTINE,
                    estimated_cost=part.reorder_quantity * part.unit_cost,
                    requested_by="inventory_monitor",
                )
            )
        return generated

    def get_stats(self) -> dict:
        by_status = Counter(req.status.value for req in self.requests.values())
        return {
            "total": len(self.requests),
            "pending": len(self.get_pending()),
            "by_status": dict(by_status),
        }

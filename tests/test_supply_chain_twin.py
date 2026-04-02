from __future__ import annotations

from src.logistics.supply_chain_twin import (
    Depot,
    InventoryItem,
    PPOReorderAgent,
    SupplyChainTwin,
    SupplyStatus,
)


class _StubPPOModel:
    def __init__(self, action_idx: int) -> None:
        self.action_idx = action_idx

    def predict(self, _obs, deterministic=True):  # noqa: ANN001
        return self.action_idx, None


class _FailingPPOModel:
    def predict(self, _obs, deterministic=True):  # noqa: ANN001
        raise RuntimeError("inference failure")


def _sample_item(
    quantity: float = 10.0,
    min_threshold: float = 20.0,
    max_capacity: float = 100.0,
    daily_rate: float = 5.0,
) -> InventoryItem:
    return InventoryItem(
        item_id="ammo-001",
        name_en="Ammo",
        name_ar="ذخيرة",
        unit="box",
        quantity=quantity,
        min_threshold=min_threshold,
        max_capacity=max_capacity,
        lead_time_days=3.0,
        daily_consumption_rate=daily_rate,
        cost_per_unit=2.5,
        category="combat",
    )


def test_supply_status_and_days_remaining() -> None:
    critical = _sample_item(quantity=5.0)
    low = _sample_item(quantity=20.0)
    adequate = _sample_item(quantity=50.0)
    surplus = _sample_item(quantity=95.0)
    assert critical.status == SupplyStatus.CRITICAL
    assert low.status == SupplyStatus.LOW
    assert adequate.status == SupplyStatus.ADEQUATE
    assert surplus.status == SupplyStatus.SURPLUS
    assert round(adequate.days_remaining, 1) == 10.0


def test_ppo_reorder_agent_uses_model_prediction() -> None:
    item = _sample_item(quantity=20.0, max_capacity=100.0)
    agent = PPOReorderAgent(model=_StubPPOModel(action_idx=3))
    qty = agent.recommend_reorder(item)
    assert qty == 75.0


def test_ppo_reorder_agent_fallback_when_model_fails() -> None:
    item = _sample_item(quantity=5.0, min_threshold=30.0, max_capacity=100.0, daily_rate=6.0)
    agent = PPOReorderAgent(model=_FailingPPOModel())
    qty = agent.recommend_reorder(item)
    # Fallback should choose a positive reorder quantity for critically low stock.
    assert qty > 0.0


def test_supply_chain_twin_generates_alerts_and_orders() -> None:
    depot = Depot(depot_id="d1", name="Depot-1", lat=0.0, lon=0.0)
    depot.add_item(_sample_item(quantity=8.0, max_capacity=100.0))
    depot.add_item(
        InventoryItem(
            item_id="fuel-001",
            name_en="Fuel",
            name_ar="وقود",
            unit="liter",
            quantity=80.0,
            min_threshold=30.0,
            max_capacity=100.0,
            lead_time_days=2.0,
            daily_consumption_rate=3.0,
            cost_per_unit=1.0,
            category="mobility",
        )
    )
    twin = SupplyChainTwin(reorder_agent=PPOReorderAgent(model=_StubPPOModel(action_idx=2)))
    twin.add_depot(depot)

    alerts = twin.generate_alerts()
    assert len(alerts) == 1
    assert alerts[0]["item_id"] == "ammo-001"
    assert alerts[0]["severity"] == "HIGH"

    orders = twin.optimize_reorders()
    assert len(orders) == 2
    assert all(order["reorder_qty"] == 50.0 for order in orders)
    assert all("cost_estimate" in order for order in orders)


def test_supply_chain_twin_step_and_full_status() -> None:
    depot = Depot(depot_id="d2", name="Depot-2", lat=1.0, lon=1.0)
    item = _sample_item(quantity=40.0, daily_rate=4.0)
    depot.add_item(item)
    twin = SupplyChainTwin()
    twin.add_depot(depot)

    before_qty = item.quantity
    twin.step(days=1.0)
    after_qty = item.quantity
    assert after_qty <= before_qty

    status = twin.full_status()
    assert status["sim_day"] == 1.0
    assert "d2" in status["depots"]
    assert status["depots"]["d2"]["inventory"]["ammo-001"]["quantity"] == after_qty

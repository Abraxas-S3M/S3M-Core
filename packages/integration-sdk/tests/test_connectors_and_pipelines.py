from connectors.local_storage import LocalStorage
from pipelines.deduplication.dedup_engine import HashBasedDeduplicator


def test_local_storage_store_query_count(tmp_path):
    storage = LocalStorage(root_dir=str(tmp_path / "data" / "integrations"))
    record = {"provider_id": "mock-satellite", "value": 42}
    storage.store(provider_id="mock-satellite", collection="normalized", record=record)

    results = storage.query(provider_id="mock-satellite", collection="normalized", filters={"value": 42})
    assert len(results) == 1
    assert results[0]["provider_id"] == "mock-satellite"
    assert storage.count(provider_id="mock-satellite", collection="normalized") == 1


def test_hash_deduplicator_stores_unique_once():
    dedup = HashBasedDeduplicator()
    records = [{"id": 1, "name": "same"}, {"id": 1, "name": "same"}]
    unique = dedup.deduplicate(records)
    assert len(unique) == 1

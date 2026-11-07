from src.cortex.manifest import manifest_digest


def test_manifest_digest_changes_with_description() -> None:
    tools = [{"name": "a", "description": "one", "inputSchema": {}}]
    first = manifest_digest(tools)
    tools[0]["description"] = "two"
    second = manifest_digest(tools)
    assert first != second

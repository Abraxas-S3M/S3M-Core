from src.cortex.tool_map import XiidToolMap


def test_tool_map_resolves_narrow_route() -> None:
    mapping = XiidToolMap.from_yaml()
    binding = mapping.resolve("narrow_route")
    assert binding.tool == "route.narrow"
    assert binding.requires_envelope is True

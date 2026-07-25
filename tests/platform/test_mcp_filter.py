from openswe_platform.harness.mcp_runtime import filter_tools


def test_allowlist():
    assert filter_tools(["a", "b", "c"], allowlist=["a", "c"], denylist=[]) == ["a", "c"]


def test_denylist():
    assert filter_tools(["a", "b"], allowlist=[], denylist=["b"]) == ["a"]


def test_both():
    assert filter_tools(["a", "b", "c"], allowlist=["a", "b"], denylist=["b"]) == ["a"]

from openswe_platform.harness.agents import REGISTRY, get_agent


def test_all_agent_types():
    for name in ("coding", "reviewer", "analyzer", "chat"):
        assert get_agent(name) is REGISTRY[name]

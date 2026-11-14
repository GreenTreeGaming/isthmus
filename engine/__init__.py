"""Isthmus evacuation engine. Public API matches contracts/engine_api.py."""
from engine.network import Network, load_network

__all__ = ["Network", "load_network", "run_scenario"]


def __getattr__(name):
    # Lazy import so `import engine` stays cheap and avoids circular imports.
    if name == "run_scenario":
        from engine.scenario import run_scenario
        return run_scenario
    raise AttributeError(name)

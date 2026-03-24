import importlib

__all__ = [
    "BaseAgent",
    "RandomAgent",
    "MarketMakerAgent",
    "MomentumAgent",
    "create_market_tools",
    "DualMemoryStore",
    "MemoryEntry",
    "RedisConnector",
    "MongoConnector",
]


def __getattr__(name: str):
    if name in ("BaseAgent",):
        module = importlib.import_module(".BaseAgent", __name__)
        return getattr(module, name)
    if name in ("RandomAgent", "MarketMakerAgent", "MomentumAgent"):
        module = importlib.import_module(".SimpleAgents", __name__)
        return getattr(module, name)
    if name == "create_market_tools":
        module = importlib.import_module(".tool.marketTools", __name__)
        return getattr(module, name)
    if name == "DualMemoryStore":
        module = importlib.import_module(".memory.memoryStore", __name__)
        return getattr(module, name)
    if name == "MemoryEntry":
        module = importlib.import_module(".memory.memoryModels", __name__)
        return getattr(module, name)
    if name == "RedisConnector":
        module = importlib.import_module("utils.connectors.RedisConnector")
        return getattr(module, name)
    if name == "MongoConnector":
        module = importlib.import_module("utils.connectors.MongoConnector")
        return getattr(module, name)
    raise AttributeError(f"module '{__name__}' has no attribute {name}")

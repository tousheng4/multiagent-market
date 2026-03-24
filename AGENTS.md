# Repository Summary
- Multi-agent market simulation with an exchange, order books, and matching.
- Simulation environment coordinating agents, data feeds, and market snapshots.
- Data pipeline for loading CSV price/factor data from `data/raw`.
- Built-in rule-based agents plus strategy helpers for signals/positioning.
- Optional memory connectors (Redis/Mongo) for agent logs.

# Key Entry Points
- `main.py` runs a sample simulation with a market-maker agent.
- `src/__init__.py` exports `Exchange`, `Simulation`, and data utilities.

# Layout
- `src/market/` exchange core, order books, orders, and client API.
- `src/environment/` simulation loop and performance tracking.
- `src/data/` CSV loading and `DataFeed` time-stepping.
- `src/agents/` base agent, simple agents, memory store.
- `src/strategy/` indicators, signals, risk helpers.
- `src/utils/connectors/` in-memory, Redis, and Mongo connectors.
- `data/raw/` expected CSV inputs (prices and factors).

# Development Notes
- Target runtime: Python 3.11 (see `pyproject.toml`).
- New agents should subclass `BaseAgent`, implement `step()`, and use `Exchange.submitOrder`.
- Simulation uses blinker signals (`sig_data`, `sig_snapshot`) for events.
- Keep changes focused and consistent with existing module boundaries.

# Quick Run
- `python main.py`

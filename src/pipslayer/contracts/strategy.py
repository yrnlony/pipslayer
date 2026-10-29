"""Strategy-independent plugin contract."""
from typing import Protocol, runtime_checkable

@runtime_checkable
class StrategyPlugin(Protocol):
    @property
    def strategy_id(self) -> str: ...
    @property
    def version(self) -> str: ...

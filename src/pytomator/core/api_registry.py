from dataclasses import dataclass
from typing import Callable, Dict, Any

@dataclass
class ApiFunction:
    name: str
    func: Callable
    description: str
    category: str
    params: Dict[str, str]
    returns: str | None
    examples: list[str]
    version: str
    deprecated: bool = False

API_REGISTRY: Dict[str, ApiFunction] = {}

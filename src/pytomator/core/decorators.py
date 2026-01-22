from pytomator.core.api_registry import API_REGISTRY, ApiFunction
import inspect

def pytomator_api(
    *,
    name: str | None = None,
    description: str = "",
    category: str = "General",
    params: dict[str, str] | None = None,
    returns: str | None = None,
    examples: list[str] | None = None,
    version: str = "1.0",
    deprecated: bool = False,
):
    def decorator(func):
        api_name = name or func.__name__

        API_REGISTRY[api_name] = ApiFunction(
            name=api_name,
            func=func,
            description=description or inspect.require_docstring(func),
            category=category,
            params=params or {},
            returns=returns,
            examples=examples or [],
            version=version,
            deprecated=deprecated,
        )

        # metadata também fica na função (útil pro autocomplete rápido)
        func.__pytomator_api__ = API_REGISTRY[api_name]

        return func

    return decorator

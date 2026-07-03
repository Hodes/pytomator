"""Project-scoped TemplateMatcher registry."""

from pathlib import Path

from pytomator.core.vision.template_matcher_service import TemplateMatcher

_matchers: dict[str, TemplateMatcher] = {}


def _key(project_path: Path) -> str:
    return str(Path(project_path).resolve()).casefold()


def get_template_matcher(project_path: Path) -> TemplateMatcher:
    key = _key(project_path)
    if key not in _matchers:
        _matchers[key] = TemplateMatcher(Path(project_path))
    return _matchers[key]


def release_template_matcher(project_path: Path) -> None:
    matcher = _matchers.pop(_key(project_path), None)
    if matcher is not None:
        matcher.clear()


def clear_template_matchers() -> None:
    for matcher in _matchers.values():
        matcher.clear()
    _matchers.clear()

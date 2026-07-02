"""JSON storage backend for Project (.pytom files)."""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from pytomator.project.models import Project


class ProjectStorage:
    """Handles serialization and deserialization of .pytom project files."""

    def __init__(self):
        self.recent_path: Optional[Path] = None

    def save(self, project: Project, path: Path) -> None:
        """Save a project to a .pytom file."""
        path = path.with_suffix(".pytom")
        # Update timestamp before saving
        project.updated_at = datetime.now()

        # Serialize to dict
        data = project.model_dump(mode="json")

        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        self.recent_path = path

    def load(self, path: Path) -> Project:
        """Load a project from a .pytom file."""
        path = path.with_suffix(".pytom")
        if not path.exists():
            raise FileNotFoundError(f"Project file not found: {path}")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        project = Project.model_validate(data)
        self.recent_path = path
        return project

    def get_recent_path(self) -> Optional[Path]:
        """Return the last saved/loaded path."""
        return self.recent_path

    @staticmethod
    def create_new(name: str, description: str = "") -> Project:
        """Create a new Project instance with defaults."""
        project = Project(name=name)
        project.settings.description = description
        return project
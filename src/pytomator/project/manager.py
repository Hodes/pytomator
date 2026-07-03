"""ProjectManager - coordinates project state, CRUD, and script management."""

from pathlib import Path
from typing import Optional

from pytomator.core.events import EventEmitter
from pytomator.project.models import Project, Script, ProjectSettings
from pytomator.project.storage import ProjectStorage


class ProjectManager(EventEmitter):
    """
    Central coordinator for project operations.

    Emits:
        "project_loaded"    - when a project is opened/created
        "project_closed"    - when the project is closed
        "project_saved"     - after saving to disk
        "script_added"      - args: (script_name)
        "script_removed"    - args: (script_name)
        "script_renamed"    - args: (old_name, new_name)
        "active_script_changed" - args: (script_name or None)
        "script_code_updated"   - args: (script_name)
    """

    def __init__(self):
        super().__init__()
        self.storage = ProjectStorage()
        self.project: Optional[Project] = None
        self._project_path: Optional[Path] = None

    # ------------------------------------------------------------------
    # Project lifecycle
    # ------------------------------------------------------------------

    def _release_current_project(self) -> None:
        """Release resources owned by the current project and notify listeners."""
        if self.project is None:
            return
        if self._project_path is not None:
            from pytomator.core.vision.template_matcher_registry import (
                release_template_matcher,
            )

            release_template_matcher(self._project_path)
        self.project = None
        self._project_path = None
        self.emit("project_closed")

    def _replace_project(
        self,
        project: Project,
        project_path: Optional[Path],
    ) -> Project:
        """Install a prepared project after cleanly releasing the current one."""
        self._release_current_project()
        self.project = project
        self._project_path = project_path
        self.emit("project_loaded")
        return project

    def create_project(self, name: str, description: str = "") -> Project:
        """Create and load a new empty project."""
        project = self.storage.create_new(name, description)
        return self._replace_project(project, None)

    def load_project(self, path: Path) -> Project:
        """Load a project from a .pytom file."""
        # Load first so a malformed/missing target does not disturb the current
        # project or its project-scoped resources.
        project = self.storage.load(path)
        loaded_path = self.storage.recent_path
        return self._replace_project(project, loaded_path)

    def save_project(self, path: Optional[Path] = None) -> bool:
        """Save the current project. If path is None, uses the last path."""
        if self.project is None:
            return False

        save_path = path or self._project_path
        if save_path is None:
            return False

        self.storage.save(self.project, save_path)
        self._project_path = self.storage.recent_path
        self.emit("project_saved")
        return True

    def close_project(self):
        """Close the current project (no save)."""
        self._release_current_project()

    @property
    def project_path(self) -> Optional[Path]:
        return self._project_path

    @property
    def is_project_open(self) -> bool:
        return self.project is not None

    # ------------------------------------------------------------------
    # Script CRUD
    # ------------------------------------------------------------------

    def add_script(self, name: str, code: str = "") -> Optional[Script]:
        """Add a new script to the current project."""
        if self.project is None:
            return None
        try:
            script = self.project.add_script(name, code)
            self.emit("script_added", script.name)
            return script
        except ValueError:
            return None

    def remove_script(self, name: str) -> bool:
        """Remove a script from the current project."""
        if self.project is None:
            return False
        result = self.project.remove_script(name)
        if result:
            self.emit("script_removed", name)
        return result

    def rename_script(self, old_name: str, new_name: str) -> bool:
        """Rename a script."""
        if self.project is None:
            return False
        result = self.project.rename_script(old_name, new_name)
        if result:
            self.emit("script_renamed", old_name, new_name)
        return result

    def set_active_script(self, name: str) -> bool:
        """Set which script is active (selected in the editor)."""
        if self.project is None:
            return False
        result = self.project.set_active_script(name)
        if result:
            self.emit("active_script_changed", name)
        return result

    def update_script_code(self, name: str, code: str) -> bool:
        """Update a script's code content."""
        if self.project is None:
            return False
        result = self.project.update_script_code(name, code)
        if result:
            self.emit("script_code_updated", name)
        return result

    def update_script_hotkey(self, name: str, hotkey: Optional[str]) -> bool:
        """Set or clear the hotkey for a script."""
        if self.project is None:
            return False
        script = self.project.get_script(name)
        if script is None:
            return False
        script.hotkey = hotkey
        self.project.updated_at = type(self.project.updated_at).now()
        self.emit("script_hotkey_changed", name, hotkey)
        return True

    def update_script_loop(self, name: str, loop: bool) -> bool:
        """Set the loop state for a script."""
        if self.project is None:
            return False
        script = self.project.get_script(name)
        if script is None:
            return False
        script.loop = loop
        self.project.updated_at = type(self.project.updated_at).now()
        self.emit("script_loop_changed", name, loop)
        return True

    def validate_hotkey(self, hotkey: str, exclude_script: Optional[str] = None, exclude_global: bool = False) -> tuple[bool, str]:
        """
        Check if a hotkey conflicts with any other script's hotkey.
        Returns (is_valid, conflict_message).
        If exclude_script is provided, that script is ignored (for when we're updating it).
        """
        if self.project is None:
            return True, ""

        # Check against other project scripts
        for script in self.project.scripts:
            if script.name == exclude_script:
                continue
            if script.hotkey and script.hotkey.lower() == hotkey.lower():
                return False, f"Hotkey '{hotkey}' is already assigned to script '{script.name}'."

        return True, ""

    def get_script(self, name: str) -> Optional[Script]:
        """Get a script by name."""
        if self.project is None:
            return None
        return self.project.get_script(name)

    def get_active_script(self) -> Optional[Script]:
        """Get the currently active script."""
        if self.project is None:
            return None
        return self.project.get_active_script()

    def list_scripts(self) -> list[Script]:
        """List all scripts in the current project."""
        if self.project is None:
            return []
        return list(self.project.scripts)

    # ------------------------------------------------------------------
    # Settings helpers
    # ------------------------------------------------------------------

    def get_project_settings(self) -> Optional[ProjectSettings]:
        if self.project is None:
            return None
        return self.project.settings

    def update_project_settings(self, **kwargs):
        """Update project settings fields."""
        if self.project is None:
            return
        for key, value in kwargs.items():
            if hasattr(self.project.settings, key):
                setattr(self.project.settings, key, value)
        self.project.updated_at = type(self.project.updated_at).now()
        self.emit("project_updated")

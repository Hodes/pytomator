"""Pydantic models for Project, Script, and ProjectSettings."""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class Script(BaseModel):
    """Represents a single automation script within a project."""

    name: str = Field(..., description="Script name (unique within the project)")
    code: str = Field(default="", description="Python code content")
    order: int = Field(default=0, description="Execution order index")
    is_active: bool = Field(default=False, description="Whether this script is currently selected in the editor")
    hotkey: Optional[str] = Field(default=None, description="Hotkey to execute this script (e.g. 'ctrl+shift+f6')")
    loop: bool = Field(default=False, description="Whether this script loops when executed")

    class Config:
        frozen = False  # Allow mutation at runtime


class ProjectSettings(BaseModel):
    """Project-level configuration."""

    loop_default: bool = Field(default=False, description="Default loop state when running scripts")
    auto_save: bool = Field(default=True, description="Automatically save on run/switch script")
    description: str = Field(default="", description="Project description")

    class Config:
        frozen = False


class Project(BaseModel):
    """Root model representing a complete .pytom project."""

    # Metadata
    pytomator_version: str = Field(default="0.1.2", description="Pytomator version that created this project")
    name: str = Field(..., description="Project name")
    version: str = Field(default="1.0.0", description="Project version")
    created_at: datetime = Field(default_factory=datetime.now, description="Creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.now, description="Last modification timestamp")

    # Content
    scripts: List[Script] = Field(default_factory=list, description="List of scripts in the project")
    settings: ProjectSettings = Field(default_factory=ProjectSettings, description="Project settings")
    current_script_name: Optional[str] = Field(default=None, description="Name of the last active script")

    def get_active_script(self) -> Optional[Script]:
        """Return the script marked as active, or the first one."""
        for s in self.scripts:
            if s.is_active:
                return s
        if self.scripts:
            return self.scripts[0]
        return None

    def get_script(self, name: str) -> Optional[Script]:
        """Find a script by name."""
        for s in self.scripts:
            if s.name == name:
                return s
        return None

    def add_script(self, name: str, code: str = "") -> Script:
        """Add a new script to the project."""
        if self.get_script(name):
            raise ValueError(f"Script '{name}' already exists in project")
        script = Script(
            name=name,
            code=code,
            order=len(self.scripts),
            is_active=len(self.scripts) == 0  # First script is active by default
        )
        self.scripts.append(script)
        self.updated_at = datetime.now()
        return script

    def remove_script(self, name: str) -> bool:
        """Remove a script by name. Returns True if removed."""
        script = self.get_script(name)
        if script is None:
            return False
        self.scripts.remove(script)
        # If the removed script was active, activate another one
        if script.is_active and self.scripts:
            self.scripts[0].is_active = True
        self.updated_at = datetime.now()
        return True

    def rename_script(self, old_name: str, new_name: str) -> bool:
        """Rename a script. Returns True if renamed."""
        script = self.get_script(old_name)
        if script is None or self.get_script(new_name):
            return False
        script.name = new_name
        self.updated_at = datetime.now()
        return True

    def set_active_script(self, name: str) -> bool:
        """Mark a script as active (selected in editor)."""
        script = self.get_script(name)
        if script is None:
            return False
        # Deactivate all, then activate the target
        for s in self.scripts:
            s.is_active = False
        script.is_active = True
        self.current_script_name = name
        return True

    def update_script_code(self, name: str, code: str) -> bool:
        """Update the code of a script."""
        script = self.get_script(name)
        if script is None:
            return False
        script.code = code
        self.updated_at = datetime.now()
        return True
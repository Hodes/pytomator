"""Pydantic models for Project, Script, ProjectSettings, and TemplateCapture."""

from datetime import datetime
from typing import Any, List, Literal, Optional
from uuid import uuid4
from pydantic import BaseModel, Field

from pytomator.core.vision.models import TemplateCapture


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


RecordingItemType = Literal[
    "key_down", "key_up", "mouse_move", "mouse_button_down",
    "mouse_button_up", "mouse_scroll", "wait", "comment", "api_call",
]


class RecordingItem(BaseModel):
    """One captured or manually authored item on a recording timeline."""

    id: str = Field(default_factory=lambda: uuid4().hex)
    type: RecordingItemType
    timestamp: float = Field(default=0.0, ge=0.0)
    data: dict[str, Any] = Field(default_factory=dict)

    @property
    def duration(self) -> float:
        return max(0.0, float(self.data.get("duration", 0.0))) if self.type == "wait" else 0.0


class MonitorContext(BaseModel):
    x: int = 0
    y: int = 0
    width: int
    height: int
    name: str = ""


class Recording(BaseModel):
    """An editable, replayable sequence of input events and commands."""

    id: str = Field(default_factory=lambda: uuid4().hex)
    name: str
    description: str = ""
    hotkey: Optional[str] = None
    speed: float = Field(default=1.0, gt=0.0, le=10.0)
    repetitions: int = Field(default=1, ge=1, le=100000)
    loop: bool = False
    cycle_interval: float = Field(default=0.0, ge=0.0)
    monitors: list[MonitorContext] = Field(default_factory=list)
    items: list[RecordingItem] = Field(default_factory=list)

    def sorted_items(self) -> list[RecordingItem]:
        return sorted(self.items, key=lambda item: item.timestamp)


class ProjectSettings(BaseModel):
    """Project-level configuration."""

    loop_default: bool = Field(default=False, description="Default loop state when running scripts")
    auto_save: bool = Field(default=True, description="Automatically save on run/switch script")
    vision_debug: bool = Field(
        default=False,
        description="Save template-matching diagnostic images and metadata",
    )
    mouse_backend: Literal["standard", "directinput"] = Field(
        default="standard",
        description="Default backend used for mouse automation",
    )
    mouse_move_duration: float = Field(
        default=0.3,
        ge=0.0,
        description="Default duration for smooth mouse movement, in seconds",
    )
    mouse_move_easing: Literal["linear", "ease_out", "ease_in_out"] = Field(
        default="ease_out",
        description="Default easing curve for smooth mouse movement",
    )
    description: str = Field(default="", description="Project description")

    class Config:
        frozen = False


class Project(BaseModel):
    """Root model representing a complete .pytom project."""

    # Metadata
    pytomator_version: str = Field(default="0.2.0", description="Pytomator version that created this project")
    name: str = Field(..., description="Project name")
    version: str = Field(default="1.0.0", description="Project version")
    created_at: datetime = Field(default_factory=datetime.now, description="Creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.now, description="Last modification timestamp")

    # Content
    scripts: List[Script] = Field(default_factory=list, description="List of scripts in the project")
    recordings: List[Recording] = Field(default_factory=list, description="Recorded action sequences")
    templates: List[TemplateCapture] = Field(default_factory=list, description="List of template captures in the project")
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

    def get_recording(self, recording_id_or_name: str) -> Optional[Recording]:
        return next((r for r in self.recordings if r.id == recording_id_or_name or r.name == recording_id_or_name), None)

    def add_recording(self, name: str) -> Recording:
        if self.get_recording(name):
            raise ValueError(f"Recording '{name}' already exists")
        recording = Recording(name=name)
        self.recordings.append(recording)
        self.updated_at = datetime.now()
        return recording

    def remove_recording(self, recording_id: str) -> bool:
        recording = self.get_recording(recording_id)
        if recording is None:
            return False
        self.recordings.remove(recording)
        self.updated_at = datetime.now()
        return True

    # ── Template management helpers ───────────────────────────

    def get_template(self, name: str) -> Optional[TemplateCapture]:
        """Find a template by name."""
        for t in self.templates:
            if t.name == name:
                return t
        return None

    def add_template(self, template: TemplateCapture) -> None:
        """Add a template to the project."""
        if self.get_template(template.name):
            raise ValueError(f"Template '{template.name}' already exists in project")
        self.templates.append(template)
        self.updated_at = datetime.now()

    def remove_template(self, name: str) -> bool:
        """Remove a template by name. Returns True if removed."""
        template = self.get_template(name)
        if template is None:
            return False
        self.templates.remove(template)
        self.updated_at = datetime.now()
        return True

    def rename_template(self, old_name: str, new_name: str) -> bool:
        """Rename a template. Returns True if renamed."""
        template = self.get_template(old_name)
        if template is None or self.get_template(new_name):
            return False
        template.name = new_name
        self.updated_at = datetime.now()
        return True

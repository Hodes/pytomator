"""Presentation model and delegate for the recording timeline."""

from dataclasses import dataclass, field

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QStyledItemDelegate

from pytomator.project.models import RecordingItem


ROW_ROLE = int(Qt.ItemDataRole.UserRole)
EXECUTING_ROLE = ROW_ROLE + 1


@dataclass
class TimelineRow:
    kind: str
    timestamp: float
    title: str
    parameters: str = ""
    icon: str = ""
    color: str = "#607d8b"
    item_ids: list[str] = field(default_factory=list)
    group_key: str | None = None
    indent: bool = False
    tooltip: str = ""

    @property
    def identity(self) -> str:
        return self.group_key or (self.item_ids[0] if self.item_ids else "")


class TimelinePresenter:
    STYLES = {
        "key_down": ("Key down", "fa6s.keyboard", "#6f42c1"),
        "key_up": ("Key up", "fa6s.keyboard", "#8e63ce"),
        "mouse_button_down": ("Mouse button down", "fa6s.computer-mouse", "#1565c0"),
        "mouse_button_up": ("Mouse button up", "fa6s.computer-mouse", "#4285c5"),
        "mouse_scroll": ("Mouse scroll", "fa6s.arrows-up-down", "#0277bd"),
        "mouse_move": ("Mouse move", "fa6s.arrow-pointer", "#00838f"),
        "wait": ("Wait", "fa6s.clock", "#b26a00"),
        "comment": ("Comment", "fa6s.comment", "#607d8b"),
        "api_call": ("API call", "fa6s.code", "#2e7d32"),
    }

    def build(self, items: list[RecordingItem], expanded: set[str]) -> list[TimelineRow]:
        rows = []; index = 0
        while index < len(items):
            item = items[index]
            if item.type == "mouse_move":
                end = index
                while end < len(items) and items[end].type == "mouse_move": end += 1
                run = items[index:end]
                key = f"mouse:{run[0].id}:{run[-1].id}"
                duration = max(0.0, run[-1].timestamp - run[0].timestamp)
                rows.append(TimelineRow(
                    "mouse_group", run[0].timestamp, "Mouse path",
                    f"{len(run)} keyframes • {duration:.3f} s • "
                    f"({run[0].data['x']}, {run[0].data['y']}) → ({run[-1].data['x']}, {run[-1].data['y']})",
                    "fa6s.route", "#00838f", [value.id for value in run], key,
                ))
                if key in expanded:
                    rows.extend(self.item_row(value, indent=True, group_key=key) for value in run)
                index = end; continue
            rows.append(self.item_row(item)); index += 1
        return rows

    def item_row(self, item: RecordingItem, indent=False, group_key=None) -> TimelineRow:
        title, icon, color = self.STYLES.get(item.type, (item.type.replace("_", " ").title(), "fa6s.circle", "#607d8b"))
        return TimelineRow(item.type, item.timestamp, title, self.format_parameters(item), icon, color, [item.id], group_key, indent, self.format_tooltip(item))

    @staticmethod
    def format_parameters(item: RecordingItem) -> str:
        data = item.data
        if item.type == "comment": return data.get("text", "") or "Add a note…"
        if item.type in {"key_down", "key_up"}:
            result = f"Key: {str(data.get('key', '')).replace('_', ' ').title()}"
            modifiers = data.get("modifiers", [])
            if modifiers: result += " • Modifiers: " + " + ".join(value.title() for value in modifiers)
            return result
        if item.type in {"mouse_button_down", "mouse_button_up"}:
            return f"{str(data.get('button', 'primary')).title()} at ({data.get('x')}, {data.get('y')})"
        if item.type == "mouse_move": return f"Position: ({data.get('x')}, {data.get('y')})"
        if item.type == "mouse_scroll": return f"Vertical: {data.get('dy', 0)} • Horizontal: {data.get('dx', 0)}"
        if item.type == "wait": return f"Duration: {float(data.get('duration', 0)):.3f} s"
        if item.type == "api_call":
            args = ", ".join(f"{key}={value!r}" for key, value in data.get("arguments", {}).items())
            return f"{data.get('name', 'unknown')}({args})"
        return str(data)

    @staticmethod
    def format_tooltip(item: RecordingItem) -> str:
        data = item.data
        if item.type not in {"key_down", "key_up"}: return ""
        physical = []
        if data.get("vk") is not None: physical.append(f"VK: {data['vk']}")
        if data.get("scan_code") is not None: physical.append(f"Scan code: {data['scan_code']}")
        if data.get("extended"): physical.append("Extended key")
        if data.get("layout"): physical.append(f"Layout: {data['layout']}")
        if not physical: physical.append("Legacy textual keyboard event")
        return "\n".join(physical)


class ExecutionRowDelegate(QStyledItemDelegate):
    """Paint one continuous green execution outline across table cells."""

    def paint(self, painter: QPainter, option, index):
        super().paint(painter, option, index)
        if not index.data(EXECUTING_ROLE):
            return
        painter.save()
        painter.setPen(QPen(QColor("#20a44b"), 2))
        rect = option.rect.adjusted(1, 1, -1, -1)
        painter.drawLine(rect.topLeft(), rect.topRight())
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())
        if index.column() == 0: painter.drawLine(rect.topLeft(), rect.bottomLeft())
        span = option.widget.columnSpan(index.row(), index.column()) if hasattr(option.widget, "columnSpan") else 1
        if index.column() + span >= index.model().columnCount(): painter.drawLine(rect.topRight(), rect.bottomRight())
        painter.restore()

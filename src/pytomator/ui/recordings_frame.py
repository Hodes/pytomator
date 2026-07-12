"""Visual editor for project recordings."""

import ast
import logging
import time
import sys
from uuid import uuid4
import qtawesome as qta
from PyQt6.QtCore import pyqtSignal, QTimer, Qt
from PyQt6.QtGui import QColor, QBrush
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QComboBox, QPushButton,
    QLineEdit, QTextEdit, QDoubleSpinBox, QSpinBox, QCheckBox, QTableWidget,
    QTableWidgetItem, QMessageBox, QInputDialog, QLabel, QAbstractItemView,
    QHeaderView,
)

from pytomator.core.recording import InputRecorder, RecordingPlayer, RecordingScriptGenerator
from pytomator.core.recording.command_catalog import available_commands, validate_call
from pytomator.project.models import RecordingItem
from pytomator.config import ConfigManager
from pytomator.core.recording.mouse_path import simplify_recording_mouse_paths
from pytomator.ui.recording_timeline import (
    TimelinePresenter, ExecutionRowDelegate, ROW_ROLE, EXECUTING_ROLE,
)
from pytomator.core.recording.physical_keyboard import active_keyboard_layout


class RecordingsFrame(QWidget):
    captured = pyqtSignal(str, object)
    state_changed = pyqtSignal(str)
    playback_item = pyqtSignal(str, int, int, int, str)
    playback_error = pyqtSignal(str)

    def __init__(self, project_manager, script_runner):
        super().__init__()
        self.pm = project_manager; self.script_runner = script_runner
        self.player = RecordingPlayer(); self.recorder = None; self.current_id = None
        self._capture_session_id = None
        self._playback_progress = None
        self._execution_item_id = None
        self._last_mouse_visual_update = 0.0
        self._expanded_mouse_groups = set()
        self._timeline_rows = []
        self._timeline_presenter = TimelinePresenter()
        self._loading_properties = False
        self._property_save_timer = QTimer(self)
        self._property_save_timer.setSingleShot(True)
        self._property_save_timer.setInterval(400)
        self._property_save_timer.timeout.connect(self._save_properties)
        self.captured.connect(self._append_captured)
        self.player.on("finished", self._player_finished)
        self.player.on("paused", lambda: self.state_changed.emit("paused"))
        self.player.on("resumed", lambda: self.state_changed.emit("playing"))
        self.player.on("item_executing", self.playback_item.emit)
        self.player.on("error", self.playback_error.emit)
        self.state_changed.connect(self._apply_state)
        self.playback_item.connect(self._show_playback_item)
        self.playback_error.connect(self._error)
        self._build_ui()
        for event in ("project_loaded", "recording_added", "recording_removed", "recording_changed", "recording_items_changed"):
            self.pm.on(event, self.refresh)
        self.pm.on("project_closed", self._project_closed)
        self.refresh()

    def _build_ui(self):
        root = QVBoxLayout(self)
        top = QHBoxLayout(); self.selector = QComboBox(); self.selector.currentIndexChanged.connect(self._selected)
        top.addWidget(QLabel("Recording:")); top.addWidget(self.selector, 1)
        for text, icon, handler in (("New", "fa6s.plus", self._new), ("Delete", "fa6s.trash-can", self._delete)):
            button = QPushButton(text); button.setIcon(qta.icon(icon)); button.clicked.connect(handler); top.addWidget(button)
        root.addLayout(top)
        form = QFormLayout(); self.name = QLineEdit(); self.description = QTextEdit(); self.description.setMaximumHeight(60)
        self.hotkey = QLineEdit(); self.speed = QDoubleSpinBox(); self.speed.setRange(.1, 10); self.speed.setValue(1)
        self.repetitions = QSpinBox(); self.repetitions.setRange(1, 100000); self.loop = QCheckBox("Repeat until stopped")
        self.interval = QDoubleSpinBox(); self.interval.setRange(0, 3600); self.interval.setSuffix(" s")
        for label, widget in (("Name", self.name), ("Description", self.description), ("Hotkey", self.hotkey), ("Speed", self.speed), ("Repetitions", self.repetitions), ("Loop", self.loop), ("Cycle interval", self.interval)): form.addRow(label, widget)
        self.loop.toggled.connect(lambda checked: self.repetitions.setEnabled(not checked))
        self.loop.clicked.connect(self._on_loop_clicked)
        self.name.editingFinished.connect(self._save_properties)
        self.hotkey.editingFinished.connect(self._save_properties)
        self.description.textChanged.connect(self._schedule_property_save)
        self.speed.valueChanged.connect(self._schedule_property_save)
        self.repetitions.valueChanged.connect(self._schedule_property_save)
        self.interval.valueChanged.connect(self._schedule_property_save)
        root.addLayout(form)
        tools = QHBoxLayout()
        actions = (
            ("Record", "fa6s.circle", lambda: self.start_recording(False)),
            ("Continue", "fa6s.forward", lambda: self.start_recording(True)),
            ("Stop", "fa6s.stop", self.stop),
            ("Clear", "fa6s.eraser", self._clear),
            ("Play", "fa6s.play", self.play),
            ("Wait", "fa6s.clock", self._add_wait),
            ("Comment", "fa6s.comment", self._add_comment),
            ("API", "fa6s.code", self._add_api),
            ("Duplicate", "fa6s.copy", self._duplicate),
            ("Remove item", "fa6s.trash-can", self._remove_item),
            ("Generate script", "fa6s.file-code", self._generate),
        )
        self.action_buttons = []
        for text, icon, handler in actions:
            button = QPushButton(text)
            button.setIcon(qta.icon(icon))
            button.setToolTip(text)
            button.clicked.connect(handler)
            tools.addWidget(button)
            self.action_buttons.append(button)
            if text == "Play":
                self.play_button = button
        root.addLayout(tools)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["", "Time", "Type", "Command", "Parameters"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setItemDelegate(ExecutionRowDelegate(self.table))
        self.table.setColumnWidth(0, 30); self.table.setColumnWidth(1, 75); self.table.setColumnWidth(2, 170)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.cellDoubleClicked.connect(self._on_timeline_double_clicked)
        root.addWidget(self.table); self.status = QLabel("Stopped"); root.addWidget(self.status)

    def recording(self): return self.pm.get_recording(self.current_id) if self.current_id else None
    def _project_closed(self):
        self.stop_without_save(); self.refresh()
    def _autosave(self) -> bool:
        project = self.pm.project
        if not project or not project.settings.auto_save or self.pm.project_path is None:
            return True
        try:
            return self.pm.save_project()
        except Exception as exc:
            self._error(f"Failed to auto-save the project:\n{exc}")
            return False
    def _player_finished(self, recording_id):
        if self.player.is_running() and self.player.recording_id != recording_id:
            return
        self.state_changed.emit("stopped")
    def refresh(self, *_):
        selected = self.current_id; self.selector.blockSignals(True); self.selector.clear()
        for recording in self.pm.list_recordings(): self.selector.addItem(recording.name, recording.id)
        index = self.selector.findData(selected); self.selector.setCurrentIndex(index if index >= 0 else (0 if self.selector.count() else -1)); self.selector.blockSignals(False)
        self.current_id = self.selector.currentData(); self._load()
    def _selected(self): self.current_id = self.selector.currentData(); self._load()
    def _load(self):
        recording = self.recording(); self.setEnabled(self.pm.is_project_open)
        if not recording: self.table.setRowCount(0); return
        self._property_save_timer.stop()
        self._loading_properties = True
        self.name.setText(recording.name); self.description.setPlainText(recording.description); self.hotkey.setText(recording.hotkey or ""); self.speed.setValue(recording.speed); self.repetitions.setValue(recording.repetitions)
        self.loop.blockSignals(True)
        self.loop.setChecked(recording.loop)
        self.loop.blockSignals(False)
        self.repetitions.setEnabled(not recording.loop)
        self.interval.setValue(recording.cycle_interval)
        self._loading_properties = False
        self._render_timeline(recording)

    def _render_timeline(self, recording):
        selected = self._selected_timeline_row()
        selected_identity = selected.identity if selected else None
        scroll_value = self.table.verticalScrollBar().value()
        self.table.clearSpans(); self.table.setRowCount(0)
        self._timeline_rows = self._timeline_presenter.build(recording.sorted_items(), self._expanded_mouse_groups)
        palette = self.table.palette()
        for row_index, row_data in enumerate(self._timeline_rows):
            self.table.insertRow(row_index); self.table.setRowHeight(row_index, 32)
            marker = QTableWidgetItem(); marker.setData(ROW_ROLE, row_data)
            self.table.setItem(row_index, 0, marker)
            time_item = QTableWidgetItem(f"{row_data.timestamp:.3f}"); time_item.setData(ROW_ROLE, row_data)
            self.table.setItem(row_index, 1, time_item)
            if row_data.kind == "comment":
                comment = QTableWidgetItem(row_data.parameters)
                comment.setIcon(qta.icon(row_data.icon, color=row_data.color)); comment.setData(ROW_ROLE, row_data)
                base = palette.base().color(); accent = QColor(row_data.color)
                blended = QColor(
                    round(base.red() * .86 + accent.red() * .14),
                    round(base.green() * .86 + accent.green() * .14),
                    round(base.blue() * .86 + accent.blue() * .14),
                )
                comment.setBackground(QBrush(blended))
                comment.setToolTip(row_data.parameters); self.table.setItem(row_index, 2, comment)
                self.table.setSpan(row_index, 2, 1, 3); self.table.setRowHeight(row_index, 48)
            else:
                prefix = "▾ " if row_data.kind == "mouse_group" and row_data.group_key in self._expanded_mouse_groups else ("▸ " if row_data.kind == "mouse_group" else ("   " if row_data.indent else ""))
                type_item = QTableWidgetItem(prefix + row_data.title)
                type_item.setIcon(qta.icon(row_data.icon, color=row_data.color)); type_item.setData(ROW_ROLE, row_data)
                command_item = QTableWidgetItem(row_data.title); command_item.setData(ROW_ROLE, row_data)
                params_item = QTableWidgetItem(row_data.parameters); params_item.setData(ROW_ROLE, row_data); params_item.setToolTip(row_data.tooltip or row_data.parameters)
                self.table.setItem(row_index, 2, type_item); self.table.setItem(row_index, 3, command_item); self.table.setItem(row_index, 4, params_item)
            if row_data.identity == selected_identity: self.table.selectRow(row_index)
        self.table.verticalScrollBar().setValue(scroll_value)
        if self._execution_item_id: self._set_execution_indicator(self._execution_item_id, scroll=False)

    def _new(self):
        name, ok = QInputDialog.getText(self, "New recording", "Name:")
        if ok and name.strip():
            recording = self.pm.add_recording(name.strip())
            if not recording: QMessageBox.warning(self, "Recordings", "That name is already in use.")
            else: self.current_id = recording.id; self.refresh(); self._autosave()
    def _delete(self):
        if self.recording() and QMessageBox.question(self, "Delete recording", "Delete this recording?") == QMessageBox.StandardButton.Yes:
            self.pm.remove_recording(self.current_id); self._autosave()
    def _schedule_property_save(self, *_):
        if not self._loading_properties:
            self._property_save_timer.start()
    def _save_properties(self):
        if self._loading_properties:
            return
        recording = self.recording()
        if not recording: return
        name = self.name.text().strip()
        if not name:
            QMessageBox.warning(self, "Recordings", "The recording name cannot be empty.")
            self._load(); return
        hotkey = self.hotkey.text().strip() or None
        if hotkey:
            valid, error = self.pm.validate_hotkey(hotkey, exclude_recording=recording.id)
            if not valid: QMessageBox.warning(self, "Hotkey", error); self._load(); return
        if not self.pm.update_recording(recording.id, name=name, description=self.description.toPlainText(), hotkey=hotkey, speed=self.speed.value(), repetitions=self.repetitions.value(), loop=self.loop.isChecked(), cycle_interval=self.interval.value()): QMessageBox.warning(self, "Recordings", "The name is invalid or already in use."); self._load()
        else: self._autosave()
    def _on_loop_clicked(self, checked):
        recording = self.recording()
        if recording and self.pm.update_recording(recording.id, loop=bool(checked)):
            self._autosave()
    def start_recording(self, append=False):
        recording = self.recording()
        if not recording: return
        self.stop_without_save()
        if self.script_runner.is_running(): self.script_runner.stop()
        if not append:
            recording.items.clear(); self.pm.mark_dirty()
        offset = max((item.timestamp + item.duration for item in recording.items), default=0)
        session_id = uuid4().hex
        self._capture_session_id = session_id
        self.recorder = InputRecorder(
            lambda item, sid=session_id: self.captured.emit(sid, item),
            excluded_hotkeys=self._control_hotkeys(),
        )
        try: self.recorder.start(offset)
        except Exception as exc:
            self._invalidate_capture_session()
            self.state_changed.emit("stopped")
            self._error(str(exc)); return
        self.state_changed.emit("recording")
    def _invalidate_capture_session(self):
        self._capture_session_id = None
        recorder, self.recorder = self.recorder, None
        if recorder:
            recorder.stop()
        return recorder is not None
    def _control_hotkeys(self):
        value = ConfigManager.get_instance().config.get("hotkeys", {}).get("toggle_recording")
        return [value] if value else []
    def _simplify_captured_mouse(self):
        recording = self.recording()
        if not recording:
            return
        simplified, original_count = simplify_recording_mouse_paths(recording.sorted_items())
        resulting_count = sum(item.type == "mouse_move" for item in simplified)
        if original_count:
            recording.items = simplified; self.pm.mark_dirty()
            self.pm.emit("recording_items_changed", recording.id)
            duration = max((item.timestamp for item in simplified), default=0.0)
            logging.getLogger(__name__).info(
                "Mouse capture simplified from %s events to %s keyframes (%.3fs)",
                original_count, resulting_count, duration,
            )
    def stop(self):
        was_recording = self._invalidate_capture_session()
        if was_recording:
            self._simplify_captured_mouse()
        if self.player.is_running(): self.player.stop()
        if self.script_runner.is_running(): self.script_runner.stop()
        self.state_changed.emit("stopped"); self.refresh(); self._autosave()
    def stop_without_save(self):
        self._invalidate_capture_session()
        if self.player.is_running(): self.player.stop()
        if self.script_runner.is_running(): self.script_runner.stop()
        self.state_changed.emit("stopped")
    def play(self):
        recording = self.recording()
        if not recording: return
        self._invalidate_capture_session()
        if not self._autosave(): return
        if self.script_runner.is_running(): self.script_runner.stop()
        previous_state = self.player.state
        if (previous_state == "stopped" or self.player.recording_id != recording.id) and not self._confirm_keyboard_layout(recording): return
        if self.player.toggle(recording):
            if previous_state == "paused" and self.player.state == "playing":
                self.state_changed.emit("playing")
            elif previous_state == "playing" and self.player.state == "paused":
                self.state_changed.emit("paused")
            elif self.player.state == "playing":
                self.state_changed.emit("playing")
    def _confirm_keyboard_layout(self, recording):
        if sys.platform != "win32": return True
        recorded = {item.data.get("layout") for item in recording.items if item.type.startswith("key_") and item.data.get("layout")}
        current = active_keyboard_layout()
        if not recorded or current in recorded: return True
        layouts = ", ".join(sorted(recorded))
        return QMessageBox.question(
            self, "Keyboard layout mismatch",
            f"This recording used keyboard layout {layouts}, but the active layout is {current}.\n"
            "Physical keys may produce different characters. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes
    def play_by_id(self, recording_id): self.current_id = recording_id; self.refresh(); self.play()
    def toggle_recording(self): self.stop() if self.recorder else self.start_recording(True)
    def stop_for_script(self):
        self.stop()
        return not self.player.is_running() and self.recorder is None
    def _append_captured(self, session_id, item):
        if session_id != self._capture_session_id or self.recorder is None:
            return
        if self.current_id:
            self.pm.add_recording_item(self.current_id, item)
    def _selected_timeline_row(self):
        row = self.table.currentRow()
        return self._timeline_rows[row] if 0 <= row < len(self._timeline_rows) else None
    def _on_timeline_double_clicked(self, row, _column):
        row_data = self._timeline_rows[row] if 0 <= row < len(self._timeline_rows) else None
        if not row_data: return
        if row_data.kind == "mouse_group":
            if row_data.group_key in self._expanded_mouse_groups: self._expanded_mouse_groups.remove(row_data.group_key)
            else: self._expanded_mouse_groups.add(row_data.group_key)
            self._render_timeline(self.recording()); return
        if row_data.kind == "comment":
            item = self._items_by_ids(row_data.item_ids)[0]
            text, ok = QInputDialog.getMultiLineText(self, "Edit comment", "Text:", item.data.get("text", ""))
            if ok:
                item.data["text"] = text; self.pm.mark_dirty(); self.pm.emit("recording_items_changed", self.current_id); self._autosave()
    def _items_by_ids(self, item_ids):
        recording = self.recording()
        by_id = {item.id: item for item in recording.items} if recording else {}
        return [by_id[item_id] for item_id in item_ids if item_id in by_id]
    def _insert_time(self):
        recording = self.recording(); row_data = self._selected_timeline_row()
        if not recording or not recording.items: return 0.0
        selected = self._items_by_ids(row_data.item_ids) if row_data else []
        return max((item.timestamp + item.duration for item in selected), default=max(i.timestamp + i.duration for i in recording.items))
    def _add_wait(self):
        duration, ok = QInputDialog.getDouble(self, "Wait", "Duration (s):", 1, 0, 3600, 3)
        if ok: self._insert(RecordingItem(type="wait", timestamp=self._insert_time(), data={"duration": duration}), shift=duration)
    def _add_comment(self):
        text, ok = QInputDialog.getText(self, "Comment", "Text:")
        if ok: self._insert_comment(text)
    def _insert_comment(self, text):
        recording = self.recording()
        if not recording:
            return
        row_data = self._selected_timeline_row()
        if not row_data or not row_data.item_ids:
            self._insert(RecordingItem(
                type="comment", timestamp=self._insert_time(), data={"text": text}
            ))
            return
        target_id = row_data.item_ids[0]
        target_index = next(
            (index for index, item in enumerate(recording.items) if item.id == target_id),
            None,
        )
        if target_index is None:
            return
        target = recording.items[target_index]
        recording.items.insert(target_index, RecordingItem(
            type="comment", timestamp=target.timestamp, data={"text": text}
        ))
        self.pm.mark_dirty()
        self.pm.emit("recording_items_changed", recording.id)
        self._autosave()
    def _add_api(self):
        commands = available_commands(); names = [c.name for c in commands]; name, ok = QInputDialog.getItem(self, "API command", "Command:", names, editable=False)
        if not ok: return
        raw, ok = QInputDialog.getMultiLineText(self, "Arguments", "Python/JSON argument dictionary:", "{}")
        if not ok: return
        try: arguments = ast.literal_eval(raw)
        except Exception as exc: self._error(str(exc)); return
        valid, error = validate_call(name, arguments)
        if not valid: self._error(error); return
        self._insert(RecordingItem(type="api_call", timestamp=self._insert_time(), data={"name": name, "arguments": arguments}))
    def _insert(self, item, shift=0):
        recording = self.recording()
        if shift:
            for existing in recording.items:
                if existing.timestamp > item.timestamp: existing.timestamp += shift
        self.pm.add_recording_item(recording.id, item)
        self._autosave()
    def _selected_item(self):
        row_data = self._selected_timeline_row(); items = self._items_by_ids(row_data.item_ids) if row_data else []
        return items[0] if len(items) == 1 else None
    def _remove_item(self):
        row_data = self._selected_timeline_row()
        if not row_data: return
        if len(row_data.item_ids) > 1 and QMessageBox.question(self, "Remove mouse path", f"Remove all {len(row_data.item_ids)} keyframes?") != QMessageBox.StandardButton.Yes: return
        recording = self.recording(); ids = set(row_data.item_ids)
        recording.items = [item for item in recording.items if item.id not in ids]
        self.pm.mark_dirty(); self.pm.emit("recording_items_changed", recording.id); self._autosave()
    def _duplicate(self):
        row_data = self._selected_timeline_row()
        if not row_data: return
        items = self._items_by_ids(row_data.item_ids); recording = self.recording()
        offset = max((item.timestamp for item in items), default=0) - min((item.timestamp for item in items), default=0) + .001
        for item in items:
            clone = item.model_copy(deep=True); clone.id = RecordingItem(type=item.type).id; clone.timestamp += offset; recording.items.append(clone)
        recording.items.sort(key=lambda item: item.timestamp); self.pm.mark_dirty(); self.pm.emit("recording_items_changed", recording.id); self._autosave()
    def _clear(self):
        recording = self.recording()
        if not recording:
            return
        self.stop()
        if QMessageBox.question(self, "Clear recording", "Delete all commands?") == QMessageBox.StandardButton.Yes:
            recording.items.clear(); self.pm.mark_dirty(); self.pm.emit("recording_items_changed", recording.id); self._autosave()
    def _generate(self):
        recording = self.recording()
        if not recording: return
        name, ok = QInputDialog.getText(self, "Generate script", "Script name:", text=f"{recording.name} script")
        if ok and name.strip():
            script = self.pm.add_script(name.strip(), RecordingScriptGenerator().generate(recording))
            if not script: QMessageBox.warning(self, "Script", "That name is already in use.")
            else: self._autosave()
    def _show_playback_item(self, recording_id, cycle, index, total, item_id):
        if recording_id != self.current_id:
            return
        item = next((value for value in self.recording().items if value.id == item_id), None)
        now = time.monotonic()
        if item and item.type == "mouse_move" and now - self._last_mouse_visual_update < 1 / 30:
            return
        if item and item.type == "mouse_move": self._last_mouse_visual_update = now
        self._playback_progress = (cycle, index, total, item_id)
        self._execution_item_id = item_id
        self._set_execution_indicator(item_id)
        self.status.setText(f"Playing — cycle {cycle} — command {index + 1}/{total}")

    def _visible_row_for_item(self, item_id):
        exact = next((i for i, row in enumerate(self._timeline_rows) if len(row.item_ids) == 1 and row.item_ids[0] == item_id), None)
        if exact is not None: return exact
        return next((i for i, row in enumerate(self._timeline_rows) if item_id in row.item_ids), None)

    def _clear_execution_indicator(self):
        self._execution_item_id = None
        for row in range(self.table.rowCount()):
            for column in range(self.table.columnCount()):
                cell = self.table.item(row, column)
                if cell:
                    cell.setData(EXECUTING_ROLE, False)
                    if column == 0: cell.setText("")
        self.table.viewport().update()

    def _set_execution_indicator(self, item_id, scroll=True):
        for row in range(self.table.rowCount()):
            for column in range(self.table.columnCount()):
                cell = self.table.item(row, column)
                if cell:
                    cell.setData(EXECUTING_ROLE, False)
                    if column == 0: cell.setText("")
        row = self._visible_row_for_item(item_id)
        if row is None: return
        marker = self.table.item(row, 0); marker.setText("➜"); marker.setForeground(QBrush(QColor("#20a44b")))
        for column in range(self.table.columnCount()):
            cell = self.table.item(row, column)
            if cell: cell.setData(EXECUTING_ROLE, True)
        if scroll: self.table.scrollToItem(self.table.item(row, 0))
        self.table.viewport().update()

    def _apply_state(self, state):
        self.table.setStyleSheet(
            "QTableWidget { border: 3px solid #d71920; }"
            if state == "recording" else ""
        )
        if state == "playing":
            self.play_button.setText("Pause"); self.play_button.setIcon(qta.icon("fa6s.pause"))
        elif state == "paused":
            self.play_button.setText("Resume"); self.play_button.setIcon(qta.icon("fa6s.play"))
        else:
            self.play_button.setText("Play"); self.play_button.setIcon(qta.icon("fa6s.play"))
        if state == "paused" and self._playback_progress:
            self._clear_execution_indicator()
            cycle, index, total, _ = self._playback_progress
            self.status.setText(f"Paused — cycle {cycle} — command {index + 1}/{total}")
        elif state == "playing" and self._playback_progress:
            cycle, index, total, item_id = self._playback_progress
            self._execution_item_id = item_id; self._set_execution_indicator(item_id)
            self.status.setText(f"Playing — cycle {cycle} — command {index + 1}/{total}")
        elif state == "recording":
            self._clear_execution_indicator()
            self.status.setText("Recording…")
        elif state == "stopped":
            self._clear_execution_indicator()
            self.status.setText("Stopped")
            self._playback_progress = None
            self.table.clearSelection()
    def _error(self, message): QMessageBox.critical(self, "Recordings", message)

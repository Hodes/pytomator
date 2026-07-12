import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from unittest.mock import MagicMock

from PyQt6.QtWidgets import QApplication

from pytomator.core.recording.command_catalog import validate_call
from pytomator.core.recording.player import RecordingPlayer
from pytomator.core.recording.script_generator import RecordingScriptGenerator
from pytomator.project.models import Project, Recording, RecordingItem
from pytomator.project.storage import ProjectStorage
from pytomator.project.manager import ProjectManager
from pytomator.ui.recordings_frame import RecordingsFrame
from pytomator.ui.recording_timeline import TimelinePresenter, EXECUTING_ROLE
from pytomator.core.recording.recorder import InputRecorder
from pytomator.core.recording.mouse_path import simplify_mouse_run, interpolate_position
from pytomator.core.automator import api as automator_api
from pytomator.core.recording import physical_keyboard


class RecordingModelTests(unittest.TestCase):
    class FakeKey:
        def __init__(self, value, vk=None): self.value = value; self.vk = vk
        def __str__(self): return self.value

    def test_modifier_snapshots_preserve_ctrl_c_and_ignore_unmatched_release(self):
        captured = []; recorder = InputRecorder(captured.append, excluded_hotkeys=["ctrl+shift+f8"]); recorder._ignore_until = 0
        with patch("pytomator.core.recording.recorder.physical_metadata", return_value={"vk": 1, "scan_code": 2, "layout": "test"}):
            recorder._key("key_up", self.FakeKey("Key.shift"))
            recorder._key("key_down", self.FakeKey("Key.ctrl_l"))
            recorder._key("key_down", self.FakeKey("c"))
            recorder._key("key_up", self.FakeKey("c"))
            recorder._key("key_up", self.FakeKey("Key.ctrl_l"))
        self.assertEqual([item.data["modifiers"] for item in captured], [["ctrl"], ["ctrl"], ["ctrl"], []])
        self.assertEqual([item.data["key"] for item in captured], ["ctrl_l", "c", "c", "ctrl_l"])

    def test_metadata_failure_does_not_stop_keyboard_capture(self):
        captured = []; recorder = InputRecorder(captured.append); recorder._ignore_until = 0
        with patch("pytomator.core.recording.recorder.physical_metadata", side_effect=TypeError("metadata")):
            recorder._key("key_down", self.FakeKey("a"))
            recorder._key("key_up", self.FakeKey("a"))
        self.assertEqual([item.type for item in captured], ["key_down", "key_up"])
        self.assertEqual(captured[0].data["key"], "a")

    def test_altgr_snapshot_does_not_duplicate_ctrl_alt(self):
        recorder = InputRecorder(lambda _: None); recorder._pressed = {"ctrl", "alt", "altgr"}
        self.assertEqual(recorder._logical_modifiers(), ["altgr"])

    def test_only_exact_recording_hotkey_is_filtered(self):
        captured = []; recorder = InputRecorder(captured.append, excluded_hotkeys=["ctrl+shift+f8"]); recorder._ignore_until = 0
        with patch("pytomator.core.recording.recorder.physical_metadata", return_value={}):
            for value in ("Key.alt", "Key.ctrl_l", "Key.shift", "Key.f8"):
                recorder._key("key_down", self.FakeKey(value))
            for value in ("Key.f8", "Key.shift", "Key.ctrl_l", "Key.alt"):
                recorder._key("key_up", self.FakeKey(value))
        self.assertEqual(len(captured), 8)

    def test_timeline_presenter_formats_comment_and_mouse_group(self):
        comment = RecordingItem(type="comment", timestamp=.5, data={"text": "Section"})
        moves = [
            RecordingItem(type="mouse_move", timestamp=1, data={"x": 10, "y": 20}),
            RecordingItem(type="mouse_move", timestamp=1.2, data={"x": 30, "y": 40}),
        ]
        presenter = TimelinePresenter(); rows = presenter.build([comment, *moves], set())
        self.assertEqual(rows[0].kind, "comment")
        self.assertEqual(rows[0].parameters, "Section")
        self.assertEqual(rows[1].kind, "mouse_group")
        self.assertIn("2 keyframes", rows[1].parameters)
        self.assertEqual(rows[1].item_ids, [moves[0].id, moves[1].id])
        expanded = presenter.build([comment, *moves], {rows[1].group_key})
        self.assertEqual(len(expanded), 4)

    def test_recording_changes_mark_project_dirty_and_save_clears_it(self):
        manager = ProjectManager()
        manager.create_project("demo")
        self.assertTrue(manager.is_dirty)
        with tempfile.TemporaryDirectory() as directory:
            self.assertTrue(manager.save_project(Path(directory) / "demo.pytom"))
            self.assertFalse(manager.is_dirty)
            recording = manager.add_recording("Login")
            self.assertTrue(manager.is_dirty)
            self.assertTrue(manager.save_project())
            self.assertFalse(manager.is_dirty)
        self.assertIsNotNone(recording)

    def test_legacy_project_defaults_to_empty_recordings(self):
        project = Project.model_validate({"name": "old"})
        self.assertEqual(project.recordings, [])

    def test_recording_round_trip(self):
        project = Project(name="demo")
        recording = project.add_recording("Login")
        recording.loop = True
        recording.items.append(RecordingItem(type="comment", timestamp=.5, data={"text": "hello"}))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "demo.pytom"
            storage = ProjectStorage(); storage.save(project, path)
            loaded = storage.load(path)
        self.assertTrue(loaded.recordings[0].loop)
        self.assertEqual(loaded.recordings[0].items[0].data["text"], "hello")

    def test_api_catalog_rejects_unknown_and_bad_arguments(self):
        self.assertFalse(validate_call("reload_script", {})[0])
        self.assertFalse(validate_call("press", {"unknown": 1})[0])
        self.assertTrue(validate_call("press", {"key": "a"})[0])

    def test_script_generator_emits_loop_comments_and_wait(self):
        recording = Recording(name="demo", loop=True, items=[
            RecordingItem(type="comment", data={"text": "start"}),
            RecordingItem(type="key_down", timestamp=1, data={"key": "a"}),
        ])
        code = RecordingScriptGenerator().generate(recording)
        self.assertIn("while not should_stop():", code)
        self.assertIn("# start", code)
        self.assertIn("wait(1)", code)
        compile(code, "<generated>", "exec")

    def test_script_generator_compacts_simple_hotkey(self):
        events = [
            RecordingItem(type="key_down", timestamp=0, data={"key": "ctrl_l"}),
            RecordingItem(type="key_down", timestamp=.02, data={"key": "c"}),
            RecordingItem(type="key_up", timestamp=.04, data={"key": "c"}),
            RecordingItem(type="key_up", timestamp=.06, data={"key": "ctrl_l"}),
        ]
        code = RecordingScriptGenerator().generate(Recording(name="copy", items=events))
        self.assertIn("hotkey('ctrl', 'c')", code)

    def test_script_generator_uses_physical_api_for_special_key(self):
        event = RecordingItem(type="key_down", data={"key": "ç", "vk": 186, "scan_code": 39, "extended": False})
        code = RecordingScriptGenerator().generate(Recording(name="special", items=[event]))
        self.assertIn("key_down_physical(scan_code=39, vk=186", code)

    def test_hotkey_releases_remaining_modifiers_after_release_error(self):
        with patch.object(automator_api, "key_down") as down, \
             patch.object(automator_api, "key_up", side_effect=[RuntimeError("release"), None]) as up:
            with self.assertRaises(RuntimeError): automator_api.hotkey("ctrl", "c")
        self.assertEqual(down.call_count, 2)
        self.assertEqual(up.call_count, 2)

    @unittest.skipUnless(physical_keyboard.sys.platform == "win32", "Windows physical keyboard only")
    def test_physical_key_flags_include_scan_extended_and_keyup(self):
        flags = physical_keyboard.physical_key_flags(scan_code=72, extended=True, key_up=True)
        self.assertTrue(flags & physical_keyboard.KEYEVENTF_SCANCODE)
        self.assertTrue(flags & physical_keyboard.KEYEVENTF_EXTENDEDKEY)
        self.assertTrue(flags & physical_keyboard.KEYEVENTF_KEYUP)
        expected_size = 40 if physical_keyboard.ctypes.sizeof(physical_keyboard.ctypes.c_void_p) == 8 else 28
        self.assertEqual(physical_keyboard.ctypes.sizeof(physical_keyboard.INPUT), expected_size)

    def test_mouse_path_preserves_square_corners_and_timestamps(self):
        points = [(0, 0), (50, 0), (100, 0), (100, 50), (100, 100),
                  (50, 100), (0, 100), (0, 50), (0, 0)]
        items = [RecordingItem(type="mouse_move", timestamp=i * .025,
                               data={"x": x, "y": y}) for i, (x, y) in enumerate(points)]
        simplified = simplify_mouse_run(items, max_time_gap=1)
        coords = {(item.data["x"], item.data["y"]) for item in simplified}
        self.assertTrue({(0, 0), (100, 0), (100, 100), (0, 100)}.issubset(coords))
        self.assertEqual(simplified[0].timestamp, items[0].timestamp)
        self.assertEqual(simplified[-1].timestamp, items[-1].timestamp)
        self.assertEqual(interpolate_position(items, .0125), (25, 0))

    def test_control_hotkey_chord_is_not_captured(self):
        captured = []
        recorder = InputRecorder(captured.append, excluded_hotkeys=["ctrl+shift+f8"])
        recorder._ignore_until = 0
        class Key:
            def __init__(self, value): self.value = value
            def __str__(self): return self.value
        for value in ("Key.ctrl_l", "Key.shift", "Key.f8"):
            recorder._key("key_down", Key(value))
        for value in ("Key.f8", "Key.shift", "Key.ctrl_l"):
            recorder._key("key_up", Key(value))
        self.assertEqual(captured, [])


class RecordingPlayerTests(unittest.TestCase):
    def test_player_uses_physical_keyboard_metadata_not_modifier_snapshot(self):
        player = RecordingPlayer()
        item = RecordingItem(type="key_down", data={"key": "ç", "vk": 186, "scan_code": 39,
                                                      "extended": False, "modifiers": ["shift"]})
        with patch("pytomator.core.recording.player.api.key_down_physical") as physical, \
             patch("pytomator.core.recording.player.api.key_down") as textual:
            player._execute_item(item, 1)
        physical.assert_called_once_with(39, 186, False)
        textual.assert_not_called()
    def test_global_input_state_release_is_idempotent(self):
        automator_api._pressed_keys.add("ctrl")
        automator_api._pressed_mouse_buttons.add(("primary", "standard"))
        def release_key(key): automator_api._pressed_keys.discard(key)
        def release_button(button, backend=None):
            automator_api._pressed_mouse_buttons.discard((button, backend))
        with patch.object(automator_api, "key_up", side_effect=release_key) as key_up, \
             patch.object(automator_api, "mouse_up", side_effect=release_button) as mouse_up:
            automator_api.release_all_inputs()
            automator_api.release_all_inputs()
        key_up.assert_called_once_with("ctrl")
        mouse_up.assert_called_once_with("primary", backend="standard")
        self.assertEqual(automator_api._pressed_keys, set())
        self.assertEqual(automator_api._pressed_mouse_buttons, set())

    def test_orphan_key_downs_are_ignored(self):
        orphan = RecordingItem(type="key_down", data={"key": "ctrl_l"})
        valid_down = RecordingItem(type="key_down", timestamp=.1, data={"key": "a"})
        valid_up = RecordingItem(type="key_up", timestamp=.2, data={"key": "a"})
        filtered = RecordingPlayer._without_orphan_key_downs([orphan, valid_down, valid_up])
        self.assertEqual(filtered, [valid_down, valid_up])

    def test_cycle_boundary_releases_held_inputs(self):
        recording = Recording(name="cycles", repetitions=2, items=[
            RecordingItem(type="comment"),
        ])
        player = RecordingPlayer()
        def hold_during_cycle(*_):
            player._keys.add("a")
        with patch.object(player, "_execute_item", side_effect=hold_during_cycle), \
             patch("pytomator.core.recording.player.api.key_up") as up:
            player.start(recording); player._thread.join(timeout=1)
        self.assertEqual(up.call_count, 2)

    def test_comment_is_noop_and_key_is_released(self):
        player = RecordingPlayer()
        with patch("pytomator.core.recording.player.api.key_down") as down, patch("pytomator.core.recording.player.api.key_up") as up:
            player._execute_item(RecordingItem(type="comment"), 1)
            player._execute_item(RecordingItem(type="key_down", data={"key": "a"}), 1)
            player._release_inputs()
        down.assert_called_once_with("a")
        up.assert_called_once_with("a")

    def test_same_recording_toggle_pauses_and_resumes(self):
        recording = Recording(name="demo", loop=True, items=[
            RecordingItem(type="comment", timestamp=10),
        ])
        player = RecordingPlayer()
        self.assertTrue(player.toggle(recording))
        self.assertEqual(player.state, "playing")
        self.assertTrue(player.toggle(recording))
        self.assertEqual(player.state, "paused")
        self.assertTrue(player.toggle(recording))
        self.assertEqual(player.state, "playing")
        player.stop()
        self.assertEqual(player.state, "stopped")
        self.assertTrue(recording.loop)

    def test_player_emits_current_item_progress(self):
        recording = Recording(name="demo", items=[RecordingItem(type="comment")])
        progress = []
        player = RecordingPlayer(); player.on("item_executing", lambda *args: progress.append(args))
        player.start(recording)
        player._thread.join(timeout=1)
        self.assertEqual(progress[0][0], recording.id)
        self.assertEqual(progress[0][2:4], (0, 1))

    def test_mouse_path_uses_recorded_duration_without_library_pause(self):
        recording = Recording(name="path", items=[
            RecordingItem(type="mouse_move", timestamp=0, data={"x": 0, "y": 0}),
            RecordingItem(type="mouse_move", timestamp=.08, data={"x": 80, "y": 0}),
        ])
        player = RecordingPlayer()
        started = time.monotonic()
        with patch("pytomator.core.recording.player.api.move_to") as move:
            player.start(recording); player._thread.join(timeout=1)
        elapsed = time.monotonic() - started
        self.assertLess(elapsed, .25)
        self.assertGreaterEqual(move.call_count, 2)


class RecordingsFrameCaptureSessionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.manager = ProjectManager(); self.manager.create_project("demo")
        self.recording = self.manager.add_recording("capture")
        self.runner = MagicMock(); self.runner.is_running.return_value = False
        self.frame = RecordingsFrame(self.manager, self.runner)
        self.frame.current_id = self.recording.id

    def test_stale_capture_event_is_discarded(self):
        self.frame._capture_session_id = "current"
        self.frame.recorder = object()
        self.frame._append_captured("stale", RecordingItem(type="comment"))
        self.assertEqual(self.recording.items, [])

        self.frame._append_captured("current", RecordingItem(type="comment"))
        self.assertEqual(len(self.recording.items), 1)

    def test_stop_invalidates_session_and_stops_script(self):
        recorder = MagicMock(); self.frame.recorder = recorder
        self.frame._capture_session_id = "current"
        self.runner.is_running.return_value = True
        self.frame.stop_without_save()
        self.assertIsNone(self.frame._capture_session_id)
        self.assertIsNone(self.frame.recorder)
        recorder.stop.assert_called_once()
        self.runner.stop.assert_called_once()

    def test_execution_indicator_does_not_change_selection(self):
        first = RecordingItem(type="comment", data={"text": "one"})
        second = RecordingItem(type="wait", timestamp=1, data={"duration": 1})
        self.recording.items = [first, second]; self.frame.refresh()
        self.frame.table.selectRow(0)
        self.frame._set_execution_indicator(second.id, scroll=False)
        self.assertEqual(self.frame.table.currentRow(), 0)
        self.assertTrue(self.frame.table.item(1, 0).data(EXECUTING_ROLE))
        self.assertFalse(bool(self.frame.table.item(0, 0).data(EXECUTING_ROLE)))

    def test_player_errors_are_forwarded_through_qt_signal(self):
        received = []
        self.frame.playback_error.connect(received.append)
        with patch("pytomator.ui.recordings_frame.QMessageBox.critical"):
            self.frame.player.emit("error", "playback failed")
        self.assertEqual(received, ["playback failed"])

    def test_comment_is_inserted_before_selected_regular_item(self):
        wait = RecordingItem(type="wait", timestamp=2, data={"duration": 1})
        self.recording.items = [wait]; self.frame.refresh(); self.frame.table.selectRow(0)
        self.frame._insert_comment("before")
        self.assertEqual([item.type for item in self.recording.items], ["comment", "wait"])
        self.assertEqual(self.recording.items[0].timestamp, wait.timestamp)

    def test_comment_is_inserted_before_selected_mouse_group(self):
        moves = [
            RecordingItem(type="mouse_move", timestamp=1, data={"x": 1, "y": 1}),
            RecordingItem(type="mouse_move", timestamp=2, data={"x": 2, "y": 2}),
        ]
        move_ids = [item.id for item in moves]
        self.recording.items = moves; self.frame.refresh(); self.frame.table.selectRow(0)
        self.frame._insert_comment("path")
        self.assertEqual(self.recording.items[0].type, "comment")
        self.assertEqual([item.id for item in self.recording.items[1:]], move_ids)

    def test_comment_is_inserted_before_selected_expanded_keyframe(self):
        moves = [
            RecordingItem(type="mouse_move", timestamp=1, data={"x": 1, "y": 1}),
            RecordingItem(type="mouse_move", timestamp=2, data={"x": 2, "y": 2}),
        ]
        self.recording.items = moves; self.frame.refresh()
        group_key = self.frame._timeline_rows[0].group_key
        self.frame._expanded_mouse_groups.add(group_key); self.frame._render_timeline(self.recording)
        self.frame.table.selectRow(2)  # group, first child, second child
        self.frame._insert_comment("keyframe")
        self.assertEqual([item.type for item in self.recording.items], ["mouse_move", "comment", "mouse_move"])
        self.assertEqual(self.recording.items[1].timestamp, moves[1].timestamp)

    def test_comment_without_selection_is_appended(self):
        wait = RecordingItem(type="wait", timestamp=2, data={"duration": 1})
        self.recording.items = [wait]; self.frame.refresh(); self.frame.table.clearSelection()
        self.frame._insert_comment("last")
        self.assertEqual([item.type for item in self.recording.items], ["wait", "comment"])


if __name__ == "__main__":
    unittest.main()

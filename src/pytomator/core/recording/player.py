"""Interruptible playback scheduler for recordings."""

import threading
import time
import logging

from pytomator.core.events import EventEmitter
from pytomator.core.global_interruption_controller import GlobalInterruptionController
from pytomator.core.automator import api
from pytomator.project.models import Recording, RecordingItem
from .command_catalog import execute
from .mouse_path import interpolate_position, simplify_mouse_run


class RecordingPlayer(EventEmitter):
    def __init__(self):
        super().__init__()
        self._state = "stopped"
        self._thread: threading.Thread | None = None
        self._condition = threading.Condition()
        self._paused_total = 0.0
        self._recording_id: str | None = None
        self._keys: set[str] = set()
        self._buttons: set[str] = set()

    def is_running(self) -> bool:
        return self._state in {"playing", "paused", "stopping"}

    @property
    def state(self) -> str:
        return self._state

    @property
    def recording_id(self) -> str | None:
        return self._recording_id

    def start(self, recording: Recording) -> bool:
        if self.is_running() or not recording.items:
            return False
        api.release_all_inputs()
        GlobalInterruptionController.clear_global_interruption()
        self._state = "playing"
        self._recording_id = recording.id
        self._paused_total = 0.0
        self._thread = threading.Thread(target=self._run, args=(recording.model_copy(deep=True),), daemon=True)
        self._thread.start()
        self.emit("started")
        return True

    def stop(self):
        if not self.is_running():
            return
        self.emit("stopping")
        self._state = "stopping"
        GlobalInterruptionController.request_global_interruption()
        with self._condition:
            self._condition.notify_all()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=1.0)

    def pause(self) -> bool:
        if self._state != "playing":
            return False
        self._state = "paused"
        self._release_inputs()
        self.emit("paused")
        return True

    def resume(self) -> bool:
        if self._state != "paused":
            return False
        self._state = "playing"
        with self._condition:
            self._condition.notify_all()
        self.emit("resumed")
        return True

    def toggle(self, recording: Recording) -> bool:
        if self.recording_id == recording.id and self._state == "playing":
            return self.pause()
        if self.recording_id == recording.id and self._state == "paused":
            return self.resume()
        if self.is_running():
            self.stop()
        return self.start(recording)

    def _wait_while_paused(self) -> bool:
        if self._state != "paused":
            return self._state == "playing"
        paused_at = time.monotonic()
        with self._condition:
            while self._state == "paused" and not GlobalInterruptionController.is_global_interruption_requested():
                self._condition.wait(timeout=0.05)
        self._paused_total += time.monotonic() - paused_at
        return self._state == "playing"

    def _wait_until(self, deadline: float) -> bool:
        while self.is_running() and not GlobalInterruptionController.is_global_interruption_requested():
            if self._state == "paused":
                paused_at = time.monotonic()
                if not self._wait_while_paused():
                    return False
                deadline += time.monotonic() - paused_at
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return True
            time.sleep(min(0.02, remaining))
        return False

    def _run(self, recording: Recording):
        try:
            cycle = 0
            items = self._without_orphan_key_downs(recording.sorted_items())
            while self._state in {"playing", "paused"} and (recording.loop or cycle < recording.repetitions):
                api.release_all_inputs()
                cycle += 1
                self.emit("cycle", cycle)
                started = time.monotonic()
                cycle_pause_base = self._paused_total
                index = 0
                while index < len(items):
                    item = items[index]
                    if item.type == "mouse_move":
                        end = index
                        while end < len(items) and items[end].type == "mouse_move":
                            end += 1
                        path = simplify_mouse_run(items[index:end])
                        if not self._execute_mouse_path(
                            path, recording, cycle, index, len(items),
                            started, cycle_pause_base,
                        ):
                            return
                        index = end
                        continue
                    target = started + item.timestamp / recording.speed + (self._paused_total - cycle_pause_base)
                    if not self._wait_until(target):
                        return
                    self.emit("item_executing", recording.id, cycle, index, len(items), item.id)
                    self._execute_item(item, recording.speed)
                    index += 1
                # A recording cycle is an isolation boundary. Never carry held
                # input into the next iteration or it may alter global hotkeys.
                self._release_inputs()
                api.release_all_inputs()
                if recording.cycle_interval and (recording.loop or cycle < recording.repetitions):
                    if not self._wait_until(time.monotonic() + recording.cycle_interval / recording.speed):
                        return
        except Exception as exc:
            self.emit("error", str(exc))
        finally:
            self._release_inputs()
            api.release_all_inputs()
            self._state = "stopped"
            self._recording_id = None
            GlobalInterruptionController.clear_global_interruption()
            self.emit("finished", recording.id)

    @staticmethod
    def _without_orphan_key_downs(items: list[RecordingItem]) -> list[RecordingItem]:
        """Ignore legacy key-down events that have no matching key-up."""
        available_ups: dict[str, int] = {}
        orphan_ids: set[str] = set()
        for item in reversed(items):
            if item.type not in {"key_down", "key_up"}:
                continue
            key = str(item.data.get("key", "")).lower()
            if item.type == "key_up":
                available_ups[key] = available_ups.get(key, 0) + 1
            elif available_ups.get(key, 0):
                available_ups[key] -= 1
            else:
                orphan_ids.add(item.id)
        if orphan_ids:
            logging.getLogger(__name__).warning(
                "Ignoring %s orphan key-down event(s) during recording playback",
                len(orphan_ids),
            )
        return [item for item in items if item.id not in orphan_ids]

    def _execute_mouse_path(self, path, recording, cycle, start_index, total,
                            cycle_started, cycle_pause_base) -> bool:
        first, last = path[0].timestamp, path[-1].timestamp
        recording_step = recording.speed / 120.0
        timestamp = first
        while timestamp < last:
            target = cycle_started + timestamp / recording.speed + (self._paused_total - cycle_pause_base)
            if not self._wait_until(target):
                return False
            x, y = interpolate_position(path, timestamp)
            api.move_to(x, y, duration=0)
            nearest = min(range(len(path)), key=lambda i: abs(path[i].timestamp - timestamp))
            self.emit("item_executing", recording.id, cycle, start_index + nearest, total, path[nearest].id)
            timestamp += recording_step
            elapsed_recording = max(
                first,
                (time.monotonic() - cycle_started - (self._paused_total - cycle_pause_base)) * recording.speed,
            )
            if elapsed_recording > timestamp:
                timestamp = elapsed_recording
        target = cycle_started + last / recording.speed + (self._paused_total - cycle_pause_base)
        if not self._wait_until(target):
            return False
        x, y = interpolate_position(path, last)
        api.move_to(x, y, duration=0)
        self.emit("item_executing", recording.id, cycle, start_index + len(path) - 1, total, path[-1].id)
        return True

    def _execute_item(self, item: RecordingItem, speed: float):
        data = item.data
        if item.type == "comment":
            return
        if item.type == "wait":
            self._wait_until(time.monotonic() + float(data.get("duration", 0)) / speed)
        elif item.type == "key_down":
            api.key_down(data["key"]); self._keys.add(data["key"])
        elif item.type == "key_up":
            api.key_up(data["key"]); self._keys.discard(data["key"])
        elif item.type == "mouse_move":
            api.move_to(data["x"], data["y"], duration=float(data.get("duration", 0)) / speed)
        elif item.type == "mouse_button_down":
            api.mouse_down(data["button"], data.get("x"), data.get("y")); self._buttons.add(data["button"])
        elif item.type == "mouse_button_up":
            api.mouse_up(data["button"], data.get("x"), data.get("y")); self._buttons.discard(data["button"])
        elif item.type == "mouse_scroll":
            api.scroll(data.get("dy", 0), data.get("dx", 0))
        elif item.type == "api_call":
            execute(data["name"], data.get("arguments", {}))

    def _release_inputs(self):
        for key in tuple(self._keys):
            try: api.key_up(key)
            except Exception: pass
        for button in tuple(self._buttons):
            try: api.mouse_up(button)
            except Exception: pass
        self._keys.clear(); self._buttons.clear()

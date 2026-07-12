"""Global keyboard/mouse capture adapter built on pynput."""

import math
import time
from typing import Callable

from pytomator.project.models import RecordingItem


class InputRecorder:
    def __init__(self, callback: Callable[[RecordingItem], None], move_interval: float = 0.008,
                 move_distance: float = 1.0, excluded_hotkeys: list[str] | None = None):
        self.callback = callback
        self.move_interval = move_interval
        self.move_distance = move_distance
        self._start = 0.0
        self._keyboard = self._mouse = None
        self._last_move: tuple[float, float, float] | None = None
        self._ignore_until = 0.0
        self._pressed: set[str] = set()
        self._buffered_keys: list[RecordingItem] = []
        self._suppressed_keys: set[str] = set()
        self._excluded_chords = [self._parse_chord(value) for value in (excluded_hotkeys or []) if value]

    def start(self, offset: float = 0.0):
        try:
            from pynput import keyboard, mouse
        except ImportError as exc:
            raise RuntimeError("Global recording requires the 'pynput' package") from exc
        self._start = time.monotonic() - offset
        self._ignore_until = time.monotonic() + 0.35
        self._keyboard = keyboard.Listener(on_press=lambda key: self._key("key_down", key), on_release=lambda key: self._key("key_up", key))
        self._mouse = mouse.Listener(on_move=self._move, on_click=self._click, on_scroll=self._scroll)
        self._keyboard.start(); self._mouse.start()

    def stop(self):
        if self._keyboard: self._keyboard.stop()
        if self._mouse: self._mouse.stop()
        self._keyboard = self._mouse = None

    def _time(self): return max(0.0, time.monotonic() - self._start)

    @staticmethod
    def _key_name(key):
        char = getattr(key, "char", None)
        return char if char is not None else str(key).removeprefix("Key.")

    @staticmethod
    def _normalize_key(key: str) -> str:
        aliases = {"ctrl_l": "ctrl", "ctrl_r": "ctrl", "control": "ctrl",
                   "shift_l": "shift", "shift_r": "shift",
                   "alt_l": "alt", "alt_r": "alt", "alt_gr": "alt",
                   "cmd": "win", "cmd_l": "win", "cmd_r": "win"}
        return aliases.get(key.lower(), key.lower())

    @classmethod
    def _parse_chord(cls, hotkey: str) -> frozenset[str]:
        return frozenset(cls._normalize_key(part.strip()) for part in hotkey.split("+") if part.strip())

    def _key(self, kind, key):
        if time.monotonic() < self._ignore_until:
            return
        raw = self._key_name(key); normalized = self._normalize_key(raw)
        item = RecordingItem(type=kind, timestamp=self._time(), data={"key": raw})
        if kind == "key_down":
            self._pressed.add(normalized)
            if any(normalized in chord or self._pressed.issubset(chord) for chord in self._excluded_chords):
                self._buffered_keys.append(item)
                matched = next((chord for chord in self._excluded_chords if chord.issubset(self._pressed)), None)
                if matched:
                    self._suppressed_keys.update(matched)
                    self._buffered_keys.clear()
                return
            self._flush_buffer(); self.callback(item)
            return
        self._pressed.discard(normalized)
        if normalized in self._suppressed_keys:
            self._suppressed_keys.discard(normalized)
            return
        self._flush_buffer(); self.callback(item)

    def _flush_buffer(self):
        for item in self._buffered_keys:
            self.callback(item)
        self._buffered_keys.clear()

    def _move(self, x, y):
        now = self._time()
        if self._last_move:
            last_time, last_x, last_y = self._last_move
            if now - last_time < self.move_interval and math.hypot(x - last_x, y - last_y) < self.move_distance:
                return
        self._last_move = (now, x, y)
        self.callback(RecordingItem(type="mouse_move", timestamp=now, data={"x": x, "y": y}))

    def _click(self, x, y, button, pressed):
        kind = "mouse_button_down" if pressed else "mouse_button_up"
        self.callback(RecordingItem(type=kind, timestamp=self._time(), data={"x": x, "y": y, "button": str(button).removeprefix("Button.")}))

    def _scroll(self, x, y, dx, dy):
        self.callback(RecordingItem(type="mouse_scroll", timestamp=self._time(), data={"x": x, "y": y, "dx": dx, "dy": dy}))

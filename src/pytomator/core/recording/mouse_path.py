"""Timed mouse-path simplification and interpolation."""

import math

from pytomator.project.models import RecordingItem


def _distance_to_segment(point, start, end) -> float:
    px, py = point; ax, ay = start; bx, by = end
    dx, dy = bx - ax, by - ay
    if dx == dy == 0:
        return math.hypot(px - ax, py - ay)
    ratio = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + ratio * dx), py - (ay + ratio * dy))


def simplify_mouse_run(items: list[RecordingItem], tolerance: float = 1.5,
                       max_time_gap: float = 0.05) -> list[RecordingItem]:
    if len(items) <= 2:
        return items
    keep = {0, len(items) - 1}

    def reduce(start: int, end: int):
        if end <= start + 1:
            return
        a = (items[start].data["x"], items[start].data["y"])
        b = (items[end].data["x"], items[end].data["y"])
        distance, index = max(
            (_distance_to_segment((items[i].data["x"], items[i].data["y"]), a, b), i)
            for i in range(start + 1, end)
        )
        if distance > tolerance:
            keep.add(index); reduce(start, index); reduce(index, end)

    reduce(0, len(items) - 1)
    last = 0
    for index in range(1, len(items)):
        if items[index].timestamp - items[last].timestamp >= max_time_gap:
            keep.add(index); last = index
    return [items[index] for index in sorted(keep)]


def simplify_recording_mouse_paths(items: list[RecordingItem]) -> tuple[list[RecordingItem], int]:
    result = []; original_moves = 0; index = 0
    while index < len(items):
        if items[index].type != "mouse_move":
            result.append(items[index]); index += 1; continue
        end = index
        while end < len(items) and items[end].type == "mouse_move":
            end += 1
        run = items[index:end]; original_moves += len(run)
        result.extend(simplify_mouse_run(run)); index = end
    return result, original_moves


def interpolate_position(items: list[RecordingItem], timestamp: float) -> tuple[int, int]:
    if timestamp <= items[0].timestamp:
        return int(items[0].data["x"]), int(items[0].data["y"])
    for left, right in zip(items, items[1:]):
        if timestamp <= right.timestamp:
            span = right.timestamp - left.timestamp
            ratio = 1.0 if span <= 0 else (timestamp - left.timestamp) / span
            return (
                round(left.data["x"] + (right.data["x"] - left.data["x"]) * ratio),
                round(left.data["y"] + (right.data["y"] - left.data["y"]) * ratio),
            )
    return int(items[-1].data["x"]), int(items[-1].data["y"])

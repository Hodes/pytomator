from pprint import pformat

from pytomator.project.models import Recording


class RecordingScriptGenerator:
    def generate(self, recording: Recording) -> str:
        body: list[str] = []
        cursor = 0.0
        items = recording.sorted_items(); index = 0
        while index < len(items):
            chord = self._simple_hotkey(items, index)
            if chord:
                keys, end = chord; item = items[index]
                delay = max(0.0, item.timestamp - cursor)
                if delay: body.append(f"wait({delay:.6g})")
                body.append("hotkey(" + ", ".join(repr(key) for key in keys) + ")")
                cursor = items[end - 1].timestamp; index = end; continue
            item = items[index]
            delay = max(0.0, item.timestamp - cursor)
            if delay: body.append(f"wait({delay:.6g})")
            data = item.data
            if item.type == "comment": body.append(f"# {data.get('text', '')}")
            elif item.type == "wait":
                duration = float(data.get("duration", 0)); body.append(f"wait({duration:.6g})"); cursor = item.timestamp + duration
            elif item.type in {"key_down", "key_up"}:
                action = "key_down" if item.type == "key_down" else "key_up"
                if data.get("scan_code") or data.get("vk") is not None:
                    body.append(f"{action}_physical(scan_code={data.get('scan_code')!r}, vk={data.get('vk')!r}, extended={data.get('extended', False)!r})")
                else: body.append(f"{action}({data['key']!r})")
            elif item.type == "mouse_move": body.append(f"move_to({data['x']!r}, {data['y']!r})")
            elif item.type == "mouse_button_down": body.append(f"mouse_down({data['button']!r}, {data.get('x')!r}, {data.get('y')!r})")
            elif item.type == "mouse_button_up": body.append(f"mouse_up({data['button']!r}, {data.get('x')!r}, {data.get('y')!r})")
            elif item.type == "mouse_scroll": body.append(f"scroll({data.get('dy', 0)!r}, {data.get('dx', 0)!r})")
            elif item.type == "api_call":
                args = ", ".join(f"{key}={value!r}" for key, value in data.get("arguments", {}).items())
                body.append(f"{data['name']}({args})")
            cursor = max(cursor, item.timestamp)
            index += 1
        if recording.cycle_interval: body.append(f"wait({recording.cycle_interval:.6g})")
        body = body or ["pass"]
        if recording.loop:
            return "while not should_stop():\n" + "\n".join(f"    {line}" for line in body) + "\n"
        if recording.repetitions > 1:
            return f"for _ in range({recording.repetitions}):\n" + "\n".join(f"    {line}" for line in body) + "\n"
        return "\n".join(body) + "\n"

    @staticmethod
    def _modifier(key):
        aliases = {"ctrl_l": "ctrl", "ctrl_r": "ctrl", "shift_l": "shift", "shift_r": "shift",
                   "alt_l": "alt", "alt_r": "alt", "alt_gr": "altgr", "cmd": "win", "cmd_l": "win", "cmd_r": "win"}
        return aliases.get(str(key).lower())

    @classmethod
    def _simple_hotkey(cls, items, start):
        index = start; modifiers = []
        while index < len(items) and items[index].type == "key_down":
            modifier = cls._modifier(items[index].data.get("key"))
            if not modifier: break
            modifiers.append((modifier, str(items[index].data.get("key")).lower())); index += 1
        if not modifiers or index + 1 >= len(items) or items[index].type != "key_down": return None
        main = items[index]; main_key = str(main.data.get("key", "")).lower(); index += 1
        if items[index].type != "key_up" or str(items[index].data.get("key", "")).lower() != main_key: return None
        index += 1
        for _, raw in reversed(modifiers):
            if index >= len(items) or items[index].type != "key_up" or str(items[index].data.get("key", "")).lower() != raw: return None
            index += 1
        if items[index - 1].timestamp - items[start].timestamp > .25: return None
        return [modifier for modifier, _ in modifiers] + [main_key], index

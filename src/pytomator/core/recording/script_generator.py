from pprint import pformat

from pytomator.project.models import Recording


class RecordingScriptGenerator:
    def generate(self, recording: Recording) -> str:
        body: list[str] = []
        cursor = 0.0
        for item in recording.sorted_items():
            delay = max(0.0, item.timestamp - cursor)
            if delay: body.append(f"wait({delay:.6g})")
            data = item.data
            if item.type == "comment": body.append(f"# {data.get('text', '')}")
            elif item.type == "wait":
                duration = float(data.get("duration", 0)); body.append(f"wait({duration:.6g})"); cursor = item.timestamp + duration
            elif item.type == "key_down": body.append(f"key_down({data['key']!r})")
            elif item.type == "key_up": body.append(f"key_up({data['key']!r})")
            elif item.type == "mouse_move": body.append(f"move_to({data['x']!r}, {data['y']!r})")
            elif item.type == "mouse_button_down": body.append(f"mouse_down({data['button']!r}, {data.get('x')!r}, {data.get('y')!r})")
            elif item.type == "mouse_button_up": body.append(f"mouse_up({data['button']!r}, {data.get('x')!r}, {data.get('y')!r})")
            elif item.type == "mouse_scroll": body.append(f"scroll({data.get('dy', 0)!r}, {data.get('dx', 0)!r})")
            elif item.type == "api_call":
                args = ", ".join(f"{key}={value!r}" for key, value in data.get("arguments", {}).items())
                body.append(f"{data['name']}({args})")
            cursor = max(cursor, item.timestamp)
        if recording.cycle_interval: body.append(f"wait({recording.cycle_interval:.6g})")
        body = body or ["pass"]
        if recording.loop:
            return "while not should_stop():\n" + "\n".join(f"    {line}" for line in body) + "\n"
        if recording.repetitions > 1:
            return f"for _ in range({recording.repetitions}):\n" + "\n".join(f"    {line}" for line in body) + "\n"
        return "\n".join(body) + "\n"


class EventEmitter:
    def __init__(self):
        self._listeners = {}

    def on(self, event_name, callback):
        self._listeners.setdefault(event_name, []).append(callback)

    def emit(self, event_name, *args, **kwargs):
        for cb in self._listeners.get(event_name, []):
            cb(*args, **kwargs)

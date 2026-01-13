import threading
import time
from pytomator.core.events import EventEmitter
from pytomator.core.automator import api as automator_api

class ScriptRunner(EventEmitter):
    def __init__(self, get_code_callback):
        super().__init__()
        self.get_code = get_code_callback
        self.script_globals = {
            "__builtins__": __builtins__,
            **automator_api.__dict__
        }
        self._running = False

    def start(self, loop=False):
        if self._running:
            return

        self._running = True
        thread = threading.Thread(
            target=self._run,
            args=(loop,),
            daemon=True
        )
        thread.start()
        self.emit("started")
    
    def stop(self):
        self._running = False

    def _run(self, loop):
        while self._running:
            code = self.get_code()

            try:
                self.emit("before_execute")
                exec(code, self.script_globals)
                self.emit("after_execute")
            except Exception as e:
                self.emit("error", e)
                print("Erro no script:", e)

            if not loop:
                break

            time.sleep(0.1)
        self.emit("finished")

        self._running = False

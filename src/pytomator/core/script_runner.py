import threading
import time
import sys

from pytomator.core.events import EventEmitter
from pytomator.core.automator import api as automator_api
from pytomator.core.script_interrupted import ScriptInterrupted
from pytomator.core.global_interruption_controller import GlobalInterruptionController, should_stop

class ScriptRunner(EventEmitter):
    def __init__(self, get_code_callback):
        super().__init__()

        self.get_code = get_code_callback

        self._running = False
        self.runner_thread = None

        self.script_globals = {
            "__builtins__": __builtins__,
            "should_stop": should_stop,
            **self._filtered_automator_api()
        }

    def _filtered_automator_api(self):
        return {
            name: value
            for name, value in automator_api.__dict__.items()
            if not name.startswith("_")
        }

    # -------------------------
    # Controls
    # -------------------------

    def start(self, loop=False):
        if self._running:
            return

        GlobalInterruptionController.clear_global_interruption()
        self._running = True

        self.runner_thread = threading.Thread(
            target=self._run,
            args=(loop,),
            daemon=True
        )
        self.runner_thread.start()

        self.emit("started")

    def stop(self):
        if not self._running:
            return
        GlobalInterruptionController.request_global_interruption()
        self.emit("stopping")

    def should_stop(self) -> bool:
        return GlobalInterruptionController.is_global_interruption_requested()
    # -------------------------
    # Execution
    # -------------------------

    def _trace(self, frame, event, arg):
        if GlobalInterruptionController.is_global_interruption_requested():
            raise ScriptInterrupted()
        return self._trace

    def _run(self, loop):
        sys.settrace(self._trace)

        try:
            while self._running:
                code = self.get_code()

                try:
                    self.emit("before_execute")
                    exec(code, self.script_globals)
                except ScriptInterrupted:
                    self.emit("interrupted")
                    break
                except Exception as e:
                    self.emit("error", e)
                    print("Erro no script:", e)
                    break
                finally:
                    self.emit("after_execute")
                

                if not loop:
                    break

                time.sleep(0.1)
                
        except ScriptInterrupted:
            # 🔥 Captura interrupção disparada FORA do exec
            self.emit("interrupted")
        finally:
            sys.settrace(None)
            self._running = False
            self.emit("finished")

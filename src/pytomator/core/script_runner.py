import threading
import time
import sys
from typing import Callable

from pytomator.core.events import EventEmitter
from pytomator.core.automator import api as automator_api
from pytomator.core.script_interrupted import ScriptInterrupted
from pytomator.core.global_interruption_controller import GlobalInterruptionController, should_stop

class ScriptRunner(EventEmitter):
    def __init__(self):
        super().__init__()

        self._running = False
        self.runner_thread = None
        self._last_lineno = None
        self._script_frame = None
        self._code = ""

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
    
    def set_code(self, code: str):
        self._code = code

    # -------------------------
    # Controls
    # -------------------------
    
    def is_running(self) -> bool:
        return self._running

    def start(self, code: str, loop=False):
        if self._running:
            return

        self.set_code(code)
        # is empty code?
        if not self._code.strip():
            return
        
        self.stop()
        GlobalInterruptionController.clear_global_interruption()
        self._running = True

        self.runner_thread = threading.Thread(
            target=self._run,
            args=(loop,),
            daemon=False
        )
        self.runner_thread.start()

        self.emit("started")

    def stop(self):
        if self._running:
            self.emit("stopping")
        GlobalInterruptionController.request_global_interruption()
        self._running = False
        if self.runner_thread and self.runner_thread.is_alive():
            self.runner_thread.join(timeout=1.0)
        

    def should_stop(self) -> bool:
        return GlobalInterruptionController.is_global_interruption_requested()
    # -------------------------
    # Execution
    # -------------------------

    def _trace(self, frame, event, arg):
        if GlobalInterruptionController.is_global_interruption_requested():
            raise ScriptInterrupted()
        
        if frame.f_code.co_filename != "<string>":
            return self._trace
        
        if self._script_frame is None:
            self._script_frame = frame
        
        # Se não for o frame do script, apenas retorne o trace padrão
        if frame is not self._script_frame:
            return self._trace
                
        if event == "line" and self._last_lineno != frame.f_lineno:
            # print(frame.f_code.co_filename, event, frame.f_lineno)
            lineno = frame.f_lineno
            self._last_lineno = lineno
            self.emit("line_executing", lineno)
        return self._trace

    def _run(self, loop):
        sys.settrace(self._trace)
        self._last_lineno = None
        self._script_frame = None

        # is empty code?
        if not self._code.strip():
            self.stop()
            return
        
        # Aways append to the code a check for interruption
        code_to_run = self._code + "\ncheck_interruption()\n"
        
        try:
            while self._running:
                # print("Thread is still running...")
                try:
                    self.emit("before_execute")
                    
                    sys.settrace(self._trace)
                    exec(code_to_run, self.script_globals)
                    
                    if should_stop():
                        raise ScriptInterrupted()
                except ScriptInterrupted:
                    self.emit("interrupted")
                    break
                except Exception as e:
                    self.emit("error", e)
                    print("Script error:", e)
                    break
                finally:
                    self.emit("after_execute")
                

                if not loop:
                    break

                time.sleep(0.1)
                
        except ScriptInterrupted:
            self.emit("interrupted")
        except Exception as e:
            self.emit("error", e)
            print("Script error:", e)
        finally:
            sys.settrace(None)
            self._running = False
            GlobalInterruptionController.clear_global_interruption()
            self.emit("finished")

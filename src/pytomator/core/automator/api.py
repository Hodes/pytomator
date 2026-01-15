import sys
import time
import pyautogui
from pytomator.core.global_interruption_controller import should_stop
from pytomator.core.script_interrupted import ScriptInterrupted

ENTER = "enter"
ESC = "esc"

use_direct_input_keys = sys.platform == "win32"
if use_direct_input_keys:
    import pydirectinput

def direct_input_keys( state: bool = True):
    global use_direct_input_keys
    use_direct_input_keys = state

def wait(seconds: float = 1, check_interval: float = 0.05):
    """
    Espera por 'seconds', podendo ser interrompido.
    check_interval controla a responsividade.
    """
    end_time = time.monotonic() + seconds

    while time.monotonic() < end_time:
        # 🔥 interrupção cooperativa
        if should_stop():
            raise ScriptInterrupted()

        remaining = end_time - time.monotonic()
        time.sleep(min(check_interval, max(0, remaining)))

def check_interruption():
    if should_stop():
        raise ScriptInterrupted()

def click(x=None, y=None):
    if x is None or y is None:
        pyautogui.click()
    else:
        pyautogui.click(x, y)

def click_hold(duration=1, x=None, y=None):
    if x is None or y is None:
        pyautogui.mouseDown()
        wait(duration)
        pyautogui.mouseUp()
    else:
        pyautogui.mouseDown(x, y)
        wait(duration)
        pyautogui.mouseUp(x, y)
        
def hold(key, duration=1):
    if use_direct_input_keys:
        pydirectinput.keyDown(key)
        wait(duration)
        pydirectinput.keyUp(key)
        return
    pyautogui.keyDown(key)
    wait(duration)
    pyautogui.keyUp(key)

def press(key):
    if use_direct_input_keys:
        pydirectinput.press(key)
        return
    pyautogui.press(key)

def write(text, interval=0.05):
    pyautogui.write(text, interval=interval)

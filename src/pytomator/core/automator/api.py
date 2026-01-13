import time
import pyautogui

ENTER = "enter"
ESC = "esc"

def wait(seconds=1):
    time.sleep(seconds)

def click(x=None, y=None):
    if x is None or y is None:
        pyautogui.click()
    else:
        pyautogui.click(x, y)

def click_hold(duration=1, x=None, y=None):
    if x is None or y is None:
        pyautogui.mouseDown()
        time.sleep(duration)
        pyautogui.mouseUp()
    else:
        pyautogui.mouseDown(x, y)
        time.sleep(duration)
        pyautogui.mouseUp(x, y)

def press(key):
    pyautogui.press(key)

def write(text, interval=0.05):
    pyautogui.write(text, interval=interval)

"""Windows implementation of desktop window control."""

from typing import Optional

from pytomator.core.windows.window_controller import WindowController, WindowInfo


class WindowsWindowController(WindowController):
    """Control top-level windows through pywin32."""

    def find_window(self, title: str) -> Optional[WindowInfo]:
        if not title or not title.strip():
            return None

        import win32gui  # type: ignore

        candidates: list[WindowInfo] = []

        def collect(hwnd: int, _extra: object) -> bool:
            if not win32gui.IsWindowVisible(hwnd):
                return True
            window_title = win32gui.GetWindowText(hwnd).strip()
            if not window_title:
                return True
            rect = win32gui.GetWindowRect(hwnd)
            candidates.append(
                {
                    "id": hwnd,
                    "title": window_title,
                    "left": rect[0],
                    "top": rect[1],
                    "width": rect[2] - rect[0],
                    "height": rect[3] - rect[1],
                }
            )
            return True

        win32gui.EnumWindows(collect, None)
        expected = title.strip().casefold()
        exact = next(
            (window for window in candidates if str(window["title"]).casefold() == expected),
            None,
        )
        if exact is not None:
            return exact
        return next(
            (window for window in candidates if expected in str(window["title"]).casefold()),
            None,
        )

    def focus_window(self, window: WindowInfo) -> bool:
        import win32con  # type: ignore
        import win32gui  # type: ignore

        hwnd = window.get("id")
        if not isinstance(hwnd, int) or not win32gui.IsWindow(hwnd):
            return False
        try:
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            return False
        return win32gui.GetForegroundWindow() == hwnd

"""Full-screen transparent overlay for selecting a screen region to capture.

Template matching via MSS works on all monitors regardless.
"""

import keyboard

from PyQt6.QtWidgets import QWidget, QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QDoubleSpinBox, QFormLayout, QGroupBox, QDialogButtonBox
from PyQt6.QtGui import QPainter, QPen, QColor, QPixmap, QFont
from PyQt6.QtCore import Qt, QRect, QPoint, pyqtSignal

from pytomator.core.vision.capture_tool import (
    get_active_window_info,
)


class CaptureOverlay(QWidget):
    """Full-screen semi-transparent overlay for region selection.
    Uses showNormal() positioned exactly over the target monitor.
    """

    region_selected = pyqtSignal(int, int, int, int)  # x, y, w, h (absolute virtual coords)
    cancelled = pyqtSignal()

    def __init__(self):
        super().__init__()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # Get primary screen size for the overlay window
        screen = QApplication.primaryScreen()
        if screen:
            screen_size = screen.size()
            self._screen_width = screen_size.width()
            self._screen_height = screen_size.height()
        else:
            self._screen_width = 1920
            self._screen_height = 1080

        # Virtual screen origin (primary monitor is at 0,0)
        self._virtual_left = 0
        self._virtual_top = 0

        self.setGeometry(0, 0, self._screen_width, self._screen_height)
        self.setCursor(Qt.CursorShape.CrossCursor)

        self._start_point: QPoint | None = None
        self._is_dragging = False
        self._current_rect: QRect | None = None
        self._background_pixmap = None
        self._esc_handler_id = None

        self._capture_background()

    def _on_esc_hotkey(self):
        """Called when ESC is pressed globally."""
        self.cancelled.emit()

    def show_on_screen(self, screen_index: int):
        """Move the overlay to a specific physical monitor.

        Args:
            screen_index: Index of the screen (0 = primary, 1, 2, ...).
        """
        screens = QApplication.screens()
        if screen_index < 0 or screen_index >= len(screens):
            return

        target = screens[screen_index]
        geometry = target.geometry()

        self._screen_width = geometry.width()
        self._screen_height = geometry.height()
        self._virtual_left = geometry.x()
        self._virtual_top = geometry.y()

        self.setGeometry(geometry)
        self._capture_background(screen_index)
        self.showNormal()
        self.activateWindow()
        self.setFocus()
        self.update()

        # Register global ESC hotkey (works even without focus)
        self._esc_handler_id = keyboard.add_hotkey("esc", self._on_esc_hotkey)

    def _capture_background(self, screen_index: int = -1):
        """Capture the current monitor screen to use as background.

        Args:
            screen_index: Monitor index to capture (-1 = primary).
        """
        if screen_index >= 0:
            screens = QApplication.screens()
            if screen_index < len(screens):
                target = screens[screen_index]
                self._background_pixmap = target.grabWindow(0)
                return
        # Fallback: primary screen
        screen = QApplication.primaryScreen()
        if screen:
            self._background_pixmap = screen.grabWindow(0)

    def paintEvent(self, event):
        painter = QPainter(self)

        # Draw the captured screen as background
        if self._background_pixmap:
            painter.drawPixmap(0, 0, self._background_pixmap)

        # Dim the entire screen
        painter.fillRect(self.rect(), QColor(0, 0, 0, 120))

        if self._current_rect and not self._current_rect.isEmpty():
            # Clear the dimming on the selected area
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(self._current_rect, QColor(0, 0, 0, 0))
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

            # Draw selection border
            pen = QPen(QColor(255, 50, 50), 3)
            painter.setPen(pen)
            painter.drawRect(self._current_rect)

            # Crosshair lines at center
            center = self._current_rect.center()
            pen.setColor(QColor(255, 255, 255, 200))
            pen.setWidth(1)
            painter.setPen(pen)
            painter.drawLine(self._current_rect.left(), center.y(), self._current_rect.right(), center.y())
            painter.drawLine(center.x(), self._current_rect.top(), center.x(), self._current_rect.bottom())

            # Size label
            size_text = f"{self._current_rect.width()} x {self._current_rect.height()}"
            font = QFont("Segoe UI", 12, QFont.Weight.Bold)
            painter.setFont(font)
            painter.setPen(QColor(255, 255, 255))
            text_bg = QRect(self._current_rect.left() + 5, self._current_rect.bottom() + 5, 110, 24)
            painter.fillRect(text_bg, QColor(0, 0, 0, 160))
            painter.drawText(text_bg, Qt.AlignmentFlag.AlignCenter, size_text)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._start_point = event.pos()
            self._is_dragging = True
            self._current_rect = QRect(self._start_point, self._start_point)
            self.update()

    def mouseMoveEvent(self, event):
        if self._is_dragging:
            self._current_rect = QRect(self._start_point, event.pos()).normalized()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._is_dragging:
            self._is_dragging = False
            r = self._current_rect
            if r and r.width() > 5 and r.height() > 5:
                # Convert to absolute virtual screen coordinates
                abs_x = r.x() + self._virtual_left
                abs_y = r.y() + self._virtual_top
                self.region_selected.emit(abs_x, abs_y, r.width(), r.height())
            else:
                self.cancelled.emit()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()

    def closeEvent(self, event):
        if self._esc_handler_id is not None:
            keyboard.remove_hotkey(self._esc_handler_id)
            self._esc_handler_id = None
        super().closeEvent(event)


class CapturePreviewDialog(QDialog):
    """Dialog shown after a region is captured, allowing the user to review and save."""

    escape_pressed = pyqtSignal()

    def __init__(
        self,
        pixmap: QPixmap,
        x: int,
        y: int,
        w: int,
        h: int,
        parent=None,
        window_info: dict | None = None,
    ):
        super().__init__(parent)

        self.setWindowTitle("Capture Preview")
        self.setMinimumSize(480, 520)
        self.setModal(True)

        self._x = x
        self._y = y
        self._w = w
        self._h = h
        self._pixmap = pixmap

        # Get primary screen size for display
        screen = QApplication.primaryScreen()
        if screen:
            size = screen.size()
            self._screen_w = size.width()
            self._screen_h = size.height()
        else:
            self._screen_w = 1920
            self._screen_h = 1080
        self._virtual_left = 0
        self._virtual_top = 0
        self._window_info = window_info or get_active_window_info()

        self._accepted = False
        self._template_name = ""
        self._confidence = 0.85

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout()
        self.setLayout(layout)

        # Preview image
        preview_group = QGroupBox("Captured Region")
        preview_layout = QVBoxLayout()
        preview_group.setLayout(preview_layout)
        preview_label = QLabel()
        scaled = self._pixmap.scaled(440, 220, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        preview_label.setPixmap(scaled)
        preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_layout.addWidget(preview_label)
        layout.addWidget(preview_group)

        # Template Name
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Template Name:"))
        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("e.g. btn_login, icon_settings")
        name_layout.addWidget(self._name_input)
        layout.addLayout(name_layout)

        # Confidence
        conf_layout = QHBoxLayout()
        conf_layout.addWidget(QLabel("Confidence:"))
        self._confidence_spin = QDoubleSpinBox()
        self._confidence_spin.setRange(0.0, 1.0)
        self._confidence_spin.setSingleStep(0.05)
        self._confidence_spin.setValue(0.85)
        self._confidence_spin.setDecimals(2)
        conf_layout.addWidget(self._confidence_spin)
        layout.addLayout(conf_layout)

        # Metadata
        meta_group = QGroupBox("Capture Metadata")
        meta_layout = QFormLayout()
        meta_group.setLayout(meta_layout)
        meta_layout.addRow("Absolute (x, y, w, h):", QLabel(f"({self._x}, {self._y}, {self._w}, {self._h})"))
        meta_layout.addRow("Screen Resolution:", QLabel(f"{self._screen_w} x {self._screen_h}"))
        win = self._window_info
        window_text = f"'{win['title']}'" if win["title"] else "(none detected)"
        meta_layout.addRow("Active Window:", QLabel(window_text))
        if win["width"] > 0 and win["height"] > 0:
            rel_x = self._x - win["left"]
            rel_y = self._y - win["top"]
            meta_layout.addRow("Relative (x, y, w, h):", QLabel(f"({rel_x}, {rel_y}, {self._w}, {self._h})"))
            pct_abs_x = round(self._x / self._screen_w * 100, 2) if self._screen_w > 0 else 0.0
            pct_abs_y = round(self._y / self._screen_h * 100, 2) if self._screen_h > 0 else 0.0
            pct_abs_w = round(self._w / self._screen_w * 100, 2) if self._screen_w > 0 else 0.0
            pct_abs_h = round(self._h / self._screen_h * 100, 2) if self._screen_h > 0 else 0.0
            meta_layout.addRow("Absolute %:", QLabel(f"({pct_abs_x}%, {pct_abs_y}%, {pct_abs_w}%, {pct_abs_h}%)"))
            pct_rel_x = round(rel_x / win["width"] * 100, 2) if win["width"] > 0 else 0
            pct_rel_y = round(rel_y / win["height"] * 100, 2) if win["height"] > 0 else 0
            pct_rel_w = round(self._w / win["width"] * 100, 2) if win["width"] > 0 else 0
            pct_rel_h = round(self._h / win["height"] * 100, 2) if win["height"] > 0 else 0
            meta_layout.addRow("Relative %:", QLabel(f"({pct_rel_x}%, {pct_rel_y}%, {pct_rel_w}%, {pct_rel_h}%)"))
        layout.addWidget(meta_group)

        # Buttons
        buttons = QDialogButtonBox()
        recapture_btn = QPushButton("Capture Again")
        recapture_btn.clicked.connect(self._on_recapture)
        buttons.addButton(recapture_btn, QDialogButtonBox.ButtonRole.ActionRole)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        buttons.addButton(cancel_btn, QDialogButtonBox.ButtonRole.RejectRole)
        save_btn = QPushButton("Save Template")
        save_btn.clicked.connect(self._on_save)
        save_btn.setDefault(True)
        buttons.addButton(save_btn, QDialogButtonBox.ButtonRole.AcceptRole)
        layout.addWidget(buttons)

    def _on_recapture(self):
        self._accepted = False
        self.done(QDialog.DialogCode.Accepted + 1)  # Custom code: recapture

    def _on_save(self):
        name = self._name_input.text().strip()
        if not name:
            self._name_input.setStyleSheet("border: 2px solid red;")
            return
        self._template_name = name
        self._confidence = self._confidence_spin.value()
        self._accepted = True
        self.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.escape_pressed.emit()
            return
        super().keyPressEvent(event)

    @property
    def template_name(self) -> str:
        return self._template_name

    @property
    def confidence(self) -> float:
        return self._confidence

    def is_accepted(self) -> bool:
        return self._accepted

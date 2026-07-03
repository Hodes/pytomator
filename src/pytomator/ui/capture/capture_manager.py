"""Manages the capture workflow: overlay, preview, and saving templates to the project."""

from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QDialog
from PyQt6.QtGui import QPixmap, QCursor
from PyQt6.QtCore import QObject, pyqtSignal
from PIL import Image

from pytomator.core.vision.capture_tool import (
    capture_region,
    get_screen_size,
    get_active_window_info,
    save_template_image,
)
from pytomator.core.vision.models import TemplateCapture
from pytomator.project.manager import ProjectManager
from pytomator.ui.capture.capture_overlay import CaptureOverlay, CapturePreviewDialog


# Custom dialog result codes
_DIALOG_RECAPTURE = QDialog.DialogCode.Accepted + 1


class CaptureManager(QObject):
    """Coordinates the capture workflow: overlay → preview → save to project."""

    template_saved = pyqtSignal(TemplateCapture)
    capture_cancelled = pyqtSignal()

    def __init__(self, project_manager: ProjectManager, parent: QObject = None):
        super().__init__(parent)
        self._project_manager = project_manager
        self._overlay: Optional[CaptureOverlay] = None
        self._overlays: set[CaptureOverlay] = set()
        self._preview_dialog: Optional[CapturePreviewDialog] = None
        self._main_window: Optional[QMainWindow] = None
        self._target_window_info: Optional[dict] = None
        self._capture_active = False
        self._cancelling = False

    def set_main_window(self, window: QMainWindow):
        """Set the reference to the main window (for minimize/restore)."""
        self._main_window = window

    def start_capture(self):
        """Start the capture workflow: show overlay, capture region, preview, save."""
        if (
            not self._project_manager.is_project_open
            or self._project_manager.project_path is None
        ):
            # Templates need a project directory in which to store their images.
            return

        self.cancel_capture(emit_signal=False)
        self._capture_active = True
        self._target_window_info = None
        self._show_overlay()

    def _show_overlay(self):
        """Show the full-screen capture overlay on the monitor where the cursor is."""
        # Minimize main window so user can see the screen
        if self._main_window:
            self._main_window.showMinimized()
            QApplication.processEvents()

        # Capture the external target after Pytomator is hidden, but before the
        # overlay itself becomes the foreground window. Preserve it on recapture.
        if self._target_window_info is None:
            self._target_window_info = get_active_window_info()

        # Create overlay
        overlay = CaptureOverlay()
        self._overlay = overlay
        self._overlays.add(overlay)
        overlay.destroyed.connect(
            lambda _object=None, item=overlay: self._overlays.discard(item)
        )
        overlay.region_selected.connect(self._on_region_selected)
        overlay.cancelled.connect(self._on_capture_cancelled)

        # Determine which monitor the cursor is on
        cursor_pos = QCursor.pos()
        screens = QApplication.screens()
        target_screen = 0  # fallback to primary
        for i, screen in enumerate(screens):
            if screen.geometry().contains(cursor_pos):
                target_screen = i
                break

        # Show overlay on the cursor's monitor
        overlay.show_on_screen(target_screen)

    def _on_region_selected(self, x: int, y: int, w: int, h: int):
        """Called when the user selects a region on the overlay."""
        # Close overlay
        if self._overlay:
            overlay = self._overlay
            self._overlay = None
            self._overlays.discard(overlay)
            overlay.close()

        # Restore main window
        if self._main_window:
            self._main_window.showNormal()
            self._main_window.raise_()
            self._main_window.activateWindow()

        # Capture the region (keep the PIL Image for later save)
        pil_image = capture_region(x, y, w, h)

        # Convert PIL Image to QPixmap for preview
        from PIL.ImageQt import ImageQt
        qimage = ImageQt(pil_image)
        pixmap = QPixmap.fromImage(qimage)

        # Show preview dialog
        self._show_preview(pixmap, pil_image, x, y, w, h)

    def _on_capture_cancelled(self):
        """Called when the user cancels the overlay (Escape or too small)."""
        self.cancel_capture()

    def cancel_capture(self, emit_signal: bool = True):
        """Cancel every open part of the current capture workflow."""
        if self._cancelling:
            return

        had_active_capture = bool(
            self._capture_active or self._overlays or self._preview_dialog
        )
        self._cancelling = True
        try:
            dialog = self._preview_dialog
            self._preview_dialog = None
            if dialog is not None:
                dialog.reject()

            overlays = tuple(self._overlays)
            self._overlays.clear()
            self._overlay = None
            for overlay in overlays:
                overlay.close()
                overlay.deleteLater()

            self._capture_active = False
            self._target_window_info = None

            if self._main_window and had_active_capture:
                self._main_window.showNormal()
                self._main_window.raise_()
                self._main_window.activateWindow()

            if emit_signal and had_active_capture:
                self.capture_cancelled.emit()
        finally:
            self._cancelling = False

    def _show_preview(self, pixmap: QPixmap, pil_image: Image.Image,
                      x: int, y: int, w: int, h: int):
        """Show the preview dialog and handle save/recapture."""
        dialog = CapturePreviewDialog(
            pixmap,
            x,
            y,
            w,
            h,
            self._main_window,
            window_info=self._target_window_info,
        )
        self._preview_dialog = dialog
        dialog.escape_pressed.connect(self.cancel_capture)

        result = dialog.exec()
        if self._preview_dialog is dialog:
            self._preview_dialog = None

        if dialog.is_accepted():
            self._save_template(dialog, pil_image, x, y, w, h)
            self._capture_active = False
            self._target_window_info = None
        elif result == _DIALOG_RECAPTURE:
            self._show_overlay()
        elif self._capture_active:
            self.cancel_capture()

    def _save_template(self, dialog: CapturePreviewDialog, pil_image: Image.Image,
                       x: int, y: int, w: int, h: int):
        """Save the captured template to the project."""
        project = self._project_manager.project
        project_path = self._project_manager.project_path

        if project is None or project_path is None:
            return

        # Get metadata (virtual screen: left, top, width, height)
        v_left, v_top, screen_w, screen_h = get_screen_size()
        window_info = self._target_window_info or get_active_window_info()

        # Calculate relative coordinates
        rel_x = x - window_info["left"] if window_info["width"] > 0 else 0
        rel_y = y - window_info["top"] if window_info["height"] > 0 else 0

        # Calculate percentages
        pct_abs = (
            round((x - v_left) / screen_w * 100, 2) if screen_w > 0 else 0.0,
            round((y - v_top) / screen_h * 100, 2) if screen_h > 0 else 0.0,
            round(w / screen_w * 100, 2) if screen_w > 0 else 0.0,
            round(h / screen_h * 100, 2) if screen_h > 0 else 0.0,
        )
        pct_rel = (
            round(rel_x / window_info["width"] * 100, 2) if window_info["width"] > 0 else 0.0,
            round(rel_y / window_info["height"] * 100, 2) if window_info["height"] > 0 else 0.0,
            round(w / window_info["width"] * 100, 2) if window_info["width"] > 0 else 0.0,
            round(h / window_info["height"] * 100, 2) if window_info["height"] > 0 else 0.0,
        )

        # Create the model (id is auto-generated)
        template = TemplateCapture(
            name=dialog.template_name,
            image_path="",  # Will be set after saving
            region_abs=(x, y, w, h),
            region_rel=(rel_x, rel_y, w, h),
            screen_width=screen_w,
            screen_height=screen_h,
            pct_abs=pct_abs,
            pct_rel=pct_rel,
            active_window_title=window_info["title"],
            confidence=dialog.confidence,
        )

        # Save the image (use the original PIL Image, no QPixmap conversion needed)
        image_path = save_template_image(project_path, template.id, pil_image)
        template.image_path = image_path

        # Add to project
        project.templates.append(template)
        project.updated_at = __import__("datetime").datetime.now()

        # Save project
        self._project_manager.save_project()

        # Emit signal
        self.template_saved.emit(template)

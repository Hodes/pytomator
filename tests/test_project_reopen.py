import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QMessageBox

from pytomator.project.manager import ProjectManager
from pytomator.ui.project_frame import ProjectFrame


class ProjectReopenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.config = MagicMock()
        self.config.config = {"last_project_dir": "", "last_project_path": ""}

        config_patcher = patch(
            "pytomator.ui.project_frame.ConfigManager.get_instance",
            return_value=self.config,
        )
        config_patcher.start()
        self.addCleanup(config_patcher.stop)

        self.manager = ProjectManager()
        self.frame = ProjectFrame(self.manager)
        self.addCleanup(self.frame.close)

    def _create_project_file(self, name="Example") -> Path:
        path = self.root / "example.pytom"
        self.manager.create_project(name)
        self.manager.save_project(path)
        self.manager.close_project()
        return path

    def test_reopen_loads_last_project_without_file_dialog(self):
        path = self._create_project_file()
        self.config.config["last_project_path"] = str(path)
        self.config.config["last_project_dir"] = str(path.parent)
        self.frame._update_ui_state()

        with patch.object(self.frame, "_open_project_file") as open_dialog:
            self.frame._on_reopen_last()

        open_dialog.assert_not_called()
        self.assertTrue(self.manager.is_project_open)
        self.assertEqual(self.manager.project.name, "Example")
        self.assertEqual(self.manager.project_path, path)

    def test_missing_project_disables_reopen(self):
        missing = self.root / "missing.pytom"
        self.config.config["last_project_path"] = str(missing)

        self.frame._update_ui_state()

        self.assertFalse(self.frame.reopen_btn.isEnabled())
        self.assertEqual(self.frame.last_project_label.text(), str(missing.resolve()))

    def test_legacy_config_still_supplies_open_dialog_directory(self):
        self.config.config = {"last_project_dir": str(self.root)}
        self.frame._update_ui_state()

        self.assertFalse(self.frame.reopen_btn.isEnabled())
        with patch.object(self.frame, "_open_project_file") as open_dialog:
            self.frame._on_open_project()
        open_dialog.assert_called_once_with(str(self.root))

    def test_failed_reopen_shows_error_without_opening_project(self):
        path = self.root / "broken.pytom"
        path.write_text("not json", encoding="utf-8")
        self.config.config["last_project_path"] = str(path)
        self.frame._update_ui_state()

        with patch("pytomator.ui.project_frame.QMessageBox.critical") as critical:
            self.frame._on_reopen_last()

        self.assertFalse(self.manager.is_project_open)
        critical.assert_called_once()

    def test_save_persists_normalized_file_and_directory(self):
        self.manager.create_project("New")
        selected_path = self.root / "new-project"

        with patch(
            "pytomator.ui.project_frame.QFileDialog.getSaveFileName",
            return_value=(str(selected_path), ""),
        ):
            self.frame._on_save_as()

        saved_path = selected_path.with_suffix(".pytom").resolve()
        self.assertEqual(self.config.config["last_project_path"], str(saved_path))
        self.assertEqual(self.config.config["last_project_dir"], str(saved_path.parent))
        self.assertTrue(saved_path.is_file())

    def test_cancel_replacement_keeps_current_project(self):
        self.manager.create_project("Current")

        with patch(
            "pytomator.ui.project_frame.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Cancel,
        ), patch(
            "pytomator.ui.project_frame.QInputDialog.getText",
            side_effect=[("Replacement", True), ("", True)],
        ):
            self.frame._on_new_project()

        self.assertEqual(self.manager.project.name, "Current")

    def test_cancel_save_as_aborts_replacement(self):
        self.manager.create_project("Unsaved")

        with patch(
            "pytomator.ui.project_frame.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Yes,
        ), patch(
            "pytomator.ui.project_frame.QFileDialog.getSaveFileName",
            return_value=("", ""),
        ), patch(
            "pytomator.ui.project_frame.QInputDialog.getText",
            side_effect=[("Replacement", True), ("", True)],
        ):
            self.frame._on_new_project()

        self.assertEqual(self.manager.project.name, "Unsaved")
        self.assertIsNone(self.manager.project_path)

    def test_discard_then_create_emits_closed_before_loaded(self):
        self.manager.create_project("Current")
        events = []
        self.manager.on("project_closed", lambda: events.append("closed"))
        self.manager.on("project_loaded", lambda: events.append("loaded"))

        with patch(
            "pytomator.ui.project_frame.QMessageBox.question",
            return_value=QMessageBox.StandardButton.No,
        ), patch(
            "pytomator.ui.project_frame.QInputDialog.getText",
            side_effect=[("Replacement", True), ("Description", True)],
        ):
            self.frame._on_new_project()

        self.assertEqual(events, ["closed", "loaded"])
        self.assertEqual(self.manager.project.name, "Replacement")

    def test_failed_load_preserves_current_project_and_matcher(self):
        current_path = self._create_project_file("Current")
        self.manager.load_project(current_path)
        broken_path = self.root / "broken.pytom"
        broken_path.write_text("not json", encoding="utf-8")
        current_project = self.manager.project

        with patch(
            "pytomator.core.vision.template_matcher_registry.release_template_matcher"
        ) as release:
            with self.assertRaises(Exception):
                self.manager.load_project(broken_path)

        self.assertIs(self.manager.project, current_project)
        self.assertEqual(self.manager.project_path, current_path)
        release.assert_not_called()

    def test_close_is_idempotent_and_releases_matcher_once(self):
        path = self._create_project_file()
        self.manager.load_project(path)
        events = []
        self.manager.on("project_closed", lambda: events.append("closed"))

        with patch(
            "pytomator.core.vision.template_matcher_registry.release_template_matcher"
        ) as release:
            self.manager.close_project()
            self.manager.close_project()

        release.assert_called_once_with(path)
        self.assertEqual(events, ["closed"])


if __name__ == "__main__":
    unittest.main()

import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
from PIL import Image

from pytomator.core.automator import api
from pytomator.core.vision import capture_tool, template_matcher


class ActiveSearchRegionTests(unittest.TestCase):
    @patch("pytomator.core.vision.capture_tool.get_screen_size")
    def test_clips_active_window_to_virtual_screen(self, get_screen_size):
        get_screen_size.return_value = (-1920, 0, 3840, 1080)
        window = {
            "id": 42,
            "title": "Target",
            "left": -2000,
            "top": -20,
            "width": 1000,
            "height": 600,
        }

        region, snapshot = capture_tool.get_active_search_region(window)

        self.assertEqual(
            region,
            {"left": -1920, "top": 0, "width": 920, "height": 580},
        )
        self.assertIs(snapshot, window)

    @patch("pytomator.core.vision.capture_tool.get_physical_monitors")
    @patch("pytomator.core.vision.capture_tool.get_screen_size")
    def test_monitor_lookup_supports_negative_coordinates(
        self, get_screen_size, get_monitors
    ):
        get_screen_size.return_value = (-1920, 0, 3840, 1080)
        get_monitors.return_value = [
            {"left": -1920, "top": 0, "width": 1920, "height": 1080},
            {"left": 0, "top": 0, "width": 1920, "height": 1080},
        ]

        monitor = capture_tool.get_monitor_at_point(-400, 300)

        self.assertEqual(monitor["left"], -1920)

    @patch("pytomator.core.vision.capture_tool.get_monitor_at_point")
    @patch("pytomator.core.vision.capture_tool.get_screen_size")
    @patch("pyautogui.position")
    def test_missing_window_falls_back_to_cursor_monitor(
        self, position, get_screen_size, get_monitor
    ):
        position.return_value = SimpleNamespace(x=2200, y=400)
        get_screen_size.return_value = (0, 0, 3840, 1080)
        get_monitor.return_value = {
            "left": 1920,
            "top": 0,
            "width": 1920,
            "height": 1080,
        }
        window = {
            "id": None,
            "title": None,
            "left": 0,
            "top": 0,
            "width": 0,
            "height": 0,
        }

        region, _ = capture_tool.get_active_search_region(window)

        get_monitor.assert_called_once_with(2200, 400)
        self.assertEqual(region["left"], 1920)


class TemplateMatcherTests(unittest.TestCase):
    @staticmethod
    def _matching_images():
        screen = np.zeros((30, 40, 3), dtype=np.uint8)
        pattern = np.random.default_rng(42).integers(
            0, 256, size=(8, 10, 3), dtype=np.uint8
        )
        screen[8:16, 12:22] = pattern
        return Image.fromarray(screen), Image.fromarray(pattern)

    @patch("pytomator.core.vision.template_matcher.capture_region")
    @patch("pytomator.core.vision.template_matcher.load_template_image")
    def test_match_coordinates_are_converted_to_desktop_coordinates(
        self, load_template, capture_region
    ):
        screen, pattern = self._matching_images()
        load_template.return_value = pattern
        capture_region.return_value = screen
        template = MagicMock(image_path="template.png", confidence=0.99)

        result = template_matcher.find_on_screen(
            template,
            Path("."),
            search_region={"left": -800, "top": 100, "width": 40, "height": 30},
        )

        self.assertEqual(result, (-788, 108, 10, 8))

    def test_multiscale_finds_resized_templates_and_refines_scale(self):
        template = np.random.default_rng(7).integers(
            0, 256, size=(24, 30, 3), dtype=np.uint8
        )
        for target_scale in (0.5, 1.0, 2.0, 2.64, 3.0):
            with self.subTest(scale=target_scale):
                scaled = template_matcher._resize_template(template, target_scale)
                height, width = scaled.shape[:2]
                screen = np.zeros((max(120, height + 30), max(140, width + 40), 3), dtype=np.uint8)
                screen[12:12 + height, 17:17 + width] = scaled

                scale, location, size, _ = template_matcher._best_multiscale_match(
                    screen, template
                )

                self.assertLessEqual(abs(scale - target_scale), 0.021)
                self.assertEqual(location, (17, 12))
                self.assertEqual(size, (width, height))

    def test_multiscale_skips_templates_larger_than_screen(self):
        screen = np.zeros((20, 20, 3), dtype=np.uint8)
        template = np.random.default_rng(9).integers(
            0, 256, size=(30, 30, 3), dtype=np.uint8
        )

        _, _, _, scores = template_matcher._best_multiscale_match(screen, template)

        self.assertTrue(any(item["skipped"] for item in scores))
        self.assertTrue(any(not item["skipped"] for item in scores))

    @patch("pytomator.core.vision.template_matcher.capture_region")
    @patch("pytomator.core.vision.template_matcher.load_template_image")
    def test_debug_disabled_creates_no_directory(
        self, load_template, capture_region
    ):
        screen, pattern = self._matching_images()
        load_template.return_value = pattern
        capture_region.return_value = screen
        template = SimpleNamespace(
            id="abc", name="capy", image_path="templates/abc.png", confidence=0.9
        )

        with TemporaryDirectory() as tmp:
            template_matcher.find_on_screen(
                template,
                Path(tmp) / "project.pytom",
                search_region={"left": 0, "top": 0, "width": 40, "height": 30},
            )
            self.assertFalse((Path(tmp) / "vision_debug").exists())

    @patch("pytomator.core.vision.template_matcher.capture_region")
    @patch("pytomator.core.vision.template_matcher.load_template_image")
    def test_debug_saves_images_and_metadata_beside_pytom(
        self, load_template, capture_region
    ):
        screen, pattern = self._matching_images()
        load_template.return_value = pattern
        capture_region.return_value = screen
        template = SimpleNamespace(
            id="abc", name="capy", image_path="templates/abc.png", confidence=1.1
        )
        window = {
            "id": 7,
            "title": "Browser",
            "left": -800,
            "top": 100,
            "width": 40,
            "height": 30,
        }

        with TemporaryDirectory() as tmp:
            result = template_matcher.find_on_screen(
                template,
                Path(tmp) / "project.pytom",
                search_region={"left": -800, "top": 100, "width": 40, "height": 30},
                debug=True,
                window_info=window,
            )
            debug_dir = Path(tmp) / "vision_debug"
            metadata_path = next(debug_dir.glob("*_metadata.json"))
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

            self.assertIsNone(result)
            self.assertEqual(len(list(debug_dir.glob("*_screen.png"))), 1)
            self.assertEqual(len(list(debug_dir.glob("*_annotated.png"))), 1)
            self.assertEqual(metadata["window"]["title"], "Browser")
            self.assertEqual(metadata["offsets"], {"left": -800, "top": 100})
            self.assertFalse(metadata["match"]["found"])
            self.assertEqual(metadata["match"]["best_region"], [-788, 108, 10, 8])
            self.assertGreater(metadata["match"]["score"], 0.9)
            self.assertEqual(metadata["match"]["scale"], 1.0)
            self.assertGreater(len(metadata["match"]["scale_scores"]), 20)

    def test_debug_retention_keeps_twenty_attempts(self):
        with TemporaryDirectory() as tmp:
            debug_dir = Path(tmp)
            for index in range(21):
                prefix = f"{index:02d}_capy"
                for suffix in ("_screen.png", "_annotated.png", "_metadata.json"):
                    (debug_dir / f"{prefix}{suffix}").write_bytes(b"x")

            template_matcher._prune_debug_attempts(debug_dir)

            self.assertEqual(len(list(debug_dir.glob("*_metadata.json"))), 20)
            self.assertFalse((debug_dir / "00_capy_metadata.json").exists())
            self.assertFalse((debug_dir / "00_capy_screen.png").exists())


class ClickTemplateTests(unittest.TestCase):
    def test_edge_positions_stay_inside_region(self):
        region = (10, 20, 30, 40)
        self.assertEqual(api._resolve_position(region, "top_right"), (39, 20))
        self.assertEqual(api._resolve_position(region, "bottom_right"), (39, 59))

    @patch("pytomator.core.vision.template_matcher.find_on_screen")
    @patch("pytomator.core.vision.capture_tool.get_active_search_region")
    @patch("pytomator.core.vision.capture_tool.get_active_window_info")
    @patch("pytomator.core.automator.api._get_project_path")
    @patch("pytomator.core.automator.api._get_template")
    @patch("pytomator.core.automator.api.pyautogui")
    def test_focus_change_cancels_click(
        self,
        pyautogui,
        get_template,
        get_project_path,
        get_active_window_info,
        get_active_search_region,
        find_on_screen,
    ):
        get_active_search_region.return_value = (
            {"left": 0, "top": 0, "width": 100, "height": 100},
            {"id": 1},
        )
        get_active_window_info.return_value = {"id": 2}
        find_on_screen.return_value = (10, 10, 20, 20)

        clicked = api.click_template("button")

        self.assertFalse(clicked)
        pyautogui.moveTo.assert_not_called()
        pyautogui.mouseDown.assert_not_called()

    @patch("pytomator.core.vision.template_matcher.find_on_screen")
    @patch("pytomator.core.vision.capture_tool.get_active_search_region")
    @patch("pytomator.core.vision.capture_tool.get_active_window_info")
    @patch("pytomator.core.automator.api._get_project_path")
    @patch("pytomator.core.automator.api._get_template")
    @patch("pytomator.core.automator.api.pyautogui")
    def test_standard_backend_moves_then_clicks(
        self,
        pyautogui,
        get_template,
        get_project_path,
        get_active_window_info,
        get_active_search_region,
        find_on_screen,
    ):
        get_active_search_region.return_value = (
            {"left": 0, "top": 0, "width": 100, "height": 100},
            {"id": 1},
        )
        get_active_window_info.return_value = {"id": 1}
        find_on_screen.return_value = (10, 10, 20, 20)

        clicked = api.click_template("button")

        self.assertTrue(clicked)
        pyautogui.moveTo.assert_called_once_with(20, 20)
        pyautogui.mouseDown.assert_called_once_with(button="primary")
        pyautogui.mouseUp.assert_called_once_with(button="primary")

    @patch("pytomator.core.vision.template_matcher.find_on_screen")
    @patch("pytomator.core.vision.capture_tool.get_active_search_region")
    @patch("pytomator.core.vision.capture_tool.get_active_window_info")
    @patch("pytomator.core.automator.api._get_project_path")
    @patch("pytomator.core.automator.api._get_template")
    @patch("pytomator.core.automator.api.pydirectinput")
    def test_directinput_backend_moves_then_clicks(
        self,
        directinput,
        get_template,
        get_project_path,
        get_active_window_info,
        get_active_search_region,
        find_on_screen,
    ):
        get_active_search_region.return_value = (
            {"left": 0, "top": 0, "width": 100, "height": 100},
            {"id": 1},
        )
        get_active_window_info.return_value = {"id": 1}
        find_on_screen.return_value = (10, 10, 20, 20)

        clicked = api.click_template("button", backend="directinput")

        self.assertTrue(clicked)
        directinput.moveTo.assert_called_once_with(20, 20)
        directinput.mouseDown.assert_called_once_with(button="left")
        directinput.mouseUp.assert_called_once_with(button="left")


if __name__ == "__main__":
    unittest.main()

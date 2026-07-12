import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
from unittest.mock import MagicMock

from pytomator.core.automator import api
from pytomator.project.models import Project
from pytomator.project.storage import ProjectStorage


class MouseBackendSettingsTests(unittest.TestCase):
    def tearDown(self):
        api.set_project_manager(None)

    def test_legacy_project_defaults_to_standard(self):
        project = Project.model_validate({"name": "Legacy"})
        self.assertEqual(project.settings.mouse_backend, "standard")
        self.assertEqual(project.settings.mouse_move_duration, 0.3)
        self.assertEqual(project.settings.mouse_move_easing, "ease_out")

    def test_mouse_backend_is_persisted(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "backend.pytom"
            project = Project(name="Backend")
            project.settings.mouse_backend = "directinput"
            project.settings.mouse_move_duration = 0.5
            project.settings.mouse_move_easing = "ease_in_out"
            storage = ProjectStorage()

            storage.save(project, path)
            loaded = storage.load(path)

            self.assertEqual(loaded.settings.mouse_backend, "directinput")
            self.assertEqual(loaded.settings.mouse_move_duration, 0.5)
            self.assertEqual(loaded.settings.mouse_move_easing, "ease_in_out")

    def test_project_backend_is_used_when_argument_is_omitted(self):
        project = Project(name="Backend")
        project.settings.mouse_backend = "directinput"
        api.set_project_manager(SimpleNamespace(project=project))

        with patch.object(api.sys, "platform", "win32"):
            self.assertEqual(api._resolve_mouse_backend(), "directinput")

    def test_explicit_backend_overrides_project_setting(self):
        project = Project(name="Backend")
        project.settings.mouse_backend = "directinput"
        api.set_project_manager(SimpleNamespace(project=project))

        self.assertEqual(api._resolve_mouse_backend("standard"), "standard")

    def test_configured_directinput_falls_back_outside_windows(self):
        project = Project(name="Backend")
        project.settings.mouse_backend = "directinput"
        api.set_project_manager(SimpleNamespace(project=project))

        with patch.object(api.sys, "platform", "linux"):
            self.assertEqual(api._resolve_mouse_backend(), "standard")

    def test_explicit_directinput_raises_outside_windows(self):
        with patch.object(api.sys, "platform", "linux"):
            with self.assertRaises(RuntimeError):
                api._resolve_mouse_backend("directinput")

    def test_movement_settings_use_project_and_allow_overrides(self):
        project = Project(name="Movement")
        project.settings.mouse_move_duration = 0.6
        project.settings.mouse_move_easing = "linear"
        api.set_project_manager(SimpleNamespace(project=project))

        self.assertEqual(api._resolve_mouse_movement(), (0.6, "linear"))
        self.assertEqual(
            api._resolve_mouse_movement(0.2, "ease_in_out"),
            (0.2, "ease_in_out"),
        )


class SmoothMouseMovementTests(unittest.TestCase):
    def test_interpolation_has_multiple_steps_and_exact_destination(self):
        positions = api._interpolate_mouse_positions(
            (0, 0), (101, 53), 0.3, "ease_out"
        )

        self.assertGreaterEqual(len(positions), 2)
        self.assertEqual(positions[-1], (101, 53))

    def test_easing_curves_have_expected_midpoint_behavior(self):
        linear = api._ease(0.25, "linear")
        ease_out = api._ease(0.25, "ease_out")
        ease_in_out = api._ease(0.25, "ease_in_out")

        self.assertLess(ease_in_out, linear)
        self.assertGreater(ease_out, linear)

    def test_zero_duration_teleports(self):
        mouse = MagicMock()
        mouse.position.return_value = (0, 0)
        with patch.object(api, "_mouse_for_backend", return_value=(mouse, "standard")):
            api._move_mouse_to((20, 30), duration=0, easing="linear")

        mouse.moveTo.assert_called_once_with(20, 30, _pause=False)

    def test_zero_duration_directinput_uses_relative_delta(self):
        mouse = MagicMock()
        mouse.position.side_effect = [(5, 7), (20, 30)]
        with patch.object(api, "_mouse_for_backend", return_value=(mouse, "directinput")):
            api._move_mouse_to((20, 30), duration=0, easing="linear")

        mouse.moveRel.assert_called_once_with(15, 23, relative=True, _pause=False)
        mouse.moveTo.assert_not_called()

    def test_public_move_to_uses_shared_backend_movement(self):
        with patch.object(api, "_move_mouse_to") as move:
            api.move_to(20, 30, duration=0.2, backend="directinput")
        move.assert_called_once_with(
            (20, 30), backend="directinput", duration=0.2, easing="linear"
        )

    @patch("pytomator.core.automator.api.time.sleep")
    def test_standard_backend_emits_multiple_absolute_positions(self, _sleep):
        mouse = MagicMock()
        mouse.position.return_value = (0, 0)
        with patch.object(api, "_mouse_for_backend", return_value=(mouse, "standard")):
            api._move_mouse_to((20, 30), duration=0.03, easing="linear")

        self.assertGreaterEqual(mouse.moveTo.call_count, 2)
        self.assertEqual(mouse.moveTo.call_args_list[-1].args, (20, 30))
        mouse.moveRel.assert_not_called()

    @patch("pytomator.core.automator.api.time.sleep")
    def test_directinput_backend_emits_relative_steps_and_corrects_position(self, _sleep):
        mouse = MagicMock()
        mouse.position.side_effect = [(0, 0), (19, 29)]
        with patch.object(api, "_mouse_for_backend", return_value=(mouse, "directinput")):
            api._move_mouse_to((20, 30), duration=0.03, easing="linear")

        self.assertGreaterEqual(mouse.moveRel.call_count, 2)
        for call in mouse.moveRel.call_args_list:
            self.assertTrue(call.kwargs["relative"])
        mouse.moveTo.assert_called_once_with(20, 30, _pause=False)

    def test_movement_can_be_interrupted(self):
        mouse = MagicMock()
        mouse.position.return_value = (0, 0)
        with (
            patch.object(api, "_mouse_for_backend", return_value=(mouse, "standard")),
            patch.object(api, "should_stop", return_value=True),
        ):
            with self.assertRaises(api.ScriptInterrupted):
                api._move_mouse_to((20, 30), duration=0.03, easing="linear")

    def test_invalid_duration_and_easing_are_rejected(self):
        with self.assertRaises(ValueError):
            api._resolve_mouse_movement(-0.1, "linear")
        with self.assertRaises(ValueError):
            api._resolve_mouse_movement(0.3, "bounce")


class SmoothTemplateApiTests(unittest.TestCase):
    def setUp(self):
        self.context = SimpleNamespace(window={"id": 1})

    @patch("pytomator.core.automator.api._move_mouse_to")
    @patch("pytomator.core.automator.api._window_still_active", return_value=True)
    @patch(
        "pytomator.core.automator.api._find_template_with_context",
        return_value=((10, 20, 20, 20), SimpleNamespace(window={"id": 1})),
    )
    def test_move_to_template_uses_smooth_movement(
        self, _find, _active, move_mouse
    ):
        moved = api.move_to_template(
            "target", duration=0.5, easing="ease_in_out", backend="standard"
        )

        self.assertTrue(moved)
        move_mouse.assert_called_once_with(
            (20, 30), backend="standard",
            duration=0.5, easing="ease_in_out",
        )

    @patch("pytomator.core.automator.api.time.sleep")
    @patch("pytomator.core.automator.api._move_mouse_to")
    @patch(
        "pytomator.core.automator.api._window_still_active",
        side_effect=[True, True],
    )
    @patch(
        "pytomator.core.automator.api._find_template_with_context",
        return_value=((10, 20, 20, 20), SimpleNamespace(window={"id": 1})),
    )
    def test_click_template_smooth_move_is_opt_in(
        self, _find, _active, move_mouse, _sleep
    ):
        mouse = MagicMock()
        with patch.object(
            api, "_mouse_for_backend", return_value=(mouse, "standard")
        ):
            clicked = api.click_template(
                "target", smooth_move=True,
                move_duration=0.4, move_easing="linear",
            )

        self.assertTrue(clicked)
        move_mouse.assert_called_once_with(
            (20, 30), backend="standard",
            duration=0.4, easing="linear",
        )
        mouse.moveTo.assert_not_called()
        mouse.mouseDown.assert_called_once()
        mouse.mouseUp.assert_called_once()

    @patch("pytomator.core.automator.api.time.sleep")
    @patch("pytomator.core.automator.api._move_mouse_to")
    @patch(
        "pytomator.core.automator.api._window_still_active",
        side_effect=[True, False],
    )
    @patch(
        "pytomator.core.automator.api._find_template_with_context",
        return_value=((10, 20, 20, 20), SimpleNamespace(window={"id": 1})),
    )
    def test_click_is_cancelled_if_focus_changes_during_smooth_move(
        self, _find, _active, _move_mouse, _sleep
    ):
        mouse = MagicMock()
        with patch.object(
            api, "_mouse_for_backend", return_value=(mouse, "standard")
        ):
            clicked = api.click_template("target", smooth_move=True)

        self.assertFalse(clicked)
        mouse.mouseDown.assert_not_called()
        mouse.mouseUp.assert_not_called()


if __name__ == "__main__":
    unittest.main()

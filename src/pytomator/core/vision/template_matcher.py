"""Template matching using OpenCV to find screen regions by image templates."""

from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from PIL import Image

from pytomator.core.vision.capture_tool import capture_full_screen, load_template_image
from pytomator.core.vision.models import TemplateCapture


def _pil_to_cv2(image: Image.Image) -> np.ndarray:
    """Convert a PIL Image to an OpenCV BGR numpy array."""
    return cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)


def find_on_screen(
    template: TemplateCapture,
    project_path: Path,
    confidence: Optional[float] = None,
) -> Optional[tuple[int, int, int, int]]:
    """Find a template on the current screen using template matching.

    Args:
        template: The TemplateCapture model with image path and default confidence.
        project_path: Root path of the project (to resolve image_path).
        confidence: Override confidence threshold (0.0 to 1.0).
                    If None, uses template.confidence.

    Returns:
        Tuple (x, y, w, h) of the best match region on screen,
        or None if no match meets the confidence threshold.
    """
    # Load template image
    template_img = load_template_image(project_path, template.image_path)
    if template_img is None:
        return None

    # Capture current screen
    screen_img = capture_full_screen()
    if screen_img is None:
        return None

    # Convert to OpenCV format
    screen_cv = _pil_to_cv2(screen_img)
    template_cv = _pil_to_cv2(template_img)

    # Get template dimensions
    t_h, t_w = template_cv.shape[:2]

    # Perform template matching
    result = cv2.matchTemplate(screen_cv, template_cv, cv2.TM_CCOEFF_NORMED)

    # Find best match
    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

    # Use the confidence threshold
    threshold = confidence if confidence is not None else template.confidence

    if max_val >= threshold:
        x, y = max_loc
        return (x, y, t_w, t_h)

    return None


def find_all_on_screen(
    template: TemplateCapture,
    project_path: Path,
    confidence: Optional[float] = None,
) -> list[tuple[int, int, int, int]]:
    """Find all occurrences of a template on the current screen.

    Args:
        template: The TemplateCapture model.
        project_path: Root path of the project.
        confidence: Override confidence threshold.

    Returns:
        List of (x, y, w, h) tuples for each match found.
    """
    # Load template image
    template_img = load_template_image(project_path, template.image_path)
    if template_img is None:
        return []

    # Capture current screen
    screen_img = capture_full_screen()
    if screen_img is None:
        return []

    # Convert to OpenCV format
    screen_cv = _pil_to_cv2(screen_img)
    template_cv = _pil_to_cv2(template_img)

    t_h, t_w = template_cv.shape[:2]

    # Perform template matching
    result = cv2.matchTemplate(screen_cv, template_cv, cv2.TM_CCOEFF_NORMED)

    threshold = confidence if confidence is not None else template.confidence

    # Find all locations above threshold
    locations = np.where(result >= threshold)
    matches: list[tuple[int, int, int, int]] = []

    # Group nearby matches using non-maximum suppression
    points = list(zip(locations[1], locations[0]))  # (x, y) pairs
    if not points:
        return []

    # Simple grouping: take unique locations with a minimum distance
    used = set()
    for x, y in points:
        # Check if this point is too close to an already used one
        too_close = False
        for ux, uy in used:
            if abs(x - ux) < t_w // 2 and abs(y - uy) < t_h // 2:
                too_close = True
                break
        if not too_close:
            used.add((x, y))
            matches.append((x, y, t_w, t_h))

    return matches


def locate_on_screen(
    template: TemplateCapture,
    project_path: Path,
    confidence: Optional[float] = None,
) -> Optional[tuple[int, int]]:
    """Find a template and return the center coordinates of the match.

    Args:
        template: The TemplateCapture model.
        project_path: Root path of the project.
        confidence: Override confidence threshold.

    Returns:
        Tuple (center_x, center_y) of the best match, or None.
    """
    result = find_on_screen(template, project_path, confidence)
    if result is None:
        return None
    x, y, w, h = result
    return (x + w // 2, y + h // 2)
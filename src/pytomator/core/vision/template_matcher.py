"""Template matching using OpenCV to find screen regions by image templates."""

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from PIL import Image, ImageDraw

from pytomator.core.vision.capture_tool import (
    capture_region,
    get_active_search_region,
    load_template_image,
)
from pytomator.core.vision.models import TemplateCapture


@dataclass
class MatchDetails:
    """Internal details for one best-match attempt."""

    region: Optional[tuple[int, int, int, int]]
    best_region: Optional[tuple[int, int, int, int]]
    score: Optional[float]
    threshold: float
    found: bool
    scale: Optional[float] = None
    original_size: Optional[tuple[int, int]] = None
    scaled_size: Optional[tuple[int, int]] = None
    scale_scores: list[dict] = field(default_factory=list)


def _pil_to_cv2(image: Image.Image) -> np.ndarray:
    """Convert a PIL Image to an OpenCV BGR numpy array."""
    return cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)


def _resize_template(template: np.ndarray, scale: float) -> np.ndarray:
    """Resize a template with interpolation suited to the scale direction."""
    height, width = template.shape[:2]
    scaled_width = max(1, round(width * scale))
    scaled_height = max(1, round(height * scale))
    interpolation = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_CUBIC
    if scaled_width == width and scaled_height == height:
        return template
    return cv2.resize(
        template,
        (scaled_width, scaled_height),
        interpolation=interpolation,
    )


def _scale_values(start: float, stop: float, step: float) -> list[float]:
    count = round((stop - start) / step)
    return [round(start + index * step, 2) for index in range(count + 1)]


def _best_multiscale_match(
    screen: np.ndarray,
    template: np.ndarray,
) -> tuple[Optional[float], Optional[tuple[int, int]], Optional[tuple[int, int]], list[dict]]:
    """Find the strongest template match using coarse and refined scale passes."""
    screen_height, screen_width = screen.shape[:2]
    scores: list[dict] = []
    evaluated_scales: set[float] = set()
    best_scale: Optional[float] = None
    best_location: Optional[tuple[int, int]] = None
    best_size: Optional[tuple[int, int]] = None
    best_score = float("-inf")

    def evaluate(scale: float) -> None:
        nonlocal best_scale, best_location, best_size, best_score
        scale = round(scale, 2)
        if scale in evaluated_scales:
            return
        evaluated_scales.add(scale)

        scaled = _resize_template(template, scale)
        scaled_height, scaled_width = scaled.shape[:2]
        if scaled_width > screen_width or scaled_height > screen_height:
            scores.append(
                {
                    "scale": scale,
                    "score": None,
                    "width": scaled_width,
                    "height": scaled_height,
                    "skipped": True,
                }
            )
            return

        result = cv2.matchTemplate(screen, scaled, cv2.TM_CCOEFF_NORMED)
        _, max_value, _, max_location = cv2.minMaxLoc(result)
        score = float(max_value)
        scores.append(
            {
                "scale": scale,
                "score": score,
                "width": scaled_width,
                "height": scaled_height,
                "skipped": False,
            }
        )
        if score > best_score:
            best_score = score
            best_scale = scale
            best_location = max_location
            best_size = (scaled_width, scaled_height)

    for scale in _scale_values(0.5, 3.0, 0.1):
        evaluate(scale)

    if best_scale is not None:
        refine_start = max(0.5, best_scale - 0.1)
        refine_stop = min(3.0, best_scale + 0.1)
        for scale in _scale_values(refine_start, refine_stop, 0.02):
            evaluate(scale)

    return best_scale, best_location, best_size, scores


def _project_dir(project_path: Path) -> Path:
    return project_path.parent if project_path.suffix == ".pytom" else project_path


def _prune_debug_attempts(debug_dir: Path, keep: int = 20) -> None:
    metadata_files = sorted(
        debug_dir.glob("*_metadata.json"),
        key=lambda path: (path.stat().st_mtime, path.name),
        reverse=True,
    )
    for metadata_path in metadata_files[keep:]:
        prefix = metadata_path.name.removesuffix("_metadata.json")
        for suffix in ("_screen.png", "_annotated.png", "_metadata.json"):
            artifact = debug_dir / f"{prefix}{suffix}"
            if artifact.exists():
                artifact.unlink()


def _save_debug_attempt(
    template: TemplateCapture,
    project_path: Path,
    screen_img: Image.Image,
    template_img: Image.Image,
    search_region: dict,
    window_info: Optional[dict],
    details: MatchDetails,
) -> None:
    debug_dir = _project_dir(project_path) / "vision_debug"
    debug_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", template.name).strip("_")
    prefix = f"{timestamp}_{safe_name or template.id}"

    screen_path = debug_dir / f"{prefix}_screen.png"
    annotated_path = debug_dir / f"{prefix}_annotated.png"
    metadata_path = debug_dir / f"{prefix}_metadata.json"
    screen_img.save(screen_path, "PNG")

    annotated = screen_img.convert("RGB")
    if details.best_region is not None:
        best_x, best_y, best_w, best_h = details.best_region
        local_x = best_x - search_region["left"]
        local_y = best_y - search_region["top"]
        color = "lime" if details.found else "red"
        ImageDraw.Draw(annotated).rectangle(
            (local_x, local_y, local_x + best_w - 1, local_y + best_h - 1),
            outline=color,
            width=3,
        )
    annotated.save(annotated_path, "PNG")

    metadata = {
        "timestamp": datetime.now().astimezone().isoformat(),
        "template": {
            "id": template.id,
            "name": template.name,
            "image_path": template.image_path,
            "size": {"width": template_img.width, "height": template_img.height},
        },
        "window": window_info or {},
        "search_region": dict(search_region),
        "screen_size": {"width": screen_img.width, "height": screen_img.height},
        "offsets": {
            "left": search_region["left"],
            "top": search_region["top"],
        },
        "match": asdict(details),
    }
    metadata_path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    _prune_debug_attempts(debug_dir)


def match_on_screen(
    template: TemplateCapture,
    project_path: Path,
    confidence: Optional[float] = None,
    search_region: Optional[dict] = None,
    *,
    debug: bool = False,
    window_info: Optional[dict] = None,
) -> MatchDetails:
    """Run one match and retain its best score independently of the threshold."""
    threshold = confidence if confidence is not None else template.confidence
    template_img = load_template_image(project_path, template.image_path)
    if template_img is None:
        return MatchDetails(None, None, None, threshold, False)

    if search_region is None:
        region, detected_window = get_active_search_region()
        window_info = window_info or detected_window
    else:
        region = search_region

    screen_img = capture_region(
        region["left"], region["top"], region["width"], region["height"]
    )
    if screen_img is None:
        return MatchDetails(None, None, None, threshold, False)

    screen_cv = _pil_to_cv2(screen_img)
    template_cv = _pil_to_cv2(template_img)
    t_h, t_w = template_cv.shape[:2]

    best_scale, best_location, best_size, scale_scores = _best_multiscale_match(
        screen_cv,
        template_cv,
    )
    if best_location is None or best_size is None:
        details = MatchDetails(
            None,
            None,
            None,
            threshold,
            False,
            original_size=(t_w, t_h),
            scale_scores=scale_scores,
        )
    else:
        x, y = best_location
        scaled_width, scaled_height = best_size
        best_region = (
            region["left"] + x,
            region["top"] + y,
            scaled_width,
            scaled_height,
        )
        best_score = max(
            item["score"]
            for item in scale_scores
            if item["score"] is not None
        )
        found = best_score >= threshold
        details = MatchDetails(
            best_region if found else None,
            best_region,
            best_score,
            threshold,
            found,
            scale=best_scale,
            original_size=(t_w, t_h),
            scaled_size=best_size,
            scale_scores=scale_scores,
        )

    if debug:
        _save_debug_attempt(
            template,
            project_path,
            screen_img,
            template_img,
            region,
            window_info,
            details,
        )
    return details


def find_on_screen(
    template: TemplateCapture,
    project_path: Path,
    confidence: Optional[float] = None,
    search_region: Optional[dict] = None,
    *,
    debug: bool = False,
    window_info: Optional[dict] = None,
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
    return match_on_screen(
        template,
        project_path,
        confidence,
        search_region,
        debug=debug,
        window_info=window_info,
    ).region


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

    region, _ = get_active_search_region()
    screen_img = capture_region(
        region["left"], region["top"], region["width"], region["height"]
    )
    if screen_img is None:
        return []

    # Convert to OpenCV format
    screen_cv = _pil_to_cv2(screen_img)
    template_cv = _pil_to_cv2(template_img)

    t_h, t_w = template_cv.shape[:2]
    if t_w > screen_cv.shape[1] or t_h > screen_cv.shape[0]:
        return []

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
            matches.append((region["left"] + x, region["top"] + y, t_w, t_h))

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

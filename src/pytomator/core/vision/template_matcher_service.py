"""Stateful, project-scoped template matching service."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from PIL import Image

from pytomator.core.vision.models import TemplateCapture


@dataclass
class _TemplateCache:
    signature: tuple
    image: Image.Image
    gray: np.ndarray
    scaled: dict[float, np.ndarray] = field(default_factory=dict)


class TemplateMatcher:
    """Match project templates while retaining safe, reusable search state."""

    def __init__(self, project_path: Path):
        self.project_path = Path(project_path)
        self._templates: dict[str, _TemplateCache] = {}
        self._scale_cache: dict[str, float] = {}
        self._last_regions: dict[str, tuple[int, int, int, int]] = {}

    @property
    def project_dir(self) -> Path:
        return (
            self.project_path.parent
            if self.project_path.suffix == ".pytom"
            else self.project_path
        )

    def clear(self) -> None:
        self._templates.clear()
        self._scale_cache.clear()
        self._last_regions.clear()

    @staticmethod
    def _template_key(template: TemplateCapture) -> str:
        return str(getattr(template, "id", template.image_path))

    def reset_search_state(self) -> None:
        self._scale_cache.clear()
        self._last_regions.clear()

    def _signature(self, template: TemplateCapture) -> tuple:
        path = self.project_dir / template.image_path
        try:
            stat = path.stat()
            file_signature = (stat.st_mtime_ns, stat.st_size)
        except OSError:
            file_signature = (None, None)
        return (
            str(path.resolve()),
            *file_signature,
            getattr(template, "multi_scale_enabled", False),
            getattr(template, "min_scale", 1.0),
            getattr(template, "max_scale", 1.0),
        )

    def _load(self, template: TemplateCapture) -> Optional[_TemplateCache]:
        # Import the compatibility module lazily. Besides avoiding a cycle, this
        # keeps its capture/load seams patchable by existing integrations.
        from pytomator.core.vision import template_matcher as helpers

        signature = self._signature(template)
        key = self._template_key(template)
        cached = self._templates.get(key)
        if cached is not None and cached.signature == signature:
            return cached
        image = helpers.load_template_image(self.project_path, template.image_path)
        if image is None:
            self._templates.pop(key, None)
            return None
        image = image.convert("RGB")
        entry = _TemplateCache(
            signature=signature,
            image=image,
            gray=cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2GRAY),
        )
        self._templates[key] = entry
        self._scale_cache.pop(key, None)
        self._last_regions.pop(key, None)
        return entry

    @staticmethod
    def _intersection(a: dict, b: tuple[int, int, int, int]) -> Optional[dict]:
        left = max(a["left"], b[0])
        top = max(a["top"], b[1])
        right = min(a["left"] + a["width"], b[0] + b[2])
        bottom = min(a["top"] + a["height"], b[1] + b[3])
        if right <= left or bottom <= top:
            return None
        return {"left": left, "top": top, "width": right - left, "height": bottom - top}

    def _local_region(self, template_id: str, search_region: dict) -> Optional[dict]:
        previous = self._last_regions.get(template_id)
        if previous is None:
            return None
        x, y, width, height = previous
        padding_x = max(width * 2, 32)
        padding_y = max(height * 2, 32)
        return self._intersection(
            search_region,
            (x - padding_x, y - padding_y, width + 2 * padding_x, height + 2 * padding_y),
        )

    def _scaled(self, entry: _TemplateCache, scale: float) -> np.ndarray:
        from pytomator.core.vision.template_matcher import _resize_template

        key = round(scale, 2)
        if key not in entry.scaled:
            entry.scaled[key] = _resize_template(entry.gray, key)
        return entry.scaled[key]

    def _best_match(self, screen: np.ndarray, entry: _TemplateCache,
                    min_scale: float, max_scale: float, refine: bool = True):
        from pytomator.core.vision.template_matcher import _scale_values

        sh, sw = screen.shape[:2]
        scores, evaluated = [], set()
        best_scale = best_location = best_size = None
        best_score = float("-inf")

        def evaluate(scale):
            nonlocal best_scale, best_location, best_size, best_score
            scale = round(scale, 2)
            if scale in evaluated:
                return
            evaluated.add(scale)
            scaled = self._scaled(entry, scale)
            height, width = scaled.shape[:2]
            if width > sw or height > sh:
                scores.append({"scale": scale, "score": None, "width": width,
                               "height": height, "skipped": True})
                return
            result = cv2.matchTemplate(screen, scaled, cv2.TM_CCOEFF_NORMED)
            _, value, _, location = cv2.minMaxLoc(result)
            value = float(value)
            scores.append({"scale": scale, "score": value, "width": width,
                           "height": height, "skipped": False})
            if value > best_score:
                best_scale, best_location, best_size, best_score = (
                    scale, location, (width, height), value
                )

        scales = ([round(min_scale, 2)] if min_scale == max_scale
                  else _scale_values(min_scale, max_scale, 0.1))
        if scales[-1] != round(max_scale, 2):
            scales.append(round(max_scale, 2))
        for scale in scales:
            evaluate(scale)
        if refine and min_scale < max_scale and best_scale is not None:
            for scale in _scale_values(
                max(min_scale, best_scale - 0.1),
                min(max_scale, best_scale + 0.1),
                0.02,
            ):
                evaluate(scale)
        return best_scale, best_location, best_size, scores

    def _match_region(self, template, entry, region, threshold):
        from pytomator.core.vision import template_matcher as helpers

        screen_image = helpers.capture_region(
            region["left"], region["top"], region["width"], region["height"]
        )
        if screen_image is None:
            return None, None
        screen = cv2.cvtColor(np.asarray(screen_image.convert("RGB")), cv2.COLOR_RGB2GRAY)
        multi = template.multi_scale_enabled
        minimum, maximum = ((template.min_scale, template.max_scale) if multi else (1.0, 1.0))
        key = self._template_key(template)
        cached_scale = self._scale_cache.get(key) if multi else None
        mode = "single_scale"
        if cached_scale is not None and minimum <= cached_scale <= maximum:
            result = self._best_match(screen, entry, cached_scale, cached_scale, False)
            score = next((x["score"] for x in result[3] if x["score"] is not None), None)
            if score is not None and score >= threshold:
                mode = "scale_cache"
            else:
                result = self._best_match(screen, entry, minimum, maximum)
                mode = "multi_scale"
        else:
            result = self._best_match(screen, entry, minimum, maximum, multi)
            if multi:
                mode = "multi_scale"
        return (screen_image, result, mode, minimum, maximum), screen

    def match_on_screen(self, template: TemplateCapture, confidence=None,
                        search_region=None, *, debug=False, window_info=None):
        from pytomator.core.vision import template_matcher as helpers

        threshold = confidence if confidence is not None else template.confidence
        entry = self._load(template)
        if entry is None:
            return helpers.MatchDetails(None, None, None, threshold, False)
        if search_region is None:
            search_region, detected = helpers.get_active_search_region()
            window_info = window_info or detected

        key = self._template_key(template)
        local = self._local_region(key, search_region)
        attempts = [local, search_region] if local and local != search_region else [search_region]
        final = None
        for region in attempts:
            packed, _ = self._match_region(template, entry, region, threshold)
            if packed is None:
                continue
            screen_image, (scale, location, size, scores), mode, minimum, maximum = packed
            if location is None or size is None:
                details = helpers.MatchDetails(
                    None, None, None, threshold, False,
                    original_size=(entry.gray.shape[1], entry.gray.shape[0]),
                    scale_scores=scores, mode=mode, scale_range=(minimum, maximum),
                )
            else:
                x, y = location
                width, height = size
                best_region = (region["left"] + x, region["top"] + y, width, height)
                score = max(item["score"] for item in scores if item["score"] is not None)
                found = score >= threshold
                details = helpers.MatchDetails(
                    best_region if found else None, best_region, score, threshold, found,
                    scale=scale, original_size=(entry.gray.shape[1], entry.gray.shape[0]),
                    scaled_size=size, scale_scores=scores, mode=mode,
                    scale_range=(minimum, maximum),
                )
            final = details
            if details.found:
                self._last_regions[key] = details.region
                if template.multi_scale_enabled and details.scale is not None:
                    self._scale_cache[key] = details.scale
                if debug:
                    helpers._save_debug_attempt(
                        template, self.project_path, screen_image, entry.image,
                        region, window_info, details,
                    )
                return details
        if debug and final is not None:
            helpers._save_debug_attempt(
                template, self.project_path, screen_image, entry.image,
                attempts[-1], window_info, final,
            )
        return final or helpers.MatchDetails(None, None, None, threshold, False)

    def find_on_screen(self, template, confidence=None, search_region=None, **kwargs):
        return self.match_on_screen(
            template, confidence, search_region, **kwargs
        ).region

    def find_all_on_screen(self, template, confidence=None, search_region=None):
        # Keep find-all semantics stable while sharing the cached grayscale template.
        from pytomator.core.vision import template_matcher as helpers

        entry = self._load(template)
        if entry is None:
            return []
        if search_region is None:
            search_region, _ = helpers.get_active_search_region()
        image = helpers.capture_region(
            search_region["left"], search_region["top"],
            search_region["width"], search_region["height"],
        )
        if image is None:
            return []
        screen = cv2.cvtColor(np.asarray(image.convert("RGB")), cv2.COLOR_RGB2GRAY)
        height, width = entry.gray.shape[:2]
        if width > screen.shape[1] or height > screen.shape[0]:
            return []
        result = cv2.matchTemplate(screen, entry.gray, cv2.TM_CCOEFF_NORMED)
        threshold = confidence if confidence is not None else template.confidence
        ys, xs = np.where(result >= threshold)
        used, matches = set(), []
        for x, y in zip(xs, ys):
            if any(abs(x - ux) < width // 2 and abs(y - uy) < height // 2
                   for ux, uy in used):
                continue
            used.add((x, y))
            matches.append((search_region["left"] + int(x),
                            search_region["top"] + int(y), width, height))
        return matches

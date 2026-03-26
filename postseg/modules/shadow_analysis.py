from collections import Counter
from pathlib import Path

import cv2
import numpy as np

from postseg.pipeline.base_pipeline import PipelineStep


class ShadowAnalysisStep(PipelineStep):
    def __init__(self, name, params=None):
        super().__init__(name, params)
        self._source_image = self.params.get('source_image')

    def _compute_non_black_mask(self, image):
        black_thresh = int(self.params.get('black_thresh', 10))
        channels = image[:, :, :3] if image.ndim == 3 and image.shape[2] > 3 else image
        return np.any(channels > black_thresh, axis=2)

    def _resolve_input_image(self, image):
        source_image = self.params.get('source_image')
        if source_image is not None and source_image.shape == image.shape:
            return source_image
        if self._source_image is not None and self._source_image.shape == image.shape:
            return self._source_image
        return image

    def _resolve_analysis_image(self, image):
        analysis_path = self.params.get('analysis_image_path')
        if analysis_path:
            analysis_image = cv2.imread(str(analysis_path))
            if analysis_image is not None:
                return analysis_image
        analysis_image = self.params.get('analysis_image')
        if analysis_image is not None and analysis_image.shape == image.shape:
            return analysis_image
        return image

    def _resolve_color_output_path(self):
        color_output_path = self.params.get('color_output_path')
        if color_output_path:
            return Path(color_output_path)
        output_path = self.params.get('output_path')
        if output_path:
            output_path = Path(output_path)
            suffix = output_path.suffix or '.png'
            name = output_path.stem
            lowered = name.lower()
            if 'shadow' in lowered:
                name = name[: lowered.rfind('shadow')].rstrip('_-.') or 'mode_color'
            return output_path.with_name(f"{name}{suffix}")
        return Path('outputs/mode_color.jpg')

    def _resolve_base_output_path(self):
        output_path = self.params.get('output_path')
        if output_path:
            return Path(output_path)
        color_output_path = self._resolve_color_output_path()
        suffix = color_output_path.suffix or '.png'
        return color_output_path.with_name(f"{color_output_path.stem}_shadow{suffix}")

    def _discover_mask_paths(self, color_output_path):
        candidate_paths = []
        if color_output_path.exists():
            candidate_paths.append(color_output_path)

        pattern = f"{color_output_path.stem}_hue_*{color_output_path.suffix}"
        split_paths = sorted(color_output_path.parent.glob(pattern))
        if split_paths:
            return split_paths
        return candidate_paths

    def _build_shadow_mask(self, region_mask, l_channel):
        l_values = l_channel[region_mask].astype(np.float32)
        if l_values.size == 0:
            return region_mask & False, 0.0, 0.0

        shadow_percentile = float(self.params.get('shadow_percentile', 0.3))
        shadow_percentile = min(max(shadow_percentile, 0.0), 1.0)
        cutoff = float(np.percentile(l_values, shadow_percentile * 100.0))
        shadow_mask = region_mask & (l_channel.astype(np.float32) <= cutoff)

        region_pixels = max(1, int(region_mask.sum()))
        shadow_ratio = float(shadow_mask.sum()) / float(region_pixels)
        return shadow_mask, cutoff, shadow_ratio

    def _build_morph_kernel(self, size):
        size = max(1, int(size))
        if size % 2 == 0:
            size += 1
        return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))

    def _apply_shadow_morphology(self, shadow_mask):
        morph_cfg = self.params.get('morphology', {}) or {}
        enabled = bool(morph_cfg.get('enabled', False))
        if not enabled:
            return shadow_mask, []

        processed = shadow_mask.astype(np.uint8) * 255
        operations = []

        open_kernel = int(morph_cfg.get('open_kernel', 0) or 0)
        if open_kernel > 0:
            kernel = self._build_morph_kernel(open_kernel)
            processed = cv2.morphologyEx(processed, cv2.MORPH_OPEN, kernel)
            operations.append({'op': 'open', 'kernel': open_kernel})

        close_kernel = int(morph_cfg.get('close_kernel', 0) or 0)
        if close_kernel > 0:
            kernel = self._build_morph_kernel(close_kernel)
            processed = cv2.morphologyEx(processed, cv2.MORPH_CLOSE, kernel)
            operations.append({'op': 'close', 'kernel': close_kernel})

        dilate_kernel = int(morph_cfg.get('dilate_kernel', 0) or 0)
        dilate_iterations = max(1, int(morph_cfg.get('dilate_iterations', 1)))
        if dilate_kernel > 0:
            kernel = self._build_morph_kernel(dilate_kernel)
            processed = cv2.dilate(processed, kernel, iterations=dilate_iterations)
            operations.append({'op': 'dilate', 'kernel': dilate_kernel, 'iterations': dilate_iterations})

        erode_kernel = int(morph_cfg.get('erode_kernel', 0) or 0)
        erode_iterations = max(1, int(morph_cfg.get('erode_iterations', 1)))
        if erode_kernel > 0:
            kernel = self._build_morph_kernel(erode_kernel)
            processed = cv2.erode(processed, kernel, iterations=erode_iterations)
            operations.append({'op': 'erode', 'kernel': erode_kernel, 'iterations': erode_iterations})

        return processed > 0, operations

    def _compute_mode_color(self, image, mask):
        valid_mask = mask & self._compute_non_black_mask(image)
        if not np.any(valid_mask):
            return [0, 0, 0]
        pixels = [tuple(px) for px in image[valid_mask]]
        return list(Counter(pixels).most_common(1)[0][0])

    def _build_region_shadow_output_path(self, region_path, base_output_path, multiple_regions):
        if not multiple_regions:
            return str(base_output_path)
        region_path = Path(region_path)
        return str(region_path.with_name(f"{region_path.stem}_shadow{region_path.suffix or base_output_path.suffix or '.png'}"))

    def _analyze_single_region(self, mask_image, working_image, source_image):
        region_mask = self._compute_non_black_mask(mask_image)
        if not np.any(region_mask):
            return np.zeros_like(source_image), None

        lab = cv2.cvtColor(working_image[:, :, :3], cv2.COLOR_BGR2LAB)
        l_channel = lab[:, :, 0]
        l_values = l_channel[region_mask].astype(np.float32)
        if l_values.size == 0:
            return np.zeros_like(source_image), None

        shadow_mask, cutoff, shadow_ratio = self._build_shadow_mask(region_mask, l_channel)
        shadow_mask, morphology_ops = self._apply_shadow_morphology(shadow_mask)
        shadow_ratio = float(shadow_mask.sum()) / float(max(1, int(region_mask.sum())))

        result = np.zeros_like(source_image)
        if np.any(shadow_mask):
            mode_color = self._compute_mode_color(source_image, shadow_mask)
            result[shadow_mask] = mode_color
        else:
            mode_color = [0, 0, 0]

        stats = {
            'region_pixels': int(region_mask.sum()),
            'shadow_pixels': int(shadow_mask.sum()),
            'l_mean': float(np.mean(l_values)),
            'l_sigma': float(np.std(l_values)),
            'l_cutoff': float(cutoff),
            'shadow_ratio': float(shadow_ratio),
            'morphology_operations': morphology_ops,
            'mode_color': mode_color,
        }
        return result, stats

    def process(self, image):
        source_image = self._resolve_input_image(image)
        working_image = self._resolve_analysis_image(image)
        color_output_path = self._resolve_color_output_path()
        base_output_path = self._resolve_base_output_path()
        base_output_path.parent.mkdir(parents=True, exist_ok=True)

        region_paths = self._discover_mask_paths(color_output_path)
        if not region_paths:
            empty = np.zeros_like(source_image)
            cv2.imwrite(str(base_output_path), empty)
            self.params['last_shadow_region_paths'] = []
            self.params['last_shadow_regions'] = []
            return working_image

        multiple_regions = len(region_paths) > 1
        combined_shadow = np.zeros_like(source_image)
        saved_paths = []
        shadow_regions = []

        for idx, region_path in enumerate(region_paths):
            mask_image = cv2.imread(str(region_path))
            if mask_image is None or mask_image.shape != working_image.shape:
                continue

            shadow_image, stats = self._analyze_single_region(mask_image, working_image, source_image)
            region_output_path = self._build_region_shadow_output_path(region_path, base_output_path, multiple_regions)
            cv2.imwrite(region_output_path, shadow_image)
            saved_paths.append(region_output_path)
            shadow_pixels = np.any(shadow_image > 0, axis=2)
            if np.any(shadow_pixels):
                combined_shadow[shadow_pixels] = shadow_image[shadow_pixels]

            shadow_regions.append({
                'index': idx,
                'mask_path': str(region_path),
                'output_path': region_output_path,
                **(stats or {
                    'region_pixels': 0,
                    'shadow_pixels': 0,
                    'l_mean': 0.0,
                    'l_sigma': 0.0,
                    'l_cutoff': 0.0,
                    'mode_color': [0, 0, 0],
                }),
            })

        if multiple_regions:
            cv2.imwrite(str(base_output_path), combined_shadow)
        elif saved_paths:
            cv2.imwrite(str(base_output_path), combined_shadow)

        self.params['last_shadow_region_paths'] = saved_paths
        self.params['last_shadow_regions'] = shadow_regions
        return working_image

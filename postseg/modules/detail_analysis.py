from collections import Counter
from pathlib import Path

import cv2
import numpy as np

from postseg.pipeline.base_pipeline import PipelineStep


class DetailAnalysisStep(PipelineStep):
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
            if 'detail' in lowered:
                name = name[: lowered.rfind('detail')].rstrip('_-.') or 'mode_color'
            return output_path.with_name(f"{name}{suffix}")
        return Path('outputs/mode_color.jpg')

    def _resolve_base_output_path(self):
        output_path = self.params.get('output_path')
        if output_path:
            return Path(output_path)
        color_output_path = self._resolve_color_output_path()
        suffix = color_output_path.suffix or '.png'
        return color_output_path.with_name(f"{color_output_path.stem}_detail{suffix}")

    def _resolve_source_color_output_path(self):
        source_color_output_path = self.params.get('source_color_output_path')
        if source_color_output_path:
            return Path(source_color_output_path)
        base_output_path = self._resolve_base_output_path()
        suffix = base_output_path.suffix or '.png'
        return base_output_path.with_name(f"{base_output_path.stem}_source{suffix}")

    def _resolve_source_gray_overlay_output_path(self):
        gray_overlay_output_path = self.params.get('source_gray_overlay_output_path')
        if gray_overlay_output_path:
            return Path(gray_overlay_output_path)
        source_color_output_path = self._resolve_source_color_output_path()
        suffix = source_color_output_path.suffix or '.png'
        return source_color_output_path.with_name(f"{source_color_output_path.stem}_gray_overlay{suffix}")

    def _discover_mask_paths(self, color_output_path):
        candidate_paths = []
        if color_output_path.exists():
            candidate_paths.append(color_output_path)

        pattern = f"{color_output_path.stem}_hue_*{color_output_path.suffix}"
        split_paths = sorted(color_output_path.parent.glob(pattern))
        if split_paths:
            return split_paths
        return candidate_paths

    def _build_highlight_mask(self, region_mask, s_channel, v_channel):
        s_values = s_channel[region_mask].astype(np.float32)
        v_values = v_channel[region_mask].astype(np.float32)
        if s_values.size == 0 or v_values.size == 0:
            return region_mask & False, {
                's_cutoff': 0.0,
                'v_cutoff': 0.0,
                'used_v_only_fallback': False,
            }

        white_s_percentile = float(self.params.get('white_s_percentile', 0.3))
        white_s_percentile = min(max(white_s_percentile, 0.0), 1.0)
        s_cutoff = float(np.percentile(s_values, white_s_percentile * 100.0))

        white_v_percentile = self.params.get('white_v_percentile')
        if white_v_percentile is None:
            white_v_percentile = self.params.get('highlight_percentile', 0.1)
        white_v_percentile = float(white_v_percentile)
        white_v_percentile = min(max(white_v_percentile, 0.0), 1.0)
        v_cutoff = float(np.percentile(v_values, (1.0 - white_v_percentile) * 100.0))

        white_highlight_mask = region_mask & (s_channel.astype(np.float32) <= s_cutoff) & (v_channel.astype(np.float32) >= v_cutoff)

        used_v_only_fallback = False
        if not np.any(white_highlight_mask):
            white_highlight_mask = region_mask & (v_channel.astype(np.float32) >= v_cutoff)
            used_v_only_fallback = True

        return white_highlight_mask, {
            's_cutoff': float(s_cutoff),
            'v_cutoff': float(v_cutoff),
            'used_v_only_fallback': used_v_only_fallback,
        }

    def _circular_hue_distance(self, hue_channel, dominant_hue):
        hue = hue_channel.astype(np.float32)
        diff = np.abs(hue - float(dominant_hue))
        return np.minimum(diff, 180.0 - diff)

    def _build_detail_mask(self, region_mask, h_channel, s_channel, v_channel):
        min_saturation = int(self.params.get('detail_hue_min_saturation', 20))
        min_value = int(self.params.get('detail_hue_min_value', 20))
        hue_valid_mask = region_mask & (s_channel >= min_saturation) & (v_channel >= min_value)
        if not np.any(hue_valid_mask):
            return region_mask & False, {
                'dominant_hue': -1,
                'hue_delta': 0.0,
                'hue_valid_pixels': 0,
            }

        hue_values = h_channel[hue_valid_mask].astype(np.int32)
        hist = np.bincount(hue_values, minlength=180)
        dominant_hue = int(np.argmax(hist))

        hue_delta = float(self.params.get('detail_hue_delta', 10.0))
        hue_delta = max(0.0, min(90.0, hue_delta))

        hue_distance = self._circular_hue_distance(h_channel, dominant_hue)
        non_dominant_mask = hue_valid_mask & (hue_distance > hue_delta)

        return non_dominant_mask, {
            'dominant_hue': dominant_hue,
            'hue_delta': float(hue_delta),
            'hue_valid_pixels': int(hue_valid_mask.sum()),
        }

    def _build_morph_kernel(self, size):
        size = max(1, int(size))
        if size % 2 == 0:
            size += 1
        return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))

    def _apply_detail_morphology(self, detail_mask):
        morph_cfg = self.params.get('morphology', {}) or {}
        enabled = bool(morph_cfg.get('enabled', False))
        if not enabled:
            return detail_mask, []

        processed = detail_mask.astype(np.uint8) * 255
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

    def _build_region_detail_output_path(self, region_path, base_output_path, multiple_regions):
        if not multiple_regions:
            return str(base_output_path)
        region_path = Path(region_path)
        return str(region_path.with_name(f"{region_path.stem}_detail{region_path.suffix or base_output_path.suffix or '.png'}"))

    def _build_region_source_detail_output_path(self, region_path, source_color_output_path, multiple_regions):
        if not multiple_regions:
            return str(source_color_output_path)
        region_path = Path(region_path)
        suffix = region_path.suffix or source_color_output_path.suffix or '.png'
        return str(region_path.with_name(f"{region_path.stem}_detail_source{suffix}"))

    def _build_region_source_gray_overlay_output_path(self, region_path, gray_overlay_output_path, multiple_regions):
        if not multiple_regions:
            return str(gray_overlay_output_path)
        region_path = Path(region_path)
        suffix = region_path.suffix or gray_overlay_output_path.suffix or '.png'
        return str(region_path.with_name(f"{region_path.stem}_detail_source_gray_overlay{suffix}"))

    def _build_gray_overlay_image(self, source_image, source_detail_image):
        source_bgr = source_image[:, :, :3]
        gray = cv2.cvtColor(source_bgr, cv2.COLOR_BGR2GRAY)
        gray_bgr = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        gray_alpha = float(self.params.get('gray_overlay_alpha', 1.0))
        gray_alpha = min(max(gray_alpha, 0.0), 1.0)
        overlay_layer = cv2.addWeighted(gray_bgr, gray_alpha, np.zeros_like(gray_bgr), 1.0 - gray_alpha, 0.0)
        mask = np.any(source_detail_image > 0, axis=2)
        if np.any(mask):
            overlay_layer[mask] = source_detail_image[mask]
        return overlay_layer

    def _analyze_single_region(self, mask_image, working_image, source_image):
        region_mask = self._compute_non_black_mask(mask_image)
        if not np.any(region_mask):
            return np.zeros_like(source_image), np.zeros_like(source_image), None

        bgr = working_image[:, :, :3]
        lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
        l_channel = lab[:, :, 0]
        l_values = l_channel[region_mask].astype(np.float32)
        if l_values.size == 0:
            return np.zeros_like(source_image), np.zeros_like(source_image), None

        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        h_channel = hsv[:, :, 0]
        s_channel = hsv[:, :, 1]
        v_channel = hsv[:, :, 2]
        highlight_mask, highlight_meta = self._build_highlight_mask(region_mask, s_channel, v_channel)
        detail_mask, detail_meta = self._build_detail_mask(region_mask, h_channel, s_channel, v_channel)
        mixed_mask = (highlight_mask | detail_mask) & region_mask
        mixed_mask, morphology_ops = self._apply_detail_morphology(mixed_mask)
        mixed_mask = mixed_mask & region_mask

        mode_result = np.zeros_like(source_image)
        source_result = np.zeros_like(source_image)
        if np.any(mixed_mask):
            mode_color = self._compute_mode_color(source_image, mixed_mask)
            mode_result[mixed_mask] = mode_color
            source_result[mixed_mask] = source_image[mixed_mask]
        else:
            mode_color = [0, 0, 0]

        region_pixels = max(1, int(region_mask.sum()))
        highlight_pixels = int((highlight_mask & region_mask).sum())
        detail_pixels = int((detail_mask & region_mask).sum())
        mixed_pixels = int(mixed_mask.sum())

        stats = {
            'region_pixels': int(region_mask.sum()),
            'detail_pixels': mixed_pixels,
            'highlight_seed_pixels': highlight_pixels,
            'texture_seed_pixels': detail_pixels,
            'l_mean': float(np.mean(l_values)),
            'l_sigma': float(np.std(l_values)),
            'white_s_cutoff': float(highlight_meta.get('s_cutoff', 0.0)),
            'white_v_cutoff': float(highlight_meta.get('v_cutoff', 0.0)),
            'highlight_used_v_only_fallback': bool(highlight_meta.get('used_v_only_fallback', False)),
            'dominant_hue': int(detail_meta.get('dominant_hue', -1)),
            'detail_hue_delta': float(detail_meta.get('hue_delta', 0.0)),
            'detail_hue_valid_pixels': int(detail_meta.get('hue_valid_pixels', 0)),
            'detail_ratio': float(mixed_pixels) / float(region_pixels),
            'morphology_operations': morphology_ops,
            'mode_color': mode_color,
        }
        return mode_result, source_result, stats

    def process(self, image):
        source_image = self._resolve_input_image(image)
        working_image = self._resolve_analysis_image(image)
        color_output_path = self._resolve_color_output_path()
        base_output_path = self._resolve_base_output_path()
        source_color_output_path = self._resolve_source_color_output_path()
        gray_overlay_output_path = self._resolve_source_gray_overlay_output_path()
        base_output_path.parent.mkdir(parents=True, exist_ok=True)
        source_color_output_path.parent.mkdir(parents=True, exist_ok=True)
        gray_overlay_output_path.parent.mkdir(parents=True, exist_ok=True)

        region_paths = self._discover_mask_paths(color_output_path)
        if not region_paths:
            empty = np.zeros_like(source_image)
            gray_bgr = self._build_gray_overlay_image(source_image, np.zeros_like(source_image))
            cv2.imwrite(str(base_output_path), empty)
            cv2.imwrite(str(source_color_output_path), empty)
            cv2.imwrite(str(gray_overlay_output_path), gray_bgr)
            self.params['last_detail_region_paths'] = []
            self.params['last_detail_source_region_paths'] = []
            self.params['last_detail_gray_overlay_region_paths'] = []
            self.params['last_detail_regions'] = []
            return working_image

        multiple_regions = len(region_paths) > 1
        combined_detail = np.zeros_like(source_image)
        combined_source_detail = np.zeros_like(source_image)
        combined_gray_overlay = self._build_gray_overlay_image(source_image, np.zeros_like(source_image))
        saved_paths = []
        saved_source_paths = []
        saved_gray_overlay_paths = []
        detail_regions = []

        for idx, region_path in enumerate(region_paths):
            mask_image = cv2.imread(str(region_path))
            if mask_image is None or mask_image.shape != working_image.shape:
                continue

            detail_image, source_detail_image, stats = self._analyze_single_region(mask_image, working_image, source_image)
            region_output_path = self._build_region_detail_output_path(region_path, base_output_path, multiple_regions)
            region_source_output_path = self._build_region_source_detail_output_path(region_path, source_color_output_path, multiple_regions)
            region_gray_overlay_output_path = self._build_region_source_gray_overlay_output_path(region_path, gray_overlay_output_path, multiple_regions)
            region_gray_overlay_image = self._build_gray_overlay_image(source_image, source_detail_image)
            cv2.imwrite(region_output_path, detail_image)
            cv2.imwrite(region_source_output_path, source_detail_image)
            cv2.imwrite(region_gray_overlay_output_path, region_gray_overlay_image)
            saved_paths.append(region_output_path)
            saved_source_paths.append(region_source_output_path)
            saved_gray_overlay_paths.append(region_gray_overlay_output_path)

            detail_pixels = np.any(detail_image > 0, axis=2)
            if np.any(detail_pixels):
                combined_detail[detail_pixels] = detail_image[detail_pixels]
            source_detail_pixels = np.any(source_detail_image > 0, axis=2)
            if np.any(source_detail_pixels):
                combined_source_detail[source_detail_pixels] = source_detail_image[source_detail_pixels]
                combined_gray_overlay[source_detail_pixels] = source_detail_image[source_detail_pixels]

            detail_regions.append({
                'index': idx,
                'mask_path': str(region_path),
                'output_path': region_output_path,
                'source_output_path': region_source_output_path,
                'gray_overlay_output_path': region_gray_overlay_output_path,
                **(stats or {
                    'region_pixels': 0,
                    'detail_pixels': 0,
                    'l_mean': 0.0,
                    'l_sigma': 0.0,
                    'white_s_cutoff': 0.0,
                    'white_v_cutoff': 0.0,
                    'dominant_hue': -1,
                    'detail_hue_delta': 0.0,
                    'detail_hue_valid_pixels': 0,
                    'mode_color': [0, 0, 0],
                }),
            })

        if multiple_regions:
            cv2.imwrite(str(base_output_path), combined_detail)
            cv2.imwrite(str(source_color_output_path), combined_source_detail)
            cv2.imwrite(str(gray_overlay_output_path), combined_gray_overlay)
        elif saved_paths:
            cv2.imwrite(str(base_output_path), combined_detail)
            cv2.imwrite(str(source_color_output_path), combined_source_detail)
            cv2.imwrite(str(gray_overlay_output_path), combined_gray_overlay)

        self.params['last_detail_region_paths'] = saved_paths
        self.params['last_detail_source_region_paths'] = saved_source_paths
        self.params['last_detail_gray_overlay_region_paths'] = saved_gray_overlay_paths
        self.params['last_detail_regions'] = detail_regions
        return working_image

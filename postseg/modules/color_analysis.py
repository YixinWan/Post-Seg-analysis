from collections import Counter
from pathlib import Path

import cv2
import numpy as np

from postseg.pipeline.base_pipeline import PipelineStep


class ColorAnalysisStep(PipelineStep):
    def _get_mode_source_image(self, image):
        source_image = self.params.get('source_image')
        if source_image is None or source_image.shape != image.shape:
            return image
        return source_image

    def _compute_non_black_mask(self, image):
        black_thresh = self.params.get('black_thresh', 10)
        channels = image[:, :, :3] if image.shape[2] > 3 else image
        return np.any(channels > black_thresh, axis=2)

    def _compute_mode_color(self, image, mask):
        valid_mask = mask & self._compute_non_black_mask(image)
        if not np.any(valid_mask):
            return [0] * image.shape[2]
        pixels = [tuple(px) for px in image[valid_mask]]
        return list(Counter(pixels).most_common(1)[0][0])

    def _get_fill_mode(self):
        mode = str(self.params.get('fill_mode', 'mode_color')).strip().lower()
        aliases = {
            'mode': 'mode_color',
            'mode_color': 'mode_color',
            'median_l': 'median_l',
            'l_median': 'median_l',
            'median_lightness': 'median_l',
            'lab_l_median': 'median_l',
        }
        return aliases.get(mode, 'mode_color')

    def _compute_median_l_color(self, image, mask):
        valid_mask = mask & self._compute_non_black_mask(image)
        channel_count = image.shape[2]
        if not np.any(valid_mask):
            return [0] * channel_count

        bgr = image[:, :, :3]
        lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
        l_channel = lab[:, :, 0].astype(np.float32)
        l_values = l_channel[valid_mask]
        if l_values.size == 0:
            return [0] * channel_count

        band_percentile = float(self.params.get('median_l_band_percentile', 0.2))
        band_percentile = min(max(band_percentile, 0.01), 1.0)
        lower_q = max(0.0, 0.5 - band_percentile / 2.0)
        upper_q = min(1.0, 0.5 + band_percentile / 2.0)
        lower = float(np.quantile(l_values, lower_q))
        upper = float(np.quantile(l_values, upper_q))

        middle_l_mask = valid_mask & (l_channel >= lower) & (l_channel <= upper)
        if not np.any(middle_l_mask):
            median_l = float(np.median(l_values))
            abs_diff = np.abs(l_channel - median_l)
            valid_indices = np.where(valid_mask)
            nearest_idx = int(np.argmin(abs_diff[valid_mask]))
            y, x = int(valid_indices[0][nearest_idx]), int(valid_indices[1][nearest_idx])
            middle_l_mask = np.zeros_like(valid_mask, dtype=bool)
            middle_l_mask[y, x] = True

        selected_pixels = [tuple(px) for px in image[middle_l_mask]]
        if not selected_pixels:
            selected_pixels = [tuple(px) for px in image[valid_mask]]

        fill_color = list(Counter(selected_pixels).most_common(1)[0][0])
        if channel_count <= 3:
            return fill_color[:channel_count]
        if len(fill_color) < channel_count:
            fill_color = fill_color + [255] * (channel_count - len(fill_color))
        return fill_color

    def _compute_fill_color(self, image, mask):
        fill_mode = self._get_fill_mode()
        if fill_mode == 'median_l':
            return self._compute_median_l_color(image, mask)
        return self._compute_mode_color(image, mask)

    def _circular_distance(self, hues, center):
        diff = np.abs(hues.astype(np.float32) - float(center))
        return np.minimum(diff, 180.0 - diff)

    def _fit_hue_clusters(self, hues):
        if hues.size == 0:
            return []

        min_cluster_pixels = max(1, int(self.params.get('min_cluster_pixels', 50)))
        peak_min_ratio = float(self.params.get('peak_min_ratio', 0.15))
        sigma_scale = float(self.params.get('sigma_scale', 2.0))
        dominant_merge_distance = float(self.params.get('dominant_merge_distance', 10.0))
        hist_smooth_kernel = int(self.params.get('hist_smooth_kernel', 9))
        if hist_smooth_kernel < 1:
            hist_smooth_kernel = 1
        if hist_smooth_kernel % 2 == 0:
            hist_smooth_kernel += 1

        hist = np.bincount(hues, minlength=180).astype(np.float32)
        if hist_smooth_kernel > 1:
            kernel = np.ones(hist_smooth_kernel, dtype=np.float32) / hist_smooth_kernel
            padded = np.concatenate([hist[-hist_smooth_kernel:], hist, hist[:hist_smooth_kernel]])
            smooth_hist = np.convolve(padded, kernel, mode='same')[hist_smooth_kernel:-hist_smooth_kernel]
        else:
            smooth_hist = hist

        max_bin = float(smooth_hist.max())
        if max_bin <= 0:
            return []

        candidate_centers = []
        min_peak_height = max_bin * peak_min_ratio
        for idx in range(180):
            prev_val = smooth_hist[(idx - 1) % 180]
            next_val = smooth_hist[(idx + 1) % 180]
            current = smooth_hist[idx]
            if current >= prev_val and current >= next_val and current >= min_peak_height:
                candidate_centers.append(idx)

        if not candidate_centers:
            candidate_centers = [int(np.argmax(smooth_hist))]

        candidate_centers = sorted(candidate_centers, key=lambda item: smooth_hist[item], reverse=True)
        merged_centers = []
        for center in candidate_centers:
            if all(self._circular_distance(np.array([center]), kept)[0] >= dominant_merge_distance for kept in merged_centers):
                merged_centers.append(center)

        assignments = []
        for center in merged_centers:
            distances = self._circular_distance(hues, center)
            if distances.size == 0:
                continue
            sigma = max(float(np.std(distances)), 1.0)
            radius = max(4.0, sigma * sigma_scale)
            mask = distances <= radius
            count = int(mask.sum())
            if count < min_cluster_pixels:
                continue
            cluster_hues = hues[mask]
            radians = cluster_hues.astype(np.float32) * (2 * np.pi / 180.0)
            refined_center = int(
                np.round(
                    (np.arctan2(np.sin(radians).mean(), np.cos(radians).mean()) % (2 * np.pi))
                    * (180.0 / (2 * np.pi))
                )
            ) % 180
            assignments.append({
                'center': refined_center,
                'count': count,
                'sigma': sigma,
                'radius': radius,
            })

        if not assignments:
            return []

        assignments.sort(key=lambda item: item['count'], reverse=True)
        return assignments

    def _extract_hue_regions(self, image, non_black_mask):
        hsv = cv2.cvtColor(image[:, :, :3], cv2.COLOR_BGR2HSV)
        hue = hsv[:, :, 0]
        valid_hues = hue[non_black_mask]
        clusters = self._fit_hue_clusters(valid_hues)
        if len(clusters) <= 1:
            return [
                {
                    'index': 0,
                    'center': int(clusters[0]['center']) if clusters else None,
                    'mask': non_black_mask.copy(),
                    'pixel_count': int(non_black_mask.sum()),
                }
            ]

        centers = np.array([item['center'] for item in clusters], dtype=np.int32)
        distances = np.stack([self._circular_distance(hue, center) for center in centers], axis=2)
        nearest = np.argmin(distances, axis=2)

        regions = []
        for idx, cluster in enumerate(clusters):
            region_mask = non_black_mask & (nearest == idx)
            if np.any(region_mask):
                regions.append({
                    'source_index': idx,
                    'center': int(cluster['center']),
                    'mask': region_mask,
                    'pixel_count': int(region_mask.sum()),
                })

        for region_index, region in enumerate(regions):
            region['index'] = region_index

        return regions or [
            {
                'index': 0,
                'source_index': 0,
                'center': None,
                'mask': non_black_mask.copy(),
                'pixel_count': int(non_black_mask.sum()),
            }
        ]

    def _build_region_output_path(self, base_output_path, region_index):
        if not base_output_path:
            return None
        base_path = Path(base_output_path)
        suffix = base_path.suffix or '.png'
        stem = base_path.stem
        return str(base_path.with_name(f"{stem}_hue_{region_index + 1}{suffix}"))

    def _save_region_outputs(self, segmentation_image, mode_source_image, regions, base_output_path):
        saved_paths = []
        if len(regions) <= 1:
            for region in regions:
                fill_color = self._compute_fill_color(mode_source_image, region['mask'])
                region['mode_color'] = fill_color
                region['fill_color'] = fill_color
                region['output_path'] = None
            return saved_paths

        for region in regions:
            fill_color = self._compute_fill_color(mode_source_image, region['mask'])
            separated = np.zeros_like(segmentation_image)
            separated[region['mask']] = fill_color
            region['mode_color'] = fill_color
            region['fill_color'] = fill_color
            region_output_path = self._build_region_output_path(base_output_path, region['index'])
            region['output_path'] = region_output_path
            if region_output_path:
                Path(region_output_path).parent.mkdir(parents=True, exist_ok=True)
                cv2.imwrite(region_output_path, separated)
                saved_paths.append(region_output_path)
        return saved_paths

    def process(self, image):
        mode_source_image = self._get_mode_source_image(image)
        non_black_mask = self._compute_non_black_mask(image)
        if not np.any(non_black_mask):
            out_img = np.zeros_like(image)
            output_path = self.params.get('output_path')
            if output_path:
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                cv2.imwrite(output_path, out_img)
            self.params['last_hue_regions'] = []
            self.params['last_saved_region_paths'] = []
            return out_img

        regions = self._extract_hue_regions(image, non_black_mask)
        output_path = self.params.get('output_path')
        saved_paths = self._save_region_outputs(image, mode_source_image, regions, output_path)

        out_img = np.zeros_like(mode_source_image)
        for region in regions:
            out_img[region['mask']] = region['fill_color']

        if output_path:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(output_path, out_img)

        fill_mode = self._get_fill_mode()
        self.params['last_hue_regions'] = [
            {
                'index': region['index'],
                'source_index': region.get('source_index', region['index']),
                'center': region['center'],
                'pixel_count': region['pixel_count'],
                'fill_mode': fill_mode,
                'fill_color': region['fill_color'],
                'mode_color': region['mode_color'],
                'output_path': region.get('output_path'),
            }
            for region in regions
        ]
        self.params['last_saved_region_paths'] = saved_paths
        return out_img

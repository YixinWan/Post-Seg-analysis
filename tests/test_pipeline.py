import os
import cv2
import numpy as np
import pytest

from postseg.main import main
from postseg.modules.color_analysis import ColorAnalysisStep

def test_pipeline(tmp_path):
    # 使用一张测试图片（需替换为实际图片路径）
    test_img = os.path.join(os.path.dirname(__file__), 'testdata', 'test.jpg')
    if not os.path.exists(test_img):
        pytest.skip('测试图片不存在，跳过测试')
    config_path = os.path.join(os.path.dirname(__file__), '..', 'configs', 'config.yaml')
    main(test_img, None, config_path)
    output_img = os.path.join(os.path.dirname(__file__), '..', 'outputs', 'mode_color.jpg')
    assert os.path.exists(output_img)
    img = cv2.imread(output_img)
    assert img is not None


def test_color_analysis_single_hue_keeps_single_region(tmp_path):
    image = np.zeros((20, 20, 3), dtype=np.uint8)
    image[2:18, 2:18] = [0, 0, 255]
    output_path = tmp_path / 'mode_color.png'
    step = ColorAnalysisStep('color', {'output_path': str(output_path), 'black_thresh': 10})

    result = step.process(image)

    assert output_path.exists()
    region_paths = step.params['last_saved_region_paths']
    assert region_paths == []
    assert np.array_equal(result[5, 5], np.array([0, 0, 255], dtype=np.uint8))


def test_color_analysis_multi_hue_saves_split_regions(tmp_path):
    image = np.zeros((30, 30, 3), dtype=np.uint8)
    image[:, :15] = [0, 0, 255]
    image[:, 15:] = [0, 255, 0]
    output_path = tmp_path / 'mode_color.png'
    step = ColorAnalysisStep(
        'color',
        {
            'output_path': str(output_path),
            'black_thresh': 10,
            'min_cluster_pixels': 20,
            'peak_min_ratio': 0.1,
        },
    )

    result = step.process(image)

    assert output_path.exists()
    region_paths = step.params['last_saved_region_paths']
    region_meta = step.params['last_hue_regions']
    assert len(region_paths) == 2
    assert len(region_meta) == 2

    saved_images = [cv2.imread(path) for path in region_paths]
    assert all(saved is not None for saved in saved_images)

    left_colors = {tuple(result[i, 5]) for i in range(30)}
    right_colors = {tuple(result[i, 25]) for i in range(30)}
    assert left_colors == {(0, 0, 255)}
    assert right_colors == {(0, 255, 0)}

    non_black_counts = [int(np.count_nonzero(np.any(saved > 0, axis=2))) for saved in saved_images]
    assert sorted(non_black_counts) == [450, 450]

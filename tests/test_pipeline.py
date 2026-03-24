import os
import cv2
import pytest
from postseg.main import main

def test_pipeline(tmp_path):
    # 使用一张测试图片（需替换为实际图片路径）
    test_img = os.path.join(os.path.dirname(__file__), 'testdata', 'test.jpg')
    if not os.path.exists(test_img):
        pytest.skip('测试图片不存在，跳过测试')
    output_img = tmp_path / 'output.jpg'
    config_path = os.path.join(os.path.dirname(__file__), '..', 'configs', 'config.yaml')
    main(test_img, str(output_img), config_path)
    assert os.path.exists(output_img)
    img = cv2.imread(str(output_img))
    assert img is not None

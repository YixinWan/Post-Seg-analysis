import cv2
from postseg.pipeline.base_pipeline import ImageProcessingPipeline
from postseg.modules.color_analysis import ColorAnalysisStep
from postseg.modules.shadow_analysis import ShadowAnalysisStep
from postseg.modules.highlight_analysis import HighlightAnalysisStep
from postseg.modules.detail_analysis import DetailAnalysisStep
from postseg.utils import load_config
from postseg.gui_utils import select_image_file
import sys

STEP_MAP = {
    'color': ColorAnalysisStep,
    'shadow': ShadowAnalysisStep,
    'highlight': HighlightAnalysisStep,
    'detail': DetailAnalysisStep,
}

def load_image(path):
    return cv2.imread(path)

def save_image(path, image):
    cv2.imwrite(path, image)

def main(input_path, output_path, config_path):
    image = load_image(input_path)
    config = load_config(config_path)
    steps = []
    for step_cfg in config['pipeline']:
        step_cls = STEP_MAP.get(step_cfg['name'])
        if step_cls:
            steps.append(step_cls(step_cfg['name'], step_cfg.get('params', {})))
    pipeline = ImageProcessingPipeline(steps)
    result = pipeline.run(image)
    save_image(output_path, result)

if __name__ == "__main__":
    if '--gui' in sys.argv:
        # 弹框选择图片
        input_path = select_image_file()
        if not input_path:
            print("未选择图片，程序退出。")
            sys.exit(1)
        if len(sys.argv) < 4:
            print("Usage: python main.py --gui <output_image> <config_path>")
            sys.exit(1)
        output_path = sys.argv[2]
        config_path = sys.argv[3]
        main(input_path, output_path, config_path)
    elif len(sys.argv) == 4:
        main(sys.argv[1], sys.argv[2], sys.argv[3])
    else:
        print("Usage: python main.py <input_image> <output_image> <config_path>\n       或: python main.py --gui <output_image> <config_path>")

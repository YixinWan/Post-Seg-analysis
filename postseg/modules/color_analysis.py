from postseg.pipeline.base_pipeline import PipelineStep
import numpy as np
import cv2

class ColorAnalysisStep(PipelineStep):
    def process(self, image):
        # 仅对非黑色区域分析主色调
        h, w, c = image.shape
        # 黑色像素定义：所有通道都小于等于阈值
        black_thresh = self.params.get('black_thresh', 10)
        if c == 3:
            mask = np.any(image > black_thresh, axis=2)
        else:
            mask = np.any(image[:,:,:3] > black_thresh, axis=2)
        # 提取非黑色像素
        non_black_pixels = image[mask]
        if non_black_pixels.size == 0:
            median_color = [0]*c
        else:
            median_color = [int(np.median(non_black_pixels[:,i])) for i in range(c)]
        # 用主色调覆盖非黑色区域，黑色区域保持原样
        out_img = image.copy()
        out_img[mask] = median_color
        # 保存输出
        output_path = self.params.get('output_path')
        if output_path:
            cv2.imwrite(output_path, out_img)
        return out_img

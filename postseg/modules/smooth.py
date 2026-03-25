from postseg.pipeline.base_pipeline import PipelineStep
import cv2

class SmoothStep(PipelineStep):
    def process(self, image):
        # 使用高斯模糊进行平滑处理，减少噪点
        ksize = self.params.get('ksize', 5)
        if ksize % 2 == 0:
            ksize += 1  # 高斯核必须为奇数
        smoothed = cv2.GaussianBlur(image, (ksize, ksize), 0)
        # 保存平滑处理后的图片
        output_path = self.params.get('output_path', 'outputs/smoothed.jpg')
        if output_path:
            cv2.imwrite(output_path, smoothed)
        return smoothed

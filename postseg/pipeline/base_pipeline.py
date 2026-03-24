from typing import List, Any

class PipelineStep:
    def __init__(self, name: str, params: dict = None):
        self.name = name
        self.params = params or {}

    def process(self, image: Any) -> Any:
        raise NotImplementedError("Each step must implement the process method.")

class ImageProcessingPipeline:
    def __init__(self, steps: List[PipelineStep]):
        self.steps = steps

    def run(self, image: Any) -> Any:
        for step in self.steps:
            image = step.process(image)
        return image

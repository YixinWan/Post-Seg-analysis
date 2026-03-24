# Post-Seg-analysis 图像处理工程

## 项目简介

本项目为可插拔式图像处理pipeline，支持如下流程：
- 输入图片
- 平滑处理（先对输入图片做高斯模糊，减少噪点，便于后续色块提取）
- 铺色分析和处理（提取整图主色调/中值色，并用主色调覆盖原图，输出到outputs/median_color.jpg）
- 暗部分析和处理
- 亮部分析和处理
- 细节分析

每个处理流程为独立模块，可灵活增减和组合，支持参数化配置，便于调参和扩展。


## 目录结构
```
postseg/
  main.py                # 主入口，加载pipeline和配置
  utils.py               # 工具函数
  gui_utils.py           # 弹框选择图片工具
  pipeline/
    base_pipeline.py     # pipeline基类与流程控制
  modules/
    color_analysis.py    # 铺色分析模块
    shadow_analysis.py   # 暗部分析模块
    highlight_analysis.py# 亮部分析模块
    detail_analysis.py   # 细节分析模块
configs/
  config.yaml            # pipeline参数配置
outputs/                 # 推荐输出图片保存目录
tests/
  test_pipeline.py       # 测试用例
requirements.txt         # pip依赖
environment.yml          # conda环境配置
```

## 环境搭建
1. 使用conda创建环境：
   ```sh
   conda env create -f environment.yml
   conda activate postseg-analysis
   ```
2. 或用pip安装依赖：
   ```sh
   pip install -r requirements.txt
   ```


## 使用方法


### 命令行直接指定图片：
```sh
python -m postseg.main <input_image> <output_image> <config_path>
# 示例：
python -m postseg.main ./input.jpg ./outputs/output.jpg ./configs/config.yaml
```

### 运行时弹框选择图片：
```sh
python -m postseg.main --gui ./outputs/output.jpg ./configs/config.yaml
# 会弹出文件选择框选择本地图片
```

> 建议将输出图片保存在 `outputs/` 目录下，便于管理。
> 铺色分析（主色调/中值色）结果会自动输出到 `outputs/median_color.jpg`。

## 配置与扩展
- `configs/config.yaml` 控制pipeline流程和各模块参数。
- 新增模块：在`modules/`下添加新模块，继承`PipelineStep`，并在`main.py`的`STEP_MAP`注册。
- 可按需调整pipeline顺序和参数。

## 测试
本项目已包含基础测试用例，需准备一张测试图片（如 `tests/testdata/test.jpg`）。

运行测试：
```sh
pytest tests/
```

---
如需进一步定制或扩展，请参考源码注释。

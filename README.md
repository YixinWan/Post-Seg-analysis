# Post-Seg-analysis 图像处理工程

## 项目简介

本项目为可插拔式图像处理pipeline，支持如下流程：
- 输入图片
- 平滑处理（先对输入图片做高斯模糊，减少噪点，便于后续色块提取）
- 铺色分析和处理（基于平滑后的输入图像做 HSV 色相分布分析，排除黑色区域；若检测到多个主要色相，则先自动分离不同色相区域，再分别做 mode_color 覆色）
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
    color_analysis.py    # 铺色分析模块（含主色相分区 + mode_color 覆色导出）
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
python -m postseg.main <input_image> <config_path>
# 示例：
python -m postseg.main ./input.jpg ./configs/config.yaml
```

### 如需额外保存最终 pipeline 结果：
```sh
python -m postseg.main <input_image> <output_image> <config_path>
# 示例：
python -m postseg.main ./input.jpg ./outputs/final_result.jpg ./configs/config.yaml
```

### 运行时弹框选择图片：
```sh
python -m postseg.main --gui ./configs/config.yaml
# 会弹出文件选择框选择本地图片
```

> 建议将输出图片保存在 `outputs/` 目录下，便于管理。
> 每次处理一张新图片前，程序会先清空 `outputs/` 目录中的旧结果，避免新旧图片输出混在一起。
> 铺色分析总结果会输出到 `color.params.output_path` 指定路径。
> 只有在检测到多个主色相时，才会额外生成 `*_hue_1.jpg`、`*_hue_2.jpg` ... 这样的单独图片；如果只有单一主色相，则只输出 1 张 `mode_color` 总图。

## 铺色分析的色相分割逻辑

铺色分析模块现在会先读取**平滑后的图片**，并按下面的方式决定是否需要先按色相拆分：

1. 转换到 HSV 色彩空间，仅统计非黑色像素的色相 $H$。
2. 对 $H$ 的分布密度做平滑，寻找主要峰值，并将每个峰近似看作一个正态分布中心。
3. 根据峰宽（标准差）和峰间距离，自动合并过近峰值、过滤过小峰值，得到主要色相。
4. 若只有一个主要色相，则直接对整块非黑区域执行 `mode_color`。
5. 若存在多个主要色相，则按最近主色相中心自动划分边界，先拆成多个色相区域，再分别执行 `mode_color`。

这样可以更稳定地区分颜色接近但色相不同的铺色区域，避免整图只被单一众数色覆盖。

## 铺色分析输出说明

- 主输出：`output_path`
  - 所有非黑区域都会被对应色相区域的 `mode_color` 覆盖。
- 分区输出：`output_path` 同目录下的 `*_hue_N.*`
  - **仅当检测到多个主色相时才会生成。**
  - 每个文件只保留一个主色相区域。
  - 该区域内部使用本区域的 `mode_color` 覆色。
  - 其他区域全部置黑。

## 输出目录清理规则

- 每次处理新图片前，会先清空配置中 `output_path` 所在的 `outputs/` 目录。
- 这样可以确保 `outputs/` 内只保留当前这一次分析对应的结果图。
- 为了安全起见，只会自动清理目录名为 `outputs` 的输出目录。

## 配置与扩展
- `configs/config.yaml` 控制pipeline流程和各模块参数。
- `color` 模块支持以下关键参数：
  - `black_thresh`：黑色区域阈值，低于该阈值的像素不参与色相分析。
  - `min_cluster_pixels`：允许成为主色相区域的最小像素数。
  - `peak_min_ratio`：色相峰值最小占比阈值，用于过滤不明显的小峰。
  - `sigma_scale`：根据拟合峰宽扩张区域边界的倍率。
  - `dominant_merge_distance`：两个主色相中心过近时的合并阈值。
  - `hist_smooth_kernel`：色相直方图平滑窗口大小，越大越倾向于忽略细碎小波动。
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

# Post-Seg-analysis 图像处理工程

## 项目简介

本项目为可插拔式图像处理pipeline，支持如下流程：
- 输入图片
- 平滑处理
- 铺色分析和处理
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
  color_analysis.py    # 铺色分析模块（含主色相分区 + 可配置铺色模式导出）
    shadow_analysis.py   # 暗部分析模块
    highlight_analysis.py# 亮部分析模块
    detail_analysis.py   # 细节分析模块
configs/
  config.yaml            # pipeline参数配置
outputs/                 # 推荐输出图片保存目录
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

### 修改并运行 pipeline（推荐流程）

pipeline 的执行顺序由 `configs/config.yaml` 里 `pipeline:` 列表从上到下决定。

1. 打开 `configs/config.yaml`，按需调整步骤顺序（当前支持：`smooth`、`color`、`shadow`、`highlight`、`detail`）。
2. 如需临时关闭某一步，直接删除对应 `- name: ...` 配置块即可。
3. 在每一步的 `params` 里修改参数（例如 `fill_mode`、`shadow_percentile`、`highlight_percentile` 等）。
4. 运行命令：
  - 直接指定输入图 + 配置：`python -m postseg.main <input_image> <config_path>`
  - 额外保存最终 pipeline 输出：`python -m postseg.main <input_image> <output_image> <config_path>`
  - 弹框选图：`python -m postseg.main --gui .\configs\config.yaml`

#### 常见修改示例

- **只跑铺色，不跑暗部/亮部/细节**：在 `pipeline` 中仅保留 `smooth` 和 `color`。
- **调整执行先后顺序**：直接调整 `pipeline` 列表中各 `- name:` 配置块的前后位置。
- **新增自定义步骤**：在 `postseg/modules/` 下新增模块并继承 `PipelineStep`，再在 `postseg/main.py` 的 `STEP_MAP` 中注册，最后把步骤写入 `configs/config.yaml` 的 `pipeline` 列表。

## 各模块逻辑简述

- `smooth`（`postseg/modules/smooth.py`）
  - 逻辑：对输入图像做高斯平滑，降低噪点，给后续色相/明暗分析提供更稳定的参考图。
  - 输入：原始输入图像。
  - 输出：平滑图（按 `output_path` 保存），并将平滑结果继续传给后续步骤。

- `color`（`postseg/modules/color_analysis.py`）
  - 逻辑：在非黑区域做 HSV 色相统计，必要时按主色相分区，再按 `fill_mode`（`mode_color` 或 `median_l`）进行铺色。
  - 输入：当前流程图像（通常为平滑图）+ 原始图（用于区域颜色统计）。
  - 输出：铺色总图 `output_path`，多主色相时额外输出 `*_hue_N.*` 分区图。

- `shadow`（`postseg/modules/shadow_analysis.py`）
  - 逻辑：基于色块区域与亮度分位提取暗部，可选形态学后处理，再输出暗部 mode 色图和原色图。
  - 输入：铺色结果（`color_output_path`）+ 分析参考图（通常为平滑图）+ 原始图。
  - 输出：暗部总图 `output_path`，以及可选 `source_color_output_path`、`source_gray_overlay_output_path` 和分区暗部图。

- `highlight`（`postseg/modules/highlight_analysis.py`）
  - 逻辑：与暗部模块对称，按亮度分位提取亮部，可选形态学后处理，再输出亮部 mode 色图和原色图。
  - 输入：铺色结果（`color_output_path`）+ 分析参考图（通常为平滑图）+ 原始图。
  - 输出：亮部总图 `output_path`，以及可选 `source_color_output_path`、`source_gray_overlay_output_path` 和分区亮部图。

- `detail`（`postseg/modules/detail_analysis.py`）
  - 逻辑：在非黑区域内，先通过 HSV（低 `S` + 高 `V`）提取白色高光，再在每个色块内统计主色相并提取“非主色相”像素作为细节，可选做形态学后处理。
  - 输入：铺色结果（`color_output_path`）+ 分析参考图（通常为平滑图）+ 原始图。
  - 输出：细节总图 `output_path`，以及可选 `source_color_output_path`、`source_gray_overlay_output_path` 和分区细节图。

## 配置与扩展
- `configs/config.yaml` 控制pipeline流程和各模块参数。
- `color` 模块支持以下关键参数：
  - `fill_mode`：铺色模式，默认 `mode_color`；可选 `median_l`（按掩码区域原图 LAB 的 $L$ 中间亮度带提取原色众数铺色）。
  - `median_l_band_percentile`：仅 `fill_mode=median_l` 时生效，默认 `0.2`，表示在区域内取 $L$ 分布中间 20% 的像素参与颜色统计。
  - `black_thresh`：黑色区域阈值，低于该阈值的像素不参与色相分析。
  - `min_cluster_pixels`：允许成为主色相区域的最小像素数。
  - `peak_min_ratio`：色相峰值最小占比阈值，用于过滤不明显的小峰。
  - `sigma_scale`：根据拟合峰宽扩张区域边界的倍率。
  - `dominant_merge_distance`：两个主色相中心过近时的合并阈值。
  - `hist_smooth_kernel`：色相直方图平滑窗口大小，越大越倾向于忽略细碎小波动。
- `shadow` 模块支持以下关键参数：
  - `color_output_path`：铺色输出总图路径，用于自动定位 `mode_color` 掩码和可选的 `*_hue_N` 分区图。
  - `output_path`：暗部总输出图路径，使用原图对应暗部区域的 `mode` 颜色填充；若存在多张色相分区图，还会额外输出对应的 `*_shadow.*` 分图。
  - `source_color_output_path`：暗部原色输出图路径，使用与 `mode_color_shadow` 相同的暗部掩码，但直接保留原图对应位置的原色。
  - `source_gray_overlay_output_path`：灰底原色叠加输出图路径，先将输入原图转成灰度底图，再把 `mode_color_shadow_source` 对应的原色暗部区域覆盖回去。
  - `shadow_percentile`：直接按 LAB 的 L 分位数提取暗部，默认 `0.3`，表示取该区域中最暗的 30% 像素。
  - `morphology`：暗部结果的形态学后处理配置，作用在 `mode_color_shadow` 的二值 mask 上，再回填 mode 颜色。
    - `enabled`：是否启用形态学后处理。
    - `open_kernel`：开运算核大小，用于优先去掉孤立小噪点。
    - `close_kernel`：闭运算核大小，用于连接近邻暗部空隙。
    - `dilate_kernel` / `dilate_iterations`：膨胀参数，用于扩展连通区域。
    - `erode_kernel` / `erode_iterations`：腐蚀参数，用于回收边缘、去掉过度膨胀。
- `highlight` 模块支持以下关键参数：
  - `color_output_path`：铺色输出总图路径，用于自动定位 `mode_color` 掩码和可选的 `*_hue_N` 分区图。
  - `output_path`：亮部总输出图路径，使用原图对应亮部区域的 `mode` 颜色填充；若存在多张色相分区图，还会额外输出对应的 `*_highlight.*` 分图。
  - `source_color_output_path`：亮部原色输出图路径，使用与 `mode_color_highlight` 相同的亮部掩码，但直接保留原图对应位置的原色。
  - `source_gray_overlay_output_path`：灰底原色叠加输出图路径，先将输入原图转成灰度底图，再把 `mode_color_highlight_source` 对应的原色亮部区域覆盖回去。
  - `highlight_percentile`：直接按 LAB 的 L 分位数提取亮部，默认 `0.2`，表示取该区域中最亮的 20% 像素。
  - `morphology`：亮部结果的形态学后处理配置，作用在 `mode_color_highlight` 的二值 mask 上，再回填 mode 颜色。
    - `enabled`：是否启用形态学后处理。
    - `open_kernel`：开运算核大小，用于优先去掉孤立小噪点。
    - `close_kernel`：闭运算核大小，用于连接近邻亮部空隙。
    - `dilate_kernel` / `dilate_iterations`：膨胀参数，用于扩展连通区域。
    - `erode_kernel` / `erode_iterations`：腐蚀参数，用于回收边缘、去掉过度膨胀。
- `detail` 模块支持以下关键参数：
  - `color_output_path`：铺色输出总图路径，用于自动定位 `mode_color` 掩码和可选的 `*_hue_N` 分区图。
  - `analysis_image_path`：细节分析参考图，建议使用 `smooth` 输出。
  - `output_path`：细节总输出图路径，输出方式与 `highlight` 一致（mode 色填充）；多分区时额外输出 `*_detail.*` 分图。
  - `source_color_output_path`：细节原色输出图路径，掩码与 `mode_color_detail` 相同，但保留原图像素。
  - `source_gray_overlay_output_path`：灰底原色叠加输出图路径，把细节原色区域覆盖到灰度底图上。
  - `white_s_percentile`：白色高光的低饱和阈值分位（HSV-S，取低分位），默认 `0.3`。
  - `white_v_percentile`：白色高光的高亮阈值分位（HSV-V，取高分位），默认 `0.1`。
  - `highlight_percentile`：兼容旧配置的备用参数；当未设置 `white_v_percentile` 时，会使用该值作为 `V` 高分位比例。
  - `detail_hue_delta`：主色相排除带宽（单位：HSV Hue，范围 0-179），默认 `10`；超过该带宽的像素视为“非主色相细节”。
  - `detail_hue_min_saturation`：参与主色相统计的最小饱和度（HSV-S），默认 `20`。
  - `detail_hue_min_value`：参与主色相统计的最小亮度（HSV-V），默认 `20`。
  - `morphology`：细节掩码形态学后处理配置，字段与 `shadow/highlight` 保持一致。

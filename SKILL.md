---
name: poster-to-layered-psd
description: Use when 扁平海报转矢量SVG/PDF/分层PSD。vtracer+SAM全流程。
version: 1.0.0
---

# 扁平海报 → 矢量SVG / AI兼容PDF / 分层PSD

把一张压平的成品海报（JPG/PNG）逆向拆成可编辑物料的完整流水线。

## 按需求选深度（可停在任一档）

| 档位 | 交付 | 需要工具 | 耗时 |
|---|---|---|---|
| **A 只要放大** | 矢量SVG | vtracer | ~2分钟 |
| **B 要进AI** | + PDF | + rsvg-convert | +1分钟 |
| **C 要PSD改图** | + 分层PSD | + psd-tools/opencv | +2分钟 |
| **D 每元素一层** | + 元素层×100+ | + SAM/torch | +30分钟 |

A 档是完整闭环：步骤 1→2→3 做完即可交付，不需要后面的任何东西。很多人（只要放大印刷/展示）到 A/B 就够了，别过度交付。

## 输出三件套

| 文件 | 工具 | 用途 |
|---|---|---|
| 矢量SVG | vtracer + 照片嵌入 | 无限放大，文字锐利 |
| PDF | rsvg-convert | Illustrator 打开→另存为 .ai（AI 无开源生成器，PDF 是等价路径） |
| 分层PSD | psd-tools + SAM | Photoshop 源文件，背景/文字/照片/元素各一层 |

## Pipeline 五步

### 1. 视觉分析定位照片区（必须先做）
先用 vision_analyze 分析图的构成：哪些区域是真实照片（矢量化必毁）、哪些是文字/色块/插画（矢量化极佳）。
让 vision 给照片 bbox 像素坐标，**然后裁出来二次复核**——首次估计经常偏小，要放大裁剪范围直到照片边界完整可见。注意海报照片常有羽化/不规则边缘，记录羽化方向。

### 2. vtracer 全图矢量化
```bash
pip3 install --user vtracer -i https://pypi.tuna.tsinghua.edu.cn/simple
```

**最简用法（打包好的扁平JPG/PNG，一行出SVG）：**
```bash
python3 scripts/vectorize_svg.py 输入.jpg 输出.svg     # 不需要任何配置
```
- PNG 透明背景会保留为矢量镂空；Logo/插画/纯平面设计稿直接这样转即可
- 判断规则：**纯平涂/文字/Logo → 直接全矢量**；**含真实照片 → 加 --photos 分离嵌入**（否则照片会糊成色块）

用 `scripts/vectorize_svg.py 输入图 输出.svg --photos boxes.json`：
- vtracer 参数：**filter_speckle=2, color_precision=8, layer_difference=4**, hierarchical='stacked', mode='spline', path_precision=2。**这是修过"元素背景色丢失"的高保真组合**——默认的 layer_difference=16 会把相近色层合并导致天空洗白/白云变蓝/装饰底色丢失，filter_speckle=4 会吞小色块。代价是 SVG 变大 2.3 倍（69MB→161MB），svgo 压缩后约 92MB。25MP 图矢量化约 2.5 分钟
- 照片区裁原图 PNG，边缘做 alpha 羽化渐变，以 `<image href="data:image/png;base64,...">` 嵌入SVG压在矢量层上——羽化区是"同内容的矢量↔位图渐变"，无接缝

**坑：libxml2 单属性 10MB 上限**。base64 超过约 7MB 的图必须切成多片分别嵌入（每片≤3MB原图），且只写 `href` 不要 xlink:href+href 双写，否则 rsvg 报 "Premature end of data"。

### 3. 渲染验证（不要跳过）
```bash
brew install librsvg   # rsvg-convert
rsvg-convert -w 3150 out.svg -o /tmp/render.png   # 1:1
rsvg-convert -w 6300 out.svg -o /tmp/render2x.png # 2x验证文字锐利度
rsvg-convert -f pdf out.svg -o out.pdf            # AI兼容PDF
```
裁关键区（标题/过渡带/卡片区/二维码）用 vision_analyze 目检：文字2x无锯齿、照片无接缝、二维码方块锐利。
注意：cairosvg 在 macOS 找不到 brew 的 libcairo（SIP 剥离 DYLD 变量），直接用 rsvg-convert。

### 4. 分层PSD
`pip3 install --user psd-tools opencv-python-headless`
用 `scripts/build_psd.py`：
- **文字层**：HSV 阈值抠主色文字（深藏青 h95-130/s≥90/v≤170 + 红色 h≤8|≥170），3×3开运算去噪，31px膨胀包住白描边，5px高斯羽化做alpha
- **背景层**：cv2.inpaint(TELEA, 7px) 修复文字区；照片区 alpha=0 镂空
- **照片层**：带羽化alpha的原图crop，按bbox定位
- **验证**：psd.composite() 与原图逐像素 diff 必须为 0（每层都是原图像素，只是分层摆放）

**坑：psd-tools 中文图层名**。直接传中文名 save 时报 mac_roman 编码错误；即使 `save(encoding='utf-8')` 能存，读回也是乱码——必须手写 luni tagged block（UTF-16BE），legacy name 用 ASCII 占位：
```python
import struct
from psd_tools.psd.tagged_blocks import TaggedBlock
def set_unicode_name(layer, name):
    data = struct.pack('>I', len(name)) + name.encode('utf-16-be')
    layer._record.tagged_blocks[b'luni'] = TaggedBlock(key=b'luni', data=data)
    layer._record.name = name.encode('ascii', 'replace').decode('ascii')
```

### 5. SAM 元素级拆解（可选，每个卡通/图标/卡片一层）
`pip3 install --user torch torchvision segment-anything`，下载 ViT-B 权重(375MB)：
`curl -L -o sam_vit_b.pth https://dl.fbaipublicfiles.com/segment_anything/sam_vit_b_01ec64.pth`

**MPS 两个必打补丁**（site-packages 里的 segment_anything）：
1. `automatic_mask_generator.py` 两处：`torch.as_tensor(transformed_points, ...)` 加 `dtype=torch.float32`（MPS不支持float64）；`predict_torch` 返回后 `masks/iou_preds .cpu()`（否则 torchvision nms 设备混用报错）
2. `modeling/sam.py` postprocess_masks：最终上采样分块在CPU做（MPS 单buffer上限约17GB，25MP图整批上采样必炸）：
```python
outs = []
for i in range(0, masks.shape[0], 8):
    outs.append(F.interpolate(masks[i:i+8].float().cpu(), original_size, mode='bilinear', align_corners=False))
return torch.cat(outs, dim=0)
```
补丁可用 `scripts/patch_sam_mps.py` 自动打。

SamAutomaticMaskGenerator 参数：points_per_side=32, pred_iou_thresh=0.86, stability_score_thresh=0.92, crop_n_layers=1, min_mask_region_area=2000。25MP 长图约 28 分钟（MPS编码+CPU分块上采样）。

后处理（`scripts/sam_elements.py`）：过滤 area<3000 或 >45%全图、iou<0.88、stab<0.92；按面积降序做包含去重（小mask被大mask包含>85%则丢弃）；每个元素按bbox裁原图+3px高斯羽化alpha→PSD图层，命名 `元素#NNN_x{X}_y{Y}` 方便定位。先生成随机色块+序号的可视化图让 vision 验收后再建PSD。

## 如实告知用户的局限

- PSD 文字层是**抠出的位图**，不是可打字编辑的文本层；改文案需设计师重排（背景已挖掉文字垫在底下）
- 色彩法只抠指定主色文字；白字/黄字留在背景层；同色系插画部件（深蓝衣服、红心）会混入文字层
- SAM 元素层含蒙版内部背景（如照片里植物的缝隙背景）；发丝级边缘需人工 defringe
- 照片层本身是位图不能再放大；海报其余部分矢量
- 自动拆解是"设计师起点"，不是完美成品

## 步骤6（可选）：可编辑文字层

用户要"文字能改"时用。PSD 格式开源库写不了真文字层，所以可编辑文字走 SVG/AI 交付：

1. **OCR**：macOS 用 `scripts/ocr_text.swift`（原生 Vision，`swift ocr_text.swift 图.jpg out.json`，中文准、零安装）；跨平台用 `scripts/ocr_text_paddle.py`（PaddleOCR）
2. **叠文字层**：`python3 scripts/build_editable_svg.py 原图.jpg 矢量海报.svg ocr.json 输出.svg [--corrections fix.json]`
3. **关键设计**：文字元素 `fill-opacity="0"` 叠在原矢量文字上——**视觉零影响（渲染diff=0已验证），Illustrator 里选中即改**。不要用色块补丁盖原文字：渐变/复杂背景上补丁必穿帮
4. textLength + lengthAdjust="spacingAndGlyphs" 强制对齐原文宽度；文字色取 bbox 内暗/饱和像素中位数；字号≈0.92×bbox高
5. **OCR 后必须人工核对错字**（Vision 对艺术字会认错，如"玩一会儿"→"玩一会八"），用 --corrections JSON 修正常见错字
6. 交付时附 OCR 全量 JSON 清单，设计师对照改文案

## Windows 适配

整条 pipeline 除 OCR 外均跨平台，Windows 用户注意：

| 环节 | macOS | Windows |
|---|---|---|
| OCR | `ocr_text.swift`（Vision） | `ocr_text_paddle.py`（`pip install paddleocr paddlepaddle`） |
| SVG渲染/PDF | `brew install librsvg` | `winget install GNOME.librsvg`，或 pip 装 cairosvg（**Windows 版自带 cairo DLL，没有 macOS 的 SIP 坑**） |
| SAM | MPS + 必打补丁 | CUDA/CPU 直接跑，**不需要 MPS 补丁** |
| 其余 | — | vtracer/psd-tools/opencv 都有 Windows wheel |

Windows 控制台中文乱码：先 `chcp 65001`；路径含中文时 python 加 `-X utf8`。

## 交付清单惯例

桌面交付：`*-矢量海报.svg` / `.pdf` / `*-分层源文件.psd`。回复附：文件表（名称+大小+用途）、PSD图层结构树、验证数字（composite diff=0、二维码解码比对）、局限说明，预览图用 MEDIA: 发出。

## 体积优化（交付大文件时做）

- **SVG**：`NODE_OPTIONS=--max-old-space-size=12288 npx -y svgo in.svg -o out.svg --config svgo.config.mjs`（svgo 4 无 --disable 参数，用 config 文件；preset-default 即可，removeViewBox 已不在默认集；**>100MB 的 SVG 不加 heap 参数会 OOM 崩溃**）。高保真 SVG 可减约 45%，渲染 diff≈0.5 可忽略。**压缩后必须重渲染 + 重解码二维码验证**。
- **PSD**：`PixelLayer.frompil(..., compression=Compression.ZIP_WITH_PREDICTION)`，比默认 RLE 再省约 37%，像素不变（composite diff 仍为 0）。
- PDF 用压缩后的 SVG 重新生成，跟着变小。

## 验证清单（交付前必过）

- [ ] SVG 1:1 + 2x 渲染目检：标题锐利/照片无接缝/二维码清晰
- [ ] PSD 重开 composite 与原图 diff = 0
- [ ] 图层名读回中文正常（luni块）
- [ ] 照片/文字层 alpha 统计合理（文字层应有大量透明区）
- [ ] SAM 元素抽检2-3层贴品红底目检边缘
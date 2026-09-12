#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在已完成的矢量SVG上叠加透明可编辑文字层（Illustrator里可选中改字）。
用法:
  python3 build_editable_svg.py 原图.jpg 矢量海报.svg ocr.json 输出.svg [--corrections fix.json]
  fix.json: {"OCR误识别文本": "修正文本", ...}
原理: <text> 元素 fill-opacity="0"，视觉零影响（已验证渲染diff=0）；不用色块补丁盖原文
      （补丁在渐变背景上必穿帮）。textLength强制对齐原文宽度，字体用近似圆体兜底。
"""
import argparse, json
import numpy as np
from PIL import Image


def est_text_color(img, x, y, w, h):
    """bbox内最暗/最饱和像素的中位数 ≈ 文字色"""
    H, W = img.shape[:2]
    x1, y1 = max(0, int(x)), max(0, int(y))
    x2, y2 = min(W, int(x + w)), min(H, int(y + h))
    region = img[y1:y2, x1:x2].reshape(-1, 3).astype(float)
    mx = region.max(1); mn = region.min(1); lum = region.mean(1)
    mask = (lum < 120) | ((mx - mn) > 80)
    fg = np.median(region[mask], axis=0) if mask.sum() > 10 else np.median(region, axis=0)
    return '#%02x%02x%02x' % tuple(int(c) for c in fg)


def esc(t):
    return t.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('image', help='原始海报图')
    ap.add_argument('base_svg', help='已生成的矢量SVG')
    ap.add_argument('ocr_json', help='OCR结果(ocr_text.swift / ocr_text_paddle.py 输出)')
    ap.add_argument('output')
    ap.add_argument('--corrections', help='错字修正JSON: {"误识别": "正确"}')
    ap.add_argument('--visible', action='store_true', help='文字可见(调试用)，默认透明')
    args = ap.parse_args()

    img = np.array(Image.open(args.image).convert('RGB'))
    ocr = json.load(open(args.ocr_json, encoding='utf-8'))
    fix = json.load(open(args.corrections, encoding='utf-8')) if args.corrections else {}

    elements = []
    for r in ocr:
        text = fix.get(r['text'].strip(), r['text'].strip())
        if not text or r['confidence'] < 0.45 or len(text) < 2:
            continue
        x, y, w, h = r['x'], r['y'], r['w'], r['h']
        if w < 20 or h < 20:
            continue
        fg = est_text_color(img, x, y, w, h)
        size = h * 0.92
        weight = 700 if h > 60 else 400
        opacity = '1' if args.visible else '0'
        elements.append(
            f'<text x="{x:.0f}" y="{y + h * 0.82:.0f}" '
            f'font-family="Yuanti SC,PingFang SC,Microsoft YaHei,Source Han Sans SC,sans-serif" '
            f'font-size="{size:.0f}" font-weight="{weight}" fill="{fg}" fill-opacity="{opacity}" '
            f'textLength="{w:.0f}" lengthAdjust="spacingAndGlyphs">{esc(text)}</text>')

    with open(args.base_svg, encoding='utf-8') as f:
        svg = f.read()
    overlay = ('<g id="editable-text" data-note="透明可编辑文字层: '
               'Illustrator里选中即可改字,改完把fill-opacity改为1并指定字体">\n'
               + '\n'.join(elements) + '\n</g>')
    svg = svg.replace('</svg>', overlay + '\n</svg>')
    with open(args.output, 'w', encoding='utf-8') as f:
        f.write(svg)
    print(f'{len(elements)} 个可编辑文字块 -> {args.output}')


if __name__ == '__main__':
    main()

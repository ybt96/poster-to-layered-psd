#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OCR文字识别（跨平台，PaddleOCR后端，Windows/macOS/Linux通用）。
输出与 ocr_text.swift (macOS Vision) 相同的JSON格式，供 build_editable_svg.py 使用。
安装: pip install paddleocr paddlepaddle   （Windows控制台先 chcp 65001 防中文乱码）
用法: python3 ocr_text_paddle.py input.jpg out.json
"""
import sys, json
from paddleocr import PaddleOCR

img_path, out_path = sys.argv[1], sys.argv[2]
ocr = PaddleOCR(use_angle_cls=False, lang='ch')
result = ocr.ocr(img_path)

items = []
for line in (result[0] if result and result[0] else []):
    box, (text, conf) = line
    xs = [p[0] for p in box]; ys = [p[1] for p in box]
    items.append({
        'text': text, 'confidence': float(conf),
        'x': min(xs), 'y': min(ys),
        'w': max(xs) - min(xs), 'h': max(ys) - min(ys),
    })

with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(items, f, ensure_ascii=False, indent=1)
print(f'识别到 {len(items)} 个文字块 -> {out_path}')

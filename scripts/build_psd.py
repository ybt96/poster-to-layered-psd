#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""扁平海报 → 分层PSD（背景去文字去照片 + 文字层 + 照片层 + 可选SAM元素层）。
用法:
  python3 build_psd.py input.jpg output.psd --photos photos.json [--sam sam_final.pkl]
  photos.json 同 vectorize_svg.py。
验证内置: 保存后重开 composite 与原图 diff 必须为 0。
"""
import argparse, json, os, pickle, struct
import numpy as np
from PIL import Image
import cv2
from psd_tools import PSDImage
from psd_tools.api.layers import PixelLayer
from psd_tools.psd.tagged_blocks import TaggedBlock

def set_unicode_name(layer, name):
    """手写luni块让Photoshop正确显示中文图层名"""
    data = struct.pack('>I', len(name)) + name.encode('utf-16-be')
    layer._record.tagged_blocks[b'luni'] = TaggedBlock(key=b'luni', data=data)
    layer._record.name = name.encode('ascii', 'replace').decode('ascii')

def text_mask_hsv(img):
    """深藏青+红色文字蒙版，含白描边（按目标海报调阈值）"""
    hsv = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)
    h, s, v = cv2.split(hsv)
    navy = ((h >= 95) & (h <= 130) & (s >= 90) & (v <= 170)).astype(np.uint8) * 255
    red = ((((h <= 8) | (h >= 170)) & (s >= 120) & (v >= 120))).astype(np.uint8) * 255
    mask = cv2.bitwise_or(navy, red)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    mask = cv2.dilate(mask, np.ones((31, 31), np.uint8))  # 膨胀15px包描边
    return mask

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('input')
    ap.add_argument('output')
    ap.add_argument('--photos', required=True)
    ap.add_argument('--sam', help='SAM去重后的pkl（可选）')
    args = ap.parse_args()

    img = np.array(Image.open(args.input).convert('RGB'))
    H, W = img.shape[:2]
    photos = json.load(open(args.photos))

    # 照片区蒙版
    photo_mask = np.zeros((H, W), np.uint8)
    for ph in photos:
        x1, y1, x2, y2 = ph['box']
        photo_mask[y1:y2, x1:x2] = 255

    # 文字层
    tmask = text_mask_hsv(img)
    text_alpha = cv2.GaussianBlur(tmask, (5, 5), 0)
    text_alpha[photo_mask > 0] = 0
    text_layer = np.dstack([img, text_alpha])

    # 背景层: 文字inpaint + 照片镂空
    inpaint_mask = cv2.bitwise_or(tmask, photo_mask)
    print('inpainting...')
    bg_rgb = cv2.inpaint(img, inpaint_mask, 7, cv2.INPAINT_TELEA)
    bg_alpha = np.full((H, W), 255, np.uint8)
    bg_alpha[photo_mask > 0] = 0
    bg_layer = np.dstack([bg_rgb, bg_alpha])

    psd = PSDImage.new('RGB', (W, H))

    def add(pil_img, name, top=0, left=0, visible=True):
        layer = PixelLayer.frompil(pil_img, psd, name='layer', top=top, left=left)
        set_unicode_name(layer, name)
        if not visible:
            layer.visible = False
        psd.append(layer)
        print(f'  + {name}', flush=True)

    add(Image.fromarray(bg_layer), '背景（已去除文字与照片）')
    # 照片层: 用带羽化的原图crop（与vectorize同一photos.json，含fade定义）
    from vectorize_svg import feather_crop  # 同目录脚本
    for i, ph in enumerate(photos):
        x1, y1, x2, y2 = ph['box']
        rgba = feather_crop(Image.open(args.input).convert('RGB'),
                            (x1, y1, x2, y2), ph.get('fade', {}))
        add(rgba, ph.get('name', f'照片{i+1}'), top=y1, left=x1)
    add(Image.fromarray(text_layer), '文字层（色彩抠出）')

    if args.sam:
        with open(args.sam, 'rb') as f:
            elements = pickle.load(f)
        for i, m in enumerate(elements):
            x, y, w, h = m['bbox']
            seg = m['segmentation'][y:y+h, x:x+w].astype(np.uint8) * 255
            seg = cv2.GaussianBlur(seg, (3, 3), 0)
            rgba = np.dstack([img[y:y+h, x:x+w], seg])
            add(Image.fromarray(rgba), f'元素#{i:03d}_x{x}_y{y}', top=y, left=x)

    add(Image.open(args.input).convert('RGB'), '完整合成参考（原图）', visible=False)
    psd.save(args.output, encoding='utf-8')
    print(f'saved: {args.output} {os.path.getsize(args.output)/1024/1024:.0f} MB layers={len(psd)}')

    # 验证: composite必须与原图一致
    chk = PSDImage.open(args.output)
    comp = np.asarray(chk.composite().convert('RGB'), dtype=np.int16)
    d = np.abs(comp - img.astype(np.int16))
    print(f'验证: 合成vs原图 平均差={d.mean():.2f}（应为0）, 层数={len(chk)}')

if __name__ == '__main__':
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SAM自动分割海报元素 → 过滤去重 → 可视化验收 → sam_final.pkl（供build_psd.py --sam用）。
前置: pip3 install torch torchvision segment-anything; python3 patch_sam_mps.py; 下载ViT-B权重。
用法: python3 sam_elements.py input.jpg sam_vit_b.pth
"""
import argparse, pickle, time
import numpy as np
from PIL import Image, ImageDraw
import torch
from segment_anything import sam_model_registry, SamAutomaticMaskGenerator

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('input')
    ap.add_argument('checkpoint')
    args = ap.parse_args()

    img = np.array(Image.open(args.input).convert('RGB'))
    H, W = img.shape[:2]
    print('image', W, H, flush=True)

    sam = sam_model_registry['vit_b'](checkpoint=args.checkpoint)
    sam.to('mps' if torch.backends.mps.is_available() else 'cpu')
    gen = SamAutomaticMaskGenerator(
        model=sam, points_per_side=32,
        pred_iou_thresh=0.86, stability_score_thresh=0.92,
        crop_n_layers=1, crop_n_points_downscale_factor=2,
        min_mask_region_area=2000)
    t0 = time.time()
    masks = gen.generate(img)
    print(f'raw masks: {len(masks)}, {time.time()-t0:.0f}s', flush=True)

    # 过滤
    kept = [m for m in masks
            if 3000 <= m['area'] <= H * W * 0.45
            and m['predicted_iou'] >= 0.88 and m['stability_score'] >= 0.92]
    # 包含去重
    kept.sort(key=lambda x: -x['area'])
    final = []
    for m in kept:
        seg = m['segmentation']
        if any(np.logical_and(seg, f['segmentation']).sum() > 0.85 * m['area'] for f in final):
            continue
        final.append(m)
    print('kept:', len(final))

    # 可视化验收图（随机色块+序号）→ 给vision目检后再建PSD
    base = img.astype(np.float32) * 0.35
    rng = np.random.default_rng(42)
    vis = base.copy()
    for i, m in enumerate(final):
        color = rng.integers(60, 255, 3).astype(np.float32)
        seg = m['segmentation']
        vis[seg] = base[seg] * 0.3 + color * 0.7
    vis_img = Image.fromarray(vis.astype(np.uint8))
    vis_img.thumbnail((900, 2250))
    d = ImageDraw.Draw(vis_img)
    sc = vis_img.size[0] / W
    for i, m in enumerate(final):
        ys, xs = np.where(m['segmentation'])
        d.text((xs.mean() * sc, ys.mean() * sc), str(i), fill=(255, 255, 0))
    vis_img.save('sam_vis.jpg', quality=90)

    with open('sam_final.pkl', 'wb') as f:
        pickle.dump(final, f)
    print('输出: sam_vis.jpg（验收用）, sam_final.pkl（建PSD用）')

if __name__ == '__main__':
    main()

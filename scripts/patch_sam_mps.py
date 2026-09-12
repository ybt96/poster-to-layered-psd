#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给 site-packages 里的 segment_anything 打 MPS 兼容补丁（macOS Apple Silicon 必需）。
用法: python3 patch_sam_mps.py   （幂等，已打过会跳过）
"""
import segment_anything, os, re, sys

base = os.path.dirname(segment_anything.__file__)
amg = os.path.join(base, 'automatic_mask_generator.py')
sam = os.path.join(base, 'modeling', 'sam.py')

def patch(path, old, new, tag):
    with open(path) as f:
        src = f.read()
    if new in src:
        print(f'[skip] {tag} 已打补丁')
        return
    if old not in src:
        print(f'[FAIL] {tag} 找不到目标代码，segment_anything版本可能变了', file=sys.stderr)
        sys.exit(1)
    with open(path, 'w') as f:
        f.write(src.replace(old, new, 1))
    print(f'[ok] {tag}')

# 1. MPS不支持float64：points转float32
patch(amg,
      'in_points = torch.as_tensor(transformed_points, device=self.predictor.device)',
      'in_points = torch.as_tensor(transformed_points, dtype=torch.float32, device=self.predictor.device)',
      'amg float32')

# 2. 后处理转CPU，避免torchvision nms设备混用
patch(amg,
      '''            return_logits=True,
        )

        # Serialize predictions and store in MaskData''',
      '''            return_logits=True,
        )
        masks = masks.cpu()
        iou_preds = iou_preds.cpu()

        # Serialize predictions and store in MaskData''',
      'amg cpu-offload')

# 3. 最终上采样分块CPU做，绕开MPS单buffer约17GB上限
patch(sam,
      '''        masks = F.interpolate(masks, original_size, mode="bilinear", align_corners=False)
        return masks''',
      '''        outs = []
        for i in range(0, masks.shape[0], 8):
            outs.append(F.interpolate(masks[i:i+8].float().cpu(), original_size, mode="bilinear", align_corners=False))
        return torch.cat(outs, dim=0)''',
      'sam chunked-upsample')

print('全部补丁就绪')

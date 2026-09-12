#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""扁平海报 → 矢量SVG（照片区以带羽化alpha的位图嵌入）。
用法:
  python3 vectorize_svg.py input.jpg output.svg --photos photos.json
  photos.json: [{"box":[x1,y1,x2,y2], "fade":{"top":400,"bottom":110} }, ...]
  fade 四方向可选: top/bottom/left/right，值为羽化像素数；缺省无边=硬边（小图建议各边12）。
注意: 单张PNG原图>3MB会自动切片嵌入（libxml2 单属性10MB上限）。
"""
import argparse, base64, json, os
import numpy as np
from PIL import Image
import vtracer

def feather_crop(img, box, fade):
    crop = img.crop(box)
    w, h = crop.size
    alpha = np.full((h, w), 255, dtype=np.uint8)
    for y in range(h):
        for x in range(w):
            a = 255
            if 'top' in fade and y < fade['top']:
                a = min(a, int(255 * y / fade['top']))
            if 'bottom' in fade and y >= h - fade['bottom']:
                a = min(a, int(255 * (h - y) / fade['bottom']))
            if 'left' in fade and x < fade['left']:
                a = min(a, int(255 * x / fade['left']))
            if 'right' in fade and x >= w - fade['right']:
                a = min(a, int(255 * (w - x) / fade['right']))
            alpha[y, x] = a
    return Image.fromarray(np.dstack([np.array(crop), alpha]))

def b64_png(pil_img):
    import io
    buf = io.BytesIO()
    pil_img.save(buf, 'PNG', optimize=True)
    return buf.getvalue()

def slice_if_big(pil_img, x0, y0, max_bytes=3_000_000):
    """PNG超过max_bytes则水平切片，返回[(png_bytes,x,y,w,h),...]"""
    data = b64_png(pil_img)
    w, h = pil_img.size
    if len(data) <= max_bytes:
        return [(data, x0, y0, w, h)]
    n = int(np.ceil(len(data) / max_bytes))
    out = []
    step = h // n + 1
    for i in range(0, h, step):
        part = pil_img.crop((0, i, w, min(h, i + step)))
        out.append((b64_png(part), x0, y0 + i, w, part.size[1]))
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('input')
    ap.add_argument('output')
    ap.add_argument('--photos', help='照片区JSON: [{"box":[x1,y1,x2,y2],"fade":{...}}]')
    args = ap.parse_args()

    img = Image.open(args.input).convert('RGB')
    W, H = img.size

    tmp_svg = args.output + '.vtraced.tmp.svg'
    print('vtracer 矢量化中...')
    vtracer.convert_image_to_svg_py(
        args.input, tmp_svg,
        colormode='color', hierarchical='stacked', mode='spline',
        filter_speckle=4, color_precision=7, layer_difference=16,
        corner_threshold=60, length_threshold=4.0, max_iterations=10,
        splice_threshold=45, path_precision=2)

    with open(tmp_svg) as f:
        svg = f.read()
    os.remove(tmp_svg)
    # 加viewBox保证无损缩放
    svg = svg.replace(f'width="{W}" height="{H}"',
                      f'width="{W}" height="{H}" viewBox="0 0 {W} {H}"', 1)

    overlays = []
    if args.photos:
        for ph in json.load(open(args.photos)):
            x1, y1, x2, y2 = ph['box']
            rgba = feather_crop(img, (x1, y1, x2, y2), ph.get('fade', {}))
            for data, x, y, w, h in slice_if_big(rgba, x1, y1):
                b64 = base64.b64encode(data).decode()
                overlays.append(
                    f'<image x="{x}" y="{y}" width="{w}" height="{h}" '
                    f'href="data:image/png;base64,{b64}"/>')

    svg = svg.replace('</svg>', '\n' + '\n'.join(overlays) + '\n</svg>')
    with open(args.output, 'w') as f:
        f.write(svg)
    print(f'done: {args.output} {os.path.getsize(args.output)/1024/1024:.1f} MB')
    print('验证: rsvg-convert -w', W, args.output, '-o /tmp/check.png')

if __name__ == '__main__':
    main()

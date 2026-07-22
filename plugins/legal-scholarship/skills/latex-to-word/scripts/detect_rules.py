# -*- coding: utf-8 -*-
"""Detect horizontal rule bands in a table PNG and report their x-segments and
gaps, to locate broken/partial rules. Usage: detect_rules.py <png> [<png> ...]"""
import sys
import numpy as np
from PIL import Image

for path in sys.argv[1:]:
    a = np.asarray(Image.open(path).convert('L'))
    H, W = a.shape
    dark = a < 110
    rowsum = dark.sum(axis=1)
    thr = 0.20 * W
    cand = [y for y in range(H) if rowsum[y] > thr]
    bands = []
    for y in cand:
        if bands and y - bands[-1][-1] <= 2:
            bands[-1].append(y)
        else:
            bands.append([y])
    print(f"\n{path}  ({W}x{H})  -> {len(bands)} horizontal rule band(s)")
    for band in bands:
        mask = dark[band[0]:band[-1] + 1].any(axis=0)
        xs = np.where(mask)[0]
        segs = []
        if len(xs):
            start = prev = xs[0]
            for x in xs[1:]:
                if x - prev > 10:
                    segs.append((int(start), int(prev)))
                    start = x
                prev = x
            segs.append((int(start), int(prev)))
        gaps = [(segs[i][1], segs[i + 1][0], segs[i + 1][0] - segs[i][1])
                for i in range(len(segs) - 1)]
        print(f"  y={band[0]:>4}-{band[-1]:<4} segs={segs}")
        big = [g for g in gaps if g[2] > 12]
        if big:
            print(f"      GAPS>12px: {big}")

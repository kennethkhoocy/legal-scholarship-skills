# -*- coding: utf-8 -*-
"""Trim white margins from a PNG. Usage: crop_white.py <in.png> <out.png> [margin]"""
import sys
from PIL import Image, ImageChops
im = Image.open(sys.argv[1]).convert('RGB')
m = int(sys.argv[3]) if len(sys.argv) > 3 else 24
bbox = ImageChops.difference(im, Image.new('RGB', im.size, (255, 255, 255))).getbbox()
if bbox:
    x0, y0, x1, y1 = bbox
    im.crop((max(0, x0 - m), max(0, y0 - m),
             min(im.width, x1 + m), min(im.height, y1 + m))).save(sys.argv[2])
    print(f"cropped {bbox} -> {sys.argv[2]}")
else:
    im.save(sys.argv[2]); print("no content found")

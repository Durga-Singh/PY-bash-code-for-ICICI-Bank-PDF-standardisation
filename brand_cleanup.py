"""Conservative visual matching against the user's reference banner.

Matches logo artwork across resizing/JPEG compression, never arbitrary text or
an orange rectangle. Unknown images are retained for review.
"""
from functools import lru_cache
from io import BytesIO
from PIL import Image
import fitz

def pixels(image):
    method=getattr(image,'get_flattened_data',None)
    return list(method() if method else image.getdata())

def signature(image):
    image = image.convert('RGB')
    image.thumbnail((1000, 400))
    values = pixels(image)
    orange = sum(r > 120 and r > g * 1.2 and g > b * 1.25 and b < 140 for r, g, b in values) / max(1, len(values))
    if orange < .30:
        return None
    mask = Image.new('L', image.size)
    mask.putdata([255 if min(p) > 190 and max(p) - min(p) < 70 else 0 for p in values])
    box = mask.getbbox()
    if not box:
        return None
    aspect = (box[2] - box[0]) / max(1, box[3] - box[1])
    ink = sum(pixels(mask)) / (255 * len(values))
    if not .03 < ink < .6:
        return None
    return aspect, pixels(mask.crop(box).resize((160, 32), Image.Resampling.LANCZOS))

@lru_cache(maxsize=4)
def reference(path):
    with Image.open(path) as image:
        return signature(image)

def matches(pixmap, reference_path):
    if pixmap.n not in (3, 4): pixmap = fitz.Pixmap(fitz.csRGB, pixmap)
    with Image.open(BytesIO(pixmap.tobytes('png'))) as image:
        candidate = signature(image)
    target = reference(str(reference_path))
    if candidate is None or target is None:
        return False
    aspect, a = candidate; ref_aspect, b = target
    if abs(aspect / ref_aspect - 1) > .13:
        return False
    dice = 2 * sum(min(x, y) for x, y in zip(a, b)) / max(1, sum(a) + sum(b))
    error = sum(abs(x-y) for x, y in zip(a, b)) / (255 * len(a))
    return dice >= .88 and error <= .10

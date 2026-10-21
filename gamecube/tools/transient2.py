# Find one-frame flashes in a run of NWII_SHOT_EVERY=1 screenshots: frames that
# differ from both neighbours more than the neighbours differ from each other.
# transient2.py <dir with shot_N.bmp> <first N> <last N>
import sys, os
from PIL import Image, ImageChops
d, a, b = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
def load(i):
    p = os.path.join(d, f"shot_{i}.bmp")
    return Image.open(p).convert("L").resize((427, 240)) if os.path.exists(p) else None
def diff(x, y):
    h = ImageChops.difference(x, y).point(lambda v: 255 if v > 50 else 0)
    return h.histogram()[255]
seq=[]; prev=None
for i in range(a, b+1):
    im = load(i)
    if im is None: continue
    if prev is None or diff(prev, im) > 0: seq.append((i, im)); prev = im
hits=[]
for k in range(1, len(seq)-1):
    (_, p), (ic, c), (_, n) = seq[k-1], seq[k], seq[k+1]
    dpc, dcn, dpn = diff(p, c), diff(c, n), diff(p, n)
    score = min(dpc, dcn) - dpn
    hits.append((score, ic, dpc, dcn, dpn))
print("distinct", len(seq))
for h in sorted(hits, reverse=True)[:10]: print(h)

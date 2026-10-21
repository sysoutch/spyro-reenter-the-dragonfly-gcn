# Resolve NWII_NPROF_OUT samples against the MSVC linker map.
import sys, re, bisect, collections
mapf, samples = sys.argv[1], sys.argv[2]
skip_intervals = int(sys.argv[3]) if len(sys.argv) > 3 else 0
base = 0x140000000
syms = []
for line in open(mapf, errors='replace'):
    m = re.match(r'\s*[0-9a-f]{4}:[0-9a-f]{8}\s+(\S+)\s+([0-9a-f]{16})\s+(.*)', line)
    if m:
        va = int(m.group(2), 16)
        if va >= base: syms.append((va - base, m.group(1), m.group(3).strip()))
syms.sort()
starts = [s[0] for s in syms]
by = collections.Counter(); objs = collections.Counter(); total = 0; interval = -1
for line in open(samples):
    if line.startswith('#'): interval += 1; continue
    if interval < skip_intervals: continue
    p = line.split()
    if p[0] == 'dll': by['[dll ' + p[1] + ']'] += int(p[2]); total += int(p[2]); continue
    rva, n = int(p[0], 16), int(p[1]); total += n
    i = bisect.bisect_right(starts, rva) - 1
    name, obj = (syms[i][1], syms[i][2]) if i >= 0 else ('?', '?')
    by[name] += n; objs[obj.split(':')[-1]] += n
print('total samples', total)
for k, v in by.most_common(40): print('%5.1f%%  %s' % (100.0 * v / total, k[:110]))
print('-- by object --')
for k, v in objs.most_common(15): print('%5.1f%%  %s' % (100.0 * v / total, k))

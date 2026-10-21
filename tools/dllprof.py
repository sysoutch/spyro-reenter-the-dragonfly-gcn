# Resolve "dll <base> <count> <offset>" samples of one module via its PE export table.
import sys, struct, bisect, collections
samples, base_hex, dll_path = sys.argv[1], sys.argv[2].lower(), sys.argv[3]
skip = int(sys.argv[4]) if len(sys.argv) > 4 else 0
d = open(dll_path, 'rb').read()
pe = struct.unpack_from('<I', d, 0x3C)[0]
nsec = struct.unpack_from('<H', d, pe + 6)[0]; opt = pe + 24
exp_rva = struct.unpack_from('<I', d, opt + 112)[0]
secs = []
for i in range(nsec):
    o = opt + struct.unpack_from('<H', d, pe + 20)[0] + i * 40
    va, vsz, raw = struct.unpack_from('<III', d, o + 12)[0], struct.unpack_from('<I', d, o + 8)[0], struct.unpack_from('<I', d, o + 20)[0]
    secs.append((va, vsz, raw))
def off(rva):
    for va, vsz, raw in secs:
        if va <= rva < va + max(vsz, 1): return rva - va + raw
    raise ValueError(rva)
e = off(exp_rva)
nfun, nnames, afun, anames, aord = struct.unpack_from('<IIIII', d, e + 20)
funcs = [struct.unpack_from('<I', d, off(afun) + 4 * i)[0] for i in range(nfun)]
syms = []
for i in range(nnames):
    nr = struct.unpack_from('<I', d, off(anames) + 4 * i)[0]
    o = struct.unpack_from('<H', d, off(aord) + 2 * i)[0]
    s = d[off(nr):d.index(b'\0', off(nr))].decode()
    syms.append((funcs[o], s))
syms.sort(); starts = [x[0] for x in syms]
c = collections.Counter(); tot = 0; interval = -1
for line in open(samples):
    if line.startswith('#'): interval += 1; continue
    if interval < skip: continue
    p = line.split()
    if len(p) == 4 and p[0] == 'dll' and p[1].lower().lstrip('0').endswith(base_hex.lower().lstrip('0x').lstrip('0')):
        n, rva = int(p[2]), int(p[3], 16)
        i = bisect.bisect_right(starts, rva) - 1
        c[syms[i][1] if i >= 0 else '?'] += n; tot += n
print('samples in module', tot)
for k, v in c.most_common(12): print('%5.1f%%  %s' % (100.0 * v / tot, k))

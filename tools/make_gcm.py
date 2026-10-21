"""Rebuild a raw GameCube disc image (.gcm) from an extracted folder, for
testing the runtime's ISO path: make_gcm.py <extracted dir> <out.gcm>"""
import os, struct, sys

root, out = sys.argv[1], sys.argv[2]
sysd = os.path.join(root, 'sys')
boot = open(os.path.join(sysd, 'boot.bin'), 'rb').read()
fst = open(os.path.join(sysd, 'fst.bin'), 'rb').read()
dol_off, fst_off = struct.unpack('>II', boot[0x420:0x428])

with open(out, 'wb') as f:
    def put(off, path):
        f.seek(off)
        with open(path, 'rb') as src:
            while chunk := src.read(1 << 22):
                f.write(chunk)
    put(0, os.path.join(sysd, 'boot.bin'))
    put(0x440, os.path.join(sysd, 'bi2.bin'))
    put(0x2440, os.path.join(sysd, 'apploader.img'))
    put(dol_off, os.path.join(sysd, 'main.dol'))
    put(fst_off, os.path.join(sysd, 'fst.bin'))
    n = struct.unpack('>I', fst[8:12])[0]
    strings = fst[n * 12:]
    dirs = [(n, os.path.join(root, 'files'))]
    count = 0
    for i in range(1, n):
        while len(dirs) > 1 and i >= dirs[-1][0]:
            dirs.pop()
        e = fst[i * 12:i * 12 + 12]
        is_dir = e[0] != 0
        name_off = int.from_bytes(e[1:4], 'big')
        off, ln = struct.unpack('>II', e[4:12])
        name = strings[name_off:strings.index(b'\0', name_off)].decode('shift_jis')
        if is_dir:
            dirs.append((ln, os.path.join(dirs[-1][1], name)))
        else:
            put(off, os.path.join(dirs[-1][1], name))
            count += 1
    f.truncate(1459978240)  # full GameCube disc size
print('files', count, 'size', os.path.getsize(out))

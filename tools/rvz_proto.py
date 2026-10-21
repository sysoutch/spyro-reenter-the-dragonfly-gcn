"""Prototype RVZ (GameCube) reader, checked against an extracted disc.
rvz_proto.py <disc.rvz> <extracted dir>"""
import os, struct, sys, hashlib, zstandard

K, J = 521, 32
BLOCK = 0x8000


class LFG:
    """Dolphin's lagged Fibonacci generator for RVZ junk data."""
    def set_seed(self, seed_bytes):
        b = list(struct.unpack('>17I', seed_bytes)) + [0] * (K - 17)
        for i in range(17, K):
            b[i] = ((b[i - 17] << 23) & 0xFFFFFFFF) ^ (b[i - 16] >> 9) ^ b[i - 1]
        # Output form: shift oddity folded in; stored so bytes come out big-endian.
        self.buf = [(x & 0xFF00FFFF) | ((x >> 2) & 0x00FF0000) for x in b]
        self.pos = 0
        for _ in range(4):
            self.forward()

    def forward(self):
        b = self.buf
        for i in range(J):
            b[i] ^= b[i + K - J]
        for i in range(J, K):
            b[i] ^= b[i - J]

    def skip(self, n):
        self.pos += n
        while self.pos >= K * 4:
            self.forward()
            self.pos -= K * 4

    def get(self, n):
        out = bytearray()
        while n:
            raw = struct.pack('>%dI' % K, *self.buf)
            take = min(n, K * 4 - self.pos)
            out += raw[self.pos:self.pos + take]
            self.pos += take
            n -= take
            if self.pos == K * 4:
                self.forward()
                self.pos = 0
        return bytes(out)


class Rvz:
    def __init__(self, path):
        self.f = open(path, 'rb')
        h1 = self.f.read(0x48)
        assert h1[:4] == b'RVZ\x01'
        h2size = struct.unpack('>I', h1[12:16])[0]
        self.iso_size = struct.unpack('>Q', h1[0x24:0x2C])[0]
        d = self.f.read(h2size)
        self.disc_type, self.comp, _, self.chunk = struct.unpack('>IIiI', d[:16])
        assert self.comp == 5, 'only zstd'
        self.disc_header = d[16:16 + 0x80]
        o = 16 + 0x80 + 16 + 20
        nraw, rawoff, rawsz, ngrp, grpoff, grpsz = struct.unpack('>IQIIQI', d[o:o + 32])
        dz = zstandard.ZstdDecompressor()
        self.f.seek(rawoff)
        raw = dz.decompress(self.f.read(rawsz), max_output_size=nraw * 24)
        self.raw = [struct.unpack('>QQII', raw[i * 24:i * 24 + 24]) for i in range(nraw)]
        self.f.seek(grpoff)
        grp = dz.decompress(self.f.read(grpsz), max_output_size=ngrp * 12)
        self.groups = [struct.unpack('>III', grp[i * 12:i * 12 + 12]) for i in range(ngrp)]
        self.cache = {}

    def group(self, gi, disc_off):
        if gi in self.cache:
            return self.cache[gi]
        off4, size, packed = self.groups[gi]
        compressed = bool(size & 0x80000000)
        size &= 0x7FFFFFFF
        if size == 0:
            data = bytes(self.chunk)
        else:
            self.f.seek(off4 << 2)
            data = self.f.read(size)
            if compressed:
                data = zstandard.ZstdDecompressor().decompress(data, max_output_size=max(self.chunk, packed))
            if packed:
                data = self.unpack(data, disc_off)
        self.cache = {gi: data}
        return data

    def unpack(self, data, disc_off):
        out = bytearray()
        p = 0
        lfg = LFG()
        while p < len(data):
            n = struct.unpack('>I', data[p:p + 4])[0]
            p += 4
            if n & 0x80000000:
                n &= 0x7FFFFFFF
                lfg.set_seed(data[p:p + 68])
                p += 68
                lfg.skip((disc_off + len(out)) % BLOCK)
                out += lfg.get(n)
            else:
                out += data[p:p + n]
                p += n
        return bytes(out)

    def read(self, offset, size):
        out = bytearray()
        while size > 0:
            if offset < 0x80:
                take = min(size, 0x80 - offset)
                out += self.disc_header[offset:offset + take]
            else:
                for (doff, dsize, gidx, ngroups) in self.raw:
                    base = doff - doff % BLOCK
                    end = doff + dsize
                    if base <= offset < end:
                        i = (offset - base) // self.chunk
                        if i >= ngroups:
                            continue
                        g = self.group(gidx + i, base + i * self.chunk)
                        within = offset - base - i * self.chunk
                        take = min(size, self.chunk - within, end - offset)
                        out += g[within:within + take]
                        break
                else:
                    take = size  # not covered: zeros
                    out += bytes(take)
            offset += take
            size -= take
        return bytes(out)


if __name__ == '__main__':
    r = Rvz(sys.argv[1])
    root = sys.argv[2]
    print('raw entries', r.raw[:3], 'groups', len(r.groups), 'chunk', hex(r.chunk))
    boot = r.read(0, 0x440)
    assert boot == open(os.path.join(root, 'sys', 'boot.bin'), 'rb').read(), 'boot.bin mismatch'
    dol_off, fst_off, fst_size = struct.unpack('>III', boot[0x420:0x42C])
    for name, off in (('bi2.bin', 0x440), ('apploader.img', 0x2440), ('main.dol', dol_off), ('fst.bin', fst_off)):
        ref = open(os.path.join(root, 'sys', name), 'rb').read()
        got = r.read(off, len(ref))
        print(name, 'OK' if got == ref else 'MISMATCH')
    # A few files from the FST.
    fst = r.read(fst_off, fst_size)
    n = struct.unpack('>I', fst[8:12])[0]
    strings = fst[n * 12:]
    dirs = [(n, os.path.join(root, 'files'))]
    checked = bad = 0
    for i in range(1, n):
        while len(dirs) > 1 and i >= dirs[-1][0]:
            dirs.pop()
        e = fst[i * 12:i * 12 + 12]
        nm = strings[int.from_bytes(e[1:4], 'big'):].split(b'\0')[0].decode('shift_jis')
        off, ln = struct.unpack('>II', e[4:12])
        if e[0]:
            dirs.append((ln, os.path.join(dirs[-1][1], nm)))
        elif i % 25 == 0 or i == n - 1:
            ref = open(os.path.join(dirs[-1][1], nm), 'rb').read()
            ok = r.read(off, ln) == ref
            checked += 1
            bad += not ok
            if not ok:
                print('MISMATCH', nm)
    print('files checked', checked, 'bad', bad)

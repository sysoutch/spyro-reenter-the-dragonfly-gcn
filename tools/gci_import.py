# Put a GameCube save (.gci: 64-byte directory entry + its 8 KB blocks) into
# a copy of a raw memory-card image. A file with the same game code and name
# on the card is replaced. The input card is never modified.
#   gci_import.py <card.raw> <save.gci> <out.raw>
import struct, sys

BLOCK = 0x2000


def checksums(data):
    c1 = c2 = 0
    for (w,) in struct.iter_unpack('>H', data):
        c1 = (c1 + w) & 0xFFFF
        c2 = (c2 + (w ^ 0xFFFF)) & 0xFFFF
    return (0 if c1 == 0xFFFF else c1), (0 if c2 == 0xFFFF else c2)


card_path, gci_path, out_path = sys.argv[1:4]
card = bytearray(open(card_path, 'rb').read())
gci = open(gci_path, 'rb').read()
entry, data = bytearray(gci[:64]), gci[64:]
nblocks = struct.unpack_from('>H', entry, 0x38)[0]
assert len(data) == nblocks * BLOCK, 'GCI size does not match its block count'
total = len(card) // BLOCK

# The current directory / BAT is the copy with the higher update counter.
dirs = [1, 2]
dir_blk = max(dirs, key=lambda b: struct.unpack_from('>H', card, b * BLOCK + 0x1FFA)[0])
bat_blk = max([3, 4], key=lambda b: struct.unpack_from('>H', card, b * BLOCK + 4)[0])
d = bytearray(card[dir_blk * BLOCK:(dir_blk + 1) * BLOCK])
bat = bytearray(card[bat_blk * BLOCK:(bat_blk + 1) * BLOCK])


def bat_get(b):
    return struct.unpack_from('>H', bat, 0xA + (b - 5) * 2)[0]


def bat_set(b, v):
    struct.pack_into('>H', bat, 0xA + (b - 5) * 2, v)


# Drop an existing file with the same game code + file name.
key = bytes(entry[0:6]) + bytes(entry[8:0x28])
free_slot = None
for i in range(127):
    e = d[i * 64:(i + 1) * 64]
    if e[0:4] == b'\xff\xff\xff\xff':
        free_slot = i if free_slot is None else free_slot
        continue
    if bytes(e[0:6]) + bytes(e[8:0x28]) == key:
        b = struct.unpack_from('>H', e, 0x36)[0]
        while b not in (0xFFFF, 0) and 5 <= b < total:
            nxt = bat_get(b)
            bat_set(b, 0)
            b = nxt
        d[i * 64:(i + 1) * 64] = b'\xff' * 64
        free_slot = i if free_slot is None or i < free_slot else free_slot
        print('replaced the existing', e[8:0x28].split(b'\0')[0].decode(), 'save')
assert free_slot is not None, 'directory full'

# Allocate free blocks and chain them in the BAT.
blocks = [b for b in range(5, total) if bat_get(b) == 0][:nblocks]
assert len(blocks) == nblocks, 'not enough free blocks'
for i, b in enumerate(blocks):
    bat_set(b, blocks[i + 1] if i + 1 < nblocks else 0xFFFF)
    card[b * BLOCK:(b + 1) * BLOCK] = data[i * BLOCK:(i + 1) * BLOCK]
struct.pack_into('>H', entry, 0x36, blocks[0])
d[free_slot * 64:(free_slot + 1) * 64] = entry

# Free count, last allocated, counters, checksums -- written to the other copy
# so the card keeps a valid backup.
struct.pack_into('>H', bat, 6, sum(1 for b in range(5, total) if bat_get(b) == 0))
struct.pack_into('>H', bat, 8, blocks[-1])
struct.pack_into('>H', bat, 4, (struct.unpack_from('>H', bat, 4)[0] + 1) & 0xFFFF)
struct.pack_into('>HH', bat, 0, *checksums(bat[4:]))
struct.pack_into('>H', d, 0x1FFA, (struct.unpack_from('>H', d, 0x1FFA)[0] + 1) & 0xFFFF)
struct.pack_into('>HH', d, 0x1FFC, *checksums(d[:0x1FFC]))
other_dir = 2 if dir_blk == 1 else 1
other_bat = 4 if bat_blk == 3 else 3
card[other_dir * BLOCK:(other_dir + 1) * BLOCK] = d
card[other_bat * BLOCK:(other_bat + 1) * BLOCK] = bat
open(out_path, 'wb').write(card)
print('imported %d blocks at block %d into %s' % (nblocks, blocks[0], out_path))

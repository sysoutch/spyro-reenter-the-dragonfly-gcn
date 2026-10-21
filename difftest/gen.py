# Build a differential test of the recompiler against the runtime interpreter:
# every distinct straight-line instruction body found in output_*.cpp becomes
# a test function; the harness runs it and interpret_one() on equal states.
import re, glob, os, sys
src = sys.argv[1]; out = sys.argv[2]
hdr = re.compile(r'^    // 0x([0-9A-F]{8}): ([0-9A-F]{8})\s*$')
bad = re.compile(r'goto|return|ctx\.pc|ctx\.lr|ctx\.ctr|ctx\.msr|srr|sprg|func_|process_pending|micro_interpret|'
                 r'handle_syscall|read_dec|write_dec|timebase|note_null|interpret_step|std::cout|std::cerr|'
                 r'trace_call|inst_count|gqr|fpscr|std::exit|nwii_|PADRead|GX|OS|VI|DC|IC|AX|AR|__')
allowed_ns = re.compile(r'nwii::runtime::(ppc_cvt_s32|fpr_low_word)')
bodies = {}
for f in sorted(glob.glob(os.path.join(src, 'output_*.cpp'))):
    word = None; body = []
    def flush():
        if word is None or not body: return
        text = '\n'.join(body)
        t2 = allowed_ns.sub('', text)
        if bad.search(t2) or 'nwii::runtime::' in t2: return
        op = int(word, 16) >> 26
        if op in (16, 17, 18, 19): return
        bodies.setdefault(int(word, 16), text)
    for line in open(f, encoding='utf-8', errors='replace'):
        line = line.rstrip('\n')
        m = hdr.match(line)
        if m:
            flush(); word = m.group(2); body = []; continue
        if word is None: continue
        if line.startswith('loc_') or line.startswith('void ') or line.startswith('}') or line.startswith('#'):
            flush(); word = None; body = []; continue
        body.append(line)
    flush()
items = sorted(bodies.items())
print('unique testable instructions:', len(items))
os.makedirs(out, exist_ok=True)
CH = 4000
nfiles = (len(items) + CH - 1) // CH
pre = ('#include "runtime/cpu_context.h"\n#include <stdint.h>\n#include <bit>\n#include <cmath>\n#include <cstring>\n'
       '#ifdef _MSC_VER\n#include <stdlib.h>\n#ifndef __builtin_bswap32\n#define __builtin_bswap32 _byteswap_ulong\n#endif\n#endif\n'
       'using namespace nwii::runtime;\n#include "tests.h"\n')
with open(os.path.join(out, 'tests.h'), 'w') as h:
    h.write('#pragma once\n#include <cstdint>\nnamespace nwii::runtime { struct CPUContext; }\n'
            'struct DiffTest { uint32_t word; void (*fn)(nwii::runtime::CPUContext&); bool mem; };\n'
            'extern const DiffTest g_tests[]; extern const unsigned g_ntests;\n')
for k in range(nfiles):
    with open(os.path.join(out, f't{k}.cpp'), 'w') as g:
        g.write(pre)
        for w, body in items[k*CH:(k+1)*CH]:
            g.write(f'void t_{w:08X}(CPUContext& ctx) {{\n{body}\n}}\n')
with open(os.path.join(out, 'table.cpp'), 'w') as g:
    g.write('#include "tests.h"\n')
    for w, _ in items: g.write(f'void t_{w:08X}(nwii::runtime::CPUContext&);\n')
    g.write('const DiffTest g_tests[] = {\n')
    for w, body in items: g.write(f'  {{0x{w:08X}u, t_{w:08X}, {"true" if "mmu." in body else "false"}}},\n')
    g.write('};\nconst unsigned g_ntests = sizeof(g_tests)/sizeof(g_tests[0]);\n')
print('files', nfiles)

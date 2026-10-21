// Differential test: recompiled instruction bodies vs nwii::runtime::interpret_one.
#include "runtime/cpu_context.h"
#include "gen/tests.h"
#include <cstdio>
#include <cstring>
#include <cmath>
#include <map>
#include <random>
#include <string>
#include <iostream>
#include <sstream>

using namespace nwii::runtime;

// Globals the runtime library expects from the game's main.cpp.
namespace nwii::runtime {
CPUContext *g_ctx_ptr = nullptr;
MMU *g_mmu = nullptr;
namespace efb {
int scale = 1, samples = 1, width = 640, height = 480, xfb_x, xfb_y, xfb_w, xfb_h;
bool widescreen = false; float sx = 1, sy = 1;
unsigned draw_fbo, resolve_fbo, display_fbo;
void create() {} void resolve() {} void snapshot(uint32_t) {} void select_display(uint32_t) {}
}
}

static constexpr uint32_t WIN = 0x80400000u, WIN_SIZE = 0x10000, CODE = 0x80003100u;

static uint64_t bits(double d) { uint64_t b; std::memcpy(&b, &d, 8); return b; }
static bool feq(double a, double b) { return (std::isnan(a) && std::isnan(b)) || bits(a) == bits(b); }

int main(int argc, char **argv) {
  const int iters = argc > 1 ? std::atoi(argv[1]) : 24;
  const char *only = argc > 2 ? argv[2] : nullptr;
  static CPUContext A, B;
  std::mt19937_64 rng(12345);
  auto r32 = [&] { return (uint32_t)rng(); };
  const uint32_t specials[] = {0, 1, 2, 0xFFFFFFFFu, 0x80000000u, 0x7FFFFFFFu, 0xFFFF, 0x8000, 31, 32, 33, 63};
  auto rgpr = [&](bool ptr) -> uint32_t {
    if (ptr) return WIN + 0x4000 + (r32() % 0x4000 & ~7u);
    switch (r32() % 4) { case 0: return specials[r32() % 12]; case 1: return r32() & 0xFF; default: return r32(); }
  };
  auto rfp = [&]() -> double {
    switch (r32() % 8) {
    case 0: return 0.0; case 1: return -0.0; case 2: return (double)(float)((int)(r32() % 2001) - 1000) / 8.0;
    case 3: return (double)(float)std::ldexp((double)(r32() % 1000000) - 500000.0, (int)(r32() % 40) - 20);
    case 4: { double d; uint64_t b = rng(); std::memcpy(&d, &b, 8); return d; }
    case 5: return (r32() & 1) ? INFINITY : -INFINITY;
    default: return (double)(float)((double)(int32_t)r32() / 65536.0);
    }
  };
  std::map<std::string, int> fails;  // mnemonic-ish key -> count
  unsigned nfail = 0, tested = 0, interp_unhandled = 0;
  std::stringstream errsink; auto *old = std::cerr.rdbuf(errsink.rdbuf());
  for (unsigned t = 0; t < g_ntests; ++t) {
    const DiffTest &T = g_tests[t];
    if (only && std::strtoul(only, nullptr, 16) != T.word) continue;
    ++tested;
    bool bad = false; std::string why;
    for (int it = 0; it < iters && !bad; ++it) {
      const bool ptr = T.mem || (it & 1);
      for (int i = 0; i < 32; ++i) { A.gpr[i] = rgpr(ptr && i != 0 ? true : (ptr ? false : false) || (ptr && (r32() & 1))); }
      if (T.mem) for (int i = 1; i < 32; ++i) A.gpr[i] = rgpr(true);
      for (int i = 0; i < 32; ++i) { A.fpr[i] = rfp(); A.ps1[i] = rfp(); }
      for (int i = 0; i < 8; ++i) { uint32_t c = r32(); A.cr[i].lt = c & 1; A.cr[i].gt = c & 2; A.cr[i].eq = c & 4; A.cr[i].so = c & 8; }
      A.xer = r32() & 0xE000007F; A.gqr = {}; A.fpscr = 0;
      B.gpr = A.gpr; B.fpr = A.fpr; B.ps1 = A.ps1; B.cr = A.cr; B.xer = A.xer; B.gqr = A.gqr; B.fpscr = 0;
      B.lr = A.lr = 0x80001000; B.ctr = A.ctr = 0x80001000;
      for (uint32_t a = 0; a < WIN_SIZE; a += 4) { uint32_t v = r32(); A.mmu.write32(WIN + a, v); B.mmu.write32(WIN + a, v); }
      B.mmu.write32(CODE, T.word); B.pc = CODE; A.pc = CODE;
      const size_t errpos = errsink.tellp();
      T.fn(A);
      interpret_one(B);
      if ((size_t)errsink.tellp() != errpos) {
        ++interp_unhandled;
        char key[64]; std::snprintf(key, sizeof key, "UNHANDLED op%u xo10=%u", T.word >> 26, (T.word >> 1) & 0x3FF);
        fails[key]++;
        bad = false; break;
      }
      std::ostringstream w;
      for (int i = 0; i < 32; ++i) if (A.gpr[i] != B.gpr[i]) w << " r" << i << " rec=" << std::hex << A.gpr[i] << " int=" << B.gpr[i] << std::dec;
      for (int i = 0; i < 32; ++i) if (!feq(A.fpr[i], B.fpr[i])) w << " f" << i << " rec=" << A.fpr[i] << " int=" << B.fpr[i];
      for (int i = 0; i < 32; ++i) if (!feq(A.ps1[i], B.ps1[i])) w << " ps1_" << i << " rec=" << A.ps1[i] << " int=" << B.ps1[i];
      for (int i = 0; i < 8; ++i) if (A.cr[i].lt != B.cr[i].lt || A.cr[i].gt != B.cr[i].gt || A.cr[i].eq != B.cr[i].eq)
        w << " cr" << i << " rec=" << A.cr[i].lt << A.cr[i].gt << A.cr[i].eq << A.cr[i].so << " int=" << B.cr[i].lt << B.cr[i].gt << B.cr[i].eq << B.cr[i].so;
      if ((A.xer ^ B.xer) & 0x20000000) w << " CA rec=" << ((A.xer >> 29) & 1) << " int=" << ((B.xer >> 29) & 1);
      for (uint32_t a = 0; a < WIN_SIZE; a += 4) if (A.mmu.read32(WIN + a) != B.mmu.read32(WIN + a)) { w << " mem@" << std::hex << WIN + a; break; }
      if (!w.str().empty()) { bad = true; why = w.str(); }
    }
    if (bad) {
      ++nfail;
      const uint32_t op = T.word >> 26, xo10 = (T.word >> 1) & 0x3FF, xo5 = (T.word >> 1) & 0x1F;
      char key[64]; std::snprintf(key, sizeof key, "op%u xo10=%u xo5=%u", op, xo10, xo5);
      if (fails[key]++ < 3) std::printf("FAIL %08X [%s]%s\n", T.word, key, why.c_str());
    }
  }
  std::cerr.rdbuf(old);
  std::printf("tested %u, failing %u, interpreter-unhandled %u\n", tested, nfail, interp_unhandled);
  for (auto &[k, n] : fails) std::printf("  %5d  %s\n", n, k.c_str());
}

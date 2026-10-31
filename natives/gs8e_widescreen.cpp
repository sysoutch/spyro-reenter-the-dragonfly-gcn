// Spyro: Enter the Dragonfly (GS8E7D) -- widescreen view culling.
//
// [hle_post_hooks] "80039114" = "gs8e_widen_cull": the game's camera setup
// (this, fovX, fovY, near, far) stores the view frustum the object culling
// tests against -- +0xF58/+0xF60 = -/+ tan(fovX/2), +0xF5C/+0xF64 the same
// for Y -- and then sets the projection. The runtime's widescreen option
// widens the projection to 16:9 at render time, but the game still culled
// against its 4:3 frustum: objects only in the extra width were not drawn
// (popping in at the side edges). With widescreen on, the horizontal extent is widened
// by the same factor. The game's own anamorphic 16:9 mode (aspect at +188
// already ~1.7) passes a wide fovX itself and is left alone.
//
// This file is part of the port, not derived from the game's code; build.ps1
// copies it next to the generated natives.

#include "runtime/cpu_context.h"
#include "runtime/efb.h"

#include <cstring>

using nwii::runtime::CPUContext;

namespace {
float ReadF(CPUContext &ctx, uint32_t a) {
  const uint32_t w = ctx.mmu.read32(a);
  float f;
  std::memcpy(&f, &w, 4);
  return f;
}
void WriteF(CPUContext &ctx, uint32_t a, float f) {
  uint32_t w;
  std::memcpy(&w, &f, 4);
  ctx.mmu.write32(a, w);
}
} // namespace

extern "C" void gs8e_widen_cull(CPUContext &ctx, const unsigned int *args) {
  if (!nwii::runtime::efb::widescreen) return;
  const uint32_t cam = args[0];
  const float aspect = ReadF(ctx, cam + 188);
  if (!(aspect > 0.0f && aspect < 1.5f)) return;
  for (uint32_t off : {0xF58u, 0xF60u})
    WriteF(ctx, cam + off, ReadF(ctx, cam + off) * nwii::runtime::efb::wide);
}

// Spyro: Enter the Dragonfly (GS8E7D) -- camera pitch smoothing.
//
// [hle_pre_hooks] "800378E4" = "gs8e_smooth_camera": the renderer's camera
// object (this) holds the view matrix at +0x118 (row-vector form, rotation
// in rows 0-2, translation in row 3); when it changed (+0xC84 set),
// func_800378E4 multiplies it into the matrix every draw uses. The game's
// follow camera kicks its pitch up by 3-6 degrees in a single frame when a
// charge is released in the air (Spyro leaves the charge pose) and eases
// back over ~5 frames: the view jumps up for a moment. Normal camera motion
// changes pitch by well under 1 degree per frame, so the main camera's pitch
// may change by at most kMaxRate; larger steps (cuts, > kSnap degrees, or the
// camera moving more than kSnapMove units at once) and the look mode (Y held)
// pass through. The matrix is turned about the camera's own x axis, so the
// camera position stays.
//
// This file is part of the port, not derived from the game's code; build.ps1
// copies it next to the generated natives.

#include "runtime/cpu_context.h"
#include "input/input_manager.h"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>

using nwii::runtime::CPUContext;

namespace {
constexpr double kMaxRate = 60.0;   // degrees per second
constexpr double kSnap = 12.0;      // degrees in one update = a cut
constexpr double kSnapMove = 300.0; // camera units in one update = a cut
constexpr double kDeg = 180.0 / 3.14159265358979323846;

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

struct View {
  double R[3][3], t[3];
  double pitch() const { return std::asin(std::clamp(-R[1][2], -1.0, 1.0)) * kDeg; }
  void position(double c[3]) const {
    for (int k = 0; k < 3; ++k) c[k] = -(t[0] * R[k][0] + t[1] * R[k][1] + t[2] * R[k][2]);
  }
  // Turn the view about its own x axis by a radians (p_view' = p_view * Rv).
  View turned(double a) const {
    const double c = std::cos(a), s = std::sin(a);
    View v = *this;
    for (int k = 0; k < 3; ++k) {
      v.R[k][1] = R[k][1] * c - R[k][2] * s;
      v.R[k][2] = R[k][1] * s + R[k][2] * c;
    }
    v.t[1] = t[1] * c - t[2] * s;
    v.t[2] = t[1] * s + t[2] * c;
    return v;
  }
};
} // namespace

extern "C" void gs8e_smooth_camera(CPUContext &ctx, const unsigned int *args) {
  const uint32_t cam = args[0];
  if (ctx.mmu.read8(cam + 0xC84) == 0) return; // unchanged since the last multiply
  const uint32_t m = cam + 0x118;
  View v;
  for (int r = 0; r < 3; ++r)
    for (int c = 0; c < 3; ++c) v.R[r][c] = ReadF(ctx, m + (r * 4 + c) * 4);
  for (int c = 0; c < 3; ++c) v.t[c] = ReadF(ctx, m + (12 + c) * 4);
  if (std::abs(v.R[1][2]) > 0.97) return; // the shadow pass looks straight down

  static bool have = false;
  static double filt = 0, last_pos[3] = {};
  static uint64_t last_tb = 0;
  const uint64_t tb = ctx.read_timebase();
  const double elapsed = have ? (double)(tb - last_tb) / ctx.tb_freq : 0.0;
  const double dt = std::min(0.1, elapsed);
  const double p = v.pitch();
  double pos[3];
  v.position(pos);
  const double moved = std::sqrt((pos[0] - last_pos[0]) * (pos[0] - last_pos[0]) +
                                 (pos[1] - last_pos[1]) * (pos[1] - last_pos[1]) +
                                 (pos[2] - last_pos[2]) * (pos[2] - last_pos[2]));
  const bool look = nwii::runtime::input::InputManager::get().get_gcpad_state(0).buttons & 0x0800;
  // Other cameras (a far-away pass with its own view) go through here every
  // frame too: far from the main camera, while it was seen within the last
  // half second, an update is left alone and does not touch the state.
  if (have && moved > kSnapMove && elapsed < 0.5) return;
  last_tb = tb;
  std::memcpy(last_pos, pos, sizeof(pos));
  if (!have || look || std::abs(p - filt) > kSnap || moved > kSnapMove) {
    have = true;
    filt = p;
    return;
  }
  filt += std::clamp(p - filt, -kMaxRate * dt, kMaxRate * dt);
  const double delta = (filt - p) / kDeg;
  if (std::abs(delta) < 1e-5) return;
  // NWII_CAMSMOOTH_LOG=1: every limited update.
  static const bool log = std::getenv("NWII_CAMSMOOTH_LOG") != nullptr;
  if (log) std::printf("[CAMSMOOTH] pitch %.2f -> %.2f\n", p, filt);
  View w = v.turned(delta);
  if (std::abs(w.pitch() - filt) > std::abs(v.turned(-delta).pitch() - filt))
    w = v.turned(-delta);
  for (int r = 0; r < 3; ++r)
    for (int c = 0; c < 3; ++c) WriteF(ctx, m + (r * 4 + c) * 4, (float)w.R[r][c]);
  for (int c = 0; c < 3; ++c) WriteF(ctx, m + (12 + c) * 4, (float)w.t[c]);
}

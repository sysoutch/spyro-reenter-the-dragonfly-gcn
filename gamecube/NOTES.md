# Spyro: Enter the Dragonfly (GameCube, GS8E7D) – NWiiRecomp port

## Layout
- `Spyro - Enter the Dragonfly (USA).rvz` – original disc image
- `extracted/` – disc contents (DolphinTool `extract`), `sys/main.dol` is what gets recompiled
- `spyro.toml` – recompiler config (top-level keys) + runtime config (`[system]`, `[game]`, `[graphics]`)
- `totaldb.dsy` – Dolphin SDK signature DB, names 418 SDK functions
- `font_western.bin`, `font_japanese.bin` – Dolphin's free IPL font replacements (see `font-licenses.txt`)
- `export/` – generated C++ project (6656 functions); `export/build/Release/SpyroEnterTheDragonfly.exe`
- `run-spyro.ps1` – launcher

## Rebuild
```
..\NWiiRecomp\build\nWiiRecomp\Release\nwiirecomp.exe spyro.toml   # regenerates export/ (wipes nothing else)
cmake --build export\build --config Release --parallel                # VS 2022 bundled cmake
```
Regenerating `export/` copies `nWiiRuntime` from `../NWiiRecomp/nWiiRuntime`, so runtime fixes belong there.

## Runtime fixes made in ../NWiiRecomp/nWiiRuntime
1. `CMakeLists.txt` – `SDL_MAIN_HANDLED` (link failed: SDL renamed `main` on Windows).
2. `src/hw/hw_exi.cpp` (new) – minimal EXI: channel 0 / device 1 IPL ROM serving the fonts at
   0x1AFF00 / 0x1FCF00. Without it `OSInitFont` fails and the game panics in `bitfont.cpp:1087`.
3. `src/hle/ios.cpp` + `exi_pending_os_interrupt()` – PI EXI interrupt was always dispatched as
   EXI_0_EXI (9); transfer-complete needs 10, otherwise an endless interrupt storm.
4. `src/hw/hw_di.cpp` – SUSPECT-dst log now dumps guest call chain + registers (diagnostic).
5. `src/hle/memory.cpp` – OOM log says request size / where the heap walk stopped (diagnostic).
6. `src/hle/gx/tev_shader_gen.cpp` – each TEV stage in its own `{}` scope. The per-stage temporaries
   were redeclared, so **every shader with 2+ TEV stages failed to link** (NVIDIA) and its draws vanished.
7. `src/hle/gx/tev_shader_gen.cpp` + `gx_state.h` – TEV swap tables (KSEL 0xF6-0xFD, selected by the
   alpha env's rswap/tswap) applied to ras/tex colour; KSEL added to the shader hash. Without it the
   logo fade mask read CMPR alpha (always 1) and painted the scene black.
8. `src/hle/gx/renderer_gl.cpp` – GX colour/alpha update bits honoured as `glColorMask`; DST_ALPHA blend
   factors resolve to ONE/ZERO when the EFB format has no alpha.
9. `src/hle/gx/fifo_parser.cpp` – cached normal (lit vertices without normals reuse the last one) and a
   parse-time shadow of XF 0x100E/0x100F (need_normal read stale renderer state).
10. `src/core/main.cpp` – screenshots saved opaque and two consecutive frames per sample.
12. Recompiler `nWiiRecomp/src/recompiler.cpp` – `VIWaitForRetrace` removed from the native-handler list:
    the stub returned instead of sleeping, so frames ran unthrottled and the streaming thread starved.
13. `src/hle/ios.cpp` – EventScheduler advanced before the in-callback early return; window-present VI
    only when *not* on the wall timebase (it tripled the retrace rate); `[hle] resched` config.
14. `config.h/.cpp`, `cpu_context.h` – `[hle] wall_timebase` / `[hle] resched` TOML keys (`g_wall_timebase`).
15. `src/core/main.cpp` – `timeBeginPeriod(1)`: the idle loop's 1 ms sleep was 15.6 ms on Windows (~3 fps).
16. All hot `std::getenv("NWII_SAMPLE")` calls cached (`s_env_sample`): they ran on the per-backward-branch
    interrupt poll; guest throughput went from ~5 to ~85 MIPS.
17. `src/input/sources/mouse_keyboard_source.cpp` – full GameCube pad on the keyboard (see run-spyro.ps1).
18. `spyro.toml [hle_hooks] "801D9D88" = "PADRead"` – PADRead wasn't in the signature DB, so the game
    polled the unemulated SI and never saw input.
19. Diagnostics: `NWII_PCPROF=1` (guest pc/lr histogram + instructions per 5 s).
20. Recompiler: every `[hle_hooks]` name is declared in the generated `functions.h` (was a fixed list).
21. (Removed) The AX free-stack cycle guard. Root cause, see 27.
22. `renderer_gl.cpp` `ApplyEfbCopyFormat` – EFB copies honour the target format (R/RA/A/G/B/RG/GB via
    texture swizzle, YUV intensity via CPU luma, alpha = 1 without EFB alpha). Fixed the black ground
    (R4 shadow mask used as dst*(1-a)), missing font glyphs and stray glyph columns.
23. `renderer_gl.cpp` `ApplySamplerMode` – GX TX_SETMODE0 wrap/filter applied per draw (the cache forced
    GL_NEAREST everywhere): fixed blocky glow/particle effects, smoother textures overall.
24. `src/hle/ios.cpp` – the "advance scheduler inside callbacks" change from item 13 was reverted (not
    needed once VIWaitForRetrace and the reschedule were fixed).
25. `src/hw/hw_exi.cpp` rewritten around EXI devices: IPL (ROM fonts + RTC + **SRAM**, with flash-ID
    checksums 0xFF so CARD mounts verify) and a **memory card** in slot A (Nintendo flash protocol:
    ID, status, read array, page program, sector/chip erase, interrupt enable), 4 Mbit / 59 blocks,
    backed by `gamecube/memcard_A.raw` with write-through. EXT presence bit on channel 0.
    `NWII_EXITRACE=1` logs channel-0 card traffic.
26. **Recompiler carry bugs**: `addic`/`addic.` added the sign-extended immediate as a 64-bit value
    (`+ -1` → inverted CA) and `subfic` never set CA at all. CodeWarrior uses both for `==`/`!=`
    (`addic -1; subfe`, `subfic 0; adde`), so comparisons game-wide could flip. Found via EXIGetID's
    `start != now` test, which made memory cards undetectable.
27. **AX DSP microcode HLE** (`src/hw/hw_ax.cpp`, called from `hw_dsp.cpp` on each command-list mail).
    Root cause of the hub freeze: the runtime only answered the DSP mailbox and never ran the AX
    microcode, so (a) there was no audio at all and (b) one-shot voices never reached "stopped", the
    game never freed them, the 64-voice pool ran dry, AX stole voices that game channels still held,
    and two channels freed the same voice (game code at 0x800A5C94) -> cycle in the free list -> the
    AX frame handler looped forever. The HLE runs SETUP / SET_LR / PB_ADDR / PROCESS / OUTPUT, decodes
    ADPCM / PCM16 / PCM8 from ARAM with SRC, volume envelope, mixer ramps, parameter updates, loop and
    end handling (end -> running = 0), and writes 5 ms stereo frames for the audio DMA.
    PB layout for this SDK: ITD is 7 words, so fields from the updates on sit one word later than in
    Dolphin's struct (update buffer 39/40, ve 50, addresses 55-62, ADPCM 63-82, SRC 83-89).
    Not modelled: aux A/B sends (reverb), the compressor, ITD.
    The audio DMA output is (R, L) pairs; `hw_dsp.cpp` swaps them for the host stream.
    Diagnostics: `NWII_AXTRACE=1` (command lists, first running PBs, voices per frame),
    `NWII_WAVDUMP=<file.wav>` (records everything the audio DMA plays).
29. **Internal resolution + anti-aliasing**: `[graphics] internal_scale` (EFB rendered at N x 640x480),
    `msaa` (multisampled EFB, resolved before copies/present via `efb::resolve()`, `runtime/efb.h`),
    `anisotropy`. EFB-to-texture copies are taken at the scaled size; textures get mip chains and
    linear-filtered ones trilinear + anisotropic sampling. Spyro runs at 3x / 4x MSAA / 16x AF at
    its native ~30 fps (render ~9 % of wall time on an RTX 3090). Screenshots are full internal size.
30. **Quiet console**: unhandled MMIO is reported 4x per address then suppressed; dispatcher /
    heartbeat / interrupt / DVD traces (runtime and recompiler-generated) only with `NWII_VERBOSE=1`.
    The old flood (~10k lines per 5 min, each flushed) slowed the game badly with a visible console.
31. **GX viewport** honoured (XF 0x101A-0x101F -> glViewport), so render-to-texture passes land where
    the game expects: Spyro's shadow pass renders into a 128x128 viewport and is now the real
    silhouette (it used to be a corner of a full-screen render). EFB copies take their rect top-left-
    origin, are flipped so texture row 0 is the top row (hardware orientation), and a copy's clear
    only touches the copied rect. The window shows the last EFB->XFB copy rect (640x448 in-game) at
    its display aspect, letterboxed/pillarboxed as needed.
32. **Widescreen** (`[graphics] widescreen = true`): EFB 4/3 wider (2560x1440 at 3x); draws in a
    full-width viewport get clip-space x * 3/4 -- 3D gets a wider FOV, 2D/HUD keeps its 4:3 shape,
    centred -- except 2D quads spanning the full width (fades, letterbox bars), which stretch.
    Render-to-texture passes (small viewports) are untouched. Known artifact: the title screen's sky
    doesn't cover the far top-right corner (geometry built for the 4:3 view).
33. **GX texgen from position/normal** (renderer_gl.cpp EmitVertex, texgen 0): XF 0x1040 regular type
    with source POS or NRM now transforms the model-space position/normal (VertexData raw_pos /
    raw_norm, filled in fifo_parser) by the tex matrix at any XF index (60 = identity), with STQ
    divide. Sparx's sparkles use UV-less vertices + normal texgen; they sampled texel (0,0) and showed
    as faint squares. Env-mapped objects use the same path.
34. **FP / paired-single translation fixes** (recompiler.cpp + interpreter.cpp + cpu_context.h),
    found auditing the instruction set: single-precision ops (op 59), frsp, lfsu/lfsx now also
    write ps1 (Gekko fills both slots); stfiwx stores the FPR's raw low word (was converting the
    bit pattern -> always 0); sraw sets CA (the reachable copy didn't; a dead duplicate with swapped
    registers was removed); fctiw/fctiwz saturate like hardware; divw skips INT_MIN/-1 (x86 trap);
    ps arithmetic rounds each lane to single; psq_l/psq_st GQR scales are signed and quantized
    stores saturate; unhandled op-4 forms (ps_res, ps_rsqrte, psq_lx/stx/lux/stux) go to the
    interpreter instead of exiting.
35. **Butterflies circling = original behaviour** (investigated, no fix needed). Hub butterflies
    are SpyroButterflyLite (a 3-slot pool at 0x8022D5A8, update 0x801C1A90, switch(state @+0x174)
    with jump table 0x8022D5D0). State 6 circles a home anchor; it only leaves when its timer is out
    AND Sparx wants food (func_801C1340, gated on Sparx health = halfword *(0x802843C0)+0x32, max 4).
    Verified: NWII_POKE16=9400:802843C0:32:1 -> Sparx eats three butterflies, health 1->2->3->4.
    The pool's 6->7->1 cycling (slots handed to other butterflies) is normal too.
36. **F1 settings overlay** (Dear ImGui v1.91.5 via FetchContent in nWiiRuntime/CMakeLists.txt;
    src/core/settings_overlay.cpp). F1 / pad Back toggles, Esc or pad B closes, F11 / Alt+Enter
    fullscreen. Graphics (internal scale, MSAA, AF, widescreen, fullscreen, VSync, FPS counter),
    audio (volume, mute), keyboard rebinding (input/key_bindings.*, swaps on conflict). Applied
    live: efb::create() rebuilds the render targets between frames; the game sees a neutral pad
    while the menu is open (InputManager::set_suppressed). The game keeps running underneath (no
    pause). Saved into the loaded TOML in place (comments kept; new keys appended to their
    section; [audio] and [keyboard] sections added). Test hooks: NWII_UI_OPEN=<present> (open +
    save), NWII_UI_TAB, NWII_UI_SHOT=<bmp>, NWII_UI_SWITCH=<scale>,<msaa>,<ws>.
37. **All 8 GX texgens** (renderer_gl.cpp ComputeTexGens + tev_shader_gen.cpp): every texcoord
    is generated per vertex from its own source (position, normal, colour, UV set 0-7) and matrix
    and passed as (s,t,q) per stage, divided per pixel. Before, every stage sampled UV set 0.
38. **Normals scaled** (fifo_parser.cpp): S8/S16 normals use their fixed exponent (/64, /16384).
    Normal-sourced texgens (sparkles, glows) got huge coordinates.
39. **GX Z mode honoured** (renderer_gl.cpp ApplyZMode; NWII_ZMODE=0 = old always-LEQUAL+write).
    Translucent effects no longer write depth over their whole quad (the "square particles" over
    water/fog). Compare-off still honours the write bit (GL_ALWAYS).
40. **SDK-cached GX setters not replaced natively** (recompiler.cpp hle_handlers): GXSetZMode,
    GXSetBlendMode, GXSetZCompLoc, GXSetDstAlpha, GXSetCullMode, GXSetNumTevStages,
    GXSetCurrentMtx. The native seams skipped __GXData's cached copy, so GXCopyTex/GXCopyDisp
    "restored" Z mode 0 after every EFB copy and the world drew without depth.
41. **Performance**: [hle_hooks] GXDrawDone (no CPU wait for the host renderer; GPU work overlaps
    the next CPU frame, ~25 -> steady 30 fps), nwii_memcpy / nwii_fill_mem (memops.cpp; MSL
    byte loops were the top of the profile), top-level `count_instructions = false` (no
    per-instruction counter; it is only statistics under the wall-clock timebase). Host loop is
    capped at ~250 Hz without VSync (spinning starved the CPU thread: stall in the logos).
    The game waits one VI retrace per frame, so it is uncapped up to 60 fps if the CPU is fast
    enough.
42. **View distance findings** (hub): far plane ~700k units, no c6LODGroup instances, GX fog never
    enabled (and not implemented in the renderer), MaxViewDistance/DistanceCoef are
    WATER_ATTRIBUTES, ActivationDistance is for sound/ripple effectors -- nothing to scale yet.
    GXSetFog (func_801EEFD8) is only called from GXInit (func_801E9CD8, fog off): the game
    never uses hardware fog, so implementing GX fog would change nothing.
    Debug aids: NWII_MEMDUMP=<present>:<file> (MEM1 dump), NWII_BPLOG=<hex reg> (first 400 BP
    writes), NWII_PURPLE_TRIGGER=1 (draw-log the frame after the purple-water glitch appears).
43. **ARAM DMA completes near-instantly** (hw_dsp.cpp): the size-based delay let faster-than-real
    DVD reads win; the sound-bank loader re-posted its ARQ request while queued, corrupting ARQ's
    list (zero-length DMA) and jamming the queue -> no music/dialogue streams, stale SFX (jump).
44. **AX srcSelect 2 = no SRC** (hw_ax.cpp): plays 1:1 and ignores the ratio (streams use ratio
    0). Music and Sparx's dialogue play now. Debug: NWII_AXVOICES=1, NWII_TRACE_STR=1.
45. **XFB model** (main.cpp efb::snapshot/select_display, renderer_gl.cpp): each EFB->XFB copy is
    snapshotted per XFB address and the window shows the one the VI scans out (register holds
    only the high address half here); copy clears happen in stream order, no per-batch clears
    (NWII_OLDCLEAR=1 for the old way); shaders compile on demand -- skipped draws dropped the
    fade overlay for single frames (NWII_SHADER_BUDGET=n restores the cap). Loading fade-in no
    longer flickers. Debug: NWII_XFBLOG=1.
46. **Projected textures / EFB copies like hardware**: q <= 0 pixels discarded; EFB-copy textures
    use the game's exact filter (no generated mips/AF unless GX asks); half-scale copies are box-
    filtered to console resolution and 4-bit formats quantised. Debug: NWII_SKIP_CMODE=<hex>,
    NWII_DIFF_CMODE=<hex> (per-draw changed-pixel bbox in a frame log), NWII_TEXDUMP.
47. **False HLE signature removed** (recompiler.cpp sig_hooked, `[system] platform`): the analyzer's
    built-in IOS_IoctlvAsync prologue pattern matched the game function 0x80134F60 (called ~12k
    times at hub start), which was then replaced by the Wii IOS stub. Symptoms: "You caught Toons!"
    and Sparx's basket hint at spawn, sheep dying, NPCs stuck in hit animations, butterflies
    swarming, doors not blocking. GameCube games now ignore IOS_* signature matches.
48. **Divide by zero / fused multiply-add like Gekko** (recompiler + interpreter): divwu/0 -> 0,
    divw/0 and INT_MIN/-1 -> the dividend's sign (0 or -1); double fmadd/fmsub/fnmadd/fnmsub fused.
    Interpreter gained the carry ops (addc/adde/addze/addme/subfc/subfe/subfze/subfme), stwux,
    mtsr/mfsr.
49. **Verification tools**: `gamecube/difftest` (gen.py + main.cpp, CMake target nwii_difftest,
    EXCLUDE_FROM_ALL) runs all ~81k distinct straight-line instruction bodies from output_*.cpp
    against interpret_one on random states -- currently 0 real mismatches. Interpreter mode:
    `NWII_CTRL` command `interp on <hexlimit>` runs every recompiled function below the limit through
    interp_run (SDK above 0x801CA000 stays compiled); `NWII_SDKLOG=1` then logs every game->SDK/HLE
    call with arguments and results. That is how the false signature was found.
50. **Texture unit clobbering** (renderer_gl.cpp draw setup): the per-draw bind loop decoded a
    stage's texture *before* glActiveTexture, and a cache miss binds the new texture on the
    active unit -- unit i-1 -- so stage 0 sampled a stale stage-1 texture. Seen as coloured blocks
    instead of "Loading... Please Wait." before the hub spawn; any frame that decoded a texture
    for a later stage could show a wrong texture on the previous one. Also: EFB-copy textures
    keep a RAM checksum and are dropped when the game reuses that memory; debug options
    `NWII_TEXDUMP_ADDR=<hex>:<file>` (+ `NWII_TEXDUMP_FROM=<frame>`), `NWII_DRAWLOG_FRAME=a-b`,
    `NWII_STRIP_TRIGGER=<present>`.
51. **2D depth like GX** (renderer_gl.cpp): 2D vertices kept z flattened to 0 and 2D draws skipped
    depth entirely, so Spyro's HUD depth-clear quad (full-screen ortho, z = far, compare ALWAYS,
    write on, colour off) never cleared anything and walls cut through the HUD models. Now 2D
    draws keep z and follow the Z mode, ortho z is mapped [-1,0] -> [-1,1] like perspective, and
    GL_DEPTH_CLAMP is on (GX clamps to the viewport range; `NWII_DEPTHCLAMP=0` to compare).
    `NWII_ZMODE=2` restores the old 2D path. The viewport's z range (XF 0x101C/0x101F) is mapped to
    glDepthRange (Spyro keeps the default; `[VPZ]` logs non-default ranges).
52. **CPU speed, round 2** (hub 30 -> ~40-44 game fps). Found with `NWII_NPROF=1` (native sampler of
    the CPU thread; `NWII_NPROF_OUT=<file>` + the linker map `/MAP` resolve symbols):
    - MMU accessors: force-inlined fast path for plain MEM1 RAM, old code as *_slow (were ~26%).
    - psq_load/psq_store: inline GQR type-0 (float) path.
    - Generated code: `/GS-`; loop back-edges call `poll_callbacks` (full check every 16th time
      or when a callback is queued); `bctrl` calls the target in place via `call_indirect`
      (flat table; `NWII_NO_DIRECT_CALLS=1` = old dispatcher route).
    - wgp_push: one precomputed debug flag instead of three env statics per byte.
    Remaining hot spots: the game's matrix helpers 0x801BBC04/0x801BBE1C/0x801BC138 (~25%;
    guest registers live in ctx memory and get reloaded around every RAM store), dispatcher 4%.
    A clang-cl build (Ninja + vcvars, `/D__PRFCHWINTRIN_H` for SDL) compiles but runs the game
    differently (probably UB in generated code) -- parked.
53. **No black flicker at high frame rates** (renderer_gl.cpp XFB copy): Spyro clears the EFB with
    EFB->XFB copies to both XFBs before drawing; those clear-only copies (no draw since the last
    clearing copy) no longer replace a display snapshot. On hardware the real copy overwrites them
    before VI scans the buffer; here a present between them showed a black frame, often once the
    game ran above 30 fps. `NWII_XFB_ALL=1` = old behaviour; `NWII_SHOTLOG=1` logs the display
    state per screenshot. (PowerShell 7 note: `$env:X = ''` can leave an empty-but-set variable --
    use `$env:X = $null` to unset.)
54. **Frame pacing / render thread** (gx.cpp ProcessGXFifo): one call (= one host present) renders
    exactly ONE game frame -- the oldest queued one; later complete frames stay queued for the next
    present, and only frames beyond the newest two have their draws dropped. Rendering every queued
    frame in one call showed only the last of them (game frames ~40/s but distinct presents ~19/s:
    the "laggy repaint" near the spawn). `NWII_GX_DROP_OLD=1` = render only the newest frame.
    The display shows the newest XFB snapshot (`NWII_XFB_VI=1` = follow the VI pointer).
    Render-thread cost: command vectors are swapped/reused instead of moved per command, the carry
    queue uses a head offset instead of front-erase, and display-list snapshots are shared
    (`GX_DL_Fetch` returns a shared_ptr) instead of copied (~45 MB/s). The main thread still spends
    ~50% in parse/decode (vertex decode, EmitVertex, ~7k small draws per hub frame).
55. **Dispatcher moved into the runtime** (recompiler `emit_dispatch`, runtime `dispatch.h/.cpp`):
    main_output.cpp used to hold `run_game` as one function with a 46,484-case switch -- the
    slowest object of the build (>75 CPU-minutes after a header change, never parallel). It is now
    data only (sorted `DispatchEntry` table, function bounds, native handlers) registered via
    `register_dispatch_tables`, and `run_game` calls `run_dispatcher` (flat O(1) lookup over MEM1,
    binary search elsewhere, same fallback to the bounds scan / `interpret_step`). It includes only
    `runtime/dispatch.h` + `functions.h`, and functions.h now forward-declares CPUContext, so runtime
    header edits no longer rebuild it: main_output.cpp compiles + links in ~2 s.
56. **Broken object parts for single frames** (gx_state_seam.cpp GXDrawDone, gx.cpp): the
    `[hle_hooks] GXDrawDone` speed hook never waited, so the host parser could fall several frames
    behind the CPU and read guest RAM -- LOAD_INDX matrices, indexed vertex arrays -- that the game
    had already rewritten for later frames: huge flat slabs over the ground/sky for one frame,
    mostly while the camera swept past walls. Now GXDrawDone waits until the host has parsed the
    draw-done token from one frame earlier (`NWII_DRAWDONE_LAG`: 1 default, 0 = full sync,
    -1 = old no-wait), and draws are decoded right after parsing instead of at render time.
    Hub: ~50 rendered fps, no dropped/queued frames. Found with per-frame captures
    (`NWII_SHOT_EVERY=1 NWII_SHOT_FROM=<n>`) and a one-frame-transient scan (tools/transient2.py).
    Ruled out on the way: DL cache (`NWII_NODLCACHE=1`), depth clamp (`NWII_DEPTHCLAMP=0`), frame queueing.
57. **Dual texgen post-transform** (renderer_gl.cpp ComputeTexGens, gx_state.h): XF 0x1012 bit 0
    enables a second texgen stage -- optional normalise, then a post matrix per coordinate (index in
    XF 0x1050+i bits 0-5, normalise bit 8, matrices in XF bank 0x0500, now kept in
    `g_state.postMatrices`). The HUD's gold digits env-map their normals through it; without it a
    face-on normal sampled the corner texel (dark brown digits). Also: q only divides for STQ
    texgens, and q == 0 halves/clamps s,t like hardware (Dolphin's rule).
    Hub after 54-57: ~58 rendered fps at the spawn (hidden run); `[GXPROF] ddwait_ms` (CPU time
    spent waiting in GXDrawDone) is ~2%, the CPU thread's top function 0x801D1B20 is the OS
    scheduler/idle path, so neither thread is saturated any more.
58. **GX parser thread** (gx.cpp, fifo_parser.cpp): at internal_scale 3 the user saw 45-50 fps.
    `NWII_FRAMEHIST=1` (game frame intervals at GXDrawDone + `[SLOWFRAME]` lines) showed 10-20% of
    frames at 33 ms: GXDrawDone waited 3-14 ms for the host to parse the previous frame, which
    happened only once per vsync'd present loop. FIFO parsing + draw decoding now run on their own
    thread (polled every 1 ms, kicked when GXDrawDone waits; `NWII_PARSE_THREAD=0` = inline, old).
    The parser has its own GXState (`g_pstate`: CP/VAT/arrays/matrix indices, BP/CP shadows for the
    0x78 merges); the renderer's `g_state` is only written in stream order at render time, so the
    old parse-time `g_state.bp` "seed" (a timing-dependent look-ahead into shader hashes) is gone.
    Result, walking the hub at 3x: every frame 14-20 ms (~60 fps), `ddwait_ms=0`, per-frame
    broken-geometry scan clean. (A parse pass right before the vsync swap was tried first: worse,
    38-45 fps -- it delayed the swap past vblank.)
59. **120 fps investigation (task 20)**: the frame loop (0x80039854) ends with GXDrawDone ->
    VISetNextFrameBuffer -> VIFlush -> ONE VIWaitForRetrace, and the simulation runs on real time
    (Spyro walks the same distance in 3 s at VI 60 and 120 Hz). `NWII_VI_HZ=<n>` sets the VI
    retrace rate (ios.cpp); `NWII_VISTAT=1` prints VI events fired/delivered (120/s delivered at
    120 Hz). But a game frame costs ~11 ms of CPU, so at 120 Hz every frame waits two retraces:
    exactly 60 fps, and odd rates quantise worse (90 Hz -> 45 fps when a frame takes > 11.1 ms).
    120 fps needs the CPU frame <= 8.3 ms (~30% faster) and a >= 120 Hz display (vsync).
60. **CPU round 3 + 120 fps mode** (task 20):
    - Native matrix helpers (`[hle_hooks]` 801BBC04/801BC138/801BBE1C -> `gs8e_mtx44_scale/add/
      concat`, generated at build time into export/natives/ by tools/gen_natives.py): the game's 4x4 scale/add/multiply used by skinning,
      ~20% of the CPU thread. Bodies generated by symbolic execution of the PPC code (tools/gen_natives.py), same float ops in the same order -> bit-identical; host-pointer fast path.
      The recompiler keeps a hooked function's instructions as comments in its stub, so the natives
      are derived from the user's disc and never stored in the repositories (they are game code).
    - Interrupt poll gate (cpu_context.h poll_callbacks): the full check runs every 16th back-edge
      AND only after `g_poll_cycles` TSC cycles (NWII_POLL_US, default 20 us). Was ~7% of the CPU.
    - Generated functions take `CPUContext& NWII_RESTRICT ctx` (recompiler emit_function): MSVC
      no longer reloads guest registers after each guest RAM store. `-DNWII_NO_RESTRICT` disables.
    - Adaptive VI retrace (ios.cpp vi_request_retrace, called by the GXDrawDone seam): the next
      retrace comes at max(frame end + 0.3 ms, previous frame's retrace + period), so a frame costs
      max(work, period) instead of whole periods. `NWII_VI_ADAPTIVE=0` = fixed grid.
      `NWII_VISTAT=1` adds `[VIFRAME]` (retraces per frame, work since the last retrace).
    - Parser thread polls every 100 us (`NWII_PARSE_POLL_US`; was 1 ms): GPU sync points signal only
      once parsed, so the interval added straight to the frame time.
    - `[graphics] frame_rate = 60|120` (Graphics tab, live) sets the VI rate; NWII_VI_HZ overrides.
    Hub, scale 1, VSync off, 120: ~60 -> ~89 fps. Limits now: CPU thread ~8-9 ms/frame, parser
    ~8.7 ms/frame (decode ~half, per-draw parallelisable), render thread ~7.4 ms/frame.
61. **Round 4 (120 mode at 3x)**, profiled per thread with ntdll/win32u exports resolved (tools/dllprof.py; `NWII_NPROF_OUT` dll lines now carry the module offset):
    - CPU thread: gather-pipe writes are staged in a CPU-thread buffer and appended to g_hw_fifo
      under one lock per flush (full / every poll check / before GXDrawDone waits). A mutex per
      Write8/16/32 was ~15% of the thread. Game frames now 8-12 ms (~95-110 game fps).
    - Render thread: vertices built once per source vertex (strips reused each 3x), texgen config
      decoded once per draw (PrepareTexGens), streaming VBO ring with unsynchronised maps
      (`NWII_VBO_RING=0` = glBufferData per batch, which created/destroyed a driver allocation per
      batch), rendered frames destroyed on the parser thread, and batches no longer end on matrix
      loads, CP writes, PE tokens, the matrix-index XF regs or unchanged lights/material/pure BP
      state (`NWII_BATCH_ALL=1` = old; `NWII_BATCHSTAT=1` prints flush causes): ~3000 -> ~900 GL
      batches per frame; most remaining flushes are real texture changes (BP 0x88/0x8C).
    - Parser: frames are split as they are parsed and queued whole (s_ready), so the render thread
      takes one in O(1) instead of rescanning a flat queue under the lock; parts render in order.
      Parallel decode of draws with own normals (`NWII_PAR_DECODE=0` off) -- no measurable gain.
    Hub, 3x, 120 setting, vsync off, hidden: rendered ~64 -> ~75 fps; game ~90+; the render thread
    (NVIDIA driver CPU time for ~900 draws/frame) is the limit now.
62. **Round 5 (level 2 / Dragonfly Dojo; user saw down to 44 fps, resolution-independent)**:
    - Indexed drawing (renderer_gl.cpp): each built vertex is stored once in the batch and
      triangles go through a 32-bit index ring (glDrawElementsBaseVertex). Strips/fans had been
      expanded to 3 copies per vertex -- triple upload, memcpy and GX-lighting vertex shading. The
      render thread had been blocked in present (NtDxgkSubmitPresentToHwQueue) on GPU vertex work.
    - Rendered frames are destroyed on their own thread (on the parser thread they delayed parsing
      -> GXDrawDone waits).
    - Gather pipe: 32-bit words staged with one store.
    Hidden runs, 3x / 120: level 2 spawn ~62 -> 70-80 fps, hub ~75 -> ~93 fps. Level 2 is now
    game-thread bound (frames 10-14 ms; game code, skinning func_8003DC54, matrix natives).
    Test save: copy of the user's card (a backed-up copy) loads into level 2.
63. **Lean entry switches** (recompiler `lean_entry_switch = true` in spyro.toml): every function
    began with `switch (ctx.pc)` listing EVERY instruction as a goto target, so each instruction
    was a join point and MSVC could not keep guest values in host registers (a 30-instruction
    leaf compiled to 2.7 KB). Now listed: the function's dispatch key (can differ from
    func.start_address -- analyzer quirk, e.g. 0x8004EA48), call return addresses, back-edge
    polls, jump-table targets, branch targets from other functions, local branch targets and
    addresses after unconditional transfers (covers switch tables the analyzer missed), and every
    constant the body stores into ctx.pc. Anything else falls to interpret_step:
    `NWII_INTERP_STAT=1` prints interpreted steps and hot pcs (now zero in hub and level 2).
    Full rebuild ~5-8 min instead of ~18. Game thread: hub frames mostly 8-10 ms.
    Also: TMEM placement writes (BP 0x8C-0x93/0xAC-0xB3) no longer end batches (renderer never
    reads them); remaining flushes are real texture switches (BP 0x94), which need texture arrays
    or bindless to merge. `NWII_NPROF_THREAD=parse` profiles the GX parser thread.
    Hidden 3x/120: hub ~93 -> ~100-106 fps, level 2 ~70-80 -> ~75-77. Level 2 is render-thread
    bound (BuildVertex/ComputeTexGens ~30%, present waiting on the GPU, texture switches), the parser
    is heap-allocation heavy (~24% in RtlAllocateHeap/FreeHeap: per-command vectors, DL-cache copies).
64. **Render back-pressure** (gx_state_seam.cpp GXDrawDone, gx.cpp): when the game outran the render
    thread (120 setting), the renderer dropped queued frames -- fast camera motion (charging) looked
    shaky. GXDrawDone now also waits while more than `NWII_RENDER_BACKLOG` drawn frames (default 1;
    -1 = off, drop instead) are waiting for the render thread. `[GXPROF] backlog_wait_ms` shows the
    wait. Level 2: dropped ~30/s -> ~0; visible run walking in level 2 ~100 fps.
65. **Steady pacing at 120** (ios.cpp vi_request_retrace): above 60 Hz the next frame starts no
    earlier than the 80th percentile of the last 32 frames' work (`NWII_VI_STEADY=0` off). Frames
    bunch at 10-14 ms instead of 6-22 ms; remaining 25-40 ms spikes are hitches (likely first-use
    shader compiles / texture uploads while moving through a level).
66. **Game's own "Widescreen 16:9" option (task 34)**: it is anamorphic -- the perspective x scale
    is 3/4 (y/x ratio ~1.72 vs ~1.29); menus are not squeezed. With our widescreen on, 3D draws in
    that mode are no longer compressed again (WidescreenWanted), so both options together look like
    ours alone. With ours off, the presenter stretches the 4:3 frame to 16:9 while the game is
    anamorphic (`g_game_anamorphic`), like a widescreen TV, instead of a squeezed pillarboxed image.
67. **Hitches (user play session, logged)**: frame times are two-humped (6-10 ms light views,
    16-20 ms heavy views = render cost). Real hitches (up to ~170 ms) were first-use shaders: the
    NVIDIA driver compiles lazily at the first draw. Fixes:
    - Persistent shader cache (renderer_gl.cpp shader_cache): linked TEV programs saved as driver
      binaries in `<config dir>/shader_cache/<GX state hash>.bin` (header: source hash, so a
      changed generator never loads stale binaries), loaded via glProgramBinary (looked up with
      SDL_GL_GetProcAddress; glad is GL 3.3). Loads ~0.5 ms; each shader hitches once, ever.
      `NWII_NO_SHADER_CACHE=1` off. `NWII_HITCHLOG=1` logs >15 ms render passes and [SHADER] loads.
    - Texture cache: LRU eviction of the oldest quarter at 2048 entries instead of clearing all at
      512 (`NWII_TEXSTAT=1` logs evictions).
    - `[graphics] frame_rate` also offers 90 (even pacing where 120 swings).
68. **Shadow-copy border** (renderer_gl.cpp ApplyEfbCopyFormat): 4-bit EFB copies (Spyro's
    projected shadow) get their 1-texel border reset to the background value; a silhouette touching
    the 128x128 viewport edge was repeated to the horizon by clamped sampling (user: lines gone).
    `NWII_SHADOW_BORDER=0` off, `NWII_SHADOWSTAT=1` logs bbox/resets.
69. **Controller rebinding** (input/key_bindings, gamepad_source.cpp, settings overlay Controls >
    Controller tab, `[controller]` TOML section: SDL names like "a", "leftshoulder",
    "righttrigger"). GC buttons A..D-pad map to any controller button or trigger; analog L/R follow
    their binding. Sticks fixed. Defaults = the old fixed layout.
70. **Audio crackle** (main.cpp audio thread, hw_dsp.cpp dsp_audio_take): the present loop always
    queued 1024 frames and dsp_audio_pull padded with zeros when the game had produced less --
    inserted silence that crackled around dialogue camera cuts (render/game-thread stalls). Now a
    dedicated thread keeps ~100 ms queued and queues only produced audio. Also AX de-pop
    (hw_ax.cpp): a stopped one-shot fades its last sample instead of dropping to 0
    (`NWII_AX_NODEPOP=1` off). `NWII_DILOG=1` logs disc reads with file names.
    Found with `NWII_CTRL` `drawlog` on the pause screen (wait ~60 s before killing the process, or
    the buffered stdout loses the frame's last draws -- the HUD).
71. **Themed pause menu** (settings_overlay.cpp draw_menu_frame, task 37): the settings window has
    no title bar and a transparent background; a purple gradient panel, double gold border, gems,
    bat wings and a "PAUSED" banner (seguibl.ttf) are drawn with ImGui draw lists, no image
    assets, all scaled by font size. Gold trim comes from apply_style. Pieces: cut gems with facets
    and a radial glow (fan_gradient = per-vertex colour fan via PrimReserve), Bezier dragon wings,
    a bevelled gold band (draw_gold_band) and corner spiral scrolls. Screenshots of a covered
    window: tools/printwin.py (PrintWindow flag 2) instead of ImageGrab. The helpers now live
    in core/ui_theme.{h,cpp} (shared with the launcher).
72. **Launcher / title menu** (core/launcher.cpp, include/runtime/launcher.h): shown after the
    window opens and before the game loads: Play (the given or most recent disc), Open Spyro ISO
    (Windows file dialog; an extracted folder opens via its sys/boot.bin or main.dol), Recent
    ISOs (`[launcher] recent`, newest first, max 8), Settings / Controller Setup (the settings
    window in launcher mode: "SETTINGS" banner, Back button), Credits, Exit. Procedural sunset
    background, logo plaque, dragonfly; own selection model (arrows/WASD/D-pad/stick, Enter/Space/
    A/Start, mouse on real motion) instead of ImGui nav, which never took focus reliably.
    Discs are probed first (launcher::probe): wrong game ID or RVZ/WIA/GCZ/CISO/WBFS gives a
    message (compressed formats: convert to ISO in Dolphin). `[launcher] enabled = false` skips
    it; so do NWII_SKIP_LAUNCHER / NWII_CTRL / NWII_INPUT_SCRIPT / NWII_HIDDEN / NWII_UI_OPEN.
    Test hooks: NWII_LAUNCHER_SHOT=<bmp> (frame 60), NWII_LAUNCHER_SELECT=<n>,
    NWII_LAUNCHER_ENTER=<frame>. The exe now takes `[disc] [config]` (a lone *.toml = config).
    Raw disc images: VirtualDisc::init_image (one region = whole file), Executable::load_dol with
    a base offset, bi2 read through VirtualDisc. Memory card and IPL fonts are looked up next to
    the config first (was: next to the disc), so an ISO elsewhere still uses gamecube/memcard_A.raw.
    Verified: a .gcm rebuilt from extracted/ (tools/make_gcm.py) boots to demo mode via Play.
73. **RVZ discs** (hle/disc_image.cpp, include/runtime/disc_image.h): DiscImage::open gives a
    reader for .iso/.gcm or RVZ (GameCube; zstd or stored chunks), used by VirtualDisc, the DOL
    loader (Executable::load_dol_from) and launcher::probe. RVZ per Dolphin's WiaAndRvz.md:
    header 1/2 (big endian), zstd-compressed raw-data (24 B) and group (12 B) tables, groups =
    chunk_size of disc data from a 32 KiB-aligned raw-data start; group size top bit =
    compressed; rvz_packed_size != 0 = packed: [u32 size][data] or [u32 size|0x80000000][68-byte
    seed] for junk, regenerated with Dolphin's lagged Fibonacci generator (K=521, J=32) skipped
    to (disc offset % 0x8000). 8-group LRU cache. zstd v1.5.6 is fetched by CMake (decompress
    sources only, nwii_zstd). Spyro's dump: zstd 19, 128 KiB chunks, 11139 groups (6371 packed).
    NWII_DISC_VERIFY=<extracted dir> compares every FST file read through the disc layer with the
    extracted copy and exits: 856 files, 0 mismatches, 6.5 s for the whole RVZ. tools/rvz_proto.py is the Python prototype. WIA/GCZ/CISO/WBFS are reported as "convert first".
74. **Starting without arguments** (main.cpp): with no config argument and no ./config.toml the
    exe looks next to itself and up to 4 folders up for a *.toml with a [game] section (creates
    <name>.toml from <name>.default.toml if only that exists), so double-clicking the exe or
    dropping a disc on it loads gamecube/spyro.toml. Before, it ran on built-in defaults
    (game ID "RSZK") and the launcher rejected every disc. `Play Spyro.bat` runs
    run-spyro.ps1 (double-clicking a .ps1 opens Notepad). run-spyro.ps1 builds its argument list
    with += -- `$x = if (...) { @($disc) }` unrolls to a string, and splatting a string passes
    it character by character (the config came out as ":").
28. `NWII_INPUT_SCRIPT="sec:BUTTON:ms,..."` (input_manager.cpp): scripted pad 0 input on a timeline,
    independent of window focus. Buttons A B X Y Z L R START, DUP.., UP/DOWN/LEFT/RIGHT (stick), CUP.. (C).
11. Diagnostics: `NWII_DRAWLOG_FRAME=<n>` (every draw of frame n, EFB readback, texture dumps to cwd),
    `NWII_FADELOG=<n>` (material regs every n frames), `NWII_FSDEBUG=tex|ras|uv`.

## Config gotcha
Without `[system] platform = "GameCube"` the runtime boots the game as a Wii title: ArenaHi
becomes 0x81700000 instead of the FST base, the game's hard-coded 20.6 MB scene pool
(0x13A7800) no longer fits, `OSAllocFromHeap` returns 0, and the game's allocator hands out
NULL-based pointers that DMA over low memory.

## Status (2026-10-19)
- Boots through the Dolphin SDK, ROM font loads, "Licensed by Nintendo" screen renders.
- Loads `LOGO.cnk` and `SPYROUSR_NGC.CFG`, then renders ~235 draws/frame at ~60 fps but the
  frame is flat grey – next thing to investigate (GX: textures / fog / blending / XFB copy).
- (2026-10-19, later) Fixed: "Licensed by Nintendo" → Universal Interactive logo fades in, holds, fades
  out at 60 fps. Not yet checked: the Check Six / Equinoxe logo, title screen, input, audio.
- Seen once: a run stalled at 80 frames in 65 s (CPU/GX thread timing?); not reproduced.
- (later) Full intro at real speed, title screen, attract demo, Start → memory-card prompt → new game →
  opening cutscene (C_1_INT1) at 30 fps. Keyboard input verified with injected key presses.
- (later) In-game: Start skips the intro cutscene, the Dragon Realms hub loads, Spyro walks, jumps,
  glides, breathes fire; camera follows. Ground, shadows, text and effects render correctly at 30 fps.
- (later) Memory card: format, create save data, save slots, progress written while playing and
  shown again ("0%", Load Game) after a relaunch.
- (later) Audio: AX HLE produces decoded speech/effects/music (verified by recording and
  spectrogram, no clipping); hub no longer freezes without any guard.
- Known issues: no reverb (aux sends); attract demo shows black; levels beyond the hub untested;
  card hot-plug / slot B not modelled.

## Rebuild after changing the recompiler or [hle_hooks]
`build.ps1` regenerates into `export_gen/` and copies only files whose hash differs into `export/`;
otherwise every generated .cpp gets a new timestamp and MSBuild recompiles everything.

## Debug env vars (runtime)
`NWII_HEADLESS=1`, `NWII_TRACE_CALLS=1` + `NWII_TRACE_ONLY=<hex,...>`, `NWII_WATCH=<hex>` +
`NWII_WATCH_REGS=1`, `NWII_SAMPLE=1` + `NWII_PEEK=<hex>,<words>` (headless only),
`NWII_SCREENSHOT=<prefix>` (+ `NWII_SHOT_EVERY=<n>` / `NWII_SHOT_FROM=<present>` for motion
bursts), `NWII_XFB=1`, `NWII_FIELDS=<hexaddr>,<bytes>,<every>` (print an object's words/floats
every n presents), `NWII_POKE16=<present>:<hexptr>:<off>:<val>` (one-shot halfword write at
*ptr+off).
Test-run helpers: `NWII_HIDDEN=1` (no visible window), `NWII_MEMCARD=<file>` (card image),
`NWII_CTRL=<file>` (lines "press NAME ms" / "shot" -> <file>.bmp / "interp on|off [hexlimit]"),
`NWII_PADLOG=1`, `NWII_WATCH_STACK=1`, `NWII_WATCH_ARM=<reg>,<hexoff>,<nth>`,
`NWII_STATE_LOG=<reg>,<hexoff>`, `NWII_TRACE_MEM=<reg>,<hexoff>,<words>`, `NWII_TRACE_STACK=1`,
`NWII_TRACE_GQR=1`, `NWII_SDKLOG=1` (interpreter mode only).

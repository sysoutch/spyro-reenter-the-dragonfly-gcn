# Launch the recompiled Spyro: Enter the Dragonfly (GameCube -> PC).
# Optional: -Screenshots <folder> saves the frame buffer every 300 frames.
#
# A title menu comes up first: Play, Open Spyro ISO (.rvz/.iso/.gcm), Recent
#   ISOs, Settings, Controller Setup. Turn it off with [launcher] enabled = false.
# Disc: the first .rvz/.iso/.gcm in this folder (else extracted\, else the
#   launcher asks). Build first with .\build.ps1.
# Settings: press F1 (or a controller's Back/View button) in-game for the
#   settings menu - resolution, anti-aliasing, texture filtering, widescreen,
#   fullscreen (also F11 / Alt+Enter), VSync, FPS counter, volume and keyboard
#   bindings. Changes apply immediately and are saved into spyro.toml.
# Default keyboard: WASD stick, arrows C-stick (camera), Space A, F B,
#   Left Shift X, R Y, Q/E L/R, Tab Z, Enter Start, numpad 8/2/4/6 D-pad.
# A controller (XInput/SDL) also works: A/B/X/Y, LB/RB = L/R, RT = Z.
# Loading a save: Start -> Load Game -> pick the slot with A (a second screen).
# Saves go to memcard_A.raw in this folder (memory card slot A, 59 blocks).
# First run: the game reports the card as corrupted -> choose Format, then
# "Create new save data" -> Yes. Back up or delete that file to keep/reset saves.
param([string]$Screenshots)

$root = $PSScriptRoot
$exe = Join-Path $root 'export\build\Release\SpyroEnterTheDragonfly.exe'
if ($Screenshots) {
    New-Item -ItemType Directory -Force $Screenshots | Out-Null
    $env:NWII_SCREENSHOT = Join-Path (Resolve-Path $Screenshots) 'shot'
}
# Run from this folder so font_western.bin / font_japanese.bin are found.
Push-Location $root
if (-not (Test-Path $exe)) { Pop-Location; throw 'Not built yet: run .\build.ps1 first.' }
$config = Join-Path $root 'spyro.toml'
if (-not (Test-Path $config)) { Copy-Item (Join-Path $root 'spyro.default.toml') $config }
$disc = Get-ChildItem -Path $root -File | Where-Object { $_.Extension -in '.rvz', '.iso', '.gcm' } | Select-Object -First 1
$disc = if ($disc) { $disc.FullName } else { Join-Path $root 'extracted' }
# [disc] config. With no disc here the launcher asks for one (Open Spyro ISO).
# (Built with += : an if-expression would unroll a one-item array into a
# string, and splatting a string passes it character by character.)
$runArgs = @()
if (Test-Path $disc) { $runArgs += $disc }
$runArgs += $config
try { & $exe @runArgs }
finally { Pop-Location }

# Build Spyro: Enter the Dragonfly for PC from your own GameCube disc.
#
#   .\build.ps1 -Disc "D:\Games\Spyro - Enter the Dragonfly (USA).rvz"
#
# -Disc: the USA disc (GS8E7D) as .rvz, .iso/.gcm or an extracted folder.
#   Default: the first .rvz/.iso/.gcm in this folder, else .\extracted.
# Steps: build the recompiler (NWiiRecomp), translate the game's code into C++
# (export\), build the executable (export\build\Release). Only changed
# generated files are copied into export\, so rebuilds stay incremental.
# Needs Visual Studio 2022 (Desktop development with C++), CMake 3.20+, Git;
# Python 3 for the generated natives (optional, see below).
param([string]$Disc, [switch]$SkipRecompiler)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$nwii = Join-Path $root 'NWiiRecomp'
# [hle_hooks] natives that tools\gen_natives.py derives from the game's code:
# the game's 4x4 matrix scale / add / multiply (skinning).
$Natives = @('gs8e_mtx44_scale', 'gs8e_mtx44_add', 'gs8e_mtx44_concat')

function Find-CMake {
    $c = Get-Command cmake -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    $vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
    if (Test-Path $vswhere) {
        $vs = & $vswhere -latest -property installationPath
        $p = Join-Path $vs 'Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe'
        if (Test-Path $p) { return $p }
    }
    throw 'CMake not found: install CMake or Visual Studio 2022 with C++ tools.'
}
$cmake = Find-CMake

function Invoke-Checked([string]$what) {
    if ($LASTEXITCODE -ne 0) { throw "$what failed (exit $LASTEXITCODE)" }
}

if (-not (Test-Path (Join-Path $nwii 'nWiiRuntime'))) {
    throw "NWiiRecomp is missing: clone with --recursive or run 'git submodule update --init'."
}

# Disc.
if (-not $Disc) {
    $found = Get-ChildItem $root -File | Where-Object { $_.Extension -in '.rvz', '.iso', '.gcm' } | Select-Object -First 1
    $Disc = if ($found) { $found.FullName } else { Join-Path $root 'extracted' }
}
if (-not (Test-Path $Disc)) { throw "Disc not found: $Disc (pass -Disc <path to your .rvz/.iso>)" }
$Disc = (Resolve-Path $Disc).Path
Write-Host "Disc: $Disc"

# Settings: spyro.toml is yours (the settings menu writes it); created from the defaults once.
$config = Join-Path $root 'spyro.toml'
if (-not (Test-Path $config)) { Copy-Item (Join-Path $root 'spyro.default.toml') $config }

# 1. Recompiler.
$recomp = Join-Path $nwii 'build\nWiiRecomp\Release\nwiirecomp.exe'
if (-not $SkipRecompiler -or -not (Test-Path $recomp)) {
    Write-Host '== Building the recompiler'
    if (-not (Test-Path (Join-Path $nwii 'build\CMakeCache.txt'))) {
        & $cmake -S $nwii -B (Join-Path $nwii 'build') -G 'Visual Studio 17 2022' -A x64 -DCMAKE_POLICY_VERSION_MINIMUM=3.5; Invoke-Checked 'CMake configure (NWiiRecomp)'
    }
    & $cmake --build (Join-Path $nwii 'build') --config Release --target nwiirecomp --parallel; Invoke-Checked 'Recompiler build'
}

# 2. Translate the game's code. The recompiler settings come from the defaults
# (so they follow updates), with the disc and output folder filled in.
Write-Host '== Recompiling the game code'
$gen = Join-Path $root 'export_gen'
$discToml = $Disc.Replace('\', '/')
$genToml = Join-Path $root 'export_gen.toml'
$text = Get-Content (Join-Path $root 'spyro.default.toml') -Raw
$text = $text -replace '(?m)^input_game_dir = .*$', "input_game_dir = `"$discToml`""
$text = $text -replace '(?m)^output_dir = .*$', 'output_dir = "export_gen"'
# Natives generated from the game's own code (tools\gen_natives.py, needs
# Python 3). Without Python their [hle_hooks] are dropped: the game then runs
# the recompiled originals, which are correct but slower.
$python = $null
foreach ($cand in @(@('python'), @('py', '-3'))) {
    try {
        $exeArgs = @($cand | Select-Object -Skip 1)
        if ((& $cand[0] @exeArgs -c 'print(1)' 2>$null) -eq '1') { $python = $cand; break }
    } catch {}
}
if (-not $python) {
    Write-Warning 'Python 3 not found: building without the generated natives (slower). Install Python and rerun to get them.'
    foreach ($n in $Natives) { $text = $text -replace "(?m)^`"[0-9A-Fa-f]{8}`" = `"$n`"\r?\n", '' }
}
Set-Content $genToml $text -NoNewline
Push-Location $root
try { & $recomp $genToml; Invoke-Checked 'Recompiling' }
finally { Pop-Location }
Remove-Item $genToml
if ($python) {
    $pyArgs = @($python | Select-Object -Skip 1)
    & $python[0] @pyArgs (Join-Path $root 'tools\gen_natives.py') $gen (Join-Path $gen 'natives\game_natives.cpp') @Natives
    Invoke-Checked 'Generating natives'
}

# Copy only what changed into export\ (unchanged files keep their timestamps).
$export = Join-Path $root 'export'
$changed = 0
foreach ($f in Get-ChildItem $gen -Recurse -File) {
    $rel = $f.FullName.Substring($gen.Length + 1)
    $dst = Join-Path $export $rel
    if (-not (Test-Path $dst) -or (Get-FileHash $f.FullName).Hash -ne (Get-FileHash $dst).Hash) {
        New-Item -ItemType Directory -Force (Split-Path $dst) | Out-Null
        Copy-Item $f.FullName $dst -Force
        $changed++
    }
}
Write-Host "$changed generated files changed"

# 3. The game.
Write-Host '== Building the game'
$build = Join-Path $export 'build'
if (-not (Test-Path (Join-Path $build 'CMakeCache.txt'))) {
    & $cmake -S $export -B $build -G 'Visual Studio 17 2022' -A x64 -DCMAKE_POLICY_VERSION_MINIMUM=3.5; Invoke-Checked 'CMake configure (game)'
}
& $cmake --build $build --config Release --target SpyroEnterTheDragonfly --parallel; Invoke-Checked 'Game build'
Write-Host "Done: $(Join-Path $build 'Release\SpyroEnterTheDragonfly.exe') -- start it with .\run-spyro.ps1"

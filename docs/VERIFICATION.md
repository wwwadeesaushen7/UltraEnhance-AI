# Verification and delivery status

Verified 28 October 2026. The project includes source and portable Windows x64 builds produced by GitHub Actions. The original Linux integration results and the newer native Windows checks are recorded below. A signed installer is not supplied.

## Original Linux integration environment

- CPython **3.11.17**, Linux x86-64; an additional initial run used Python 3.12.
- PySide6 / Qt **6.12.0**, Pillow **13.0.0**, OpenCV **5.0.0.93**, NumPy **2.4.6**, psutil **7.2.2**.
- Official Real-ESRGAN NCNN Vulkan **v0.2.0** Linux executable.
- Official Video2X **6.4.0** Linux AppImage, extracted for testing with its distributed models.
- The environment's pre-existing **SwiftShader** software Vulkan device. No graphics driver was installed or changed.
- System FFmpeg and FFprobe. All external engines are separate test resources and are **not included** in the project archive.

## Automated results

**21 passed, 1 skipped in 33.81 seconds** in the final Python 3.11 run. The skipped case requires a RIFE-compatible Vulkan device. A separate incompatibility test confirmed this environment's device fails without committing an output.

The tests exercise:

- Atomic settings save/load, queue persistence, interrupted-job recovery and per-job parameter snapshots.
- Landscape/portrait/aspect-preserving/custom targets and resolution safety limits.
- Real PNG, JPG and WebP export; alpha preservation; actual conventional adjustments.
- Image-region processing, measured auto-enhancement recommendations and missing-AI failures.
- **Real NCNN neural inference**, with output compared against a Lanczos result to ensure the AI path is distinct.
- **Real Video2X neural inference** on a short B-frame input, preserving frame count and audio after lossless zero-delay preparation.
- Real FFmpeg landscape/audio and portrait/silent exports, original FPS, conventional filters and stabilization.
- A five-second preview generated from a six-second video, preserving audio.
- Unsupported frame-rate conversion rejection, file collision handling and source preservation.
- Subprocess cancellation, cancellation during a job, and temporary-output cleanup.
- Native Qt import, analysis, automatic queue advancement through two jobs, unique exports, comparison result loading, and an actual region-preview dialog.
- Explicit RIFE shader incompatibility failure with **no completed/partial export** committed.

## Video2X compatibility finding

Video2X 6.4.0's released `--no-copy-streams` flag differs from development source's separate audio/subtitle flags. Both are detected from the installed executable's help.

The released engine reported success and zero processed frames on a two-frame H.264 B-frame clip. The app now detects reordered inputs and prepares a lossless zero-delay stream before AI processing. Final decoded-frame counts are checked against exact source counts when available. The same clip then exported all frames with its original audio. This is why process exit code alone is not treated as export success.

## Packaging check

The provided PyInstaller specification built successfully with PyInstaller **6.22.3** on Linux. The resulting native application remained running after startup in an offscreen Qt smoke test, without a startup error. That initial check validated general bundling on Linux. The native Windows build and startup results below provide the additional Windows checks.

Windows packaging is supplied through `UltraEnhance.spec`, `Build-Windows.cmd`, and the optional manual GitHub Actions workflow. Build on Windows 10/11 x64 using Python 3.11 or 3.12 and test with the target GPU. Setup and Build share automatic detection for either supported runtime. The CI workflow covers both versions and now runs for setup-script changes on main, as well as manual requests.

## Stages

| Stage | Implemented | Verification boundary |
| --- | --- | --- |
| 1 | Native dark workspace, import, drag/drop, persistent configuration, engine/hardware detection | Native Qt import/export workflow tested on Linux and Windows; GPU compatibility still needs target-hardware testing |
| 2 | Real NCNN image inference, conventional adjustments, region preview, comparison/zoom/pan, exports | Real anime-v3 2× inference and all export formats tested; photograph x4 weights and full 4K AI were not benchmarked |
| 3 | Video2X super-resolution, FFmpeg audio/filters/export/progress, five-second preview | Real short-clip AI and CPU pipelines tested; long-form, H.265 and 4K performance remain hardware checks |
| 4 | Persistent sequential batch queue, reorder/cancel/retry/history, transactional exports | Queue advancement, recovery, collisions and cancellation tested |
| 5 | Exact-multiplier Video2X RIFE adapter and conventional deshake | Deshake tested; RIFE device rejected unsupported shader capabilities. GFPGAN is not integrated |
| 6 | Tests, Windows setup/launch/build scripts, PyInstaller spec, manual CI configuration | Python 3.11/3.12 setup, application tests, Windows packaging and packaged-window startup checks passed in GitHub Actions; portable ZIP artifacts available |

## Remaining checks before distributing a Windows binary

Use the supplied build script on Windows. Confirm image and video inference on a supported Vulkan GPU; test 4K memory consumption, long videos, H.265, RIFE 30/60 FPS, non-ASCII paths and packaging on the intended hardware. This release is 8-bit SDR, keeps a single active processing job and does not preserve subtitles or image ICC metadata. Review `THIRD_PARTY_NOTICES.md` and the exact distributions you intend to ship.

Sources for engine contracts: [Real-ESRGAN CLI](https://github.com/xinntao/Real-ESRGAN-ncnn-vulkan), [Video2X](https://github.com/k4yt3x/video2x), [FFmpeg](https://ffmpeg.org/). These links document the actual engines; their capabilities are still checked locally before use.

## Python 3.12 setup compatibility update

The setup script now detects installed 64-bit Python 3.12 or 3.11, in that order, and can fall back to a compatible `python.exe` on PATH if the Windows launcher is absent. Build uses the same detection. Existing virtual environments are validated before use.

Rechecked on CPython **3.12.14**: **18 passed, 4 skipped in 9.89 seconds**. The skipped cases require explicitly configured external AI test engines/devices; this run did not repeat those integration tests. The original real-engine results above remain the recorded integration verification. The newer native Windows checks are recorded below.

## Windows interpreter-discovery update

Setup now reads installed runtimes from the launcher, both 32-bit and 64-bit Python registry views, PATH and standard installation folders. It verifies the actual interpreter version and bitness. A native file picker supports custom installations without PATH or launcher registration. Setup records attempted runtimes and failures in `setup-diagnostics.txt`, which is excluded from source control.

The Windows CI workflow checks setup under Windows PowerShell 5.1, including an explicit interpreter path with Python removed from PATH and a destination directory containing spaces. It then checks automatic discovery through the .cmd launcher, runs the application test suite and packages each supported Python version. These setup checks passed on Windows in both supported Python jobs. The follow-up run below pins each build to its selected runtime and checks the resulting native application window.

## Native Windows build and startup verification

[Windows CI run 40723205320](https://github.com/wwwadeesaushen7/UltraEnhance-AI/actions/runs/40723205320) built the portable Windows x64 application with each selected Python version. The setup checks passed under Windows PowerShell 5.1 with Python absent from PATH, using a destination with spaces, and through the .cmd launcher. Each selected-version Windows build passed 10 application tests with 12 tests skipped; tests requiring externally installed FFmpeg or AI backends were skipped on these Windows runners and retain their earlier Linux integration results.

Both packaged executable startup checks passed: CI launched `UltraEnhanceAI.exe` on Windows and verified that its real main window, `UltraEnhance AI — Local enhancement studio`, opened. The test closes the process after confirming the window. No AI engine or model weights are bundled in the application ZIP. Python and the GUI/image dependencies are bundled, so launching the portable build does not require a separate Python installation.

This verifies startup on the hosted Windows runner, not every Windows version, GPU or installed driver. Long videos, 4K resource use, RIFE and target-GPU inference remain hardware-specific checks. GitHub Actions artifacts expire according to the repository retention policy; use the latest successful run if an older download has expired.

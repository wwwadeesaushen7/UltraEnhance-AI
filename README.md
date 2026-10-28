# UltraEnhance AI

A native, offline-first Windows image and video enhancement studio supporting Python 3.11 and 3.12 with PySide6. Real-ESRGAN NCNN Vulkan performs image inference; Video2X 6.x performs streaming video inference; FFmpeg handles encoding, audio and conventional video filters. No paid APIs, accounts or subscriptions are used.

This is a working source release, not a signed Windows installer. See `docs/VERIFICATION.md` for exactly what was exercised and what still needs Windows/hardware validation. Third-party engines and weights are installed separately from their official sources.

## Start on Windows

1. Use **64-bit Windows 10/11** with **64-bit Python 3.12 or 3.11**. If either is already installed, keep it; no additional Python installation is needed.
2. Extract this project to a writable folder. Double-click **Setup-Windows.cmd** to create a private virtual environment and install the Python dependencies. Setup checks the launcher, PATH, registered Python installations and standard install folders. If needed, a file picker lets you select your installed `python.exe` directly. It verifies Python 3.12/3.11 and 64-bit architecture without changing PATH or installing another runtime. Keep the `scripts` folder alongside Setup-Windows.cmd.
3. Double-click **Launch-UltraEnhance.cmd**. The application opens without a console window. Alternatively, open the project in VS Code and use the supplied **UltraEnhance desktop** debug configuration.
4. Open **Settings & engines**. Select the official processing executables and the Real-ESRGAN models folder, then click **Save settings & check engines**.
5. Import files, choose a processing engine and output folder, preview a region or the first five seconds, then enhance and export.

Setup needs an Internet connection to install Python packages. Once engines and model weights are installed, processing runs locally and does not need a network connection. After packaging, the standalone application does not require Python or a terminal.

## Install the processing engines

**Real-ESRGAN NCNN Vulkan**: https://github.com/xinntao/Real-ESRGAN-ncnn-vulkan/releases

Download a Windows release and extract the entire distribution. Keep its DLLs beside `realesrgan-ncnn-vulkan.exe`. Some releases distribute binaries and models separately: the selected models folder must contain matching `.param` and `.bin` files. Photograph uses `realesrgan-x4plus`, illustration/anime uses `realesrgan-x4plus-anime`, and anime video uses `realesr-animevideov3-x2`, `-x3`, and `-x4` weights. Use weights from the official project; Video2X's renamed photograph model files are not interchangeable by filename with the standalone engine.

**Video2X 6.x CLI**: https://github.com/k4yt3x/video2x/releases

Download the Windows CLI archive or install the official distribution. Select **video2x.exe**, not `video2x-qt6.exe`. Preserve its model directories, DLLs and distribution layout. This integration reads `--help` and supports both the released `--no-copy-streams` option and the development split audio/subtitle flags. Legacy Python Video2X 4/5 CLIs are not supported.

**FFmpeg + FFprobe**: https://ffmpeg.org/download.html

Follow the Windows builds links from the official FFmpeg page. Extract the full distribution. Select `bin/ffmpeg.exe` and `bin/ffprobe.exe`. The build must include `libx264`; H.265 additionally requires `libx265`. Stabilization requires the `deshake` filter. All are checked before use.

You may instead place engines beside the installed application:

```text
UltraEnhanceAI.exe
engines/
  realesrgan/realesrgan-ncnn-vulkan.exe
  realesrgan/models/...
  video2x/video2x.exe
  video2x/<keep the rest of the official distribution>
  ffmpeg/ffmpeg.exe
  ffprobe/ffprobe.exe
```

PATH lookup is also supported. Explicit paths in Settings take priority. A missing or broken AI backend reports an error and never silently uses conventional scaling. Select **Lanczos · CPU (non-AI)** to use the explicit fallback.

## Workflow

- **Image Enhancer** supports JPG/JPEG, PNG and WebP; 2×/3×/4×, 1080p, 1440p, 4K and custom targets; aspect-ratio preservation; PNG/JPG/WebP export; transparency (JPG flattens onto white); and EXIF orientation.
- **Real AI:** NCNN model inference. Dedicated anime weights support 2×/3×/4×. Photograph and illustration x4 models infer at 4× and use Lanczos to reduce to the requested output. Requests above native model magnification are rejected rather than mislabeled as additional AI enlargement.
- **Conventional adjustments:** OpenCV non-local-means denoise, bilateral artifact reduction, unsharp mask, brightness, contrast, saturation and a bounded gray-world white-balance correction. These are not described as AI. Filters run before image inference to limit cost. Noise reduction also removes texture; inspect a region first.
- **Preview:** drag the comparison divider, switch to side-by-side, scroll to zoom, drag to pan, click 100% for native result pixels. Select a region to test up to one megapixel of source content; otherwise the central 256×256 source region is used. The enhanced region appears in its own comparison window. Video uses a five-second clip and your default media player; video playback is not embedded in Qt.
- **Auto Enhance:** applies practical brightness/contrast/noise/sharpness measurements from a bounded image or first video frame. These are heuristic recommendations, not content recognition or promises to recover missing information.
- **Batch Processing:** import or drag multiple files, select them using Ctrl/Shift, configure settings and add to queue. A mixed batch uses the active export controls for the current media type and saved format defaults for the other type. Each queued job has its own immutable settings snapshot.
- **Processing Queue:** reorder adjacent waiting jobs, start, stop after current, cancel, retry failures, inspect errors and open results/folders. One expensive job runs at a time. Pending jobs and the most recent 100 history records persist across restarts. Jobs that were running at an unexpected close become Interrupted.
- **Video:** MP4, MOV, MKV, AVI and WebM input; MP4/MKV H.264 or supported H.265 output; portrait and landscape; original FPS; optional exact-multiplier RIFE; conventional denoise, unsharp mask, brightness, contrast, saturation and deshake stabilization.

## Memory, temporary files and export integrity

Video2X streams frames; this app never loads an entire video into RAM or extracts a frame directory. Necessary lossless video intermediates are stored in a private temporary directory and cleaned on normal success, failure or cancellation. B-frame inputs are normalized to a lossless zero-delay stream because Video2X 6.4.0 can omit delayed frames at EOF. They can be large: allow ample temporary disk space, especially for 4K or RIFE. AI inference, interpolation and final export run sequentially. Video2X controls its own memory; the app's tile size applies only to standalone image NCNN. Official Video2X binaries also require an AVX2-capable CPU; older computers should use the explicit CPU/FFmpeg fallback with compatible FFmpeg/Python builds.

Final output is encoded into a hidden transaction directory beside its destination. Images are reopened and verified. Videos are checked for dimensions, duration, FPS and audio presence, then fully decoded with FFmpeg's `-xerror` before committing a unique final filename. Existing source and output files are preserved. Cancellation terminates the subprocess tree and discards the transaction. OpenCV/Pillow operations complete their current call before observing cancellation. A forced process kill/power loss may leave hidden temporary directories; these are never listed as completed jobs and can be removed after confirming no processing is active.

Original audio is copied when compatible. If the chosen container rejects its codec, audio is converted to AAC at 192 kbps and the current stage explains this. Subtitles, attachments, chapters and extra video streams are not carried into the export in this release. Variable-rate input uses FFmpeg timestamp passthrough in CPU mode. AI mode rejects apparent variable-rate input because Video2X produces a fixed output rate. Source-frame counts from metadata can be estimates; progress percentages are emitted only from the engines' actual frame/time reports. Unknown stages use an indeterminate indicator.

Input images and outputs are limited to 80 megapixels and 16,384 pixels per side. File-list thumbnails are bounded, and only the current original and result are kept at full preview resolution. Use small tiles (32/64/128) and a modest region preview on low-memory hardware. Driver installation is outside this app. A Vulkan loader alone is reported as unverified, and actual engine execution is the final compatibility check.

## Presets

| Preset | Image NCNN | Final video encoding |
| --- | --- | --- |
| Fast | 64-pixel tiles, 1:1:1 loading/inference/saving | veryfast |
| Balanced | 128-pixel tiles, 1:1:1 | medium |
| Maximum Quality | 256-pixel tiles, test-time augmentation | slow |

Tile size remains configurable in Settings. Presets keep your selected engine and model; none silently swaps AI for a conventional algorithm. CRF independently controls video compression (lower = better quality/larger file); image quality applies to JPG/WebP, while PNG is lossless.

## Build a Windows executable

Run **Build-Windows.cmd** on 64-bit Windows with Python 3.12 or 3.11. It uses the same automatic Python detection as Setup, installs development dependencies, runs tests, and invokes the supplied PyInstaller specification. Distribute the **entire** `dist/UltraEnhanceAI/` folder, not only its `.exe`. It is a windowed application and uses no terminal after installation. Engines remain separate to avoid silently redistributing their binaries/models/licenses.

The optional `.github/workflows/windows-build.yml` builds separate Python 3.11 and 3.12 artifacts on `windows-latest` when run in your own repository. The workflow runs for setup-script changes pushed to main, and can also be started manually from GitHub Actions. Windows binaries cannot be built or validated on this Linux host; the spec and CI workflow are provided for the native build.

For command-line development:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe main.py
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m PyInstaller --noconfirm UltraEnhance.spec
```

Use `py -3.11` in the first command if your installed version is Python 3.11. If automatic discovery fails, run Setup-Windows.cmd and select your installation in the file picker. Diagnostics, including detected version and architecture, are saved in `setup-diagnostics.txt` beside the scripts. A 32-bit interpreter is explicitly reported and cannot run this 64-bit desktop stack.

## Current limits

- GFPGAN face restoration is not integrated; there is no pretend restoration control.
- RIFE uses compatible Video2X 6.x models and exact 2×/3×/4× constant FPS ratios: e.g. 15→30/60 or 30→60. 24→60 and 29.97→60 are rejected rather than silently duplicating/dropping frames. This release selects the official `rife-v4.6` model.
- Video output is **8-bit SDR, yuv420p**. HDR/10-bit/color-managed workflows are unsupported and should use dedicated software. Image ICC profiles and metadata are not preserved; verify color-critical work externally.
- One processing job is enforced; higher concurrency is intentionally not exposed as a nonfunctional preference.
- Windows GPU vendors, long videos, full-resolution 4K AI, Windows packaging and installer behavior require testing on the target machine. A successful tiny software-Vulkan smoke test is not a performance benchmark or a GPU compatibility guarantee.

## Source layout

```text
main.py                       Qt application entry point
ultraenhance/config.py         validated, atomic preferences
ultraenhance/backends.py       engine discovery, CLI checks, hardware report
ultraenhance/process.py        bounded subprocess logs and cancellation
ultraenhance/media.py          metadata, aspect ratio, quality heuristics
ultraenhance/image_engine.py   NCNN image inference and conventional filters
ultraenhance/video_engine.py   Video2X / RIFE / FFmpeg pipeline
ultraenhance/jobs.py           queue persistence and export transactions
ultraenhance/ui/               native workspace, comparison view, workers
tests/                        real export, cancellation and desktop tests
```

Settings and queue history live in `%APPDATA%/UltraEnhanceAI/` (or `$XDG_CONFIG_HOME` equivalent fallback on Linux). `ULTRAENHANCE_CONFIG_DIR` overrides this for isolated development/testing. Paths in history remain on your computer. This app contains no network client, telemetry, auto-updater, paid service or cloud processing integration.

See `THIRD_PARTY_NOTICES.md` before distributing any third-party engines, models or Qt components.

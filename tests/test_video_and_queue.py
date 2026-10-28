from dataclasses import replace
from pathlib import Path
import shutil
import os
import sys
import threading
import time

from PIL import Image
import pytest

from ultraenhance.backends import BackendManager
from ultraenhance.config import Settings
from ultraenhance.image_engine import JobOptions
from ultraenhance.jobs import Job, execute_job, load_queue, save_queue
from ultraenhance.media import probe
from ultraenhance.process import Cancelled, ProcessingError, run_process


@pytest.fixture
def backends(tmp_path):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("FFmpeg / FFprobe not installed")
    return BackendManager(Settings(output_dir=str(tmp_path / "exports"))).scan()


def make_video(path, audio=False, portrait=False, fps=15, duration=1):
    args = [shutil.which("ffmpeg"), "-v", "error", "-nostdin", "-y", "-f", "lavfi", "-i", f"testsrc2=size={'64x96' if portrait else '96x64'}:rate={fps}"]
    if audio:
        args += ["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100"]
    args += ["-t", str(duration), "-c:v", "libx264", "-pix_fmt", "yuv420p"]
    if audio:
        args += ["-c:a", "aac", "-shortest"]
    run_process(args + [str(path)])


@pytest.mark.parametrize("audio,portrait", [(True, False), (False, True)])
def test_real_ffmpeg_export_and_audio(tmp_path, backends, audio, portrait):
    source = tmp_path / "input with spaces.mp4"
    make_video(source, audio, portrait)
    options = JobOptions(engine="CPU", denoise=1, brightness=.05, contrast=1.1, saturation=1.05, sharpness=.2, stabilize=True)
    events = []
    output, size = execute_job(Job(str(source), options), backends, threading.Event(), lambda *args: events.append(args))
    info = probe(output, backends)
    assert (info.width, info.height) == ((128, 192) if portrait else (192, 128))
    assert info.audio is audio
    assert abs(info.duration - 1) < .1
    assert abs(info.fps - 15) < .01
    assert any(e[1] is not None for e in events)
    assert not list(Path(output).parent.glob(".ultraenhance-partial-*"))


def test_five_second_preview(tmp_path, backends):
    source = tmp_path / "six-seconds.mp4"; make_video(source, True, duration=6)
    output, _ = execute_job(Job(str(source), JobOptions(engine="CPU"), preview=True), backends, threading.Event(), lambda *s: None, tmp_path / "preview")
    info = probe(output, backends)
    assert 4.9 <= info.duration <= 5.2
    assert info.audio


def test_failed_engine_never_commits_output(tmp_path, backends):
    source = tmp_path / "source.mp4"; make_video(source)
    with pytest.raises(ProcessingError, match="video2x is unavailable"):
        execute_job(Job(str(source), JobOptions(engine="AI")), backends, threading.Event(), lambda *s: None)
    exports = Path(backends.settings.output_dir)
    assert list(exports.iterdir()) == []


def test_unsupported_interpolation_fails_clearly(tmp_path, backends):
    source = tmp_path / "source.mp4"; make_video(source, fps=24)
    with pytest.raises(ProcessingError, match="exact 2×"):
        execute_job(Job(str(source), JobOptions(engine="CPU", interpolation=60)), backends, threading.Event(), lambda *s: None)


def test_collision_does_not_overwrite_source_or_export(tmp_path, backends):
    source = tmp_path / "source.png"; Image.new("RGB", (16, 12), "blue").save(source)
    original = source.read_bytes()
    job = Job(str(source), JobOptions(engine="CPU"))
    first, _ = execute_job(job, backends, threading.Event(), lambda *s: None)
    first_content = Path(first).read_bytes()
    second, _ = execute_job(job, backends, threading.Event(), lambda *s: None)
    assert first != second
    assert Path(first).read_bytes() == first_content
    assert source.read_bytes() == original


def test_cancel_subprocess_and_no_leftover_file(tmp_path, backends):
    source = tmp_path / "source.png"; Image.new("RGB", (16, 16)).save(source)
    event = threading.Event(); event.set()
    with pytest.raises(Cancelled):
        execute_job(Job(str(source), JobOptions(engine="CPU")), backends, event, lambda *s: None)
    assert not Path(backends.settings.output_dir).exists()
    event.clear()
    timer = threading.Timer(.2, event.set); timer.start()
    start = time.monotonic()
    with pytest.raises(Cancelled):
        run_process([sys.executable, "-c", "import time;time.sleep(20)"], event)
    timer.join()
    assert time.monotonic() - start < 5


def test_queue_recovery_and_settings_snapshot(tmp_path, monkeypatch):
    monkeypatch.setenv("ULTRAENHANCE_CONFIG_DIR", str(tmp_path))
    options = JobOptions(engine="CPU", brightness=.1)
    jobs = [Job("one.png", replace(options)), Job("two.png", replace(options), status="Running")]
    options.brightness = .4
    save_queue(jobs)
    loaded = load_queue()
    assert [j.status for j in loaded] == ["Queued", "Interrupted"]
    assert loaded[0].options.brightness == .1
    assert loaded[1].output == ""


def test_cancellation_during_job_cleans_transaction(tmp_path, backends):
    source = tmp_path / "source.png"; Image.new("RGB", (32, 32), "red").save(source)
    event = threading.Event()
    def cancel_after_start(*args):
        event.set()
    with pytest.raises(Cancelled):
        execute_job(Job(str(source), JobOptions(engine="CPU")), backends, event, cancel_after_start)
    assert list(Path(backends.settings.output_dir).iterdir()) == []


@pytest.mark.skipif(not os.environ.get("ULTRAENHANCE_TEST_VIDEO2X"), reason="Real Video2X not configured")
@pytest.mark.parametrize("fps_target", [0, pytest.param(30, marks=pytest.mark.skipif(
    not os.environ.get("ULTRAENHANCE_TEST_RIFE"), reason="RIFE requires a Vulkan device with compatible FP16/8-bit shader support"))])
def test_actual_video2x_ai_and_rife(tmp_path, backends, fps_target):
    backends.settings.video2x = os.environ["ULTRAENHANCE_TEST_VIDEO2X"]
    backends.scan()
    source = tmp_path / "tiny-b-frame-video.mp4"
    make_video(source, audio=True, fps=15, duration=.14)
    original = probe(source, backends)
    assert original.has_b_frames > 0
    output, size = execute_job(Job(str(source), JobOptions(model="realesr-animevideov3", interpolation=fps_target)), backends,
                               threading.Event(), lambda *s: None)
    result = probe(output, backends)
    assert (result.width, result.height) == (192, 128)
    assert result.audio
    assert result.frames == original.frames * (2 if fps_target else 1)
    assert abs(result.fps - (fps_target or 15)) < .01


@pytest.mark.skipif(not os.environ.get("ULTRAENHANCE_TEST_RIFE_UNSUPPORTED"), reason="Only for the known incompatible software Vulkan test device")
def test_incompatible_rife_device_never_exports(tmp_path, backends):
    backends.settings.video2x = os.environ["ULTRAENHANCE_TEST_VIDEO2X"]
    backends.scan()
    source = tmp_path / "rife-source.mp4"; make_video(source, fps=15, duration=.14)
    with pytest.raises(ProcessingError, match="video2x exited") as error:
        execute_job(Job(str(source), JobOptions(engine="CPU", interpolation=30)), backends, threading.Event(), lambda *s: None)
    assert "UNSUPPORTED" in str(error.value) or "capability" in str(error.value)
    assert list(Path(backends.settings.output_dir).iterdir()) == []

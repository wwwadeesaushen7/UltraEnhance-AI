from dataclasses import replace
from pathlib import Path
import os
import threading

from PIL import Image
import pytest

from ultraenhance.backends import BackendManager
from ultraenhance.config import Settings, load_settings, save_settings
from ultraenhance.image_engine import JobOptions, enhance_image
from ultraenhance.media import target_size, analyze
from ultraenhance.process import Cancelled, ProcessingError


def test_settings_atomic_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("ULTRAENHANCE_CONFIG_DIR", str(tmp_path))
    settings = Settings(output_dir=str(tmp_path / "exports"), tile_size=64)
    save_settings(settings)
    assert load_settings() == settings
    assert list(tmp_path.glob("settings-*.json")) == []


def test_resolution_and_portrait():
    assert target_size(1920, 1080, "4K") == (3840, 2160)
    assert target_size(1080, 1920, "4K") == (2160, 3840)
    assert target_size(800, 600, "4K") == (2880, 2160)
    assert target_size(800, 600, "Custom", (1000, 1000), False) == (1000, 1000)
    with pytest.raises(ProcessingError):
        target_size(10000, 10000, "4×")


@pytest.mark.parametrize("fmt,suffix", [("PNG", ".png"), ("JPG", ".jpg"), ("WEBP", ".webp")])
def test_cpu_filters_and_real_export(tmp_path, fmt, suffix):
    source = tmp_path / "input image.png"
    Image.new("RGBA", (32, 24), (40, 65, 80, 128)).save(source)
    output = tmp_path / ("result" + suffix)
    options = JobOptions(engine="CPU", image_format=fmt, brightness=0.2, contrast=1.1, sharpness=0.3,
                         denoise=2, artifact_reduction=True, color_correct=True)
    stages = []
    enhance_image(source, output, options, BackendManager(Settings()), threading.Event(), lambda *s: stages.append(s))
    with Image.open(output) as result:
        assert result.size == (64, 48)
        assert result.getpixel((10, 10))[0] > 40
        if fmt == "PNG":
            assert result.getpixel((10, 10))[3] == 128
    assert any("non-AI" in s[0] for s in stages)


def test_region_and_cancellation(tmp_path):
    source = tmp_path / "input.png"
    Image.new("RGB", (64, 48), "gray").save(source)
    output = tmp_path / "result.png"
    enhance_image(source, output, JobOptions(engine="CPU"), BackendManager(Settings()), threading.Event(), lambda *s: None, (4, 4, 20, 20))
    assert Image.open(output).size == (32, 32)
    canceled = threading.Event(); canceled.set()
    with pytest.raises(Cancelled):
        enhance_image(source, tmp_path / "canceled.png", JobOptions(), BackendManager(Settings()), canceled, lambda *s: None)
    assert not (tmp_path / "canceled.png").exists()


def test_missing_ai_is_an_error(tmp_path):
    source = tmp_path / "input.png"; Image.new("RGB", (8, 8)).save(source)
    with pytest.raises(ProcessingError, match="unavailable"):
        enhance_image(source, tmp_path / "result.png", JobOptions(), BackendManager(Settings()), threading.Event(), lambda *s: None)
    assert not (tmp_path / "result.png").exists()


def test_analysis_changes_real_settings():
    stats = analyze(Image.new("RGB", (64, 64), (20, 20, 20)))
    assert stats["recommended"]["brightness"] > 0
    assert stats["recommended"]["contrast"] > 1


@pytest.mark.skipif(not os.environ.get("ULTRAENHANCE_TEST_ESRGAN"), reason="Real backend not configured")
def test_real_ncnn_inference(tmp_path):
    settings = Settings(realesrgan=os.environ["ULTRAENHANCE_TEST_ESRGAN"], models_dir=os.environ["ULTRAENHANCE_TEST_MODELS"])
    backends = BackendManager(settings).scan()
    source = tmp_path / "actual input.png"
    image = Image.new("RGB", (32, 24), (20, 60, 110)); image.putpixel((10, 10), (255, 255, 255)); image.save(source)
    output = tmp_path / "actual-ai.png"
    progress = []
    enhance_image(source, output, JobOptions(model="realesr-animevideov3", tile=32), backends, threading.Event(), lambda *s: progress.append(s))
    result = Image.open(output)
    assert result.size == (64, 48)
    assert result.tobytes() != image.resize((64, 48), Image.Resampling.LANCZOS).tobytes()
    assert any("Real-ESRGAN" in p[0] for p in progress)

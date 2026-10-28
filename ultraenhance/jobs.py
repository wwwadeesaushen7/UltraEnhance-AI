"""Persistent queue records and atomic, collision-safe export transactions."""
from dataclasses import asdict, dataclass, field
import json
import os
from pathlib import Path
import tempfile
import uuid

from .config import config_dir
from .image_engine import JobOptions, enhance_image
from .media import probe
from .process import check_cancel, ProcessingError
from .video_engine import enhance_video


@dataclass
class Job:
    source: str
    options: JobOptions
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    status: str = "Queued"
    output: str = ""
    error: str = ""
    preview: bool = False
    region: tuple | None = None


def save_queue(jobs):
    path = config_dir()
    path.mkdir(parents=True, exist_ok=True)
    active = [j for j in jobs if not j.preview and j.status in ("Queued", "Running")]
    history = [j for j in jobs if not j.preview and j.status not in ("Queued", "Running")][-100:]
    keep = {j.id for j in active + history}
    data = [asdict(j) for j in jobs if j.id in keep]
    fd, temp = tempfile.mkstemp(dir=path, prefix="queue-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2)
            stream.flush(); os.fsync(stream.fileno())
        os.replace(temp, path / "queue.json")
    finally:
        Path(temp).unlink(missing_ok=True)


def load_queue():
    path = config_dir() / "queue.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        result = []
        for row in data:
            row["options"] = JobOptions(**row["options"])
            row["options"].validate()
            job = Job(**row)
            if job.status == "Running":
                job.status = "Interrupted"
                job.error = "The application closed during processing. Add the source again to retry; no incomplete export is treated as successful."
            result.append(job)
        return result
    except (OSError, ValueError, TypeError) as exc:
        raise ProcessingError(f"Cannot load queue history: {path}\n{exc}") from exc


def execute_job(job, backends, cancel, progress, preview_directory=None):
    job.options.validate()
    check_cancel(cancel)
    info = probe(job.source, backends, cancel)
    extension = job.options.image_format.lower() if info.kind == "image" else job.options.video_format.lower()
    directory = Path(preview_directory) if job.preview else Path(job.options.output_dir or backends.settings.output_dir).expanduser()
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".ultraenhance-partial-", dir=directory) as temporary:
        candidate = Path(temporary) / f"result.{extension}"
        if info.kind == "image":
            size = enhance_image(job.source, candidate, job.options, backends, cancel, progress, job.region if job.preview else None)
        else:
            size = enhance_video(job.source, candidate, job.options, backends, cancel, progress, job.preview)
        check_cancel(cancel)
        if not candidate.is_file() or candidate.stat().st_size == 0:
            raise ProcessingError("The processing engine did not create a valid output file.")
        stem = f"{Path(job.source).stem}_{'preview' if job.preview else 'enhanced'}"
        destination = None
        for index in range(10000):
            destination = directory / f"{stem}{'' if index == 0 else '_' + str(index)}.{extension}"
            try:
                fd = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.close(fd)
                break
            except FileExistsError:
                continue
        else:
            raise ProcessingError("Unable to reserve a unique export filename.")
        try:
            check_cancel(cancel)
            os.replace(candidate, destination)
        except BaseException:
            destination.unlink(missing_ok=True)
            raise
    return str(destination), size

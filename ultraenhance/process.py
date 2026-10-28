"""Bounded subprocess output, responsive cancellation and process-tree cleanup."""
from collections import deque
import os
from pathlib import Path
import queue
import re
import subprocess
import threading
import time

import psutil


class ProcessingError(RuntimeError):
    pass


class Cancelled(ProcessingError):
    pass


def check_cancel(event):
    if event.is_set():
        raise Cancelled("Canceled. No partial output was exported.")


def stop_tree(process):
    try:
        parent = psutil.Process(process.pid)
        children = parent.children(recursive=True)
        for child in children:
            try:
                child.terminate()
            except psutil.Error:
                pass
        try:
            parent.terminate()
        except psutil.Error:
            pass
        _, alive = psutil.wait_procs(children + [parent], timeout=2)
        for child in alive:
            try:
                child.kill()
            except psutil.Error:
                pass
    except psutil.NoSuchProcess:
        pass
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def run_process(args, cancel=None, on_line=None, timeout=None, cwd=None):
    """Run argument arrays only. Returns at most the last 120 output lines."""
    cancel = cancel or threading.Event()
    check_cancel(cancel)
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        proc = subprocess.Popen(
            [str(a) for a in args], cwd=cwd, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            creationflags=creationflags,
        )
    except OSError as exc:
        raise ProcessingError(f"Cannot start {Path(args[0]).name}: {exc}") from exc
    chunks = queue.Queue(maxsize=64)
    reader_stop = threading.Event()

    def reader():
        try:
            while not reader_stop.is_set():
                chunk = os.read(proc.stdout.fileno(), 4096)
                if not chunk:
                    break
                while not reader_stop.is_set():
                    try:
                        chunks.put(chunk, timeout=0.1)
                        break
                    except queue.Full:
                        pass
        finally:
            while not reader_stop.is_set():
                try:
                    chunks.put(None, timeout=0.1)
                    break
                except queue.Full:
                    pass

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    lines = deque(maxlen=120)
    pending = b""
    start = time.monotonic()
    try:
        while True:
            check_cancel(cancel)
            if timeout is not None and time.monotonic() - start > timeout:
                raise ProcessingError(f"{Path(args[0]).name} exceeded its {timeout:g}s timeout.")
            try:
                chunk = chunks.get(timeout=0.1)
            except queue.Empty:
                continue
            if chunk is None:
                break
            pending += chunk
            parts = re.split(rb"[\r\n]", pending)
            pending = parts.pop()[-65536:]
            for part in parts:
                line = part.decode("utf-8", errors="replace").strip()
                if line:
                    lines.append(line)
                    if on_line:
                        on_line(line)
        if pending:
            line = pending.decode("utf-8", errors="replace")
            lines.append(line)
            if on_line:
                on_line(line)
        code = proc.wait(timeout=3)
        check_cancel(cancel)
        result = "\n".join(lines)
        if code:
            raise ProcessingError(f"{Path(args[0]).name} exited with code {code}.\n{result}")
        return result
    finally:
        reader_stop.set()
        if proc.poll() is None:
            stop_tree(proc)
        thread.join(timeout=2)
        proc.stdout.close()


def capture(args, timeout=10):
    """Help commands sometimes exit nonzero; preserve their output for capability detection."""
    try:
        return run_process(args, timeout=timeout)
    except ProcessingError as exc:
        return str(exc)

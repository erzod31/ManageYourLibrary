"""Disposable document readers with OS-enforced resource limits.

This is fault isolation, not a security sandbox: readers still run as the user.
No parser objects, pickle payloads, or document text are written to the profile.
Document/OCR readers stay offline. A separate remote-cover action accepts only
an allowlisted HTTPS URL and thumbnail size, without document input.
"""
from __future__ import annotations

import base64
import functools
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

MAX_RESULT_BYTES = 16 * 1024 * 1024
_IN_WORKER = False
_DOCUMENT_SLOTS = threading.BoundedSemaphore(2)
_COVER_SLOTS = threading.BoundedSemaphore(2)


class ReaderFailure(RuntimeError):
    """A reader failed, exceeded its budget, or returned an invalid response."""


def in_worker():
    return _IN_WORKER


def _windows_job(process, memory_bytes):
    import ctypes
    from ctypes import wintypes

    class BasicLimit(ctypes.Structure):
        _fields_ = [('process_time', ctypes.c_int64), ('job_time', ctypes.c_int64),
                    ('flags', wintypes.DWORD), ('min_ws', ctypes.c_size_t),
                    ('max_ws', ctypes.c_size_t), ('active', wintypes.DWORD),
                    ('affinity', ctypes.c_size_t), ('priority', wintypes.DWORD),
                    ('scheduling', wintypes.DWORD)]

    class IoCounters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint64) for name in
                    ('read_ops', 'write_ops', 'other_ops', 'read_bytes', 'write_bytes', 'other_bytes')]

    class ExtendedLimit(ctypes.Structure):
        _fields_ = [('basic', BasicLimit), ('io', IoCounters),
                    ('process_memory', ctypes.c_size_t), ('job_memory', ctypes.c_size_t),
                    ('peak_process', ctypes.c_size_t), ('peak_job', ctypes.c_size_t)]

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateJobObjectW(None, None)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    limits = ExtendedLimit()
    limits.basic.flags = 0x2000 | 0x100 | 0x200  # kill on close, process and whole-job memory
    limits.process_memory = limits.job_memory = memory_bytes
    if (not kernel.SetInformationJobObject(handle, 9, ctypes.byref(limits), ctypes.sizeof(limits))
            or not kernel.AssignProcessToJobObject(handle, wintypes.HANDLE(int(process._handle)))):
        error = ctypes.WinError(ctypes.get_last_error())
        kernel.CloseHandle(handle)
        raise error
    return lambda: kernel.CloseHandle(handle)


def run_reader(kind, payload, *, timeout=45, memory_mb=1024, cancellation=None):
    slots = _COVER_SLOTS if kind in {'cover', 'image_decode', 'remote_cover'} else _DOCUMENT_SLOTS
    while not slots.acquire(timeout=.025):
        if cancellation:
            cancellation.raise_if_cancelled()
    try:
        return _run_reader(kind, payload, timeout=timeout, memory_mb=memory_mb, cancellation=cancellation)
    finally:
        slots.release()


def _mac_memory_reader(process):
    """Darwin does not implement Linux's address-space limit semantics.

    Read the native task RSS while the child executes, including native hangs.
    Darwin's data/address-space rlimits reject otherwise valid limits on supported
    hosts. This watchdog is sampled, unlike a Windows Job's allocation cap.
    """
    import ctypes
    lib = ctypes.CDLL('/usr/lib/libproc.dylib', use_errno=True)
    lib.proc_pidinfo.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_uint64,
                                ctypes.c_void_p, ctypes.c_int]
    lib.proc_pidinfo.restype = ctypes.c_int
    buffer = ctypes.create_string_buffer(96)  # struct proc_taskinfo, PROC_PIDTASKINFO=4
    def resident_bytes():
        count = lib.proc_pidinfo(process.pid, 4, 0, buffer, len(buffer))
        if count < 16:
            # A process can become a zombie between poll and proc_pidinfo.
            # Darwin may report EPERM in that window; reap it before deciding
            # that a live process cannot be monitored.
            try:
                process.wait(timeout=.05)
                return 0
            except subprocess.TimeoutExpired:
                pass
            raise ReaderFailure('Cannot monitor Darwin reader memory')
        return ctypes.c_uint64.from_buffer(buffer, 8).value
    return resident_bytes


def _reader_environment(kind):
    environment = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}
    if kind != 'remote_cover':
        environment['MANAGE_YOUR_LIBRARY_OFFLINE'] = '1'
    return environment


def _run_reader(kind, payload, *, timeout=45, memory_mb=1024, cancellation=None):
    """Run a single allowlisted operation; time includes interpreter startup.

    Limits cannot be disabled on failure. Windows Job objects include descendants;
    POSIX readers use RLIMIT_AS and a separate process group. Parent polls every
    25ms, including during a native hang, rather than waiting on a Python thread.
    """
    if cancellation:
        cancellation.raise_if_cancelled()
    if timeout <= 0 or memory_mb < 64:
        raise ValueError('Invalid reader budget')
    with tempfile.TemporaryDirectory(prefix='myl_reader_') as directory:
        result_path = Path(directory) / 'result.json'
        request_path = Path(directory) / 'request.json'
        ready_path = Path(directory) / 'ready'
        request = dict(kind=kind, payload=payload, output=str(result_path), memory_mb=memory_mb)
        raw = json.dumps(request, ensure_ascii=True).encode('utf-8')
        if len(raw) > 1024 * 1024:
            raise ReaderFailure('Reader request exceeds its limit')
        request_path.write_bytes(raw)
        command = [sys.executable]
        if not getattr(sys, 'frozen', False):
            command += ['-B', str(Path(__file__).resolve().parents[1] / 'main.py')]
        # Windowed frozen executables have sys.stdin=None. A bounded private
        # request file also avoids a blocking pipe write before the timeout loop.
        # The child waits for ready, published only after OS limits are attached.
        command += ['--reader-worker', str(request_path)]
        started = time.monotonic()
        process = subprocess.Popen(
            command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
            start_new_session=os.name != 'nt',
            env=_reader_environment(kind),
        )
        close_job = None
        try:
            rss = _mac_memory_reader(process) if sys.platform == 'darwin' else None
            if os.name == 'nt':
                close_job = _windows_job(process, int(memory_mb * 1024 * 1024))
            ready_path.touch(exist_ok=False)
            while process.poll() is None:
                if cancellation:
                    cancellation.raise_if_cancelled()
                if time.monotonic() - started >= timeout:
                    raise ReaderFailure(f'Reader {kind} exceeded {timeout:g}s; manual review required')
                if rss and rss() > memory_mb * 1024 * 1024:
                    raise ReaderFailure(f'Reader {kind} exceeded its resident-memory budget')
                time.sleep(.025)
            if cancellation:
                cancellation.raise_if_cancelled()
            if process.returncode != 0 or not result_path.is_file():
                raise ReaderFailure(f'Reader {kind} exited ({process.returncode}); manual review required')
            with result_path.open('rb') as stream:
                data = stream.read(MAX_RESULT_BYTES + 1)
            if len(data) > MAX_RESULT_BYTES:
                raise ReaderFailure('Reader result exceeds its limit')
            result = json.loads(data)
            if not isinstance(result, dict) or not result.get('ok'):
                raise ReaderFailure(str(result.get('error', 'Invalid reader response'))[:1000])
            return result['value']
        except (OSError, ValueError, KeyError) as exc:
            raise ReaderFailure(f'Reader {kind} could not complete: {exc}') from exc
        finally:
            if close_job:
                close_job()  # Also terminates any orphaned OCR/LibreOffice child.
            elif os.name != 'nt':
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    if process.poll() is None:
                        process.kill()
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
            if process.stdin and not process.stdin.closed:
                process.stdin.close()


def isolated(kind, *, timeout=45):
    """Wrap file-reader APIs, retaining their in-process bodies for the child."""
    def decorate(function):
        @functools.wraps(function)
        def call(path, *args, **kwargs):
            if in_worker():
                return function(path, *args, **kwargs)
            import inspect
            bound = inspect.signature(function).bind(path, *args, **kwargs)
            arguments = dict(bound.arguments)
            arguments.pop(next(iter(arguments)))
            cancellation = arguments.pop('cancellation', None)
            callback = arguments.pop('callback', None)
            if callback:
                callback('Analizando documento en un proceso local aislado…')
            return run_reader(kind, {'path': str(Path(path).resolve()), 'kwargs': arguments},
                              timeout=timeout, cancellation=cancellation)
        return call
    return decorate


def _image_result(image, size):
    from PIL import Image, ImageOps
    if image is None:
        return None
    try:
        normalized = ImageOps.exif_transpose(image).convert('RGB')
        normalized.thumbnail(tuple(size), Image.Resampling.LANCZOS)
        return {'size': normalized.size, 'rgb': base64.b64encode(normalized.tobytes()).decode('ascii')}
    finally:
        image.close()


def decode_image_result(result):
    from PIL import Image
    if result is None:
        return None
    width, height = result['size']
    if not (0 < width <= 2048 and 0 < height <= 2048):
        raise ReaderFailure('Invalid decoded image dimensions')
    raw = base64.b64decode(result['rgb'], validate=True)
    if len(raw) != width * height * 3:
        raise ReaderFailure('Invalid decoded image length')
    return Image.frombytes('RGB', (width, height), raw)


def _dispatch(kind, payload):
    path = Path(payload.get('path', ''))
    kwargs = payload.get('kwargs', {})
    if kind in {'local_fast', 'local_full'}:
        import library_core
        function = library_core.extraer_datos_rapidos if kind == 'local_fast' else library_core.extraer_datos_locales
        return function(path, **kwargs)
    if kind == 'document':
        from .document_readers import extract_document
        return extract_document(path, **kwargs)
    if kind == 'ocr_file':
        from ocr_engine import extraer_texto_documento_ocr
        return extraer_texto_documento_ocr(path, **kwargs)
    if kind in {'cover', 'image_decode', 'remote_cover'}:
        from .cover_service import CoverService
        size = payload['size']
        if len(size) != 2 or not all(isinstance(n, int) and 0 < n <= 2048 for n in size):
            raise ValueError('Invalid thumbnail size')
        if kind == 'remote_cover':
            if set(payload) != {'url', 'size'} or not CoverService._validated_remote_url(payload['url']):
                raise ValueError('Remote cover accepts only an allowlisted URL and thumbnail size')
            image = CoverService(Path('.'), size=size)._fetch_remote(payload['url'])
        elif kind == 'cover':
            image = CoverService(path.parent, size=size)._extract(path)
        else:
            from PIL import Image
            image = Image.open(path)
            if image.width * image.height > 24_000_000:
                raise ValueError('Image pixel limit exceeded')
        return _image_result(image, size)
    if kind == 'probe':
        # No file input: exercised in source and frozen release self-tests.
        return {'isolated': in_worker(), 'pid': os.getpid()}
    raise ValueError('Unknown reader operation')


def _set_posix_limits(memory_mb):
    if os.name == 'nt':
        return
    import resource
    budget = int(memory_mb) * 1024 * 1024
    limits = [(resource.RLIMIT_CORE, 0), (resource.RLIMIT_FSIZE, 64 * 1024 * 1024)]
    if sys.platform != 'darwin':
        limits.insert(0, (resource.RLIMIT_AS, budget))
    for category, requested in limits:
        _, inherited_hard = resource.getrlimit(category)
        effective = requested if inherited_hard == resource.RLIM_INFINITY else min(requested, inherited_hard)
        resource.setrlimit(category, (effective, effective))


def worker_main(request_path):
    global _IN_WORKER
    _IN_WORKER = True
    request_path = Path(request_path)
    ready_path = request_path.parent / 'ready'
    deadline = time.monotonic() + 10
    while not ready_path.is_file():
        if time.monotonic() > deadline:
            return 2
        time.sleep(.025)
    with request_path.open('rb') as stream:
        raw = stream.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        return 2
    request = json.loads(raw)
    output = Path(request['output'])
    try:
        _set_posix_limits(request['memory_mb'])
        value = _dispatch(request['kind'], request['payload'])
        response = json.dumps({'ok': True, 'value': value}, ensure_ascii=True).encode('utf-8')
        if len(response) > MAX_RESULT_BYTES:
            raise ReaderFailure('Reader result exceeds its limit')
    except Exception as exc:
        response = json.dumps({'ok': False, 'error': f'{type(exc).__name__}: {exc}'[:1000]}).encode('utf-8')
    with output.open('xb') as stream:
        stream.write(response)
    return 0

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import uuid
from pathlib import Path
from shutil import which
from typing import Any

import yt_dlp

ROOT = Path(__file__).resolve().parent
DEFAULT_DOWNLOADS = Path.home() / "Videos" / "YouTube Downloads"
SETTINGS_FILE = ROOT / "settings.json"

jobs: dict[str, dict[str, Any]] = {}
jobs_lock = threading.Lock()
handles: dict[str, "JobHandle"] = {}
_save_lock = threading.Lock()
_save_dir: Path | None = None
_ffmpeg_path: str | None = None
TERMINAL = {"done", "error", "stopped", "paused"}


class JobPaused(Exception):
    pass


class JobStopped(Exception):
    pass


class JobHandle:
    def __init__(self) -> None:
        self.pause = threading.Event()
        self.stop = threading.Event()
        self.request: dict[str, Any] = {}
        self.remaining: list[str] = []
        self.next_index = 1
        self.folder: Path | None = None
        self.last_filename: str | None = None
        self.errors: list[str] = []
        self.single_url: str | None = None
        self.outtmpl: str | None = None


def caused_by(exc: BaseException, cls: type[BaseException]) -> bool:
    current: BaseException | None = exc
    seen: set[int] = set()
    while current and id(current) not in seen:
        if isinstance(current, cls):
            return True
        seen.add(id(current))
        current = current.__cause__ or current.__context__
    return False


def cleanup_partials(folder: Path | None) -> None:
    if not folder or not folder.exists():
        return
    for extra in folder.glob("*.part"):
        extra.unlink(missing_ok=True)
    for extra in folder.glob("*.ytdl"):
        extra.unlink(missing_ok=True)


def update_job(job_id: str, **fields: Any) -> None:
    with jobs_lock:
        job = jobs.setdefault(job_id, {})
        job.update(fields)


def get_job(job_id: str) -> dict[str, Any] | None:
    with jobs_lock:
        job = jobs.get(job_id)
        return dict(job) if job else None


def append_error(job_id: str, message: str) -> None:
    handle = handles.get(job_id)
    if handle:
        handle.errors.append(message)
        update_job(job_id, errors=list(handle.errors), error=message)


def _load_save_dir() -> Path:
    try:
        if SETTINGS_FILE.exists():
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            candidate = Path(str(data.get("save_dir", ""))).expanduser()
            if candidate.is_absolute():
                return candidate
    except Exception:
        pass
    return DEFAULT_DOWNLOADS


def get_save_dir() -> Path:
    global _save_dir
    with _save_lock:
        if _save_dir is None:
            _save_dir = _load_save_dir()
        _save_dir.mkdir(parents=True, exist_ok=True)
        return _save_dir


def set_save_dir(path: str | Path) -> Path:
    global _save_dir
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        raise ValueError("Choose a full folder path.")
    candidate.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(
        json.dumps({"save_dir": str(candidate)}, indent=2),
        encoding="utf-8",
    )
    with _save_lock:
        _save_dir = candidate
    return candidate


def native_pick_folder(initial: Path | None = None) -> Path | None:
    start = str(initial or get_save_dir())
    script = (
        "import sys\n"
        "import tkinter as tk\n"
        "from tkinter import filedialog\n"
        "root = tk.Tk()\n"
        "root.withdraw()\n"
        "root.update_idletasks()\n"
        "try:\n"
        "    root.attributes('-topmost', True)\n"
        "except Exception:\n"
        "    pass\n"
        "chosen = filedialog.askdirectory(initialdir=sys.argv[1], title='Choose save folder')\n"
        "print(chosen or '', end='')\n"
    )
    kwargs: dict[str, Any] = {
        "args": [sys.executable, "-c", script, start],
        "capture_output": True,
        "text": True,
        "timeout": 300,
    }
    if sys.platform.startswith("win"):
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    result = subprocess.run(**kwargs)
    text = (result.stdout or "").strip()
    return Path(text) if text else None


def open_save_folder() -> str:
    folder = str(get_save_dir())
    if sys.platform.startswith("win"):
        os.startfile(folder)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", folder])
    else:
        subprocess.Popen(["xdg-open", folder])
    return folder


def ffmpeg_path() -> str | None:
    global _ffmpeg_path
    if _ffmpeg_path is not None:
        return _ffmpeg_path or None

    found = which("ffmpeg")
    if found:
        _ffmpeg_path = str(Path(found).resolve())
        return _ffmpeg_path

    try:
        import imageio_ffmpeg

        bundled = Path(imageio_ffmpeg.get_ffmpeg_exe()).resolve()
        _ffmpeg_path = str(bundled)
        return _ffmpeg_path
    except Exception:
        _ffmpeg_path = ""
        return None


def format_selector(quality: str) -> str:
    height = {
        "best": "",
        "1080p": "[height<=1080]",
        "720p": "[height<=720]",
        "480p": "[height<=480]",
        "360p": "[height<=360]",
    }.get(quality, "")
    return (
        f"bestvideo[ext=mp4]{height}+bestaudio[ext=m4a]/"
        f"bestvideo{height}+bestaudio/"
        f"best[ext=mp4]{height}/"
        f"best{height}"
    )


def base_ydl_opts(extra: dict[str, Any] | None = None) -> dict[str, Any]:
    opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "windowsfilenames": True,
        "overwrites": False,
        "continuedl": True,
        "noplaylist": True,
    }
    loc = ffmpeg_path()
    if loc:
        opts["ffmpeg_location"] = loc
    if extra:
        opts.update(extra)
    return opts


INVALID_FS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_folder_name(name: str) -> str:
    cleaned = INVALID_FS.sub("", name).strip(" .")
    return cleaned[:80] or "Playlist"


def watch_url(video_id: str) -> str:
    if video_id.startswith("http://") or video_id.startswith("https://"):
        return video_id
    return f"https://www.youtube.com/watch?v={video_id}"


def flatten_info(info: dict[str, Any]) -> dict[str, Any]:
    entries = info.get("entries") or []
    is_playlist = info.get("_type") == "playlist" or bool(entries)
    if is_playlist:
        videos = []
        for item in entries:
            if not item or item.get("id") in {None, ""}:
                continue
            video_id = str(item.get("id"))
            videos.append(
                {
                    "id": video_id,
                    "title": item.get("title") or "Untitled",
                    "duration": item.get("duration"),
                    "thumbnail": item.get("thumbnail")
                    or f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
                    "channel": item.get("channel") or item.get("uploader"),
                    "webpage_url": item.get("webpage_url") or watch_url(video_id),
                }
            )
        return {
            "type": "playlist",
            "id": info.get("id"),
            "title": info.get("title") or "Playlist",
            "channel": info.get("channel") or info.get("uploader"),
            "count": len(videos),
            "thumbnail": (videos[0].get("thumbnail") if videos else None),
            "videos": videos,
        }

    return {
        "type": "video",
        "id": info.get("id"),
        "title": info.get("title") or "Untitled",
        "duration": info.get("duration"),
        "thumbnail": info.get("thumbnail"),
        "channel": info.get("channel") or info.get("uploader"),
        "webpage_url": info.get("webpage_url"),
        "width": info.get("width"),
        "height": info.get("height"),
    }


def lookup_info(url: str, playlist: bool = False) -> dict[str, Any]:
    url = url.strip()
    try:
        with yt_dlp.YoutubeDL(
            base_ydl_opts({"extract_flat": "in_playlist", "noplaylist": not playlist})
        ) as ydl:
            info = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as exc:
        raise RuntimeError(str(exc)) from exc
    except Exception as exc:
        raise RuntimeError(f"Could not read that URL: {exc}") from exc

    if not info:
        raise RuntimeError("No video found at that URL.")
    result = flatten_info(info)
    if playlist and result.get("type") != "playlist":
        raise RuntimeError(
            "That link is a single video. In Playlist mode, paste a playlist URL such as youtube.com/playlist?list=…"
        )
    return result


def resolve_mp4(prepared: str | None, last_filename: str | None) -> Path | None:
    for raw in (prepared, last_filename):
        if not raw:
            continue
        path = Path(raw)
        mp4 = path.with_suffix(".mp4")
        if mp4.exists():
            return mp4
        if path.exists():
            return path
    return None


def playlist_entries(url: str) -> tuple[str, list[str]]:
    with yt_dlp.YoutubeDL(
        base_ydl_opts({"extract_flat": "in_playlist", "noplaylist": False})
    ) as ydl:
        info = ydl.extract_info(url, download=False)
    if not info:
        raise RuntimeError("No playlist found at that URL.")
    title = info.get("title") or "Playlist"
    ids = [str(item["id"]) for item in (info.get("entries") or []) if item and item.get("id")]
    if not ids:
        raise RuntimeError("That playlist has no downloadable videos.")
    return title, ids


def download_one(
    job_id: str,
    url: str,
    quality: str,
    outtmpl: str,
    *,
    index: int = 1,
    total: int = 1,
) -> Path | None:
    handle = handles[job_id]
    last_filename: str | None = None

    def hook(d: dict[str, Any]) -> None:
        nonlocal last_filename
        if handle.stop.is_set():
            raise JobStopped()
        if handle.pause.is_set():
            raise JobPaused()
        status = d.get("status")
        name = d.get("filename") or last_filename
        if name:
            last_filename = name
            handle.last_filename = name
        prefix = "Downloading…" if total == 1 else f"Video {index} of {total}"
        if status == "downloading":
            total_bytes = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes") or 0
            file_pct = (downloaded / total_bytes * 100) if total_bytes else 0
            overall = ((index - 1) + min(file_pct, 99.0) / 100) / total * 100
            update_job(
                job_id,
                status="downloading",
                percent=round(min(overall, 99.0), 1),
                message=prefix,
                speed=d.get("_speed_str") or "",
                eta=d.get("_eta_str") or "",
                filename=Path(name).name if name else None,
                current=index,
                total=total,
                errors=list(handle.errors),
            )
        elif status == "finished":
            overall = ((index - 1) + 0.95) / total * 100
            update_job(
                job_id,
                status="processing",
                percent=round(min(overall, 99.0), 1),
                message="Merging video and audio into MP4…"
                if total == 1
                else f"Video {index} of {total} · merging MP4…",
                filename=Path(name).name if name else None,
                current=index,
                total=total,
                errors=list(handle.errors),
            )

    opts = base_ydl_opts(
        {
            "format": format_selector(quality),
            "merge_output_format": "mp4",
            "outtmpl": outtmpl,
            "progress_hooks": [hook],
            "noplaylist": True,
            "postprocessors": [
                {"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"},
            ],
        }
    )
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            prepared = ydl.prepare_filename(info) if info else last_filename
            return resolve_mp4(prepared, last_filename)
    except Exception as exc:
        if handle.stop.is_set() or caused_by(exc, JobStopped):
            raise JobStopped() from exc
        if handle.pause.is_set() or caused_by(exc, JobPaused):
            raise JobPaused() from exc
        raise


def mark_paused(job_id: str, handle: JobHandle, remaining: list[str], index: int, total: int) -> None:
    handle.remaining = remaining
    handle.next_index = index
    update_job(
        job_id,
        status="paused",
        message="Paused. Press Resume to continue.",
        current=index,
        total=total,
        errors=list(handle.errors),
    )


def mark_stopped(job_id: str, handle: JobHandle) -> None:
    cleanup_partials(handle.folder or get_save_dir())
    update_job(
        job_id,
        status="stopped",
        message="Stopped.",
        errors=list(handle.errors),
    )


def run_download(job_id: str) -> None:
    handle = handles[job_id]
    req = handle.request
    url = req["url"]
    quality = req["quality"]
    playlist = req["playlist"]
    current = get_job(job_id) or {}
    update_job(
        job_id,
        status="starting",
        percent=current.get("percent", 0),
        message="Preparing download…",
        filename=None,
        current=handle.next_index,
        total=max(len(handle.remaining), 1),
        errors=list(handle.errors),
    )

    try:
        if playlist:
            ids = list(handle.remaining)
            title = req.get("playlist_title")
            if not ids:
                title, ids = playlist_entries(url)
                handle.remaining = ids
                handle.next_index = 1
            folder = handle.folder or (get_save_dir() / safe_folder_name(title or "Playlist"))
            folder.mkdir(parents=True, exist_ok=True)
            handle.folder = folder
            saved: list[str] = []
            total = handle.next_index + len(ids) - 1
            index = handle.next_index
            while ids:
                if handle.stop.is_set():
                    mark_stopped(job_id, handle)
                    return
                if handle.pause.is_set():
                    mark_paused(job_id, handle, ids, index, total)
                    return
                video_id = ids[0]
                outtmpl = str(folder / f"{index:02d} - %(title)s.%(ext)s")
                try:
                    path = download_one(
                        job_id,
                        watch_url(video_id),
                        quality,
                        outtmpl,
                        index=index,
                        total=total,
                    )
                    if path:
                        saved.append(path.name)
                    else:
                        append_error(job_id, f"{video_id}: file was not saved.")
                    ids.pop(0)
                    index += 1
                    handle.remaining = ids
                    handle.next_index = index
                except JobPaused:
                    mark_paused(job_id, handle, ids, index, total)
                    return
                except JobStopped:
                    mark_stopped(job_id, handle)
                    return
                except Exception as exc:
                    append_error(job_id, f"{video_id}: {exc}")
                    ids.pop(0)
                    index += 1
                    handle.remaining = ids
                    handle.next_index = index

            if not saved and handle.errors:
                raise RuntimeError(handle.errors[-1])
            if not saved:
                raise RuntimeError("No videos were saved.")
            extra = f" {len(handle.errors)} skipped." if handle.errors else ""
            update_job(
                job_id,
                status="done",
                percent=100,
                message=f"Saved {len(saved)} of {total} MP4 files with audio.{extra}",
                filename=saved[-1],
                path=str(folder),
                saved=len(saved),
                failed=len(handle.errors),
                current=total,
                total=total,
                errors=list(handle.errors),
            )
            return

        handle.folder = get_save_dir()
        handle.single_url = url
        handle.outtmpl = str(get_save_dir() / "%(title)s.%(ext)s")
        path = download_one(job_id, url, quality, handle.outtmpl)
        update_job(
            job_id,
            status="done",
            percent=100,
            message="Saved as MP4 with audio.",
            filename=path.name if path else None,
            path=str(path) if path else None,
            current=1,
            total=1,
            errors=list(handle.errors),
        )
    except JobPaused:
        mark_paused(job_id, handle, handle.remaining or ([url] if not playlist else []), 1, 1)
    except JobStopped:
        mark_stopped(job_id, handle)
    except Exception as exc:
        append_error(job_id, str(exc))
        update_job(
            job_id,
            status="error",
            message="Download failed.",
            error=str(exc),
            errors=list(handle.errors),
        )


def start_download(
    url: str,
    quality: str = "best",
    playlist: bool = False,
    video_ids: list[str] | None = None,
    playlist_title: str | None = None,
) -> str:
    if not ffmpeg_path():
        raise RuntimeError(
            "ffmpeg is required to save MP4 files with audio. Install ffmpeg and try again."
        )
    job_id = uuid.uuid4().hex
    handle = JobHandle()
    handle.request = {
        "url": url.strip(),
        "quality": quality,
        "playlist": playlist,
        "playlist_title": playlist_title,
    }
    handle.remaining = [vid.strip() for vid in (video_ids or []) if vid and vid.strip()]
    handle.next_index = 1
    handles[job_id] = handle
    update_job(job_id, status="queued", percent=0, message="Queued…", errors=[])
    threading.Thread(target=run_download, args=(job_id,), daemon=True).start()
    return job_id


def pause_job(job_id: str) -> None:
    handle = handles.get(job_id)
    if not handle:
        raise RuntimeError("Unknown download.")
    handle.pause.set()
    update_job(job_id, message="Pausing…")


def stop_job(job_id: str) -> None:
    handle = handles.get(job_id)
    if not handle:
        raise RuntimeError("Unknown download.")
    handle.stop.set()
    handle.pause.clear()
    update_job(job_id, message="Stopping…")


def resume_job(job_id: str) -> None:
    handle = handles.get(job_id)
    job = get_job(job_id)
    if not handle or not job:
        raise RuntimeError("Unknown download.")
    if job.get("status") not in {"paused", "error"}:
        raise RuntimeError("That download is not paused.")
    handle.pause.clear()
    handle.stop.clear()
    update_job(job_id, status="starting", message="Resuming…")
    threading.Thread(target=run_download, args=(job_id,), daemon=True).start()

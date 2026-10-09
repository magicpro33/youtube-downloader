from __future__ import annotations

import base64
import html
import time
from pathlib import Path

import streamlit as st

from downloader import (
    TERMINAL,
    get_job,
    get_save_dir,
    lookup_info,
    native_pick_folder,
    open_save_folder,
    pause_job,
    resume_job,
    set_save_dir,
    start_download,
    stop_job,
)

ROOT = Path(__file__).resolve().parent
LOGO_PATH = ROOT / "static" / "logo.jpg"
HOME_URL = "https://aiupscalellc.netlify.app/"
COMPANY = "AI Upscale LLC"

st.set_page_config(
    page_title="AI Upscale · YouTube Downloader",
    page_icon=str(LOGO_PATH) if LOGO_PATH.exists() else None,
    layout="centered",
    initial_sidebar_state="collapsed",
)

DISCLAIMER = f"""
**LEGAL DISCLAIMER, WAIVER, AND RELEASE OF LIABILITY**

This YouTube downloader is provided by **{COMPANY}** (“Company,” “we,” “us”) solely as a convenience tool. By checking the box below and clicking **I Accept**, you (“User”) agree to all of the following. If you do not agree, do not use this software.

**1. Not affiliated with YouTube.** This tool is not endorsed, sponsored, or affiliated with YouTube, Google LLC, or any of their affiliates. YouTube’s name and trademarks belong to their respective owners.

**2. YouTube’s terms and copyright.** Downloading videos from YouTube may violate YouTube’s Terms of Service and applicable copyright law. You agree to use this tool **only** for content you own, content you have a legal right to download and keep, or content that is otherwise lawfully available for personal archival. You will not use this tool to infringe copyright, circumvent technological protection measures, or obtain content you are not authorized to possess.

**3. You are solely responsible.** You alone are responsible for every URL you paste, every file this app writes to disk, and every way those files are used, copied, shared, or stored. You are solely responsible for complying with YouTube’s terms, copyright law, and all other laws in your jurisdiction.

**4. Assumption of risk.** You understand that use of this software may result in account restrictions, takedown notices, civil or criminal liability, data loss, malware risk from third-party streams, or other harm. You voluntarily assume **all** such risks.

**5. No warranty.** THE SOFTWARE IS PROVIDED “AS IS” AND “AS AVAILABLE,” WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, TITLE, AND NON-INFRINGEMENT. We do not warrant that downloads will succeed, that files will play, or that the software is error-free.

**6. Release and waiver.** TO THE MAXIMUM EXTENT PERMITTED BY LAW, YOU HEREBY IRREVOCABLY RELEASE, WAIVE, AND DISCHARGE {COMPANY.upper()}, ITS OWNERS, OFFICERS, EMPLOYEES, CONTRACTORS, AFFILIATES, AND THE DEVELOPER/OPERATOR OF THIS APPLICATION FROM ANY AND ALL CLAIMS, DAMAGES, LOSSES, COSTS, AND LIABILITIES OF EVERY KIND, WHETHER KNOWN OR UNKNOWN, ARISING OUT OF OR RELATED TO YOUR USE OF THIS SOFTWARE OR ANY FILES OBTAINED WITH IT. THIS INCLUDES DIRECT, INDIRECT, INCIDENTAL, SPECIAL, CONSEQUENTIAL, EXEMPLARY, AND PUNITIVE DAMAGES, AND CLAIMS BY THIRD PARTIES.

**7. Indemnification.** You agree to defend, indemnify, and hold harmless {COMPANY} and the people listed in section 6 from any claim, demand, loss, or expense (including attorneys’ fees) arising from your use of this tool, your downloaded files, or your breach of this disclaimer.

**8. No legal advice.** This notice is a condition of use. It is not legal advice. Local laws vary. If you are unsure of your rights, do not use this software.

**9. Acceptance is required.** You may not use the downloader until you accept this disclaimer. Acceptance is a binding condition of access.
"""


def logo_markup() -> str:
    if not LOGO_PATH.exists():
        return f'<a class="brand-link" href="{HOME_URL}" target="_blank" rel="noopener noreferrer">{COMPANY}</a>'
    b64 = base64.b64encode(LOGO_PATH.read_bytes()).decode("ascii")
    return (
        f'<a class="brand-link" href="{HOME_URL}" target="_blank" rel="noopener noreferrer" '
        f'aria-label="AI Upscale home">'
        f'<img src="data:image/jpeg;base64,{b64}" alt="AI Upscale" />'
        f"</a>"
    )


def inject_css() -> None:
    st.markdown(
        """
<style>
    .stApp { background: #081325; }
    header[data-testid="stHeader"] { background: rgba(8,19,37,0.92); }
    .block-container { padding-top: 1.4rem; max-width: 760px; }
    .brand-link { display: inline-block; margin: 0 0 0.4rem; }
    .brand-link img {
        width: min(280px, 72vw);
        height: auto;
        border-radius: 14px;
        background: #050d1c;
        box-shadow: 0 0 0 1px rgba(240,244,250,0.1);
    }
    .kicker {
        color: #f28217;
        font-size: 12px;
        font-weight: 700;
        letter-spacing: 0.16em;
        text-transform: uppercase;
        margin: 0.6rem 0 0.2rem;
    }
    .disclaimer-box {
        max-height: 320px;
        overflow: auto;
        padding: 1rem 1.1rem;
        border: 1px solid rgba(240,244,250,0.12);
        border-radius: 14px;
        background: #0d1d38;
        color: rgba(255,255,255,0.88);
        font-size: 0.92rem;
        line-height: 1.5;
    }
    .error-readout {
        min-height: 3.2em;
        max-height: 8em;
        overflow: auto;
        padding: 10px 12px;
        border-radius: 10px;
        background: #07101f;
        color: #ffd4d4;
        font: 12px/1.45 ui-monospace, Consolas, monospace;
        white-space: pre-wrap;
        border: 1px solid rgba(240,244,250,0.1);
    }
    .error-readout.empty { color: rgba(255,255,255,0.55); }
    div[data-testid="stMetricValue"] { color: #ffffff; }
</style>
        """,
        unsafe_allow_html=True,
    )


def format_duration(seconds) -> str:
    if seconds in (None, ""):
        return ""
    s = int(round(float(seconds)))
    h, rem = divmod(s, 3600)
    m, r = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{r:02d}"
    return f"{m}:{r:02d}"


def show_brand() -> None:
    st.markdown(logo_markup(), unsafe_allow_html=True)
    st.markdown('<p class="kicker">YouTube downloader</p>', unsafe_allow_html=True)


def show_disclaimer_gate() -> None:
    show_brand()
    st.title("Before you continue")
    st.caption("You must read and accept this disclaimer. The downloader will not load until you do.")
    with st.expander("Legal disclaimer, waiver, and release of liability", expanded=True):
        st.markdown(DISCLAIMER)
    agreed = st.checkbox(
        "I have read this disclaimer in full. I understand it, I accept it, and I release AI Upscale LLC "
        "and the operator of this app from all liability related to my use of this software."
    )
    if st.button("I Accept", type="primary", disabled=not agreed, use_container_width=True):
        st.session_state.disclaimer_accepted = True
        st.rerun()
    st.caption("If you do not accept, close this window. No downloads are possible without acceptance.")


def show_downloader() -> None:
    show_brand()
    st.title("Save videos as MP4")
    st.caption("Choose Video or Playlist, paste the YouTube link, then save MP4 files with audio.")

    errors: list[str] = list(st.session_state.get("errors") or [])

    mode = st.radio("Mode", ["Video", "Playlist"], horizontal=True, label_visibility="collapsed")
    playlist_mode = mode == "Playlist"
    url = st.text_input(
        "Playlist URL" if playlist_mode else "Video URL",
        placeholder=(
            "https://www.youtube.com/playlist?list=…"
            if playlist_mode
            else "https://www.youtube.com/watch?v=…"
        ),
    )

    if st.button("Load playlist" if playlist_mode else "Look up", type="primary"):
        st.session_state.errors = []
        errors = []
        if not url.strip():
            errors.append("Paste a YouTube URL first.")
            st.session_state.errors = errors
        else:
            try:
                with st.spinner("Looking up…"):
                    info = lookup_info(url.strip(), playlist=playlist_mode)
                st.session_state.info = info
                st.session_state.url = url.strip()
            except Exception as exc:
                st.session_state.info = None
                errors.append(str(exc))
                st.session_state.errors = errors

    info = st.session_state.get("info")
    if info:
        left, right = st.columns([1, 2])
        with left:
            if info.get("thumbnail"):
                st.image(info["thumbnail"], use_container_width=True)
        with right:
            st.caption(info.get("type", "video").upper())
            st.subheader(info.get("title") or "Untitled")
            st.write(info.get("channel") or "")
            if info.get("type") == "playlist":
                st.write(f"{info.get('count', 0)} videos · each saved as an MP4 with audio")
            else:
                bits = [format_duration(info.get("duration"))]
                if info.get("height"):
                    bits.append(f"{info['height']}p source")
                st.write(" · ".join(b for b in bits if b))

        selected_ids: list[str] = []
        if info.get("type") == "playlist":
            videos = info.get("videos") or []
            labels = [f"{i + 1}. {v.get('title') or 'Untitled'}" for i, v in enumerate(videos)]
            chosen = st.multiselect("Videos to download", labels, default=labels)
            lookup = {labels[i]: videos[i]["id"] for i in range(len(videos))}
            selected_ids = [lookup[label] for label in chosen if label in lookup]
            st.caption(f"{len(selected_ids)} of {len(videos)} selected")
        quality = st.radio("Quality", ["best", "1080p", "720p", "480p", "360p"], horizontal=True)

        job_id = st.session_state.get("job_id")
        job = get_job(job_id) if job_id else None
        status = (job or {}).get("status")
        running = status in {"queued", "starting", "downloading", "processing", "pausing", "stopping"}
        paused = status == "paused"

        c1, c2, c3 = st.columns(3)
        with c1:
            download_clicked = st.button(
                "Download MP4" if info.get("type") != "playlist" else f"Download {len(selected_ids) or 0} videos",
                type="primary",
                disabled=running or (info.get("type") == "playlist" and not selected_ids),
                use_container_width=True,
            )
        with c2:
            if paused:
                resume_clicked = st.button("Resume", use_container_width=True)
                pause_clicked = False
            else:
                pause_clicked = st.button("Pause", disabled=not running, use_container_width=True)
                resume_clicked = False
        with c3:
            stop_clicked = st.button("Stop", disabled=not (running or paused), use_container_width=True)

        if download_clicked:
            st.session_state.errors = []
            try:
                st.session_state.job_id = start_download(
                    url=st.session_state.get("url") or url.strip(),
                    quality=quality,
                    playlist=info.get("type") == "playlist",
                    video_ids=selected_ids,
                    playlist_title=info.get("title"),
                )
                st.rerun()
            except Exception as exc:
                errors.append(str(exc))
                st.session_state.errors = errors

        if pause_clicked and job_id:
            try:
                pause_job(job_id)
                st.rerun()
            except Exception as exc:
                errors.append(str(exc))
                st.session_state.errors = errors

        if resume_clicked and job_id:
            try:
                resume_job(job_id)
                st.rerun()
            except Exception as exc:
                errors.append(str(exc))
                st.session_state.errors = errors

        if stop_clicked and job_id:
            try:
                stop_job(job_id)
                st.rerun()
            except Exception as exc:
                errors.append(str(exc))
                st.session_state.errors = errors

        if job:
            percent = float(job.get("percent") or 0) / 100.0
            st.progress(min(max(percent, 0.0), 1.0))
            parts = [job.get("message") or job.get("status") or ""]
            if job.get("speed"):
                parts.append(str(job["speed"]))
            if job.get("eta"):
                parts.append(f"ETA {job['eta']}")
            if job.get("filename"):
                parts.append(str(job["filename"]))
            st.caption(" · ".join(p for p in parts if p))
            for item in job.get("errors") or []:
                if item not in errors:
                    errors.append(item)
            st.session_state.errors = errors
            if status not in TERMINAL:
                time.sleep(0.4)
                st.rerun()

    st.markdown("---")
    st.subheader("Save folder")
    if "save_dir_input" not in st.session_state:
        st.session_state.save_dir_input = str(get_save_dir())
    folder_col, browse_col, open_col = st.columns([3, 1, 1])
    with folder_col:
        st.text_input("Save folder path", key="save_dir_input", label_visibility="collapsed")
    with browse_col:
        if st.button("Browse", use_container_width=True):
            chosen = native_pick_folder()
            if chosen:
                set_save_dir(chosen)
                st.session_state.save_dir_input = str(chosen)
                st.rerun()
    with open_col:
        if st.button("Open", use_container_width=True):
            try:
                path_value = (st.session_state.save_dir_input or "").strip()
                if path_value:
                    set_save_dir(path_value)
                    st.session_state.save_dir_input = str(get_save_dir())
                open_save_folder()
            except Exception as exc:
                errors.append(str(exc))
                st.session_state.errors = errors

    st.caption("Downloads, including playlist folders, go here.")

    st.markdown("---")
    st.markdown('<p class="kicker">Error readout</p>', unsafe_allow_html=True)
    text = html.escape("\n".join(errors)) if errors else "No errors."
    css_class = "error-readout" if errors else "error-readout empty"
    st.markdown(f'<div class="{css_class}">{text}</div>', unsafe_allow_html=True)


inject_css()
if not st.session_state.get("disclaimer_accepted"):
    show_disclaimer_gate()
    st.stop()

if "save_dir" not in st.session_state:
    st.session_state.save_dir = str(get_save_dir())
if "errors" not in st.session_state:
    st.session_state.errors = []

show_downloader()

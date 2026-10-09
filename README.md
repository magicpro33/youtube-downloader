# AI Upscale YouTube Downloader

A Streamlit app that saves YouTube videos as **MP4 files with audio**.

You must accept the on-screen liability disclaimer before the downloader will load. Use this only for videos you own or have the right to download.

## Run

Double-click `run.bat`, or from this folder:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Then open [http://127.0.0.1:8501](http://127.0.0.1:8501).

## What it does

1. Accept the disclaimer
2. Paste a YouTube video or playlist URL
3. Pick a quality and save folder
4. Download a merged MP4 (video + audio)

Pause and Stop are available while a download is running.

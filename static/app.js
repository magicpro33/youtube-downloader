const form = document.getElementById("lookup-form");
const urlInput = document.getElementById("url");
const lookupBtn = document.getElementById("lookup-btn");
const preview = document.getElementById("preview");
const thumb = document.getElementById("thumb");
const kind = document.getElementById("kind");
const title = document.getElementById("title");
const channel = document.getElementById("channel");
const details = document.getElementById("details");
const downloadBtn = document.getElementById("download-btn");
const pauseBtn = document.getElementById("pause-btn");
const stopBtn = document.getElementById("stop-btn");
const progressWrap = document.getElementById("progress-wrap");
const progressFill = document.getElementById("progress-fill");
const progressText = document.getElementById("progress-text");
const errorLog = document.getElementById("error-log");
const saveDirInput = document.getElementById("save-dir");
const saveStatus = document.getElementById("save-status");
const browseFolder = document.getElementById("browse-folder");
const openFolder = document.getElementById("open-folder");
const playlistWrap = document.getElementById("playlist-wrap");
const playlistVideos = document.getElementById("playlist-videos");
const selectAll = document.getElementById("select-all");
const selectedCount = document.getElementById("selected-count");
const modeVideo = document.getElementById("mode-video");
const modePlaylist = document.getElementById("mode-playlist");
const urlLabel = document.getElementById("url-label");
const modeHint = document.getElementById("mode-hint");

let current = null;
let downloading = false;
let playlistMode = false;
let activeJobId = null;
const errorLines = [];

function setErrorLog(lines) {
  const items = (lines || []).filter(Boolean);
  errorLog.textContent = items.length ? items.join("\n") : "No errors.";
  errorLog.classList.toggle("is-empty", items.length === 0);
}

function addError(message) {
  if (!message) return;
  if (!errorLines.includes(message)) errorLines.push(message);
  setErrorLog(errorLines);
}

function clearErrors() {
  errorLines.length = 0;
  setErrorLog([]);
}

function showError(message) {
  addError(message);
}

function setTransport({ running = false, canResume = false } = {}) {
  pauseBtn.disabled = !running && !canResume;
  stopBtn.disabled = !running && !canResume;
  pauseBtn.textContent = canResume ? "Resume" : "Pause";
}

function formatDuration(seconds) {
  if (!seconds && seconds !== 0) return "";
  const s = Math.round(Number(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const r = s % 60;
  if (h) return `${h}:${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}`;
  return `${m}:${String(r).padStart(2, "0")}`;
}

function selectedQuality() {
  const picked = document.querySelector('input[name="quality"]:checked');
  return picked ? picked.value : "best";
}

function selectedVideoIds() {
  return [...document.querySelectorAll(".video-pick:checked")].map((el) => el.value);
}

function updateSelectedCount() {
  if (!current || current.type !== "playlist") return;
  const picked = selectedVideoIds().length;
  const total = current.videos.length;
  selectedCount.textContent = `${picked} of ${total} selected`;
  selectAll.checked = picked === total && total > 0;
  downloadBtn.textContent = picked === 1 ? "Download 1 video" : `Download ${picked} videos`;
  downloadBtn.disabled = downloading || picked === 0;
}

function renderPlaylist(videos) {
  playlistVideos.innerHTML = "";
  videos.forEach((video, index) => {
    const item = document.createElement("li");
    const label = document.createElement("label");
    const box = document.createElement("input");
    box.type = "checkbox";
    box.className = "video-pick";
    box.value = video.id;
    box.checked = true;
    const num = document.createElement("span");
    num.className = "num";
    num.textContent = String(index + 1);
    const name = document.createElement("span");
    name.className = "vtitle";
    name.textContent = video.title || "Untitled";
    const dur = document.createElement("span");
    dur.className = "vdur";
    dur.textContent = formatDuration(video.duration);
    label.append(box, num, name, dur);
    item.append(label);
    playlistVideos.append(item);
  });
  playlistWrap.hidden = false;
  selectAll.checked = true;
  updateSelectedCount();
}

function looksLikePlaylist(url) {
  const value = (url || "").toLowerCase();
  return value.includes("list=") || value.includes("/playlist");
}

function setMode(nextPlaylist) {
  playlistMode = nextPlaylist;
  modeVideo.classList.toggle("is-active", !playlistMode);
  modePlaylist.classList.toggle("is-active", playlistMode);
  modeVideo.setAttribute("aria-pressed", String(!playlistMode));
  modePlaylist.setAttribute("aria-pressed", String(playlistMode));
  urlLabel.textContent = playlistMode ? "Playlist URL" : "Video URL";
  urlInput.placeholder = playlistMode
    ? "https://www.youtube.com/playlist?list=…"
    : "https://www.youtube.com/watch?v=…";
  modeHint.textContent = playlistMode
    ? "Paste a playlist link, or a video link that includes list=. Then pick which videos to save."
    : "Paste one video link. To grab a whole list, switch to Playlist.";
  lookupBtn.textContent = playlistMode ? "Load playlist" : "Look up";
}

function applyModeFromUrl() {
  const url = urlInput.value.trim();
  if (url && looksLikePlaylist(url) && !playlistMode) setMode(true);
}

function showSaveStatus(message, isError = false) {
  saveStatus.textContent = message;
  saveStatus.classList.toggle("error", isError);
}

async function loadStatus() {
  const res = await fetch("/api/status");
  const data = await res.json();
  saveDirInput.value = data.downloads || "";
  showSaveStatus("Downloads, including playlist folders, go here.");
}

async function applySaveDir() {
  const path = saveDirInput.value.trim();
  if (!path) {
    showSaveStatus("Enter a folder path or click Browse.", true);
    return;
  }
  const res = await fetch("/api/save-dir", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Could not use that folder.");
  saveDirInput.value = data.path;
  showSaveStatus(`Saving to ${data.path}`);
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearErrors();
  preview.hidden = true;
  progressWrap.hidden = true;
  lookupBtn.disabled = true;
  lookupBtn.textContent = "Looking up…";

  try {
    const res = await fetch("/api/info", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: urlInput.value.trim(), playlist: playlistMode }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Could not read that URL.");

    current = data;
    thumb.src = data.thumbnail || "";
    thumb.hidden = !data.thumbnail;
    title.textContent = data.title;
    channel.textContent = data.channel || "";
    playlistWrap.hidden = true;
    playlistVideos.innerHTML = "";
    downloadBtn.disabled = false;
    if (data.type === "playlist") {
      kind.textContent = "Playlist";
      details.textContent = `${data.count} videos · each saved as an MP4 with audio`;
      renderPlaylist(data.videos || []);
    } else {
      kind.textContent = "Video";
      const bits = [formatDuration(data.duration)];
      if (data.height) bits.push(`${data.height}p source`);
      details.textContent = bits.filter(Boolean).join(" · ");
      downloadBtn.textContent = "Download MP4";
    }
    preview.hidden = false;
  } catch (err) {
    showError(err.message);
  } finally {
    lookupBtn.disabled = false;
    lookupBtn.textContent = playlistMode ? "Load playlist" : "Look up";
  }
});

function finishTransport() {
  downloading = false;
  setTransport({ running: false, canResume: false });
  downloadBtn.disabled = current && current.type === "playlist" && selectedVideoIds().length === 0;
  if (current && current.type === "playlist") updateSelectedCount();
  else if (current) downloadBtn.disabled = false;
}

function listenToJob(jobId) {
  activeJobId = jobId;
  const stream = new EventSource(`/api/progress/${jobId}`);
  stream.onmessage = (event) => {
    const job = JSON.parse(event.data);
    progressFill.style.width = `${job.percent || 0}%`;
    if (Array.isArray(job.errors)) {
      job.errors.forEach(addError);
    }
    if (job.status === "done") {
      progressText.textContent = job.message || (
        job.filename
          ? `Saved as MP4 with audio: ${job.filename}`
          : "Saved as MP4 with audio."
      );
      stream.close();
      finishTransport();
      return;
    }
    if (job.status === "paused") {
      progressText.textContent = job.message || "Paused.";
      stream.close();
      downloading = false;
      setTransport({ running: false, canResume: true });
      downloadBtn.disabled = true;
      return;
    }
    if (job.status === "stopped") {
      progressText.textContent = job.message || "Stopped.";
      stream.close();
      finishTransport();
      return;
    }
    if (job.status === "error") {
      progressText.textContent = "Download failed.";
      addError(job.error || "Download failed.");
      stream.close();
      finishTransport();
      return;
    }
    const parts = [job.message || job.status];
    if (job.speed) parts.push(job.speed);
    if (job.eta) parts.push(`ETA ${job.eta}`);
    if (job.filename) parts.push(job.filename);
    progressText.textContent = parts.join(" · ");
  };
  stream.onerror = () => {
    stream.close();
    if (downloading) {
      downloading = false;
      setTransport({ running: false, canResume: false });
      downloadBtn.disabled = false;
    }
  };
}

downloadBtn.addEventListener("click", async () => {
  if (!current || downloading) return;
  if (current.type === "playlist" && selectedVideoIds().length === 0) {
    showError("Select at least one video from the playlist.");
    return;
  }
  clearErrors();
  downloading = true;
  downloadBtn.disabled = true;
  setTransport({ running: true });
  progressWrap.hidden = false;
  progressFill.style.width = "4%";
  progressText.textContent = "Starting download…";

  try {
    const res = await fetch("/api/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: urlInput.value.trim(),
        quality: selectedQuality(),
        playlist: current.type === "playlist",
        video_ids: current.type === "playlist" ? selectedVideoIds() : [],
        playlist_title: current.type === "playlist" ? current.title : null,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Download failed to start.");
    listenToJob(data.job_id);
  } catch (err) {
    finishTransport();
    showError(err.message);
  }
});

pauseBtn.addEventListener("click", async () => {
  if (!activeJobId) return;
  const resume = pauseBtn.textContent === "Resume";
  try {
    if (resume) {
      downloading = true;
      setTransport({ running: true });
      progressText.textContent = "Resuming…";
      const res = await fetch(`/api/jobs/${activeJobId}/resume`, { method: "POST" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Could not resume.");
      listenToJob(activeJobId);
      return;
    }
    const res = await fetch(`/api/jobs/${activeJobId}/pause`, { method: "POST" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Could not pause.");
    progressText.textContent = "Pausing…";
  } catch (err) {
    showError(err.message);
  }
});

stopBtn.addEventListener("click", async () => {
  if (!activeJobId) return;
  try {
    const res = await fetch(`/api/jobs/${activeJobId}/stop`, { method: "POST" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Could not stop.");
    progressText.textContent = "Stopping…";
  } catch (err) {
    showError(err.message);
  }
});

selectAll.addEventListener("change", () => {
  document.querySelectorAll(".video-pick").forEach((box) => {
    box.checked = selectAll.checked;
  });
  updateSelectedCount();
});

playlistVideos.addEventListener("change", (event) => {
  if (event.target.classList.contains("video-pick")) {
    updateSelectedCount();
  }
});

modeVideo.addEventListener("click", () => setMode(false));
modePlaylist.addEventListener("click", () => setMode(true));
urlInput.addEventListener("input", applyModeFromUrl);
urlInput.addEventListener("paste", () => setTimeout(applyModeFromUrl, 0));

browseFolder.addEventListener("click", async () => {
  browseFolder.disabled = true;
  browseFolder.textContent = "Choose a folder…";
  try {
    const res = await fetch("/api/pick-folder", { method: "POST" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Could not open the folder picker.");
    if (data.cancelled) {
      showSaveStatus("Folder picker was cancelled.");
      return;
    }
    saveDirInput.value = data.path;
    showSaveStatus(`Saving to ${data.path}`);
  } catch (err) {
    showSaveStatus(err.message, true);
  } finally {
    browseFolder.disabled = false;
    browseFolder.textContent = "Browse";
  }
});

saveDirInput.addEventListener("keydown", async (event) => {
  if (event.key !== "Enter") return;
  event.preventDefault();
  try {
    await applySaveDir();
  } catch (err) {
    showSaveStatus(err.message, true);
  }
});

saveDirInput.addEventListener("blur", async () => {
  if (!saveDirInput.value.trim()) return;
  try {
    await applySaveDir();
  } catch (err) {
    showSaveStatus(err.message, true);
  }
});

openFolder.addEventListener("click", async () => {
  try {
    await applySaveDir();
  } catch (err) {
    showSaveStatus(err.message, true);
    return;
  }
  await fetch("/api/open-folder", { method: "POST" });
});

setErrorLog([]);
loadStatus().catch(() => {
  showSaveStatus("Could not read the save folder.", true);
});

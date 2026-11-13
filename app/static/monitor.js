(() => {
  const panels = {
    loading: document.getElementById("loading-panel"),
    error: document.getElementById("error-panel"),
    empty: document.getElementById("empty-panel"),
    data: document.getElementById("data-panel"),
  };
  const consent = document.getElementById("privacy-consent");
  const startButton = document.getElementById("start-button");
  const video = document.getElementById("video");
  const audio = [
    document.getElementById("audio-level-1"),
    document.getElementById("audio-level-2"),
    document.getElementById("audio-level-3"),
  ];
  let latestStatus = null;
  let lastAlertSequence = 0;
  let requestFailed = false;

  function showPanel(name) {
    for (const [key, panel] of Object.entries(panels)) {
      panel.hidden = key !== name;
    }
  }

  function showError(message) {
    document.getElementById("error-message").textContent = message;
    showPanel("error");
  }

  function primeAudio() {
    for (const sound of audio) {
      sound.muted = true;
      const playback = sound.play();
      if (playback) {
        playback.then(() => {
          sound.pause();
          sound.currentTime = 0;
          sound.muted = false;
        }).catch(() => {
          sound.muted = false;
        });
      } else {
        sound.muted = false;
      }
    }
  }

  function stopSounds() {
    for (const sound of audio) {
      sound.pause();
      sound.currentTime = 0;
    }
  }

  function playAlert(status) {
    const level = status.alert_level;
    if (!level || !status.alert_sound_enabled) {
      stopSounds();
      return;
    }
    const sound = audio[level - 1];
    if (level === 3 && !sound.paused) return;
    stopSounds();
    sound.currentTime = 0;
    sound.play().catch(() => {
      document.getElementById("status-message").textContent =
        `${status.message} (Trình duyệt chưa cho phép phát âm thanh.)`;
    });
    if (navigator.vibrate) {
      const patterns = { 1: [100], 2: [250, 100, 250], 3: [500, 150, 500] };
      navigator.vibrate(patterns[level]);
    }
  }

  function updateMetrics(status) {
    const format = (value, digits = 3, suffix = "") =>
      Number.isFinite(value) ? `${value.toFixed(digits)}${suffix}` : "—";
    document.getElementById("ear-value").textContent = format(status.ear);
    document.getElementById("mar-value").textContent = format(status.mar);
    document.getElementById("perclos-value").textContent =
      format(status.perclos, 1, "%");
    document.getElementById("pitch-value").textContent =
      format(status.pitch, 1, "°");
    document.getElementById("fps-value").textContent = format(status.fps, 1);
  }

  function render(status) {
    latestStatus = status;
    requestFailed = false;
    if (status.error) {
      stopSounds();
      video.removeAttribute("src");
      showError(status.error);
      return;
    }
    if (!status.session_started || !status.running) {
      stopSounds();
      showPanel("empty");
      return;
    }

    document.body.dataset.state = status.state || "UNKNOWN";
    document.getElementById("state-label").textContent = status.state_label;
    document.getElementById("status-message").textContent = status.message || "";
    document.getElementById("level-badge").hidden = !status.alert_level;
    document.getElementById("level-badge").textContent =
      status.alert_level ? `CẢNH BÁO MỨC ${status.alert_level}` : "";
    document.getElementById("calibration-panel").hidden = !status.calibrating;
    document.getElementById("countdown").textContent =
      Math.ceil(status.calibration_remaining || 0);
    const partialNote = document.getElementById("partial-note");
    partialNote.hidden = !status.partial_data;
    partialNote.textContent = status.partial_reason
      ? `Dữ liệu một phần — ${status.partial_reason.toLowerCase()}.`
      : "Dữ liệu một phần — một số chỉ số không khả dụng.";
    document.getElementById("ack-button").hidden =
      !status.alert_level || !status.running;
    document.getElementById("stop-button").disabled = !status.running;
    updateMetrics(status);
    showPanel("data");

    if (status.running) {
      video.hidden = false;
      document.getElementById("video-placeholder").hidden = true;
      updateVideoUrl();
    } else {
      video.hidden = true;
      video.removeAttribute("src");
      document.getElementById("video-placeholder").hidden = false;
    }
    if (status.alert_sequence > lastAlertSequence) {
      lastAlertSequence = status.alert_sequence;
      playAlert(status);
    } else if (!status.alert_level || !status.alert_sound_enabled) {
      stopSounds();
    }
  }

  async function fetchStatus() {
    const response = await fetch("/api/status", { cache: "no-store" });
    if (!response.ok) throw new Error(`Lỗi máy chủ (${response.status}).`);
    render(await response.json());
  }

  async function post(path, payload = null) {
    const options = { method: "POST" };
    if (payload) {
      options.headers = { "Content-Type": "application/json" };
      options.body = JSON.stringify(payload);
    }
    const response = await fetch(path, options);
    const status = await response.json();
    if (!response.ok && response.status !== 202) {
      throw new Error(status.error || status.message || `Lỗi máy chủ (${response.status}).`);
    }
    render(status);
  }

  function updateVideoUrl() {
    const overlay = document.getElementById("overlay-toggle").checked ? "1" : "0";
    const nextUrl = `/video_feed?overlay=${overlay}`;
    if (!video.src.endsWith(nextUrl)) video.src = nextUrl;
  }

  consent.addEventListener("change", () => {
    startButton.disabled = !consent.checked;
  });
  document.getElementById("start-button").addEventListener("click", async () => {
    primeAudio();
    startButton.disabled = true;
    try {
      await post("/api/start", { consent: true });
    } catch (error) {
      showError(error.message);
    } finally {
      startButton.disabled = !consent.checked;
    }
  });
  document.getElementById("stop-button").addEventListener("click", async (event) => {
    event.currentTarget.disabled = true;
    stopSounds();
    try {
      await post("/api/stop");
    } catch (error) {
      showError(error.message);
    }
  });
  document.getElementById("ack-button").addEventListener("click", async () => {
    try {
      await post("/api/ack");
    } catch (error) {
      showError(error.message);
    }
  });
  document.getElementById("retry-button").addEventListener("click", async () => {
    showPanel("loading");
    try {
      if (latestStatus && latestStatus.error) {
        await post("/api/start", { consent: true });
      } else {
        await fetchStatus();
      }
    } catch (error) {
      showError(error.message);
    }
  });
  document.getElementById("overlay-toggle").addEventListener("change", updateVideoUrl);

  async function poll() {
    try {
      await fetchStatus();
    } catch (error) {
      if (!requestFailed) showError(error.message);
      requestFailed = true;
    }
  }

  showPanel("loading");
  poll();
  window.setInterval(poll, 500);
})();

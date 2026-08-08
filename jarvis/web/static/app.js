/* JARVIS web UI — WebSocket state mirror, orb animation, weather + system stats. */
(function () {
  "use strict";

  const STATE_CAPTIONS = {
    IDLE: "Idle",
    WAKE_DETECTED: "Wake word detected",
    LISTENING: "Listening",
    TRANSCRIBING: "Transcribing",
    THINKING: "Thinking",
    SPEAKING: "Speaking",
    AWAITING_CONFIRM: "Awaiting confirmation",
  };

  const orbWrap = document.getElementById("orb-wrap");
  const stateText = document.getElementById("state-text");
  const conn = document.getElementById("conn");
  const connLabel = document.getElementById("conn-label");
  const transcriptScroll = document.getElementById("transcript-scroll");
  const transcriptEmpty = document.getElementById("transcript-empty");

  let ws = null;
  let reconnectDelay = 1000;
  const maxLines = 60;

  /* ---------- Orb state ---------- */
  function setState(state) {
    if (!STATE_CAPTIONS[state]) state = "IDLE";
    orbWrap.dataset.state = state;
    stateText.textContent = STATE_CAPTIONS[state];
  }

  /* ---------- Connection ---------- */
  function setConn(ok, label) {
    conn.classList.toggle("ok", ok);
    connLabel.textContent = label;
  }

  function connect() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${proto}://${location.host}/ws`);

    ws.onopen = () => {
      setConn(true, "connected");
      reconnectDelay = 1000;
    };

    ws.onmessage = (ev) => {
      let msg;
      try { msg = JSON.parse(ev.data); } catch { return; }
      handleMessage(msg);
    };

    ws.onclose = () => {
      setConn(false, "reconnecting…");
      setTimeout(connect, reconnectDelay);
      reconnectDelay = Math.min(reconnectDelay * 1.6, 10000);
    };

    ws.onerror = () => ws.close();
  }

  function handleMessage(msg) {
    switch (msg.event) {
      case "snapshot":
        if (msg.state) setState(msg.state);
        if (msg.last_user) addLine("user", msg.last_user);
        if (msg.last_jarvis) addLine("jarvis", msg.last_jarvis);
        break;
      case "state":
        setState(msg.state);
        break;
      case "user_text":
        addLine("user", msg.text || "");
        break;
      case "jarvis_text":
        addLine("jarvis", msg.text || "");
        break;
    }
  }

  /* ---------- Transcript ---------- */
  function addLine(who, text) {
    if (!text || !text.trim()) return;
    transcriptEmpty.style.display = "none";
    const line = document.createElement("div");
    line.className = `line ${who}`;
    const whoEl = document.createElement("span");
    whoEl.className = "who";
    whoEl.textContent = who === "user" ? "YOU" : "JARVIS";
    const txtEl = document.createElement("span");
    txtEl.className = "txt";
    txtEl.textContent = text.trim();
    line.appendChild(whoEl);
    line.appendChild(txtEl);
    transcriptScroll.appendChild(line);

    while (transcriptScroll.children.length > maxLines) {
      transcriptScroll.removeChild(transcriptScroll.firstChild);
    }
    transcriptScroll.scrollTop = transcriptScroll.scrollHeight;
  }

  /* ---------- System stats ---------- */
  function fmtBytes(n) {
    const units = ["B", "KB", "MB", "GB", "TB"];
    let i = 0;
    while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
    return `${n.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
  }

  function barClass(pct) {
    if (pct >= 90) return "crit";
    if (pct >= 70) return "warn";
    return "";
  }

  async function refreshSystem() {
    try {
      const r = await fetch("/api/system");
      const d = await r.json();
      const cpu = d.cpu_percent, ram = d.ram.percent, disk = d.disk.percent;
      document.getElementById("cpu-label").textContent = `${cpu.toFixed(0)}%`;
      document.getElementById("ram-label").textContent = `${ram.toFixed(0)}%`;
      document.getElementById("disk-label").textContent = `${disk.toFixed(0)}%`;

      const cpuBar = document.getElementById("cpu-bar");
      const ramBar = document.getElementById("ram-bar");
      const diskBar = document.getElementById("disk-bar");
      cpuBar.style.width = `${cpu}%`; cpuBar.className = `bar-fill ${barClass(cpu)}`;
      ramBar.style.width = `${ram}%`; ramBar.className = `bar-fill ${barClass(ram)}`;
      diskBar.style.width = `${disk}%`; diskBar.className = `bar-fill ${barClass(disk)}`;

      document.getElementById("sys-foot").textContent =
        `${d.cpu_count} cores` +
        (d.cpu_freq_mhz ? ` · ${Math.round(d.cpu_freq_mhz)} MHz` : "") +
        ` · RAM ${fmtBytes(d.ram.used)} / ${fmtBytes(d.ram.total)}` +
        ` · Disk ${fmtBytes(d.disk.used)} / ${fmtBytes(d.disk.total)}`;
    } catch {
      document.getElementById("sys-foot").textContent = "system stats unavailable";
    }
  }

  /* ---------- Weather ---------- */
  async function refreshWeather() {
    const body = document.getElementById("weather-body");
    try {
      const r = await fetch("/api/weather");
      const d = await r.json();
      if (d.error) {
        body.querySelector("#weather-desc").textContent = d.desc || "unavailable";
        return;
      }
      document.getElementById("weather-icon").src = d.icon;
      document.getElementById("weather-temp").textContent = `${Math.round(d.temp_c)}°C`;
      document.getElementById("weather-loc").textContent =
        `${d.location}${d.region ? ", " + d.region : ""}`;
      document.getElementById("weather-desc").textContent = d.desc;
      document.getElementById("weather-feels").textContent = `Feels like ${Math.round(d.feels_like_c)}°C`;
      document.getElementById("weather-hum").textContent = `Humidity ${d.humidity}%`;
      document.getElementById("weather-wind").textContent = `Wind ${d.wind_dir} ${d.wind_kph} km/h`;
    } catch {
      document.getElementById("weather-desc").textContent = "weather unavailable";
    }
  }

  /* ---------- Boot ---------- */
  connect();
  refreshSystem();
  refreshWeather();
  setInterval(refreshSystem, 4000);
  setInterval(refreshWeather, 600000);
})();

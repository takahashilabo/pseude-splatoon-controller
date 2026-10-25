// Splatoon Dummy Bot Frontend Client

let isRunning = false;
let pollingInterval = null;

// DOM Elements
const btnMainToggle = document.getElementById("btnMainToggle");
const mainBtnText = document.getElementById("mainBtnText");
const mainBtnSub = document.getElementById("mainBtnSub");
const modeBanner = document.getElementById("modeBanner");
const modeText = document.getElementById("modeText");
const controllerStatus = document.getElementById("controllerStatus");
const deviceStatus = document.getElementById("deviceStatus");
const actionName = document.getElementById("actionName");
const elapsedTime = document.getElementById("elapsedTime");
const lStickDot = document.getElementById("lStickDot");
const rStickDot = document.getElementById("rStickDot");
const btnZR = document.getElementById("btnZR");
const btnZL = document.getElementById("btnZL");
const btnB = document.getElementById("btnB");
const playStyleSelect = document.getElementById("playStyleSelect");
const timerSelect = document.getElementById("timerSelect");
const btnSwitchConn = document.getElementById("btnSwitchConn");
const btnShutdown = document.getElementById("btnShutdown");

let outputMuted = false;

function formatTime(sec) {
  const m = Math.floor(sec / 60).toString().padStart(2, '0');
  const s = Math.floor(sec % 60).toString().padStart(2, '0');
  return `${m}:${s}`;
}

async function fetchStatus() {
  try {
    const res = await fetch("/api/status");
    if (!res.ok) return;
    const data = await res.json();
    updateUI(data);
  } catch (err) {
    console.error("Status fetch failed:", err);
  }
}

function updateUI(data) {
  isRunning = data.is_running;

  // デバイスステータスバッジ (ラズパイ→Switch側。この接続方式は常にBluetooth固定で、
  // 本物のプロコン→ラズパイの接続方式(有線/BT)とは無関係)
  if (data.is_mock) {
    deviceStatus.textContent = "シミュレーション (Mock)";
    deviceStatus.className = "status-badge mock";
  } else if (data.switch_paired) {
    deviceStatus.textContent = "ラズパイ→Switch: 接続中";
    deviceStatus.className = "status-badge connected";
  } else {
    deviceStatus.textContent = "ラズパイ→Switch: ペアリング待ち";
    deviceStatus.className = "status-badge mock";
  }

  // Switchへの入力送信 一時停止/再開ボタンの表示切り替え
  // (Bluetooth接続自体は維持したまま、入力送信だけ止める安全な方式)
  outputMuted = !!data.switch_output_muted;
  if (data.is_mock) {
    btnSwitchConn.disabled = true;
    btnSwitchConn.textContent = "Mockモードのため操作不可";
  } else {
    btnSwitchConn.disabled = false;
    btnSwitchConn.textContent = outputMuted ? "再開する" : "一時停止する";
  }

  // 本物のプロコン→ラズパイ側の接続状態バッジ (有線/Bluetoothを明示)
  if (data.controller_connected) {
    const linkLabel = data.controller_link_type === "usb" ? "有線"
      : data.controller_link_type === "bluetooth" ? "Bluetooth"
      : "不明";
    controllerStatus.textContent = `プロコン→ラズパイ: 接続中 (${linkLabel})`;
    controllerStatus.className = "status-badge connected";
  } else {
    controllerStatus.textContent = "プロコン→ラズパイ: 未接続";
    controllerStatus.className = "status-badge mock";
  }

  // 中継モードバナー & メインボタン
  if (isRunning) {
    modeBanner.className = "mode-banner bot";
    modeBanner.innerHTML = '<span class="mode-icon">🤖</span><span>BOT自動操作中 (プロコン遮断中)</span>';

    btnMainToggle.className = "big-power-btn running";
    mainBtnText.textContent = "STOP BOT";
    mainBtnSub.textContent = "タップしてプロコン操作に戻す";
    actionName.textContent = data.action_name || "稼働中";
    actionName.style.color = "var(--neon-yellow)";
    elapsedTime.textContent = formatTime(data.elapsed_sec);
  } else {
    modeBanner.className = "mode-banner passthrough";
    modeBanner.innerHTML = '<span class="mode-icon">🎮</span><span>プロコン中継中 (普段通りプレイ可能)</span>';

    btnMainToggle.className = "big-power-btn stopped";
    mainBtnText.textContent = "START BOT";
    mainBtnSub.textContent = "タップしてダミー操作に切替";
    actionName.textContent = "プロコン操作中 (パススルー)";
    actionName.style.color = "var(--neon-cyan)";
    elapsedTime.textContent = "00:00";
  }

  // スティックのドット位置更新
  const maxOffset = 28;
  if (isRunning) {
    const lx = (data.lx / 100) * maxOffset;
    const ly = (-data.ly / 100) * maxOffset;
    const rx = (data.rx / 100) * maxOffset;
    const ry = (-data.ry / 100) * maxOffset;
    lStickDot.style.transform = `translate(calc(-50% + ${lx}px), calc(-50% + ${ly}px))`;
    rStickDot.style.transform = `translate(calc(-50% + ${rx}px), calc(-50% + ${ry}px))`;

    btnZR.className = data.zr ? "btn-pill active-zr" : "btn-pill";
    btnZL.className = data.zl ? "btn-pill active-zl" : "btn-pill";
    btnB.className = data.b ? "btn-pill active-b" : "btn-pill";
  } else {
    lStickDot.style.transform = "translate(-50%, -50%)";
    rStickDot.style.transform = "translate(-50%, -50%)";
    btnZR.className = "btn-pill";
    btnZL.className = "btn-pill";
    btnB.className = "btn-pill";
  }
}

async function toggleBot() {
  if (isRunning) {
    try {
      await fetch("/api/stop", { method: "POST" });
    } catch (e) {
      console.error(e);
    }
  } else {
    const style = playStyleSelect.value;
    const autoStopSec = parseInt(timerSelect.value, 10);
    try {
      await fetch("/api/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ style: style, auto_stop_sec: autoStopSec })
      });
    } catch (e) {
      console.error(e);
    }
  }
  fetchStatus();
}

function onSettingChange() {
  if (isRunning) {
    const style = playStyleSelect.value;
    const autoStopSec = parseInt(timerSelect.value, 10);
    fetch("/api/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ style: style, auto_stop_sec: autoStopSec })
    });
  }
}

async function toggleSwitchConnection() {
  const endpoint = outputMuted ? "/api/switch/reconnect" : "/api/switch/disconnect";
  btnSwitchConn.disabled = true;
  try {
    await fetch(endpoint, { method: "POST" });
  } catch (e) {
    console.error(e);
  }
  fetchStatus();
}

async function shutdownPi() {
  if (!confirm("ラズパイをシャットダウンします。再度使うには電源を入れ直す必要があります。よろしいですか？")) {
    return;
  }
  btnShutdown.disabled = true;
  btnShutdown.textContent = "シャットダウン中...";
  try {
    await fetch("/api/system/shutdown", { method: "POST" });
  } catch (e) {
    console.error(e);
  }
}

fetchStatus();
pollingInterval = setInterval(fetchStatus, 150);

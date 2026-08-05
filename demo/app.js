const scenarios = {
  vanish: {
    label: "Vanish",
    sublabel: "false negative",
    title: "Vanish",
    headline: "A vehicle disappears from perception.",
    description:
      "The injector suppresses a real detected object. The trajectory hybrid sees the sudden change in the perception/planning relationship.",
    path: "Trajectory hybrid",
    p50: "107.135 ms",
    p99: "131.858 ms",
    features: ["object-count delta", "unmatched previous object", "centroid shift"],
    serviceTitle: "Replay detection only",
    hasServiceEvidence: false,
    serviceDescription:
      "Vanish was detected in all three held-out replays. It was not one of the four integrated safe-stop service trial paths, so this page does not imply an accepted service response for it.",
    serviceBadge: "REPLAY EVIDENCE",
  },
  phantom: {
    label: "Phantom",
    sublabel: "false positive",
    title: "Phantom",
    headline: "A pedestrian appears where none exists.",
    description:
      "The injector inserts a nonexistent object. The trajectory hybrid notices the discontinuity and crosses its frozen anomaly threshold.",
    path: "Trajectory hybrid",
    p50: "104.384 ms",
    p99: "131.168 ms",
    features: ["object-count delta", "centroid shift", "trajectory hybrid"],
    serviceTitle: "Accepted service response: 3 / 3",
    hasServiceEvidence: true,
    serviceDescription:
      "The integrated Arm phantom path produced accepted Autoware safe-stop responses in 3/3 trials. Its p50 fault-to-safe-stop-request time was 9,141.416 ms, so it must not be presented as low-latency safety performance.",
    serviceBadge: "SERVICE RESPONSE EVIDENCE",
  },
  freeze: {
    label: "Freeze",
    sublabel: "stale frames",
    title: "Freeze",
    headline: "Perception repeats a stale frame.",
    description:
      "The source-freshness monitor detects repeated source timestamps. It was first to decide in two of the three held-out replays; the hybrid decided first in the other one.",
    path: "Source freshness (2/3)",
    p50: "168.180 ms",
    p99: "195.799 ms",
    features: ["source age", "two consecutive frames", "hybrid fallback"],
    serviceTitle: "Accepted service response: 3 / 3",
    hasServiceEvidence: true,
    serviceDescription:
      "The source-freshness path received an accepted Autoware safe-stop response in every integrated Arm trial: 101.836 ms p50 fault-to-safe-stop request.",
    serviceBadge: "SERVICE RESPONSE EVIDENCE",
  },
  teleport: {
    label: "Teleport",
    sublabel: "position jump",
    title: "Teleport",
    headline: "A vehicle jumps to an impossible position.",
    description:
      "The injector applies a discontinuous position change. Route-invariant motion features allow the trajectory hybrid to flag the jump without relying on the route's absolute object count.",
    path: "Trajectory hybrid",
    p50: "110.611 ms",
    p99: "132.440 ms",
    features: ["mean displacement", "max displacement", "relative displacement"],
    serviceTitle: "Replay detection only",
    hasServiceEvidence: false,
    serviceDescription:
      "Teleport was detected in all three held-out replays. It was intentionally not used as an integrated safe-stop service latency claim.",
    serviceBadge: "REPLAY EVIDENCE",
  },
  confidence: {
    label: "Confidence",
    sublabel: "collapse",
    title: "Confidence collapse",
    headline: "The detector loses confidence without crashing.",
    description:
      "Classification confidence collapses across consecutive frames. A dedicated normal-data-calibrated confidence-health monitor catches this signal directly.",
    path: "Confidence health",
    p50: "167.807 ms",
    p99: "195.148 ms",
    features: ["mean classification floor", "two consecutive frames", "normal-data calibration"],
    serviceTitle: "Accepted service response: 3 / 3",
    hasServiceEvidence: true,
    serviceDescription:
      "The confidence-health path received an accepted Autoware safe-stop response in every integrated Arm trial: 101.738 ms p50 fault-to-safe-stop request.",
    serviceBadge: "SERVICE RESPONSE EVIDENCE",
  },
  hang: {
    label: "Perception hang",
    sublabel: "silent timeout",
    title: "Perception hang",
    headline: "The perception stream silently stops.",
    description:
      "No new perception messages arrive. The liveness monitor uses a timeout calibrated from normal stream gaps, with a 300 ms minimum.",
    path: "Liveness timeout",
    p50: "267.535 ms",
    p99: "294.845 ms",
    features: ["inter-message gap", "300 ms minimum timeout", "normal stream gaps"],
    serviceTitle: "Accepted service response: 3 / 3",
    hasServiceEvidence: true,
    serviceDescription:
      "The liveness path received an accepted Autoware safe-stop response in every integrated Arm trial: 233.077 ms p50 fault-to-safe-stop request.",
    serviceBadge: "SERVICE RESPONSE EVIDENCE",
  },
};

const elements = {
  tabs: document.querySelector("#scenario-tabs"),
  scene: document.querySelector("#road-scene"),
  sceneFrame: document.querySelector("#scene-frame"),
  sceneTitle: document.querySelector("#scene-title"),
  sceneOverlay: document.querySelector("#scene-overlay"),
  injectButton: document.querySelector("#inject-button"),
  resetButton: document.querySelector("#reset-button"),
  liveBadge: document.querySelector("#live-badge"),
  controlMode: document.querySelector("#control-mode"),
  replayStatus: document.querySelector("#replay-status"),
  statusDot: document.querySelector("#status-dot"),
  mode: document.querySelector("#mode-pill"),
  signal: document.querySelector("#signal-value"),
  signalDetail: document.querySelector("#signal-detail"),
  path: document.querySelector("#decision-path"),
  modelArtifact: document.querySelector("#model-artifact"),
  modelScore: document.querySelector("#model-score"),
  monitorEvidence: document.querySelector("#monitor-evidence"),
  telemetryLog: document.querySelector("#telemetry-log"),
  pulseBars: document.querySelector("#pulse-bars"),
  pulseMarker: document.querySelector("#pulse-marker"),
  timeline: document.querySelector("#event-timeline"),
  p50: document.querySelector("#p50-detect"),
  p99: document.querySelector("#p99-detect"),
  headline: document.querySelector("#fault-headline"),
  description: document.querySelector("#fault-description"),
  features: document.querySelector("#feature-list"),
  serviceTitle: document.querySelector("#service-title"),
  serviceDescription: document.querySelector("#service-description"),
  serviceBadge: document.querySelector("#service-badge"),
};

// Confidence collapse is the clearest first live demonstration: it exercises
// the frozen V2 confidence-health path directly on the incoming ROS stream.
let selected = "confidence";
let frame = 0;
let visualStartedAt = performance.now();
let injectionStartedAt = null;
let alertStartedAt = null;
const injectionDuration = 3300;
const alertHoldDuration = 2400;
const decoder = new TextDecoder();
const encoder = new TextEncoder();
const live = {
  connected: false,
  controlReady: false,
  socket: null,
  channels: new Map(),
  subscriptionTopics: new Map(),
  subscriptionsSent: false,
  phase: 0,
  path: null,
  detail: "",
  faultActive: false,
  resetPending: false,
  lastFaultId: null,
  stopObserved: false,
  loggedDecisionPaths: new Set(),
  loggedMonitorPaths: new Set(),
};

const liveTopics = {
  "/second_sight/status": "string",
  "/second_sight/anomaly": "bool",
  "/second_sight/anomaly_score": "float64",
  "/second_sight/fault/event": "string",
  "/second_sight/fault/active": "bool",
  "/second_sight/latency/decision": "string",
  "/second_sight/safe_stop_requested": "bool",
};

for (let index = 0; index < 42; index += 1) {
  const bar = document.createElement("span");
  bar.className = "pulse-bar";
  elements.pulseBars.append(bar);
}

function renderTabs() {
  elements.tabs.replaceChildren(
    ...Object.entries(scenarios).map(([key, scenario]) => {
      const button = document.createElement("button");
      button.className = "scenario-tab";
      button.type = "button";
      button.role = "tab";
      button.dataset.scenario = key;
      button.setAttribute("aria-selected", String(key === selected));
      button.innerHTML = `<span>${scenario.label}</span><small>${scenario.sublabel}</small>`;
      button.addEventListener("click", () => selectScenario(key));
      return button;
    }),
  );
}

function updateScenarioCopy() {
  const scenario = scenarios[selected];
  elements.scene.dataset.fault = selected;
  elements.sceneTitle.textContent = scenario.title;
  elements.path.textContent = scenario.path;
  elements.p50.textContent = scenario.p50;
  elements.p99.textContent = scenario.p99;
  elements.headline.textContent = scenario.headline;
  elements.description.textContent = scenario.description;
  elements.features.replaceChildren(
    ...scenario.features.map((feature) => {
      const chip = document.createElement("span");
      chip.className = "feature-chip";
      chip.textContent = feature;
      return chip;
    }),
  );
  elements.serviceTitle.textContent = scenario.serviceTitle;
  elements.serviceDescription.textContent = scenario.serviceDescription;
  elements.serviceBadge.textContent = scenario.serviceBadge;
  elements.injectButton.innerHTML = `<span class="inject-icon" aria-hidden="true">↯</span> Inject ${scenario.label.toLowerCase()}`;
}

function selectScenario(key) {
  if (injectionStartedAt !== null || alertStartedAt !== null || live.phase !== 0) return;
  selected = key;
  updateScenarioCopy();
  renderTabs();
}

function replayPhase(progress) {
  if (progress < 0.16) return 0;
  if (progress < 0.46) return 1;
  if (progress < 0.72) return 2;
  return 3;
}

function setTimeline(activeIndex) {
  [...elements.timeline.children].forEach((item, index) => {
    item.classList.toggle("active", index <= activeIndex);
  });
}

function renderPulse(progress, phase) {
  const bars = [...elements.pulseBars.children];
  const center = Math.round(progress * (bars.length - 1));
  bars.forEach((bar, index) => {
    const distance = Math.abs(index - center);
    const idle = 10 + ((index * 17 + Math.round(progress * 40)) % 10);
    const spike = phase >= 2 ? Math.max(0, 102 - distance * 28) : 0;
    bar.style.height = `${Math.max(idle, spike)}%`;
    bar.classList.toggle("hot", phase >= 2 && distance < 3);
  });
  elements.pulseMarker.classList.toggle("visible", phase >= 1);
  elements.pulseMarker.style.left = `${Math.min(92, 27 + progress * 66)}%`;
}

function renderState(signalProgress, requestedPhase, frameNumber) {
  const phase = live.connected
    ? requestedPhase
    : requestedPhase === 3 && !scenarios[selected].hasServiceEvidence
      ? 2
      : requestedPhase;
  const labels = ["Normal stream", "Fault injected", "Anomaly detected", "Safe-stop request"];
  const sceneStates = ["clean", "fault", "detected", "detected"];
  elements.scene.dataset.state = sceneStates[phase];
  elements.scene.dataset.running = "true";
  elements.sceneOverlay.textContent = phase === 0 ? "NORMAL PERCEPTION" : labels[phase].toUpperCase();
  const visualStatus = [
    "Monitoring normal perception",
    `Injecting ${scenarios[selected].label.toLowerCase()} fault`,
    `Anomaly detected via ${scenarios[selected].path.toLowerCase()}`,
    "Safe-stop request issued",
  ][phase];
  const liveStatus = [
    "Live model processing normal perception",
    `Live injector applying ${scenarios[selected].label.toLowerCase()} fault`,
    "Live model emitted an anomaly decision",
    "Live model issued a dry-run safe-stop request",
  ][phase];
  elements.replayStatus.textContent = live.connected ? liveStatus : visualStatus;
  elements.statusDot.className = `status-dot${phase === 1 ? " warning" : phase >= 2 ? " danger" : ""}`;
  elements.mode.textContent = phase >= 2 ? "ANOMALY" : "MONITORING";
  elements.mode.classList.toggle("detected", phase >= 2);
  elements.signal.textContent = phase >= 2 ? "ANOMALY" : "NORMAL";
  elements.signal.style.color = phase >= 2 ? "var(--danger)" : "var(--lime)";
  elements.path.textContent = live.connected && live.path ? live.path : scenarios[selected].path;
  elements.signalDetail.textContent = live.connected
    ? live.detail || "Live ROS 2 model stream connected"
    : "Visual fallback · model connection unavailable";
  elements.sceneFrame.textContent = `FRAME ${String(frameNumber % 1000).padStart(3, "0")}`;
  setTimeline(phase);
  renderPulse(signalProgress, phase);
}

function tick(now) {
  const idleSignal = ((now - visualStartedAt) % 8000) / 8000;
  const frameNumber = Math.floor((now - visualStartedAt) / 33);
  let phase = 0;
  let signalProgress = idleSignal;

  if (live.connected) {
    phase = live.phase;
    signalProgress = phase === 0 ? idleSignal : 0.5 + phase * 0.12;
  } else if (injectionStartedAt !== null) {
    const progress = Math.min((now - injectionStartedAt) / injectionDuration, 1);
    phase = replayPhase(progress);
    signalProgress = progress;
    if (progress === 1) {
      injectionStartedAt = null;
      alertStartedAt = now;
    }
  } else if (alertStartedAt !== null) {
    const alertElapsed = now - alertStartedAt;
    phase = scenarios[selected].hasServiceEvidence ? 3 : 2;
    signalProgress = 0.74 + ((alertElapsed % 520) / 520) * 0.18;
    if (alertElapsed >= alertHoldDuration) {
      alertStartedAt = null;
      updateScenarioCopy();
    }
  }

  elements.injectButton.disabled = live.connected
    ? !live.controlReady || live.phase !== 0
    : injectionStartedAt !== null || alertStartedAt !== null;
  elements.resetButton.hidden = !live.connected || live.phase < 2;
  elements.resetButton.disabled = !live.controlReady;
  renderState(signalProgress, phase, frameNumber);
  frame = requestAnimationFrame(tick);
}

function injectFault() {
  if (live.connected) {
    if (!live.controlReady || live.phase !== 0) return;
    publishLiveFault();
    return;
  }
  if (injectionStartedAt !== null || alertStartedAt !== null) return;
  injectionStartedAt = performance.now();
  elements.injectButton.disabled = true;
}

elements.injectButton.addEventListener("click", injectFault);
elements.resetButton.addEventListener("click", () => {
  if (!live.connected || !live.controlReady || live.phase < 2) return;
  live.resetPending = true;
  publishLiveCommand({ action: "reset" });
  live.detail = "Live dry-run reset requested";
  elements.resetButton.disabled = true;
});

function faultKey(faultType) {
  return {
    confidence_collapse: "confidence",
    liveness: "hang",
  }[faultType] || faultType;
}

function faultType(key) {
  return {
    confidence: "confidence_collapse",
    hang: "liveness",
  }[key] || key;
}

function readablePath(path) {
  return {
    trajectory_hybrid: "Trajectory hybrid",
    confidence_health: "Confidence health",
    source_freshness: "Source freshness",
    perception_liveness_timeout: "Liveness timeout",
    perception_guardrails: "Perception guardrails",
  }[path] || path.replaceAll("_", " ");
}

function setLiveConnection(connected) {
  live.connected = connected;
  live.controlReady = false;
  elements.liveBadge.textContent = connected ? "LIVE MODEL CONNECTED" : "LIVE MODEL OFFLINE";
  elements.liveBadge.classList.toggle("connected", connected);
  elements.controlMode.textContent = connected
    ? "Live V2 mode: this button sends a command through Foxglove Bridge to the ROS 2 fault injector. The model, decision path, and dry-run safe-stop request below are live telemetry."
    : "Visual fallback: this button triggers the browser demonstration. Start the live stack to send commands to the ROS 2 fault injector and score the real loaded model.";
}

function parseCdrString(data) {
  const view = new DataView(data);
  const offset = 17;
  if (data.byteLength < offset + 4) return null;
  const length = view.getUint32(offset, true);
  if (length === 0 || data.byteLength < offset + 4 + length) return "";
  return decoder.decode(new Uint8Array(data, offset + 4, length - 1));
}

function parseCdrBool(data) {
  return new DataView(data).getUint8(17) !== 0;
}

function parseCdrFloat64(data) {
  return new DataView(data).getFloat64(17, true);
}

function appendTelemetry(label, payload) {
  const waitingEntry = elements.telemetryLog.querySelector("li:first-child span");
  if (waitingEntry?.textContent === "WAITING") elements.telemetryLog.replaceChildren();
  const entry = document.createElement("li");
  const heading = document.createElement("span");
  const message = document.createElement("code");
  heading.textContent = label;
  message.textContent = typeof payload === "string" ? payload : JSON.stringify(payload);
  entry.append(heading, message);
  elements.telemetryLog.prepend(entry);
  while (elements.telemetryLog.children.length > 5) {
    elements.telemetryLog.lastElementChild.remove();
  }
}

function showMonitorEvidence(status) {
  const monitor = status.monitor;
  const config = status.monitor_config || {};
  if (!monitor) return;
  if (monitor.path === "confidence_health") {
    const score = Number(monitor.mean_classification_probability).toFixed(4);
    const floor = Number(config.mean_classification_floor).toFixed(4);
    elements.monitorEvidence.textContent = `Classification ${score} < frozen floor ${floor} · ${monitor.consecutive_anomalies} consecutive frames`;
    return;
  }
  if (monitor.path === "source_freshness") {
    elements.monitorEvidence.textContent = `Source age ${Number(monitor.source_age_ms).toFixed(3)} ms · ${monitor.consecutive_anomalies} consecutive frames`;
  }
}

function handleLiveMessage(topic, data) {
  if (topic === "/second_sight/status") {
    const payloadText = parseCdrString(data);
    if (payloadText === null) return;
    try {
      const status = JSON.parse(payloadText);
      if (typeof status.model_sha256 === "string") {
        elements.modelArtifact.textContent = `SHA-256 ${status.model_sha256.slice(0, 12)}… · ${status.mode || "model"}`;
      }
      if (typeof status.forest_score === "number") {
        live.detail = `Live model score ${status.forest_score.toFixed(4)}`;
        elements.modelScore.textContent = status.forest_score.toFixed(6);
      }
      if (status.anomalous === true) {
        live.phase = Math.max(live.phase, 2);
        showMonitorEvidence(status);
        const path = String(status.path || status.monitor?.path || "model");
        if (!live.loggedMonitorPaths.has(path)) {
          live.loggedMonitorPaths.add(path);
          appendTelemetry("MODEL MONITOR", {
            topic: "/second_sight/status",
            path,
            monitor: status.monitor,
            frozen_config: status.monitor_config,
          });
        }
      }
    } catch {
      live.detail = "Live model status received";
    }
    return;
  }
  if (topic === "/second_sight/anomaly_score") {
    const score = parseCdrFloat64(data);
    live.detail = `Live model score ${score.toFixed(4)}`;
    elements.modelScore.textContent = score.toFixed(6);
    return;
  }
  if (topic === "/second_sight/fault/event") {
    const payloadText = parseCdrString(data);
    if (payloadText === null) return;
    try {
      const fault = JSON.parse(payloadText);
      const nextSelected = faultKey(fault.fault_types?.[0]);
      if (scenarios[nextSelected]) {
        selected = nextSelected;
        updateScenarioCopy();
        renderTabs();
      }
      live.phase = Math.max(live.phase, 1);
      if (live.phase === 1) {
        live.detail = "Live fault injector confirmed corrupted stream";
      }
      const faultId = String(fault.fault_ids?.[0] || "fault");
      if (live.lastFaultId !== faultId) {
        live.lastFaultId = faultId;
        appendTelemetry("INJECTOR", { topic: "/second_sight/fault/event", ...fault });
      }
    } catch {
      live.phase = Math.max(live.phase, 1);
    }
    return;
  }
  if (topic === "/second_sight/fault/active") {
    live.faultActive = parseCdrBool(data);
    if (!live.faultActive && live.phase === 1) {
      live.phase = 0;
      live.detail = "Live injector completed without an anomaly decision";
    }
    return;
  }
  if (topic === "/second_sight/latency/decision") {
    const payloadText = parseCdrString(data);
    if (payloadText === null) return;
    try {
      const decision = JSON.parse(payloadText);
      if (decision.anomalous === true) {
        live.phase = Math.max(live.phase, 2);
        live.path = readablePath(String(decision.path));
        live.detail = `Live decision · ${live.path}`;
        const path = String(decision.path);
        if (!live.loggedDecisionPaths.has(path)) {
          live.loggedDecisionPaths.add(path);
          appendTelemetry("MODEL DECISION", {
            topic: "/second_sight/latency/decision",
            ...decision,
          });
        }
      }
    } catch {
      // Ignore malformed visual telemetry; the model continues independently.
    }
    return;
  }
  if (topic === "/second_sight/safe_stop_requested") {
    if (parseCdrBool(data)) {
      live.phase = 3;
      live.detail = "Live model requested a dry-run safe stop";
      if (!live.stopObserved) {
        live.stopObserved = true;
        appendTelemetry("SAFE STOP", {
          topic: "/second_sight/safe_stop_requested",
          value: true,
          mode: "dry-run",
        });
      }
    } else if (live.resetPending) {
      live.phase = 0;
      live.path = null;
      live.faultActive = false;
      live.resetPending = false;
      live.lastFaultId = null;
      live.stopObserved = false;
      live.loggedDecisionPaths.clear();
      live.loggedMonitorPaths.clear();
      live.detail = "Live watchdog reset; monitoring normal perception";
      appendTelemetry("DASHBOARD", { action: "reset", value: "accepted" });
    }
  }
}

function subscribeToLiveTopics() {
  if (live.subscriptionsSent || live.socket?.readyState !== WebSocket.OPEN) return;
  const subscriptions = [];
  let id = 1;
  for (const [topic, kind] of Object.entries(liveTopics)) {
    const channel = live.channels.get(topic);
    if (!channel) return;
    subscriptions.push({ id, channelId: channel.id });
    live.subscriptionTopics.set(id, { topic, kind });
    id += 1;
  }
  live.socket.send(JSON.stringify({ op: "subscribe", subscriptions }));
  live.subscriptionsSent = true;
}

function advertiseLiveControl() {
  if (live.socket?.readyState !== WebSocket.OPEN) return;
  live.socket.send(
    JSON.stringify({
      op: "advertise",
      channels: [
        {
          id: 100,
          topic: "/second_sight/dashboard/inject_fault",
          encoding: "cdr",
          schemaName: "std_msgs/msg/String",
          schemaEncoding: "ros2msg",
          schema: "string data",
        },
      ],
    }),
  );
}

function publishLiveFault() {
  publishLiveCommand({ fault_type: faultType(selected), duration_ms: 900 });
  live.detail = `Live command sent · injecting ${scenarios[selected].label.toLowerCase()}`;
  elements.injectButton.disabled = true;
}

function publishLiveCommand(commandPayload) {
  const command = JSON.stringify(commandPayload);
  const text = encoder.encode(command);
  const cdr = new Uint8Array(8 + text.length + 1);
  const cdrView = new DataView(cdr.buffer);
  cdr.set([0, 1, 0, 0], 0);
  cdrView.setUint32(4, text.length + 1, true);
  cdr.set(text, 8);
  const frame = new Uint8Array(5 + cdr.length);
  const frameView = new DataView(frame.buffer);
  frame[0] = 1;
  frameView.setUint32(1, 100, true);
  frame.set(cdr, 5);
  live.socket.send(frame);
}

function connectLiveModel() {
  const socket = new WebSocket("ws://localhost:8765", "foxglove.sdk.v1");
  socket.binaryType = "arraybuffer";
  live.socket = socket;
  socket.onopen = () => {
    setLiveConnection(true);
    advertiseLiveControl();
  };
  socket.onmessage = (event) => {
    if (typeof event.data === "string") {
      try {
        const message = JSON.parse(event.data);
        if (message.op === "advertise") {
          for (const channel of message.channels) live.channels.set(channel.topic, channel);
          subscribeToLiveTopics();
          if (live.subscriptionsSent && !live.controlReady) {
            // Give Foxglove Bridge a brief turn to register the client publisher
            // before exposing the dashboard's real injector control.
            window.setTimeout(() => {
              if (live.socket === socket && socket.readyState === WebSocket.OPEN) {
                live.controlReady = true;
              }
            }, 150);
          }
        }
      } catch {
        // Ignore non-protocol text frames.
      }
      return;
    }
    const view = new DataView(event.data);
    if (view.getUint8(0) !== 1) return;
    const subscription = live.subscriptionTopics.get(view.getUint32(1, true));
    if (subscription) handleLiveMessage(subscription.topic, event.data);
  };
  socket.onclose = () => {
    live.channels.clear();
    live.subscriptionTopics.clear();
    live.subscriptionsSent = false;
    live.phase = 0;
    live.path = null;
    live.detail = "";
    live.faultActive = false;
    live.resetPending = false;
    live.lastFaultId = null;
    live.stopObserved = false;
    live.loggedDecisionPaths.clear();
    live.loggedMonitorPaths.clear();
    setLiveConnection(false);
    window.setTimeout(connectLiveModel, 3000);
  };
  socket.onerror = () => socket.close();
}

updateScenarioCopy();
renderTabs();
frame = requestAnimationFrame(tick);
connectLiveModel();

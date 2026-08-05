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
  playButton: document.querySelector("#play-button"),
  resetButton: document.querySelector("#reset-button"),
  replayStatus: document.querySelector("#replay-status"),
  statusDot: document.querySelector("#status-dot"),
  mode: document.querySelector("#mode-pill"),
  signal: document.querySelector("#signal-value"),
  path: document.querySelector("#decision-path"),
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

let selected = "vanish";
let playing = false;
let startedAt = 0;
let frame = 0;
const replayDuration = 7100;

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
}

function selectScenario(key) {
  selected = key;
  stopReplay();
  updateScenarioCopy();
  renderTabs();
  renderState(0);
}

function replayPhase(progress) {
  if (progress < 0.35) return 0;
  if (progress < 0.59) return 1;
  if (progress < 0.81) return 2;
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

function renderState(progress) {
  const requestedPhase = replayPhase(progress);
  const phase = requestedPhase === 3 && !scenarios[selected].hasServiceEvidence ? 2 : requestedPhase;
  const labels = ["Normal stream", "Fault injected", "Anomaly detected", "Safe-stop request"];
  const sceneStates = ["clean", "fault", "detected", "detected"];
  elements.scene.dataset.state = sceneStates[phase];
  elements.scene.dataset.running = String(playing);
  elements.sceneOverlay.textContent = phase === 0 ? "NORMAL PERCEPTION" : labels[phase].toUpperCase();
  elements.replayStatus.textContent = playing ? labels[phase] : "Ready to replay";
  elements.statusDot.className = `status-dot${phase === 1 ? " warning" : phase >= 2 ? " danger" : ""}`;
  elements.mode.textContent = phase >= 2 ? "ANOMALY" : "MONITORING";
  elements.mode.classList.toggle("detected", phase >= 2);
  elements.signal.textContent = phase >= 2 ? "ANOMALY" : "NORMAL";
  elements.signal.style.color = phase >= 2 ? "var(--danger)" : "var(--lime)";
  elements.sceneFrame.textContent = `FRAME ${String(Math.round(progress * 180)).padStart(3, "0")}`;
  setTimeline(phase);
  renderPulse(progress, phase);
}

function tick(now) {
  const progress = Math.min((now - startedAt) / replayDuration, 1);
  renderState(progress);
  if (progress < 1 && playing) {
    frame = requestAnimationFrame(tick);
    return;
  }
  playing = false;
  elements.scene.dataset.running = "false";
  elements.playButton.innerHTML = '<span aria-hidden="true">↻</span> Replay again';
  elements.replayStatus.textContent = "Replay complete";
}

function startReplay() {
  if (playing) {
    stopReplay();
    return;
  }
  playing = true;
  startedAt = performance.now();
  elements.playButton.innerHTML = '<span aria-hidden="true">■</span> Stop replay';
  frame = requestAnimationFrame(tick);
}

function stopReplay() {
  playing = false;
  cancelAnimationFrame(frame);
  elements.scene.dataset.running = "false";
  elements.playButton.innerHTML = '<span aria-hidden="true">▶</span> Start replay';
  elements.replayStatus.textContent = "Replay paused";
}

elements.playButton.addEventListener("click", startReplay);
elements.resetButton.addEventListener("click", () => {
  stopReplay();
  renderState(0);
});

updateScenarioCopy();
renderTabs();
renderState(0);

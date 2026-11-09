(function () {
  "use strict";

  const canvas = document.getElementById("fourier-canvas");
  const ctx = canvas.getContext("2d");
  const harmonicsInput = document.getElementById("harmonics");
  const speedInput = document.getElementById("speed");
  const harmonicsValue = document.getElementById("harmonics-value");
  const speedValue = document.getElementById("speed-value");
  const toggleButton = document.getElementById("toggle-animation");
  const clearButton = document.getElementById("clear-trace");
  const status = document.getElementById("fourier-status");
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const sampleCount = 128;
  const samples = [];
  let coefficients = [];
  let trace = [];
  let t = 0;
  let running = !reducedMotion;
  let lastTime = 0;
  let cssWidth = 900;
  let cssHeight = 520;

  for (let index = 0; index < sampleCount; index += 1) {
    const angle = (index / sampleCount) * Math.PI * 2;
    samples.push({
      x: 0.62 * Math.cos(angle) + 0.2 * Math.cos(angle * 2),
      y: 0.62 * Math.sin(angle) - 0.14 * Math.sin(angle * 3)
    });
  }

  function computeCoefficients() {
    coefficients = [];
    for (let frequency = 0; frequency < sampleCount; frequency += 1) {
      let real = 0;
      let imaginary = 0;
      for (let index = 0; index < sampleCount; index += 1) {
        const angle = (Math.PI * 2 * frequency * index) / sampleCount;
        const sample = samples[index];
        const realSample = sample.x;
        const imaginarySample = -sample.y;
        real += realSample * Math.cos(angle) - imaginarySample * Math.sin(angle);
        imaginary += realSample * Math.sin(angle) + imaginarySample * Math.cos(angle);
      }
      const normalizedFrequency = frequency <= sampleCount / 2 ? frequency : frequency - sampleCount;
      coefficients.push({ real: real / sampleCount, imaginary: -imaginary / sampleCount, frequency: normalizedFrequency });
    }
    coefficients.sort((first, second) => (second.real ** 2 + second.imaginary ** 2) - (first.real ** 2 + first.imaginary ** 2));
  }

  function complexPoint(coefficient, phase) {
    const angle = coefficient.frequency * phase * Math.PI * 2;
    const c = Math.cos(angle);
    const s = Math.sin(angle);
    return {
      x: coefficient.real * c - coefficient.imaginary * s,
      y: coefficient.real * s + coefficient.imaginary * c
    };
  }

  function resize() {
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    cssWidth = Math.max(300, canvas.parentElement.clientWidth - 2);
    cssHeight = Math.max(340, Math.min(560, Math.round(cssWidth * 0.52)));
    canvas.style.width = `${cssWidth}px`;
    canvas.style.height = `${cssHeight}px`;
    canvas.width = Math.round(cssWidth * ratio);
    canvas.height = Math.round(cssHeight * ratio);
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  }

  function drawPath(points, scale, dashed, closed) {
    if (!points.length) return;
    ctx.save();
    ctx.beginPath();
    points.forEach((point, index) => {
      const x = cssWidth / 2 + point.x * scale;
      const y = cssHeight / 2 - point.y * scale;
      if (index === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    });
    if (closed) ctx.closePath();
    if (dashed) {
      ctx.setLineDash([5, 7]);
      ctx.strokeStyle = "rgba(29,117,133,.35)";
      ctx.lineWidth = 1.4;
    } else {
      ctx.setLineDash([]);
      ctx.strokeStyle = "#c86b4a";
      ctx.lineWidth = 2.5;
    }
    ctx.stroke();
    ctx.restore();
  }

  function draw() {
    const dark = document.documentElement.classList.contains("dark");
    const ink = dark ? "#e5edf9" : "#17243b";
    const muted = dark ? "#a4b4cb" : "#52647d";
    const panel = dark ? "#111d30" : "#ffffff";
    const scale = Math.min(cssWidth, cssHeight) * 0.37;
    ctx.clearRect(0, 0, cssWidth, cssHeight);
    ctx.fillStyle = panel;
    ctx.fillRect(0, 0, cssWidth, cssHeight);
    ctx.strokeStyle = dark ? "rgba(114,196,207,.12)" : "rgba(29,117,133,.1)";
    ctx.lineWidth = 1;
    for (let x = 0; x < cssWidth; x += 28) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, cssHeight); ctx.stroke(); }
    for (let y = 0; y < cssHeight; y += 28) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(cssWidth, y); ctx.stroke(); }

    drawPath(samples, scale, true, true);
    const count = Number(harmonicsInput.value);
    let cursor = { x: 0, y: 0 };
    ctx.save();
    for (let index = 0; index < count; index += 1) {
      const vector = complexPoint(coefficients[index], t);
      const next = { x: cursor.x + vector.x, y: cursor.y + vector.y };
      const radius = Math.hypot(vector.x, vector.y) * scale;
      const centerX = cssWidth / 2 + cursor.x * scale;
      const centerY = cssHeight / 2 - cursor.y * scale;
      ctx.beginPath();
      ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
      ctx.strokeStyle = index === 0 ? "rgba(29,117,133,.52)" : "rgba(82,100,125,.34)";
      ctx.lineWidth = 1;
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(centerX, centerY);
      ctx.lineTo(cssWidth / 2 + next.x * scale, cssHeight / 2 - next.y * scale);
      ctx.strokeStyle = index === 0 ? "#1d7585" : "#8796aa";
      ctx.lineWidth = index === 0 ? 2.1 : 1.25;
      ctx.stroke();
      cursor = next;
    }
    ctx.restore();

    trace.push(cursor);
    if (trace.length > 260) trace.shift();
    drawPath(trace, scale, false, false);
    ctx.beginPath();
    ctx.arc(cssWidth / 2 + cursor.x * scale, cssHeight / 2 - cursor.y * scale, 4, 0, Math.PI * 2);
    ctx.fillStyle = "#c86b4a";
    ctx.fill();
    ctx.fillStyle = muted;
    ctx.font = "12px ui-monospace, monospace";
    ctx.fillText(`${count} harmonics`, 18, 26);
    ctx.fillStyle = ink;
    ctx.font = "600 14px Inter, system-ui, sans-serif";
    ctx.fillText("target contour", 18, cssHeight - 20);
  }

  function updateLabels() {
    harmonicsValue.value = harmonicsInput.value;
    speedValue.value = `${Number(speedInput.value).toFixed(2)}×`;
    status.textContent = `${harmonicsInput.value} гармоник собирают кривую.`;
  }

  function frame(now) {
    const delta = Math.min(50, now - (lastTime || now));
    lastTime = now;
    if (running) t = (t + delta * Number(speedInput.value) / 9000) % 1;
    draw();
    requestAnimationFrame(frame);
  }

  harmonicsInput.addEventListener("input", () => { trace = []; updateLabels(); });
  speedInput.addEventListener("input", updateLabels);
  toggleButton.addEventListener("click", () => {
    running = !running;
    toggleButton.textContent = running ? "Пауза" : "Продолжить";
    toggleButton.setAttribute("aria-pressed", String(running));
  });
  clearButton.addEventListener("click", () => { trace = []; t = 0; });
  window.addEventListener("resize", resize);
  computeCoefficients();
  resize();
  updateLabels();
  if (reducedMotion) toggleButton.textContent = "Продолжить";
  requestAnimationFrame(frame);
})();

(function () {
  "use strict";

  const input = document.getElementById("virtual-address");
  const addressDisplay = document.getElementById("address-display");
  const status = document.getElementById("paging-status");
  const error = document.getElementById("paging-error");
  const diagram = document.getElementById("paging-diagram");
  const parseButton = document.getElementById("parse-address");
  const nextButton = document.getElementById("next-step");
  const resetButton = document.getElementById("reset-walk");
  const tlbButton = document.getElementById("tlb-hit");
  const NS = "http://www.w3.org/2000/svg";
  const MASK_9 = 0x1ffn;
  const MASK_12 = 0xfffn;
  const MAX_48 = (1n << 48n) - 1n;

  const state = { address: 0n, parts: null, step: 0, tlb: false };
  const levels = ["CR3", "PML4", "PDPT", "PD", "PT", "Фрейм"];

  function setMessage(message, tone) {
    status.textContent = message;
    status.dataset.state = tone || "";
  }

  function clearError() {
    error.textContent = "";
  }

  function parseAddress() {
    const raw = input.value.trim().replace(/_/g, "");
    if (!/^0x[0-9a-f]+$/i.test(raw)) throw new Error("Введите адрес в шестнадцатеричном виде, например 0x7FFF_CAFE_B000.");
    const address = BigInt(raw);
    if (address > MAX_48) throw new Error("Демо принимает 48-битные канонические адреса (не больше 0x0000FFFFFFFFFFFF).");
    const parts = {
      sign: Number((address >> 47n) & 1n),
      pml4: Number((address >> 39n) & MASK_9),
      pdpt: Number((address >> 30n) & MASK_9),
      pd: Number((address >> 21n) & MASK_9),
      pt: Number((address >> 12n) & MASK_9),
      offset: Number(address & MASK_12)
    };
    state.address = address;
    state.parts = parts;
    state.step = 0;
    state.tlb = false;
    addressDisplay.textContent = `0x${address.toString(16).toUpperCase().padStart(12, "0")}`;
    clearError();
    setMessage("Шаг 0: адрес разобран. Нажмите «Следующий шаг». ", "success");
    draw();
  }

  function makeSvg(tag, attrs, text) {
    const node = document.createElementNS(NS, tag);
    Object.entries(attrs || {}).forEach(([key, value]) => node.setAttribute(key, value));
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function draw() {
    diagram.replaceChildren(
      makeSvg("text", { x: 40, y: 40, fill: "currentColor", "font-size": 14, "font-weight": 700 }, state.tlb ? "TLB hit: таблицы не читаются" : "Пошаговый обход таблиц страниц")
    );
    const xPositions = [36, 205, 374, 543, 712, 850];
    const y = 130;
    const boxWidth = 132;
    const boxHeight = 104;
    const values = state.parts ? ["CR3", state.parts.pml4, state.parts.pdpt, state.parts.pd, state.parts.pt, `+${state.parts.offset}`] : ["—", "—", "—", "—", "—", "—"];
    const descriptions = ["база", "индекс 9 бит", "индекс 9 бит", "индекс 9 бит", "индекс 9 бит", "offset 12 бит"];

    for (let index = 0; index < levels.length; index += 1) {
      if (index < levels.length - 1) {
        diagram.appendChild(makeSvg("line", { x1: xPositions[index] + boxWidth, y1: y + boxHeight / 2, x2: xPositions[index + 1] - 10, y2: y + boxHeight / 2, stroke: "currentColor", "stroke-width": 2, "marker-end": "url(#arrow)" }));
      }
    }
    const defs = makeSvg("defs");
    const marker = makeSvg("marker", { id: "arrow", markerWidth: 8, markerHeight: 8, refX: 6, refY: 3, orient: "auto", markerUnits: "strokeWidth" });
    marker.appendChild(makeSvg("path", { d: "M0,0 L0,6 L6,3 z", fill: "currentColor" }));
    defs.appendChild(marker);
    diagram.insertBefore(defs, diagram.firstChild);

    levels.forEach((level, index) => {
      const active = state.tlb || (state.step > 0 && index <= state.step);
      const group = makeSvg("g", { "aria-label": `${level}: ${values[index]}` });
      group.appendChild(makeSvg("rect", { x: xPositions[index], y, width: boxWidth, height: boxHeight, rx: 14, fill: active ? "#dce9ff" : "var(--lab-panel)", stroke: active ? "#245bea" : "currentColor", "stroke-opacity": active ? 1 : 0.22, "stroke-width": active ? 2.5 : 1.2 }));
      group.appendChild(makeSvg("text", { x: xPositions[index] + 14, y: y + 28, fill: "currentColor", "font-size": 13, "font-weight": 750 }, level));
      group.appendChild(makeSvg("text", { x: xPositions[index] + 14, y: y + 63, fill: active ? "#245bea" : "currentColor", "font-size": 18, "font-family": "ui-monospace, monospace", "font-weight": 750 }, String(values[index])));
      group.appendChild(makeSvg("text", { x: xPositions[index] + 14, y: y + 86, fill: "currentColor", "fill-opacity": 0.64, "font-size": 11 }, descriptions[index]));
      diagram.appendChild(group);
    });

    if (state.parts) {
      const bitText = `sign ${state.parts.sign} · ${state.parts.pml4} · ${state.parts.pdpt} · ${state.parts.pd} · ${state.parts.pt} · ${state.parts.offset}`;
      diagram.appendChild(makeSvg("text", { x: 40, y: 310, fill: "currentColor", "fill-opacity": 0.66, "font-size": 12, "font-family": "ui-monospace, monospace" }, bitText));
    }
    nextButton.disabled = !state.parts || state.tlb || state.step >= levels.length - 1;
  }

  parseButton.addEventListener("click", () => {
    try { parseAddress(); } catch (caught) { setMessage(caught.message, "error"); error.textContent = caught.message; }
  });

  nextButton.addEventListener("click", () => {
    if (!state.parts) return;
    state.step = Math.min(levels.length - 1, state.step + 1);
    const level = levels[state.step];
    setMessage(`Шаг ${state.step}: читаем ${level}.`, "success");
    draw();
  });

  resetButton.addEventListener("click", () => {
    state.step = 0;
    state.tlb = false;
    clearError();
    setMessage(state.parts ? "Шаг 0: адрес разобран." : "Шаг 0: адрес готов к разбору.", "");
    draw();
  });

  tlbButton.addEventListener("click", () => {
    if (!state.parts) {
      setMessage("Сначала разберите виртуальный адрес.", "error");
      return;
    }
    state.tlb = true;
    state.step = levels.length - 1;
    clearError();
    setMessage("TLB hit: готовая трансляция вернулась без обхода таблиц.", "success");
    draw();
  });

  try { parseAddress(); } catch (_error) { draw(); }
})();

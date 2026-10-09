"""Render an offline, source-linked audit of curriculum OCR experiments.

This is a presentation step after independent inference. Ground truth is used
only for evaluation, ordering review rows and cropping visual reference images.
No OCR, dictionary correction, publication or network operation runs here.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import shutil
import sys
from datetime import UTC, datetime
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.benchmark_curriculum_ocr import (  # noqa: E402
    FIELDS,
    KINDS,
    align_rows,
    control_semesters,
    evaluate,
    normalized,
)
from shared_lib.services.curriculum_ocr import _code  # noqa: E402

LABELS = {
    "discipline_code": "Индекс",
    "discipline_name": "Дисциплина / раздел",
    "exam": "Экзамен",
    "pass": "Зачёт",
    "graded_pass": "Зачёт с оценкой",
    "coursework": "Курсовая работа",
    "course_project": "Курсовой проект",
}
ROW_TYPES = {"discipline": "Дисциплина", "section": "Раздел", "summary": "Итог"}

CSS = """
:root{color-scheme:light;--ink:#162436;--muted:#526276;--line:#d8e0e8;--paper:#fff;--blue:#2459a6}
*{box-sizing:border-box}body{margin:0;background:#edf1f5;color:var(--ink);font:15px/1.5 system-ui,sans-serif}
main{max-width:1560px;margin:auto;padding:30px 24px 80px}a{color:var(--blue)}h1{font-size:clamp(26px,4vw,42px);line-height:1.15;margin:8px 0 18px}h2{font-size:24px;margin:0 0 12px}h3{margin:0 0 6px;font-size:18px}p{margin:8px 0 14px}.muted,small{color:var(--muted)}.eyebrow{text-transform:uppercase;letter-spacing:.11em;font-size:12px;font-weight:750;color:var(--blue)}
.panel,.row-card{background:var(--paper);border:1px solid var(--line);border-radius:14px;padding:22px;margin:20px 0}.stats{display:flex;flex-wrap:wrap;gap:12px;margin:22px 0}.stat{background:white;border:1px solid var(--line);border-radius:12px;padding:15px 20px;min-width:150px}.stat strong{display:block;font-size:27px}.downloads,.toolbar,.models{display:flex;align-items:center;gap:12px;flex-wrap:wrap}.downloads a,button{border:1px solid var(--line);border-radius:8px;background:white;padding:8px 12px;text-decoration:none;font:inherit;color:var(--blue);cursor:pointer}.downloads a:hover,button:hover{background:#eaf1fa}.table-scroll{overflow-x:auto;max-width:100%;border:1px solid var(--line);border-radius:8px;margin:12px 0}table{border-collapse:collapse;width:100%;font-size:13px;text-align:left}th,td{padding:9px 11px;border-bottom:1px solid var(--line);vertical-align:top}th{background:#f1f5fa;font-weight:700;white-space:normal}tr:last-child td{border-bottom:0}td code{font-size:12px}.metrics{min-width:1080px}.metrics td:first-child{min-width:205px}.metric-num{font-variant-numeric:tabular-nums;white-space:nowrap}.tag{display:inline-block;background:#edf2f8;border:1px solid #d9e1ec;border-radius:6px;padding:1px 7px;font-size:12px;margin:0 5px 3px 0}.featured{border-left:4px solid var(--blue)}.warn{background:#fff3c9;color:#6a4f08}.bad{background:#ffe5e3;color:#861d26}.good{background:#e8f5ec;color:#175b35}.empty{font-style:italic;color:#657181}.notice{border-left:4px solid #cc901e;padding:10px 14px;background:#fff7e5}.checks{display:flex;gap:14px;flex-wrap:wrap}.checks label,.models label{display:flex;align-items:center;gap:6px}.models{gap:8px 14px}.models label{font-size:13px}input[type=search]{width:min(520px,100%);padding:10px 12px;border:1px solid #aebbc9;border-radius:8px;font:inherit}input[type=checkbox]{accent-color:var(--blue);width:17px;height:17px}select{font:inherit;border:1px solid #aebbc9;padding:10px;border-radius:8px;background:white;max-width:100%}details>summary{cursor:pointer}summary{list-style-position:outside}summary h3{display:inline}.row-card>summary{padding:2px 0}.row-subtitle{display:block;font-size:13px;margin-top:5px;color:var(--muted)}.row-card[open]>summary{margin-bottom:14px}.compare{min-width:1220px;table-layout:fixed}.compare th:first-child{width:190px}.compare th:nth-child(2){width:165px}.compare th:nth-child(3){width:305px}.compare td{overflow-wrap:anywhere}.gt td{background:#edf6ef;font-weight:600}.cell-note{display:block;font-size:11px;margin-top:4px}.crop{margin:14px 0}.crop img{display:block;width:100%;height:auto;border:1px solid #d2dce6;background:white}.crop figcaption{font-size:12px;color:var(--muted);margin-top:4px}.legend{display:flex;gap:10px;flex-wrap:wrap;font-size:13px}.legend span{padding:4px 8px;border-radius:5px}.problem-list{padding-left:22px}.problem-list li{margin:8px 0}.hidden-model,[hidden]{display:none!important}.count{font-variant-numeric:tabular-nums;font-weight:700}.source-hash{word-break:break-all;font:12px ui-monospace,monospace}.notes{font-size:13px;background:#f5f7fa;border-radius:8px;padding:10px 12px}.candidates{min-width:1000px}.candidates td:nth-child(4){min-width:280px}.small-table{min-width:900px}footer{color:var(--muted);font-size:13px}.no-results{padding:22px;border:1px dashed var(--line);border-radius:12px}
@media(max-width:650px){main{padding:18px 12px 50px}.panel,.row-card{padding:14px;border-radius:10px}.stats{gap:8px}.stat{min-width:calc(50% - 5px);flex:1;padding:11px 14px}.stat strong{font-size:23px}.toolbar>*{width:100%}.downloads a{font-size:13px}.row-subtitle{line-height:1.6}h2{font-size:21px}}
.crop>a{display:block;overflow-x:auto}.crop img{min-width:900px}
.scroll-hint{margin:8px 0;color:var(--blue);font-size:13px}.classification{font-weight:650}.metrics{min-width:1330px}
"""

JS = """
const search=document.querySelector('#search'),kind=document.querySelector('#row-type'),only=document.querySelector('#only-problems'),order=document.querySelector('#row-order');
const cards=Array.from(document.querySelectorAll('.row-card')),container=document.querySelector('#rows');
function applyFilters(){const query=search.value.toLocaleLowerCase('ru').trim();let count=0;for(const card of cards){const show=(!query||card.dataset.search.includes(query))&&(!kind.value||card.dataset.kind===kind.value)&&(!only.checked||Number(card.dataset.score)>0);card.hidden=!show;if(show)count++;}document.querySelector('#visible-count').textContent=count;document.querySelector('#no-results').hidden=count>0;}
search.addEventListener('input',applyFilters);kind.addEventListener('change',applyFilters);only.addEventListener('change',applyFilters);
order.addEventListener('change',()=>{cards.sort(order.value==='source'?(a,b)=>Number(a.dataset.source)-Number(b.dataset.source):(a,b)=>Number(b.dataset.score)-Number(a.dataset.score)||Number(a.dataset.source)-Number(b.dataset.source));for(const card of cards)container.appendChild(card);});
for(const box of document.querySelectorAll('[data-model-toggle]'))box.addEventListener('change',()=>{for(const row of document.querySelectorAll('[data-model="'+box.dataset.modelToggle+'"]'))row.classList.toggle('hidden-model',!box.checked);});
document.querySelector('#expand-visible').addEventListener('click',()=>{for(const card of cards)if(!card.hidden)card.open=true;});
document.querySelector('#collapse-all').addEventListener('click',()=>{for(const card of cards)card.open=false;});
function openLinkedRow(){let id;try{id=decodeURIComponent(location.hash.slice(1));}catch{return;}const card=document.getElementById(id);if(!card||!card.classList.contains('row-card'))return;if(card.hidden){search.value='';kind.value='';only.checked=false;applyFilters();}card.open=true;card.scrollIntoView({block:'start'});}
window.addEventListener('hashchange',openLinkedRow);
applyFilters();
openLinkedRow();
"""


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _e(value) -> str:
    return escape(str(value if value is not None else ""), quote=True)


def _csv(path: Path, rows: list[dict], columns: list[str]):
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            # Keep source values literal; spreadsheets must import this file as
            # text. The report itself never executes cell contents.
            writer.writerow({key: row.get(key, "") for key in columns})


def _truth_value(row: dict, field: str) -> str:
    return row.get("controls", {}).get(field, "") if field in KINDS else row.get(field, "")


def _cell_state(pred: dict | None, field: str) -> tuple[str, str]:
    if pred is None:
        return "", "missing_row"
    reading = pred.get("cells", {}).get(field)
    if reading is None:
        return "", "missing_cell"
    value = str(reading.get("text", ""))
    if reading.get("abstained"):
        return value, "abstained"
    return value, "blank" if not value.strip() else "value"


def _correct(row: dict, field: str, value: str, state: str) -> bool:
    if state not in ("blank", "value"):
        return False
    if field in KINDS and row.get("row_type") == "discipline":
        return control_semesters(value) == row.get("semesters", {}).get(field, [])
    return normalized(value) == normalized(_truth_value(row, field))


def _fact_sets(truth: dict, pred: dict | None):
    expected = (
        {
            (kind, semester)
            for kind in KINDS
            for semester in truth.get("semesters", {}).get(kind, [])
        }
        if truth.get("row_type") == "discipline"
        else set()
    )
    actual = set()
    if pred and pred.get("is_discipline"):
        for kind in KINDS:
            value, state = _cell_state(pred, kind)
            if state in ("value", "blank"):
                actual.update((kind, semester) for semester in (control_semesters(value) or []))
    return expected, actual


def _classification(truth: dict, pred: dict | None) -> tuple[str, str]:
    """Keep a missing decision distinct from a negative classification."""
    if pred is None or not isinstance(pred.get("is_discipline"), bool):
        return "missing", "Нет решения о типе строки"
    expected = truth.get("row_type") == "discipline"
    actual = pred["is_discipline"]
    if actual != expected:
        return (
            "mismatch",
            "Ошибка: дисциплина исключена"
            if expected
            else "Ошибка: раздел / итог принят за дисциплину",
        )
    return "correct", "Дисциплина: верно" if actual else "Раздел / итог: верно"


def _development_badge(result: dict) -> str:
    if (
        result.get("development_hypothesis")
        or result.get("scenario") == "hybrid_fields_development"
    ):
        return '<span class="tag warn">Development · настроено на этом GT</span>'
    return ""


def _baseline_problem(truth: dict, pred: dict | None) -> tuple[int, str]:
    expected, actual = _fact_sets(truth, pred)
    missing, extra = expected - actual, actual - expected
    code, code_state = _cell_state(pred, "discipline_code")
    name, name_state = _cell_state(pred, "discipline_name")
    code_bad = code_state not in ("blank", "value") or _code(code) != _code(
        truth.get("discipline_code", "")
    )
    name_bad = name_state not in ("blank", "value") or normalized(name) != normalized(
        truth.get("discipline_name", "")
    )
    control_bad = sum(not _correct(truth, kind, *_cell_state(pred, kind)) for kind in KINDS)
    classification_state, classification_label = _classification(truth, pred)
    # Fact loss in the reference parser, rather than a deliberately broken
    # no-deskew ablation, drives review priority. Section counts remain separate.
    score = 50 * len(missing) + 40 * len(extra)
    score += (
        30 if classification_state == "mismatch" else 25 if classification_state == "missing" else 0
    )
    if truth.get("row_type") == "discipline":
        score += 10 * code_bad + 8 * name_bad + 2 * control_bad
    else:
        score += min(5, control_bad)
    labels = []
    if missing:
        labels.append("потеряно фактов: " + str(len(missing)))
    if extra:
        labels.append("лишних фактов: " + str(len(extra)))
    if classification_state != "correct":
        labels.append(classification_label.lower())
    if truth.get("row_type") == "discipline" and code_bad:
        labels.append("ошибка индекса")
    if truth.get("row_type") == "discipline" and name_bad:
        labels.append("отличие названия")
    if control_bad:
        labels.append("ячеек контроля с отличиями: " + str(control_bad))
    return score, "; ".join(labels) or "совпадает с GT"


def _display_cell(truth: dict, pred: dict | None, field: str) -> str:
    value, state = _cell_state(pred, field)
    if state == "abstained":
        label = "Нет согласия"
        detail = '<small class="cell-note">Ансамбль воздержался; это не пустая ячейка.</small>'
        if value:
            detail += '<small class="cell-note">Сырое значение: ' + _e(value) + "</small>"
        return '<td class="warn">' + label + detail + "</td>"
    if state in ("missing_row", "missing_cell"):
        return (
            '<td class="warn">'
            + ("Строка не найдена" if state == "missing_row" else "Нет результата")
            + "</td>"
        )
    correct = _correct(truth, field, value, state)
    # Show literal spelling differences even if canonical control values agree.
    literal = normalized(value) == normalized(_truth_value(truth, field))
    cls = "bad" if not correct or not literal else ""
    content = _e(value) if value else '<span class="empty">Пусто</span>'
    if correct and not literal and field in KINDS:
        content += '<small class="cell-note">Семестры совпали; запись отличается.</small>'
    return '<td class="' + cls + '">' + content + "</td>"


def _timing(result: dict) -> tuple[str, str]:
    seconds = float(result.get("inference_seconds", 0))
    if result.get("members"):
        return (
            f"{seconds:.2f} с",
            "Сумма распознавания участников; объединение "
            + f"{float(result.get('fusion_seconds', 0)):.3f} с. "
            + ", ".join(result["members"]),
        )
    timing = result.get("timing", {})
    if result.get("batched"):
        description = "Пакетный OCR без кэша ячеек"
    else:
        kind = {"cold": "Холодный", "warm": "Кэш", "mixed": "Смешанный"}.get(
            timing.get("kind"), "Режим кэша не указан"
        )
        description = (
            kind + f"; попаданий в кэш {timing.get('cache_hits', 0)}/{timing.get('ocr_calls', 0)}"
        )
    if not result.get("rows"):
        description += "; строки не обнаружены"
    return f"{seconds:.2f} с", description


def _source_crops(pdf: Path, rows: list[dict], output: Path):
    import pypdfium2

    folder = output / "rows"
    folder.mkdir(parents=True, exist_ok=True)
    with pypdfium2.PdfDocument(pdf) as document:
        for number in sorted({row["page"] for row in rows}):
            if not 1 <= number <= len(document):
                raise ValueError(f"GT page outside source PDF: {number}")
            page = document[number - 1]
            width, height = page.get_size()
            scale = min(5, 6000 / max(width, height), math.sqrt(24_000_000 / (width * height)))
            bitmap = page.render(scale=scale, grayscale=True)
            image = bitmap.to_pil().copy()
            bitmap.close()
            page.close()
            try:
                for row in rows:
                    if row["page"] != number:
                        continue
                    x0, y0, x1, y1 = row["bbox"]
                    crop = image.crop(
                        (
                            math.floor(x0 * image.width),
                            math.floor(y0 * image.height),
                            math.ceil(x1 * image.width),
                            math.ceil(y1 * image.height),
                        )
                    )
                    try:
                        crop.save(folder / (row["row_id"] + ".png"))
                    finally:
                        crop.close()
            finally:
                image.close()


def render_report(pdf: Path, gt_paths: list[Path], results_dir: Path, output: Path) -> dict:
    """Write a standalone audit package; saved predictions are never modified."""
    source_hash = hashlib.sha256(pdf.read_bytes()).hexdigest()
    truth = []
    for path in gt_paths:
        page = _read_json(path)
        if page.get("source_sha256") != source_hash:
            raise ValueError(f"GT source hash mismatch: {path}")
        for row in page["rows"]:
            if not row.get("verified") or not re.fullmatch(
                r"[A-Za-z0-9_-]{1,80}", row.get("row_id", "")
            ):
                raise ValueError("GT rows must be verified and have safe unique IDs")
            bbox = row.get("bbox", [])
            if (
                len(bbox) != 4
                or not all(
                    isinstance(v, (int, float)) and math.isfinite(v) and 0 <= v <= 1 for v in bbox
                )
                or not (bbox[0] < bbox[2] and bbox[1] < bbox[3])
            ):
                raise ValueError(f"Invalid original-page GT bbox: {row['row_id']}")
            truth.append(dict(row, page=page["page"]))
    if not truth or len({row["row_id"] for row in truth}) != len(truth):
        raise ValueError("GT must contain unique, nonempty physical rows")
    truth.sort(key=lambda row: (row["page"], row["bbox"][1], row["row_id"]))
    results, metrics, mappings = {}, {}, {}
    for path in sorted(results_dir.glob("predictions-*.json")):
        result = _read_json(path)
        name = result.get("scenario", path.stem.removeprefix("predictions-"))
        if result.get("source_sha256") != source_hash:
            raise ValueError(f"Prediction source hash mismatch: {path}")
        if name in results:
            raise ValueError(f"Duplicate scenario name: {name}")
        results[name] = result
        metrics[name], _ = evaluate(truth, result["rows"])
        mappings[name], _ = align_rows(truth, result["rows"])
    if not results:
        raise ValueError("No predictions-*.json found")
    baseline = "baseline" if "baseline" in results else next(iter(results))
    best = max(
        results,
        key=lambda name: (
            metrics[name].get("fact_f1", 0),
            metrics[name].get("strict_identity_tp", 0),
            metrics[name].get("nonblank_control_accuracy", 0),
        ),
    )
    ensembles = [name for name in results if name.startswith("ensemble")]
    best_ensemble = (
        max(
            ensembles,
            key=lambda name: (
                metrics[name].get("fact_f1", 0),
                metrics[name].get("strict_identity_tp", 0),
            ),
        )
        if ensembles
        else None
    )
    defaults = {baseline, best, *[name for name in results if name.startswith("onnx")]}
    if best_ensemble:
        defaults.add(best_ensemble)
    # Keep at least one independently evaluated best checkpoint visible.
    if "best_clean6" in results:
        defaults.add("best_clean6")
    order = sorted(
        results,
        key=lambda name: (
            name != baseline,
            name != best,
            not name.startswith("onnx"),
            name != best_ensemble,
            name,
        ),
    )
    model_ids = {name: "m" + str(i) for i, name in enumerate(order)}
    output.mkdir(parents=True, exist_ok=True)
    if pdf.resolve() != (output / "source.pdf").resolve():
        shutil.copyfile(pdf, output / "source.pdf")
    _source_crops(pdf, truth, output)
    gt_csv = [
        {
            "page": row["page"],
            "row_id": row["row_id"],
            "row_type": row["row_type"],
            **{field: _truth_value(row, field) for field in FIELDS},
            "notes": row.get("notes", ""),
        }
        for row in truth
    ]
    _csv(output / "gt.csv", gt_csv, ["page", "row_id", "row_type", *FIELDS, "notes"])
    comparison = []
    ranked_rows = []
    for i, row in enumerate(truth):
        base_match = mappings[baseline].get(i)
        base_pred = results[baseline]["rows"][base_match[0]] if base_match else None
        score, reason = _baseline_problem(row, base_pred)
        ranked_rows.append((score, i, row, reason))
        for name in order:
            match = mappings[name].get(i)
            pred = results[name]["rows"][match[0]] if match else None
            classification_state, _ = _classification(row, pred)
            predicted_type = (
                pred["is_discipline"]
                if pred and isinstance(pred.get("is_discipline"), bool)
                else ""
            )
            record = {
                "page": row["page"],
                "row_id": row["row_id"],
                "row_type": row["row_type"],
                "scenario": name,
                "matched_row": bool(match),
                "y_iou": match[1] if match else 0,
                "expected_is_discipline": row["row_type"] == "discipline",
                "predicted_is_discipline": predicted_type,
                "classification_state": classification_state,
                "notes": row.get("notes", ""),
            }
            for field in FIELDS:
                value, state = _cell_state(pred, field)
                record["gt_" + field], record["ocr_" + field], record["state_" + field] = (
                    _truth_value(row, field),
                    value,
                    state,
                )
            comparison.append(record)
    comparison_columns = [
        "page",
        "row_id",
        "row_type",
        "scenario",
        "matched_row",
        "y_iou",
        "expected_is_discipline",
        "predicted_is_discipline",
        "classification_state",
        *[prefix + field for field in FIELDS for prefix in ("gt_", "ocr_", "state_")],
        "notes",
    ]
    _csv(output / "row_comparison.csv", comparison, comparison_columns)
    ranked_rows.sort(key=lambda item: (-item[0], item[1]))
    facts = sum(
        len(row.get("semesters", {}).get(kind, []))
        for row in truth
        if row["row_type"] == "discipline"
        for kind in KINDS
    )
    discipline_count = sum(row["row_type"] == "discipline" for row in truth)
    metrics_data = {
        "source_sha256": source_hash,
        "gt_rows": len(truth),
        "gt_discipline_facts": facts,
        "reference_scenario": baseline,
        "metrics_recomputed_from_saved_predictions": True,
        "results": [
            dict(
                metrics[name],
                scenario=name,
                inference_seconds=results[name].get("inference_seconds", 0),
            )
            for name in order
        ],
    }
    (output / "report-metrics.json").write_text(
        json.dumps(metrics_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    production_path = results_dir / "production-candidates.json"
    production = _read_json(production_path) if production_path.exists() else {}
    if production.get("source_sha256") not in (None, source_hash):
        raise ValueError("Production candidates source hash mismatch")
    candidates = production.get("assessments", [])
    if (
        production_path.exists()
        and production_path.resolve() != (output / production_path.name).resolve()
    ):
        shutil.copyfile(production_path, output / production_path.name)
    html = [
        '<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Аудит OCR учебного плана</title><style>',
        CSS,
        "</style></head><body><main>",
        '<header><div class="eyebrow">Matplobbot · проверка сканированного учебного плана</div><h1>Вся таблица, GT и результаты OCR</h1><p>Ручная разметка сверена с оригиналом. Здесь сохранены все физические строки, включая разделы и пустые ячейки. Часы и зачётные единицы не входят в разметку.</p></header>',
        '<div class="stats">',
    ]
    for number, label in (
        (len(truth), "строк GT"),
        (discipline_count, "дисциплин"),
        (len(truth) * len(KINDS), "ячеек контроля"),
        (facts, "фактов по дисциплинам"),
        (len(results), "OCR-сценариев"),
    ):
        html.append('<div class="stat"><strong>' + str(number) + "</strong>" + label + "</div>")
    html.extend(
        [
            '</div><nav class="downloads" aria-label="Файлы отчёта"><a href="source.pdf" target="_blank" rel="noopener">Оригинал PDF</a><a href="gt.csv" download>GT · CSV</a><a href="row_comparison.csv" download>Все сравнения · CSV</a><a href="report-metrics.json" download>Метрики · JSON</a><a href="#rows-section">К строкам</a><a href="#candidates">К кандидатам</a></nav>',
            '<section class="panel"><h2>Сравнение сценариев</h2><p class="muted">TP — верный факт, FP — лишний, FN — пропущенный. Факт — строка дисциплины, форма контроля и семестр. Строгая оценка дополнительно требует правильных индекса и названия. В оценке строк положительный класс — дисциплина; TN — верно исключённый раздел или итог. Отсутствующее решение считается отдельно, даже если все ячейки контроля пусты.</p><p class="scroll-hint">↔ На узком экране прокрутите таблицу вправо, чтобы увидеть все столбцы.</p><div class="table-scroll"><table class="metrics"><thead><tr><th>Сценарий</th><th>Непустые ячейки контроля</th><th>Факты TP / FP / FN</th><th>Строгие факты TP / FP / FN</th><th>Названия дисциплин</th><th>Строки TP / FP / FN / TN</th><th>Распознавание</th><th>Кэш / пояснение</th></tr></thead><tbody>',
        ]
    )
    for name in order:
        score, result = metrics[name], results[name]
        timing, timing_note = _timing(result)
        badges = (
            ('<span class="tag">Базовый</span>' if name == baseline else "")
            + ('<span class="tag">Макс. F1 фактов</span>' if name == best else "")
            + _development_badge(result)
        )
        html.append(
            "<tr"
            + (' class="featured"' if name in defaults else "")
            + "><td><strong>"
            + _e(name)
            + "</strong><br>"
            + badges
            + '</td><td class="metric-num">'
            + f"{score.get('nonblank_control_accuracy', 0):.1%}"
            + "<br><small>"
            + f"{score.get('nonblank_cells_exact', 0)} / {score.get('nonblank_cells', 0)}"
            + '</small></td><td class="metric-num">'
            + " / ".join(str(score.get("facts_" + key, 0)) for key in ("tp", "fp", "fn"))
            + '</td><td class="metric-num">'
            + " / ".join(str(score.get("strict_identity_" + key, 0)) for key in ("tp", "fp", "fn"))
            + '</td><td class="metric-num">'
            + f"{score.get('discipline_name_exact_only', 0)} / {discipline_count}"
            + "<br><small>ANLS "
            + f"{score.get('discipline_name_anls', 0):.3f}"
            + '</small></td><td class="metric-num">'
            + " / ".join(
                str(score.get("row_classifier_" + key, 0)) for key in ("tp", "fp", "fn", "tn")
            )
            + "<br><small>Нет решения: "
            + str(score.get("row_classifier_missing", 0))
            + '</small></td><td class="metric-num">'
            + timing
            + "</td><td>"
            + _e(timing_note)
            + "</td></tr>"
        )
    html.extend(
        [
            '</tbody></table></div><p class="notice">Время измерено на локальном CPU, а не на сервере. Попадания в кэш и сумма времени участников ансамбля показаны отдельно. Это проверка одного плана; она не измеряет качество на новых документах.</p><details><summary>Как читать оценку</summary><p>Строки сопоставляются однозначно по странице и пересечению вертикальных координат (IoU ≥ 0,45), без названий и индексов. GT не передаётся моделям. Метрики пересчитаны из сохранённых предсказаний при создании отчёта.</p><p>Пустая ячейка, отсутствующая строка и отказ ансамбля от ответа — разные состояния. Для дисциплин оцениваются семестры; у разделов и итогов — буквальная запись. Числа разделов не переносятся в дочерние дисциплины. «Строгие факты» используют нормализованный индекс и название.</p><p>Цвет ячейки также показывает буквальные отличия, даже если номера семестров совпали. Высокую общую точность может давать большое число пустых ячеек, поэтому основной столбец отдельно оценивает непустые.</p></details></section>'
        ]
    )
    if any(_development_badge(result) for result in results.values()):
        html.append(
            '<section class="panel notice"><h2>Development-сценарий: подбор на этом GT</h2><p>В <strong>hybrid_fields_development</strong> источники отдельных полей выбраны после сравнения на этом же GT. Отдельного набора для независимой проверки (held-out) нет. Результат показывает гипотезу для дальнейшей проверки и не является оценкой качества на новых документах. Само объединение не читает GT и не подставляет эталонные значения.</p></section>'
        )
    problems = [item for item in ranked_rows if item[0] and item[2]["row_type"] == "discipline"][
        :12
    ]
    html.append(
        '<section class="panel"><h2>Что проверить в первую очередь</h2><p class="muted">Приоритет рассчитан по базовому сценарию '
        + _e(baseline)
        + ': потери фактов, лишние факты, ошибки классификации строки, затем индекса, названия и ячеек. Сценарий без deskew не влияет на этот порядок.</p><ol class="problem-list">'
    )
    for _, _, row, reason in problems:
        html.append(
            '<li><a href="#'
            + _e(row["row_id"])
            + '">'
            + _e(row["discipline_name"])
            + '</a> <span class="tag">'
            + _e(row["row_id"])
            + "</span><br><small>"
            + _e(reason)
            + "</small></li>"
        )
    if not problems:
        html.append("<li>В базовом сценарии отличий дисциплин не обнаружено.</li>")
    html.append("</ol></section>")
    html.append(
        '<section class="panel" id="rows-section"><h2>Все строки таблицы</h2><div class="toolbar"><input id="search" type="search" aria-label="Поиск по названию, индексу или ID" placeholder="Название, индекс или ID строки"><select id="row-type" aria-label="Тип строки"><option value="">Все типы строк</option value="discipline">Дисциплины</option><option value="section">Разделы</option><option value="summary">Итоги</option></select><select id="row-order" aria-label="Порядок строк"><option value="problems">Сначала проблемные</option><option value="source">Как в документе</option></select></div><p class="checks"><label><input id="only-problems" type="checkbox">Только отличия базового сценария</label><span>Показано <span id="visible-count" class="count">'
        + str(len(truth))
        + "</span> из "
        + str(len(truth))
        + '</span></p><details><summary>Выбрать OCR-сценарии</summary><div class="models">'
    )
    for name in order:
        html.append(
            '<label><input type="checkbox" data-model-toggle="'
            + model_ids[name]
            + '"'
            + (" checked" if name in defaults else "")
            + ">"
            + _e(name)
            + _development_badge(results[name])
            + "</label>"
        )
    html.append(
        '</div></details><p class="legend"><span class="good">GT: проверено по скану</span><span class="bad">Отличие от GT</span><span class="warn">Нет ответа / нет согласия</span><span>Пусто: распознанное отсутствие значения</span></p><p class="scroll-hint">↔ Таблицы и фрагменты скана можно прокручивать вправо. Ошибка типа строки выделяется отдельно, даже при пустых ячейках.</p><div class="toolbar"><button id="expand-visible" type="button">Раскрыть найденные строки</button><button id="collapse-all" type="button">Свернуть всё</button></div></section><div id="no-results" class="no-results" hidden>Строки не найдены. Измените поиск или фильтр.</div><div id="rows">'
    )
    for position, (score, i, row, reason) in enumerate(ranked_rows):
        search_text = " ".join(
            str(row.get(key, ""))
            for key in ("row_id", "discipline_code", "discipline_name", "notes")
        ).lower()
        html.append(
            '<details class="row-card" id="'
            + _e(row["row_id"])
            + '" data-source="'
            + str(i)
            + '" data-score="'
            + str(score)
            + '" data-kind="'
            + _e(row["row_type"])
            + '" data-search="'
            + _e(search_text)
            + '"'
            + (" open" if position < 3 else "")
            + '><summary><span class="tag">'
            + _e(row["row_id"])
            + '</span><span class="tag">'
            + _e(ROW_TYPES.get(row["row_type"], row["row_type"]))
            + "</span><h3>"
            + _e(row["discipline_name"])
            + '</h3><span class="row-subtitle">Страница '
            + str(row["page"])
            + " · "
            + _e(row["discipline_code"] or "без индекса")
            + " · "
            + _e(reason)
            + "</span></summary>"
        )
        if row.get("notes"):
            html.append('<p class="notes">' + _e(row["notes"]) + "</p>")
        crop_path = "rows/" + row["row_id"] + ".png"
        html.append(
            '<figure class="crop"><a href="'
            + crop_path
            + '" target="_blank" rel="noopener"><img src="'
            + crop_path
            + '" alt="Оригинальная строка '
            + _e(row["row_id"])
            + '" loading="lazy"></a><figcaption>Исходный скан без deskew и обработки. Нажмите для полного размера. <a href="source.pdf#page='
            + str(row["page"])
            + '" target="_blank" rel="noopener">Страница в PDF</a></figcaption></figure><div class="table-scroll"><table class="compare"><thead><tr><th>Источник</th>'
            + "".join("<th>" + LABELS[field] + "</th>" for field in FIELDS)
            + '</tr></thead><tbody><tr class="gt"><td>GT · проверено</td>'
            + "".join(
                "<td>"
                + (_e(_truth_value(row, field)) or '<span class="empty">Пусто</span>')
                + "</td>"
                for field in FIELDS
            )
            + "</tr>"
        )
        for name in order:
            match = mappings[name].get(i)
            pred = results[name]["rows"][match[0]] if match else None
            classification_state, classification = _classification(row, pred)
            classification_css = (
                "bad"
                if classification_state == "mismatch"
                else "warn"
                if classification_state == "missing"
                else ""
            )
            html.append(
                '<tr data-model="'
                + model_ids[name]
                + '"'
                + (' class="hidden-model"' if name not in defaults else "")
                + '><td class="'
                + classification_css
                + '"><strong>'
                + _e(name)
                + "</strong>"
                + _development_badge(results[name])
                + '<small class="cell-note classification">'
                + classification
                + '</small><small class="cell-note">GT: '
                + _e(ROW_TYPES.get(row["row_type"], row["row_type"]))
                + "</small></td>"
                + "".join(_display_cell(row, pred, field) for field in FIELDS)
                + "</tr>"
            )
        html.append("</tbody></table></div></details>")
    html.append("</div>")
    dictionary_path = results_dir / "dictionary-metrics.json"
    if dictionary_path.exists():
        dictionary_metrics = _read_json(dictionary_path)
        independent = [
            entry
            for entry in dictionary_metrics
            if not entry.get("gt_leakage") and entry.get("scenario") in results
        ]
        if independent:
            html.append(
                '<section class="panel"><h2>Уточнение названий по независимому словарю</h2><p>Исходный OCR сохранён. Предложение принимается только при достаточной близости и отрыве от второго кандидата. Это лексическая подсказка, а не доказательство эквивалентности дисциплин.</p><details><summary>Все пороги и результаты</summary><div class="table-scroll"><table class="small-table"><thead><tr><th>Сценарий</th><th>Порог</th><th>Отрыв</th><th>Есть в словаре</th><th>Принято</th><th>Неверных предложений</th><th>Исправлено / испорчено</th><th>Итог верных</th></tr></thead><tbody>'
            )
            for entry in independent:
                html.append(
                    "<tr><td>"
                    + _e(entry["scenario"])
                    + "</td><td>"
                    + _e(entry.get("minimum_similarity"))
                    + "</td><td>"
                    + _e(entry.get("minimum_margin"))
                    + "</td><td>"
                    + str(entry.get("in_dictionary", 0))
                    + "</td><td>"
                    + str(entry.get("accepted", 0))
                    + "</td><td>"
                    + str(entry.get("accepted_wrong", 0))
                    + "</td><td>"
                    + str(entry.get("fixed", 0))
                    + " / "
                    + str(entry.get("hurt", 0))
                    + "</td><td>"
                    + str(entry.get("final_correct", 0))
                    + " / "
                    + str(entry.get("disciplines", 0))
                    + "</td></tr>"
                )
            html.append(
                '</tbody></table></div></details><p class="notice">Результаты со словарём, собранным из GT, намеренно не представлены как независимая проверка: это эксперимент с утечкой ответов.</p></section>'
            )
    html.append(
        '<section class="panel" id="candidates"><h2>Кандидаты текущего производственного парсера</h2><p>'
        + str(len(candidates))
        + " записей. Это сохранённый результат импорта до ручного подтверждения, отдельно от экспериментальных сценариев.</p>"
    )
    if production_path.exists():
        html.append(
            '<p><a href="production-candidates.json" download>Исходные кандидаты · JSON</a></p>'
        )
    if production.get("warnings"):
        html.append(
            "<details><summary>Предупреждения парсера ("
            + str(len(production["warnings"]))
            + ")</summary><ul>"
            + "".join("<li>" + _e(warning) + "</li>" for warning in production["warnings"])
            + "</ul></details>"
        )
    if candidates:
        html.append(
            '<details><summary>Показать все записи</summary><div class="table-scroll"><table class="candidates"><thead><tr><th>№</th><th>Стр.</th><th>Индекс</th><th>Дисциплина</th><th>Форма контроля</th><th>Семестр</th><th>Уверенность OCR</th></tr></thead><tbody>'
        )
        for number, candidate in enumerate(candidates, 1):
            html.append(
                "<tr><td>"
                + str(number)
                + "</td><td>"
                + _e(candidate.get("page"))
                + "</td><td>"
                + _e(candidate.get("discipline_code"))
                + "</td><td>"
                + _e(candidate.get("discipline_name"))
                + "</td><td>"
                + _e(LABELS.get(candidate.get("kind"), candidate.get("kind")))
                + "</td><td>"
                + _e(candidate.get("semester"))
                + "</td><td>"
                + _e(candidate.get("ocr", {}).get("confidence", "—"))
                + "</td></tr>"
            )
        html.append("</tbody></table></div></details>")
    html.append(
        '</section><footer><p>Источник SHA-256: <span class="source-hash">'
        + source_hash
        + "</span></p><p>Создано "
        + datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
        + ". Отчёт работает локально, без внешних библиотек и запросов. CSV использует UTF-8 с BOM; импортируйте значения как текст для сохранения индексов и запятых.</p></footer></main><script>"
        + JS
        + "</script></body></html>"
    )
    (output / "report.html").write_text("".join(html), encoding="utf-8")
    return {
        "report": str((output / "report.html").resolve()),
        "rows": len(truth),
        "scenarios": len(results),
        "comparison_records": len(comparison),
        "production_candidates": len(candidates),
        "source_sha256": source_hash,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--gt", type=Path, nargs="+", required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    print(
        json.dumps(
            render_report(args.pdf, args.gt, args.results, args.output),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

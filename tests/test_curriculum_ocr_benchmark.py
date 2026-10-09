"""Offline benchmark metric invariants; no PDF downloads or OCR subprocesses."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.benchmark_curriculum_ocr import (
    KINDS,
    OnnxEngine,
    align_rows,
    anls,
    consensus,
    deskew_bbox_to_original,
    ensemble,
    evaluate,
    evaluate_candidates,
    hybrid_fields_development,
    match_name,
    parse_tesseract_tsv,
    similarity,
)


def truth_row(row_id="r1", *, controls=None, kind="discipline", bbox=None):
    raw = {key: "" for key in KINDS}
    raw.update(controls or {"exam": "7"})
    return {
        "page": 1,
        "row_id": row_id,
        "row_type": kind,
        "discipline_code": "Б.1.1",
        "discipline_name": "Электронные деньги",
        "controls": raw,
        "semesters": {
            key: [int(value)] if value and kind == "discipline" else []
            for key, value in raw.items()
        },
        "bbox": bbox or [0, 0.2, 0.4, 0.3],
    }


def predicted(truth, **changes):
    cells = {field: {"text": truth[field]} for field in ("discipline_code", "discipline_name")}
    cells.update({key: {"text": value} for key, value in truth["controls"].items()})
    cells.update({key: {"text": value} for key, value in changes.items()})
    return {
        "page": truth["page"],
        "bbox": truth["bbox"],
        "cells": cells,
        "is_discipline": truth["row_type"] == "discipline",
    }


class BenchmarkMetricTests(unittest.TestCase):
    def test_anls_strict_half_distance_boundary(self):
        self.assertEqual(anls("ab", "ac"), 0)
        self.assertAlmostEqual(anls("abc", "abd"), 2 / 3)
        self.assertEqual(anls("SAME", "same"), 1)
        self.assertEqual(anls(" a", "a"), 0)
        self.assertEqual(anls("", ""), 1)
        self.assertEqual(similarity("ab", "ac"), 0.5)

    def test_dictionary_threshold_and_margin_preserve_raw(self):
        result = match_name("Семантические технологни", ["Семантические технологии", "Математика"])
        self.assertTrue(result["accepted"])
        self.assertEqual(result["raw"], "Семантические технологни")
        self.assertFalse(
            match_name("Дисциплина", ["Дисциплина 1", "Дисциплина 2"], minimum=0.7)["accepted"]
        )
        self.assertFalse(match_name("", ["Математика"])["accepted"])

    def test_views_of_same_model_do_not_form_ensemble_majority(self):
        value = consensus([{"family": "fast", "text": "7"}, {"family": "fast", "text": "7"}])
        self.assertTrue(value["abstained"])
        value = consensus([{"family": "fast", "text": "7"}, {"family": "best", "text": "7"}])
        self.assertFalse(value["abstained"])
        self.assertEqual(value["text"], "7")

    def test_family_internal_disagreement_abstains(self):
        result = consensus(
            [
                {"family": "fast", "text": "7"},
                {"family": "fast", "text": "1"},
                {"family": "best", "text": "7"},
            ]
        )
        self.assertTrue(result["abstained"])
        result = consensus([{"family": "a", "text": ""}, {"family": "b", "text": ""}])
        self.assertFalse(result["abstained"])
        result = consensus(
            [{"family": "a", "text": "", "abstained": True}, {"family": "b", "text": ""}]
        )
        self.assertTrue(result["abstained"])

    def test_semantic_vote_normalizes_only_unambiguous_values(self):
        result = consensus(
            [{"family": "a", "text": "2,4"}, {"family": "b", "text": "2 4"}], field="pass"
        )
        self.assertFalse(result["abstained"])
        result = consensus(
            [{"family": "a", "text": "24"}, {"family": "b", "text": "2 4"}], field="pass"
        )
        self.assertTrue(result["abstained"])
        result = consensus(
            [{"family": "a", "text": "6.1.1"}, {"family": "b", "text": "Б.1.1"}],
            field="discipline_code",
        )
        self.assertFalse(result["abstained"])
        result = consensus(
            [{"family": "a", "text": "24"}, {"family": "b", "text": "24"}], field="pass"
        )
        self.assertTrue(result["abstained"])
        result = consensus(
            [
                {"family": "a", "text": "Семантические технологни"},
                {"family": "b", "text": "Семантические технологии", "confidence": 90},
            ],
            field="discipline_name",
        )
        self.assertEqual(result["text"], "Семантические технологии")

    def test_geometry_does_not_match_by_name_or_reuse_a_row(self):
        first = truth_row()
        second = truth_row("r2", bbox=[0, 0.31, 0.4, 0.4])
        pred = predicted(second)
        matches, extra = align_rows([first, second], [pred])
        self.assertNotIn(0, matches)
        self.assertEqual(matches[1][0], 0)
        self.assertFalse(extra)

    def test_fact_recall_counts_omitted_rows_and_false_positive_blanks(self):
        first = truth_row()
        second = truth_row("r2", bbox=[0, 0.4, 0.4, 0.5])
        score, errors = evaluate([first, second], [predicted(first, **{"pass": "6"})])
        self.assertEqual(score["facts_tp"], 1)
        self.assertEqual(score["facts_fp"], 1)
        self.assertEqual(score["facts_fn"], 1)
        self.assertEqual(score["missing_rows"], 1)
        self.assertEqual(score["blank_false_positive"], 1)
        self.assertEqual(len(errors), 2)

    def test_section_counts_are_literal_cells_not_semester_facts(self):
        truth = truth_row(kind="section", controls={"exam": "30", "coursework": "1"})
        score, errors = evaluate([truth], [predicted(truth)])
        self.assertEqual(score["control_accuracy"], 1)
        self.assertEqual(score["gt_facts"], 0)
        self.assertEqual(score["nonblank_cells"], 2)
        self.assertFalse(errors)

    def test_consensus_abstention_is_not_correct_blank(self):
        truth = truth_row()
        pred = predicted(truth)
        pred["cells"]["pass"] = {"text": "", "abstained": True}
        score, errors = evaluate([truth], [pred])
        self.assertEqual(score["accepted_control_coverage"], 0.8)
        self.assertEqual(score["control_accuracy"], 0.8)
        self.assertTrue(errors)

    def test_missing_header_cell_is_not_a_correct_blank(self):
        truth = truth_row()
        pred = predicted(truth)
        del pred["cells"]["pass"]
        score, _ = evaluate([truth], [pred])
        self.assertEqual(score["control_accuracy"], 0.8)
        self.assertEqual(score["accepted_control_coverage"], 0.8)
        pred["prediction_id"] = "p1_r001"
        for reading in pred["cells"].values():
            reading["family"] = "a"
        second = predicted(truth)
        second["prediction_id"] = "p1_r001"
        del second["cells"]["pass"]
        for reading in second["cells"].values():
            reading["family"] = "b"
        voted = ensemble([{"rows": [pred]}, {"rows": [second]}])
        self.assertTrue(voted[0]["cells"]["pass"]["abstained"])

    def test_wrong_code_not_hidden_by_geometry_and_classifier_drop_visible(self):
        truth = truth_row()
        pred = predicted(truth, discipline_code="Б.1.2")
        score, _ = evaluate([truth], [pred])
        self.assertEqual(score["facts_tp"], 1)
        self.assertEqual(score["strict_code_tp"], 0)
        self.assertEqual(score["strict_code_fp"], 1)
        pred["is_discipline"] = False
        score, errors = evaluate([truth], [pred])
        self.assertEqual(score["facts_fn"], 1)
        self.assertTrue(any(d.get("dropped_by_row_classifier") for d in errors[0]["differences"]))

    def test_actual_candidates_scored_separately_and_existing_name_cleanup(self):
        truth = truth_row()
        pred = predicted(truth, discipline_name="Электронные деньги |")
        score, _ = evaluate([truth], [pred])
        self.assertEqual(score["name_accuracy"], 0)
        self.assertEqual(score["strict_identity_tp"], 1)
        candidate = {
            "page": 1,
            "discipline_code": "Б.1.2",
            "discipline_name": truth["discipline_name"],
            "kind": "exam",
            "semester": 7,
            "ocr": {"bbox": truth["bbox"]},
        }
        actual = evaluate_candidates([truth], [candidate])
        self.assertEqual(actual["scores"]["geometry"]["tp"], 1)
        self.assertEqual(actual["scores"]["strict_identity"]["fp"], 1)

    def test_development_hybrid_has_fixed_field_sources_without_gt(self):
        scenarios = {}
        for source in ("baseline", "best_clean6", "onnx_clean"):
            row = {
                "prediction_id": "p1_r001",
                "page": 1,
                "bbox": [0, 0, 1, 1],
                "cells": {
                    field: {"text": source + ":" + field}
                    for field in ("discipline_code", "discipline_name", *KINDS)
                },
            }
            scenarios[source] = {"rows": [row]}
        fused = hybrid_fields_development(scenarios)[0]["cells"]
        self.assertEqual(fused["discipline_code"]["text"], "best_clean6:discipline_code")
        self.assertEqual(fused["discipline_name"]["text"], "baseline:discipline_name")
        self.assertTrue(all(fused[kind]["text"] == "onnx_clean:" + kind for kind in KINDS))
        self.assertNotIn(
            "source_scenario", scenarios["baseline"]["rows"][0]["cells"]["discipline_name"]
        )

    def test_classifier_mismatch_visible_even_when_all_controls_blank(self):
        discipline = truth_row(controls={key: "" for key in KINDS})
        discipline_pred = predicted(discipline)
        discipline_pred["is_discipline"] = False
        section = truth_row(
            "r2", kind="section", controls={key: "" for key in KINDS}, bbox=[0, 0.5, 0.4, 0.6]
        )
        section_pred = predicted(section)
        section_pred["is_discipline"] = True
        score, errors = evaluate([discipline, section], [discipline_pred, section_pred])
        self.assertEqual(score["row_classifier_fn"], 1)
        self.assertEqual(score["row_classifier_fp"], 1)
        self.assertEqual(score["control_accuracy"], 1)
        self.assertEqual(score["gt_facts"], 0)
        self.assertEqual(len(errors), 2)
        self.assertTrue(
            all(any(d["field"] == "row_type" for d in row["differences"]) for row in errors)
        )
        missing_score, _ = evaluate([discipline, section], [])
        self.assertEqual(missing_score["row_classifier_missing"], 2)
        self.assertEqual(missing_score["row_classifier_missing_positive"], 1)
        self.assertEqual(missing_score["row_classifier_fn"], 0)

    def test_candidate_rotation_inversion_changes_alignment_when_required(self):
        geometry = {"width": 1000, "height": 1000, "deskew_degrees": 90}
        raw_bbox = [0.2, 0.8, 0.3, 0.9]
        expected_bbox = [0.1, 0.2, 0.2, 0.3]
        for actual, expected in zip(deskew_bbox_to_original(raw_bbox, geometry), expected_bbox):
            self.assertAlmostEqual(actual, expected)
        truth = truth_row(bbox=expected_bbox)
        candidate = {
            "page": 1,
            "discipline_code": truth["discipline_code"],
            "discipline_name": truth["discipline_name"],
            "kind": "exam",
            "semester": 7,
            "ocr": {"bbox": raw_bbox, "deskew_degrees": 90},
        }
        with self.assertRaises(ValueError):
            evaluate_candidates([truth], [candidate])
        score = evaluate_candidates([truth], [candidate], {1: geometry})
        self.assertEqual(score["scores"]["strict_identity"]["tp"], 1)
        self.assertEqual(score["candidate_alignments"][0]["gt_row_id"], "r1")

    def test_onnx_runtime_version_is_part_of_cache_fingerprint(self):
        with tempfile.TemporaryDirectory() as temporary:
            model = Path(temporary) / "model.onnx"
            model.write_bytes(b"test fixture only")
            with (
                patch("scripts.curriculum_ocr_onnx.OnnxCellRecognizer"),
                patch(
                    "scripts.benchmark_curriculum_ocr.package_version",
                    side_effect=["1.23.2", "1.24.0"],
                ),
            ):
                first = OnnxEngine(model, Path(temporary))
                second = OnnxEngine(model, Path(temporary))
            self.assertEqual(first.fingerprint["onnxruntime_version"], "1.23.2")
            self.assertIn("1.23.2", first.version)
            self.assertNotEqual(first.fingerprint, second.fingerprint)

    def test_tesseract_quotes_do_not_swallow_following_rows(self):
        tsv = 'level\tpage_num\tconf\ttext\n5\t1\t90\t"Анализ\n5\t1\t91\tданных"\n5\t1\t92\t7\n'
        rows = parse_tesseract_tsv(tsv)
        self.assertEqual([row["text"] for row in rows], ['"Анализ', 'данных"', "7"])
        self.assertEqual([row["conf"] for row in rows], ["90", "91", "92"])
        with self.assertRaises(RuntimeError):
            parse_tesseract_tsv("not tsv")


if __name__ == "__main__":
    unittest.main()

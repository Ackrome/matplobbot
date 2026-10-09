"""Offline regressions for the optional PP-OCR cell benchmark adapter."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import cv2
import numpy as np

from scripts import curriculum_ocr_onnx as ocr


def probabilities(labels, classes=4):
    scores = np.zeros((1, len(labels), classes), dtype=np.float32)
    for position, label in enumerate(labels):
        scores[0, position, label] = 0.9
    return scores


def fake_runtime(*, metadata="А\nБ", input_height="dynamic", classes=4):
    session = Mock()
    session.get_inputs.return_value = [
        SimpleNamespace(
            name="image", type="tensor(float)", shape=["batch", 3, input_height, "width"]
        )
    ]
    session.get_outputs.return_value = [SimpleNamespace(name="text", shape=[1, "steps", classes])]
    session.get_modelmeta.return_value = SimpleNamespace(
        custom_metadata_map={"character": metadata}
    )
    session.run.return_value = [probabilities([1, 1, 0, 2])]
    runtime = SimpleNamespace(
        InferenceSession=Mock(return_value=session),
        SessionOptions=Mock(side_effect=SimpleNamespace),
        ExecutionMode=SimpleNamespace(ORT_SEQUENTIAL="sequential"),
        RunOptions=Mock(side_effect=lambda: SimpleNamespace(terminate=False)),
    )
    return runtime, session


class OnnxCurriculumCellTests(unittest.TestCase):
    def test_ctc_repeats_are_collapsed_except_across_blank(self):
        text, confidence = ocr._decode_ctc(
            probabilities([0, 1, 1, 0, 1, 3, 2, 2]), ["", "А", "Б", " "]
        )
        self.assertEqual(text, "АА Б")
        self.assertEqual(len(confidence), 4)
        self.assertTrue(all(abs(value - 0.9) < 0.001 for value in confidence))

    def test_decoder_rejects_wrong_alphabet_and_nonprobabilities(self):
        with self.assertRaises(ValueError):
            ocr._decode_ctc(probabilities([1]), ["", "А"])
        bad = probabilities([1])
        bad[0, 0, 1] = np.nan
        with self.assertRaises(ValueError):
            ocr._decode_ctc(bad, ["", "А", "Б", " "])

    def test_blank_cells_and_sparse_speckles_do_not_reach_the_model(self):
        blank = np.full((80, 160), 255, np.uint8)
        blank[42, 42] = 0
        self.assertEqual(ocr._line_images(blank), [])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "model.onnx"
            path.write_bytes(b"mock model")
            runtime, session = fake_runtime()
            with patch.dict("sys.modules", {"onnxruntime": runtime}):
                result = ocr.OnnxCellRecognizer(path).recognize(blank)
        self.assertEqual(result["text"], "")
        self.assertEqual(result["confidence"], 0)
        session.run.assert_not_called()

    def test_wrapped_cell_is_split_in_visual_order(self):
        cell = np.full((95, 210), 255, np.uint8)
        cv2.putText(cell, "FIRST", (10, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.7, 0, 2)
        cv2.putText(cell, "SECOND", (10, 77), cv2.FONT_HERSHEY_SIMPLEX, 0.7, 0, 2)
        lines = ocr._line_images(cell)
        self.assertEqual(len(lines), 2)
        self.assertLess(lines[0].shape[1], lines[1].shape[1])
        self.assertTrue(all(np.all(line[0] == 255) for line in lines))

    def test_pixel_normalization_and_right_padding_follow_ppocr(self):
        cell = np.full((24, 48), 255, np.uint8)
        cell[:, :24] = 0
        tensor = ocr._normalized_input(cell)
        self.assertEqual(tensor.shape, (1, 3, 48, 320))
        self.assertEqual(tensor.dtype, np.float32)
        np.testing.assert_array_equal(tensor[0, 0], tensor[0, 2])
        self.assertEqual(float(tensor[0, 0, 20, 10]), -1)
        self.assertEqual(float(tensor[0, 0, 20, 80]), 1)
        self.assertEqual(float(tensor[0, 0, 20, 200]), 0)

    def test_oversized_or_non_gray_input_is_rejected(self):
        for cell in (
            np.zeros((1, 4100), np.uint8),
            np.zeros((1001, 1001), np.uint8),
            np.zeros((30, 30, 3), np.uint8),
            np.zeros((30, 30), np.float32),
        ):
            with self.subTest(shape=cell.shape), self.assertRaises(ValueError):
                ocr._line_images(cell)
        with self.assertRaises(ValueError):
            ocr._normalized_input(np.zeros((2, 200), np.uint8))

    def test_session_is_cpu_only_and_uses_embedded_alphabet(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "model.onnx"
            path.write_bytes(b"mock model")
            runtime, session = fake_runtime()
            with patch.dict("sys.modules", {"onnxruntime": runtime}):
                reader = ocr.OnnxCellRecognizer(path)
                cell = np.full((60, 120), 255, np.uint8)
                cv2.putText(cell, "7", (20, 45), cv2.FONT_HERSHEY_SIMPLEX, 1, 0, 2)
                result = reader.recognize(cell)
        kwargs = runtime.InferenceSession.call_args.kwargs
        self.assertEqual(kwargs["providers"], ["CPUExecutionProvider"])
        self.assertEqual(kwargs["sess_options"].intra_op_num_threads, 1)
        self.assertEqual(kwargs["sess_options"].inter_op_num_threads, 1)
        self.assertEqual(reader.alphabet, ["", "А", "Б", " "])
        self.assertEqual(result["text"], "АБ")
        self.assertAlmostEqual(result["confidence"], 90, places=3)
        self.assertEqual(result["family"], "ppocr_v5_eslav")
        self.assertGreaterEqual(result["seconds"], 0)
        self.assertEqual(len(reader.model_sha256), 64)
        self.assertEqual(session.run.call_args.args[0], ["text"])

    def test_wrong_model_metadata_and_fixed_height_fail_explicitly(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "model.onnx"
            path.write_bytes(b"mock model")
            for kwargs in ({"metadata": ""}, {"classes": 5}, {"input_height": 32}):
                runtime, _ = fake_runtime(**kwargs)
                with (
                    self.subTest(kwargs=kwargs),
                    patch.dict("sys.modules", {"onnxruntime": runtime}),
                ):
                    with self.assertRaises(ValueError):
                        ocr.OnnxCellRecognizer(path)

    def test_expired_runtime_is_reported_as_timeout(self):
        class ExpiringTimer:
            def __init__(self, seconds, callback):
                self.callback = callback

            def start(self):
                self.callback()

            def cancel(self):
                pass

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "model.onnx"
            path.write_bytes(b"mock model")
            runtime, session = fake_runtime()
            session.run.side_effect = RuntimeError("ORT run terminated")
            with patch.dict("sys.modules", {"onnxruntime": runtime}):
                reader = ocr.OnnxCellRecognizer(path)
                cell = np.full((60, 120), 255, np.uint8)
                cv2.putText(cell, "7", (20, 45), cv2.FONT_HERSHEY_SIMPLEX, 1, 0, 2)
                with (
                    patch.object(ocr.threading, "Timer", ExpiringTimer),
                    self.assertRaises(TimeoutError),
                ):
                    reader.recognize(cell)


if __name__ == "__main__":
    unittest.main()

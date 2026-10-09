"""Train/export tiny numeric CNN+CTC using generated fonts only, never PDFs/GT."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import sys
import time
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from shared_lib.services.curriculum_numeric import ALPHABET, HEIGHT, decode_ctc, prepare_cell


@lru_cache(maxsize=2048)
def load_font(path, size):
    from PIL import ImageFont

    return ImageFont.truetype(path, size)


def synthetic_cell(seed, fonts, *, stress=False):
    """Draw a numeric string with independently sampled scan degradation."""
    import cv2
    import numpy as np
    from PIL import Image, ImageDraw

    rng = random.Random(seed)
    nrng = np.random.default_rng(seed)
    choice = rng.random()
    if choice < 0.08:
        text = ""
    elif choice < 0.48:
        text = str(rng.randrange(10))
    elif choice < 0.76:
        text = ",".join(str(rng.randrange(10)) for _ in range(rng.randint(2, 6)))
    elif choice < 0.90:
        text = str(rng.randrange(10, 100))
    elif choice < 0.97:
        text = f"{rng.randrange(10)}-{rng.randrange(10)}"
    else:
        text = "-"
    font = load_font(rng.choice(fonts), rng.randint(18, 38))
    box = font.getbbox(text or "1")
    tw, th = max(1, box[2] - box[0]), max(1, box[3] - box[1])
    px, py = rng.randint(6, 20), rng.randint(6, 16)
    width, height = max(35, tw + 2 * px), max(32, th + 2 * py)
    background = rng.randint(205, 255)
    image = Image.new("L", (width, height), background)
    if text:
        ImageDraw.Draw(image).text(
            (px - box[0], py - box[1]),
            text,
            font=font,
            fill=rng.randint(0, 95),
            stroke_width=int(rng.random() < 0.12),
        )
    array = np.array(image)
    scale_x = rng.uniform(0.72, 1.3)
    array = cv2.resize(
        array, (max(10, round(width * scale_x)), height), interpolation=cv2.INTER_AREA
    )
    h, w = array.shape
    angle = rng.uniform(-3.5, 3.5) if stress else rng.uniform(-2.0, 2.0)
    array = cv2.warpAffine(
        array, cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1), (w, h), borderValue=background
    )
    if rng.random() < 0.5:
        small = rng.uniform(0.55 if stress else 0.7, 1)
        array = cv2.resize(
            cv2.resize(array, (max(10, round(w * small)), max(10, round(h * small)))), (w, h)
        )
    if rng.random() < 0.45:
        array = cv2.GaussianBlur(array, (3, 3), rng.uniform(0.25, 0.9 if stress else 0.65))
    # Uneven paper/scan background, grain and a few isolated dark specks.
    noise = nrng.normal(0, rng.uniform(1, 11 if stress else 7), array.shape)
    gradient = np.linspace(rng.uniform(-12, 6), rng.uniform(-6, 12), w)[None, :]
    array = np.clip(array.astype(float) + noise + gradient, 0, 255).astype(np.uint8)
    if rng.random() < 0.30:
        for _ in range(rng.randint(1, 4)):
            array[rng.randrange(h), rng.randrange(w)] = rng.randint(0, 160)
    if rng.random() < 0.25:
        # Border remnants are position-independent of the generated answer.
        edge = rng.choice((0, 1, h - 2, h - 1))
        cv2.line(array, (0, edge), (w - 1, edge), rng.randint(0, 130), rng.randint(1, 2))
    tensor, _ = prepare_cell(array)
    return tensor[0], text


class SyntheticDataset:
    def __init__(self, count, fonts, seed, stress=False):
        self.count, self.fonts, self.seed, self.stress = count, fonts, seed, stress

    def __len__(self):
        return self.count

    def __getitem__(self, index):
        # No external answer or image paths enter synthesis.
        for attempt in range(12):
            try:
                return synthetic_cell(
                    self.seed + index + attempt * 100_000_007, self.fonts, stress=self.stress
                )
            except ValueError as exc:
                if "too wide" not in str(exc):
                    raise
        raise ValueError("Could not generate a bounded synthetic numeric cell.")


def collate(items):
    import numpy as np
    import torch

    widths = [image.shape[2] for image, _ in items]
    x = np.zeros((len(items), 1, HEIGHT, max(widths)), dtype=np.float32)
    targets, lengths = [], []
    for i, (image, text) in enumerate(items):
        x[i, :, :, : image.shape[2]] = image
        targets.extend(ALPHABET.index(char) + 1 for char in text)
        lengths.append(len(text))
    return (
        torch.from_numpy(x),
        torch.tensor(targets),
        torch.tensor(widths) // 4,
        torch.tensor(lengths),
        [text for _, text in items],
    )


def make_model():
    from torch import nn

    class TinyNumeric(nn.Module):
        def __init__(self):
            super().__init__()
            layers = []
            previous = 1
            for channels, stride in [(16, (2, 2)), (32, (2, 2)), (48, (2, 1)), (64, (2, 1))]:
                layers.extend(
                    [
                        nn.Conv2d(previous, channels, 3, stride, padding=1, bias=False),
                        nn.BatchNorm2d(channels),
                        nn.ReLU(),
                    ]
                )
                previous = channels
            self.features = nn.Sequential(*layers)
            self.sequence = nn.Sequential(
                nn.Conv1d(64 * 3, 96, 3, padding=1),
                nn.ReLU(),
                nn.Conv1d(96, 64, 3, padding=2, dilation=2),
                nn.ReLU(),
                nn.Conv1d(64, len(ALPHABET) + 1, 1),
            )

        def forward(self, x):
            features = self.features(x).flatten(1, 2)
            return self.sequence(features).transpose(1, 2)

    return TinyNumeric()


def validate(model, loader, device):
    import torch

    results = []
    model.eval()
    with torch.inference_mode():
        for images, _, widths, _, texts in loader:
            probs = model(images.to(device)).softmax(-1).cpu().numpy()
            for p, length, target in zip(probs, widths, texts):
                pred, confidence = decode_ctc(p[: int(length)])
                results.append({"expected": target, "predicted": pred, "confidence": confidence})
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fonts", type=Path, default=Path("C:/Windows/Fonts"))
    parser.add_argument("--package-path", action="append", default=[])
    parser.add_argument("--steps", type=int, default=4000)
    parser.add_argument("--batch-size", type=int, default=96)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--seed", type=int, default=419031)
    parser.add_argument("--validation-count", type=int, default=2000)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    args = parser.parse_args(argv)
    sys.path[:0] = args.package_path
    import numpy as np
    import torch
    from torch.utils.data import DataLoader

    torch.manual_seed(args.seed)
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.set_num_threads(4)
    torch.backends.cudnn.benchmark = False
    train_names = [
        "arial.ttf",
        "arialbd.ttf",
        "ariali.ttf",
        "times.ttf",
        "timesbd.ttf",
        "timesi.ttf",
        "calibri.ttf",
        "calibrib.ttf",
        "tahoma.ttf",
        "tahomabd.ttf",
        "verdana.ttf",
        "verdanab.ttf",
        "segoeui.ttf",
        "segoeuib.ttf",
        "ARIALN.TTF",
        "ARIALNB.TTF",
        "cambria.ttc",
        "consola.ttf",
        "cour.ttf",
        "courbd.ttf",
        "couri.ttf",
        "consolab.ttf",
        "cambriab.ttf",
    ]
    valid_names = [
        "arialbi.ttf",
        "timesbi.ttf",
        "consolai.ttf",
        "calibril.ttf",
        "verdana.ttf",
        "arial.ttf",
    ]
    fonts = [str(args.fonts / name) for name in train_names if (args.fonts / name).is_file()]
    val_fonts = [str(args.fonts / name) for name in valid_names if (args.fonts / name).is_file()]
    if len(fonts) < 4 or len(val_fonts) < 2:
        raise ValueError("Expected multiple independently varied fonts.")
    args.output.mkdir(parents=True, exist_ok=True)
    training = SyntheticDataset(args.steps * args.batch_size, fonts, args.seed)
    validation = SyntheticDataset(args.validation_count, val_fonts, args.seed + 10_000_000)
    loader = DataLoader(
        training,
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=args.workers,
        collate_fn=collate,
        persistent_workers=args.workers > 0,
    )
    val_loader = DataLoader(
        validation,
        batch_size=args.batch_size,
        num_workers=args.workers,
        collate_fn=collate,
        persistent_workers=args.workers > 0,
    )
    model = make_model().to(args.device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.002, weight_decay=0.0001)
    criterion = torch.nn.CTCLoss(blank=0, zero_infinity=False)
    started = time.monotonic()
    loss_sum = 0
    for step, (images, targets, widths, lengths, _) in enumerate(loader, 1):
        model.train()
        lr = 0.002 * (0.10 + 0.90 * 0.5 * (1 + math.cos(math.pi * (step - 1) / args.steps)))
        optimizer.param_groups[0]["lr"] = lr
        optimizer.zero_grad(set_to_none=True)
        logits = model(images.to(args.device))
        loss = criterion(
            logits.log_softmax(-1).transpose(0, 1), targets.to(args.device), widths, lengths
        )
        if not torch.isfinite(loss):
            raise RuntimeError("Non-finite CTC training loss.")
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 5)
        optimizer.step()
        loss_sum += float(loss.detach())
        if step % 50 == 0:
            print(
                json.dumps(
                    {"step": step, "loss": loss_sum / 50, "seconds": time.monotonic() - started}
                ),
                flush=True,
            )
            loss_sum = 0
        if step % 500 == 0:
            metrics = validate(model, val_loader, args.device)
            correct = sum(r["expected"] == r["predicted"] for r in metrics)
            print(
                json.dumps({"validation_step": step, "exact": correct, "total": len(metrics)}),
                flush=True,
            )
            torch.save(model.state_dict(), args.output / f"step-{step}.pt")
    validation_rows = validate(model, val_loader, args.device)
    (args.output / "synthetic-validation.json").write_text(
        json.dumps(validation_rows, indent=2), encoding="utf-8"
    )
    torch.save(model.state_dict(), args.output / "weights.pt")
    model = model.cpu().eval()
    dummy = torch.zeros((1, 1, HEIGHT, 128))
    model_path = args.output / "curriculum_numeric.onnx"
    torch.onnx.export(
        model,
        dummy,
        str(model_path),
        input_names=["image"],
        output_names=["logits"],
        dynamic_axes={"image": {0: "batch", 3: "width"}, "logits": {0: "batch", 1: "time"}},
        opset_version=17,
        dynamo=False,
    )
    threshold = 0.90
    accepted = [r for r in validation_rows if r["confidence"] >= threshold]
    metadata = {
        "architecture": "tiny_convolutional_ctc_v2_height_preserved",
        "alphabet": ALPHABET,
        "blank_index": 0,
        "synthetic_only": True,
        "training_seed": args.seed,
        "validation_seed": args.seed + 10_000_000,
        "training_sources": [
            "Procedural PIL/font rendering only; no PDFs, OCR predictions or real GT.",
            *fonts,
        ],
        "validation_fonts": val_fonts,
        "training_steps": args.steps,
        "batch_size": args.batch_size,
        "training_examples": len(training),
        "parameters": sum(p.numel() for p in model.parameters()),
        "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "preprocessing_sha256": hashlib.sha256(
            (ROOT / "shared_lib/services/curriculum_numeric.py").read_bytes()
        ).hexdigest(),
        "sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
        "confidence_threshold": threshold,
        "synthetic_validation": {
            "count": len(validation_rows),
            "exact": sum(r["expected"] == r["predicted"] for r in validation_rows),
            "accepted": len(accepted),
            "accepted_correct": sum(r["expected"] == r["predicted"] for r in accepted),
        },
        "training_device": args.device,
        "inference_device": "CPUExecutionProvider",
        "torch_version": torch.__version__,
        "model_bytes": model_path.stat().st_size,
        "elapsed_seconds": time.monotonic() - started,
    }
    metadata["model_sha256"] = metadata["sha256"]
    (args.output / "curriculum_numeric.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(metadata, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()

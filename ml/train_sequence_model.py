"""Huấn luyện GRU/1D-CNN nhỏ trên cửa sổ chuỗi và xuất TFLite."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import SEQ_LABELS
from ml.seq_dataset import load_dataset, stack_xy


def build_model(input_shape: tuple[int, int], n_classes: int, kind: str = "gru"):
    """Tạo mô hình nhỏ; TensorFlow chỉ được import khi thực sự huấn luyện."""
    import tensorflow as tf
    from tensorflow import keras
    from tensorflow.keras import layers

    inputs = keras.Input(shape=input_shape)
    if kind == "gru":
        features = layers.GRU(48, return_sequences=False)(inputs)
    elif kind == "cnn":
        features = layers.Conv1D(32, 3, activation="relu", padding="same")(inputs)
        features = layers.Conv1D(64, 3, activation="relu", padding="same")(features)
        features = layers.GlobalAveragePooling1D()(features)
    else:
        raise ValueError("kind phải là 'gru' hoặc 'cnn'.")
    features = layers.Dropout(0.3)(features)
    outputs = layers.Dense(n_classes, activation="softmax")(features)
    model = keras.Model(inputs, outputs)
    model.compile(
        optimizer=keras.optimizers.Adam(1e-3),
        loss="sparse_categorical_crossentropy",
        metrics=["accuracy"],
    )
    return model


def class_weights_from_y(y: np.ndarray, n_classes: int) -> dict[int, float]:
    counts = np.bincount(y, minlength=n_classes).astype(np.float64)
    counts[counts == 0] = 1.0
    weights = 1.0 / counts
    weights *= counts.sum() / n_classes
    return {index: float(weights[index]) for index in range(n_classes)}


def evaluate_and_report(
    y_true: np.ndarray, y_prob: np.ndarray, labels=SEQ_LABELS
) -> None:
    from sklearn.metrics import classification_report, confusion_matrix

    y_pred = y_prob.argmax(axis=1)
    label_indices = list(range(len(labels)))
    print(
        classification_report(
            y_true,
            y_pred,
            labels=label_indices,
            target_names=list(labels),
            digits=3,
            zero_division=0,
        )
    )
    print("Confusion matrix:")
    print(confusion_matrix(y_true, y_pred, labels=label_indices))


def export_tflite(model, path: Path) -> None:
    import tensorflow as tf

    path.parent.mkdir(parents=True, exist_ok=True)
    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    tflite_model = converter.convert()
    path.write_bytes(tflite_model)
    print(f"Exported {path} ({len(tflite_model)} bytes)")


def parse_pairs(raw: list[str]) -> list[tuple[Path, Path, str]]:
    """Parse feature.csv:labels.csv:subject, including Windows drive paths."""
    pairs = []
    for item in raw:
        parts = re.split(r":(?![\\/])", item)
        if len(parts) != 3:
            raise ValueError(
                f"pair phải dạng feature.csv:label.csv:subject_id, nhận '{item}'"
            )
        pairs.append((Path(parts[0]), Path(parts[1]), parts[2]))
    return pairs


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Huấn luyện mô hình chuỗi buồn ngủ.")
    parser.add_argument(
        "--pair",
        action="append",
        required=True,
        help="feature.csv:label.csv:subject_id (lặp lại)",
    )
    parser.add_argument("--model", choices=("gru", "cnn"), default="gru")
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "models" / "sequence_model.tflite",
    )
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)
    if args.epochs <= 0 or args.batch_size <= 0:
        parser.error("--epochs và --batch-size phải > 0.")

    train_windows, validation_windows, test_windows = load_dataset(
        parse_pairs(args.pair), seed=args.seed
    )
    x_train, y_train = stack_xy(train_windows)
    x_validation, y_validation = stack_xy(validation_windows)
    x_test, y_test = stack_xy(test_windows)

    model = build_model(x_train.shape[1:], len(SEQ_LABELS), kind=args.model)
    weights = class_weights_from_y(y_train, len(SEQ_LABELS))
    import tensorflow as tf
    from tensorflow import keras

    callbacks = [
        keras.callbacks.EarlyStopping(
            monitor="val_loss",
            patience=8,
            restore_best_weights=True,
        )
    ]
    model.fit(
        x_train,
        y_train,
        validation_data=(x_validation, y_validation),
        epochs=args.epochs,
        batch_size=args.batch_size,
        class_weight=weights,
        callbacks=callbacks,
        verbose=2,
    )

    print("--- Validation ---")
    evaluate_and_report(y_validation, model.predict(x_validation, verbose=0))
    print("--- Test ---")
    evaluate_and_report(y_test, model.predict(x_test, verbose=0))
    export_tflite(model, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

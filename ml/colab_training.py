"""Reusable Colab training helpers; dataset-specific configuration stays in notebooks."""

from dataclasses import dataclass
import hashlib
from pathlib import Path
import random
import re
from typing import Callable, Sequence

import cv2
import numpy as np


@dataclass(frozen=True)
class SampleRecord:
    path: str
    label: int
    subject_id: str


def scan_mrl_eye_dataset(
    root: str | Path,
    *,
    state_field_index: int = 3,
    closed_value: str = "0",
    open_value: str = "1",
) -> list[SampleRecord]:
    """Read MRL eye crops and derive identity/state from standard filenames."""
    root = Path(root)
    if not root.is_dir():
        raise FileNotFoundError(f"Không tìm thấy thư mục MRL Eye: {root}")
    records = []
    errors = []
    for path in sorted(_image_paths(root)):
        fields = path.stem.split("_")
        subject_match = re.fullmatch(r"s\d+", fields[0], re.IGNORECASE)
        if subject_match is None:
            errors.append(f"{path.name}: không đọc được subject ID (field đầu).")
            continue
        folder_label = _label_from_directories(path.parent, root)
        if folder_label is not None:
            label = folder_label
        elif 0 <= state_field_index < len(fields):
            state = fields[state_field_index]
            if state == closed_value:
                label = 1
            elif state == open_value:
                label = 0
            else:
                errors.append(f"{path.name}: eye state '{state}' chưa được map.")
                continue
        else:
            errors.append(
                f"{path.name}: thiếu field state index {state_field_index}."
            )
            continue
        records.append(SampleRecord(str(path), label, fields[0].lower()))
    if errors:
        raise ValueError(
            "Không phân loại được MRL Eye. Kiểm tra cấu trúc/tên file và cấu hình "
            f"parser. Một số lỗi: {'; '.join(errors[:5])}"
        )
    _require_records(records, root)
    return records


def split_by_subject(
    records: Sequence[SampleRecord],
    *,
    train_fraction: float = 0.70,
    validation_fraction: float = 0.15,
    seed: int = 42,
) -> tuple[list[SampleRecord], list[SampleRecord], list[SampleRecord]]:
    """Split approximate sample ratios while keeping each subject in one set."""
    test_fraction = 1.0 - train_fraction - validation_fraction
    if (
        not 0 < train_fraction < 1
        or not 0 < validation_fraction < 1
        or not 0 < test_fraction < 1
    ):
        raise ValueError("Train/validation/test fractions must all be positive.")
    if not records:
        raise ValueError("No samples are available to split.")

    by_subject: dict[str, list[SampleRecord]] = {}
    for record in records:
        by_subject.setdefault(record.subject_id, []).append(record)
    if len(by_subject) < 3:
        raise ValueError("At least 3 distinct subjects are required for a split.")

    rng = random.Random(seed)
    subjects = list(by_subject)
    rng.shuffle(subjects)
    subjects.sort(key=lambda subject: len(by_subject[subject]), reverse=True)

    fractions = (train_fraction, validation_fraction, test_fraction)
    target_counts = [len(records) * fraction for fraction in fractions]
    split_subjects: list[list[str]] = [[], [], []]
    split_counts = [0, 0, 0]

    for index, subject in enumerate(subjects):
        empty_splits = [
            split_index
            for split_index, group in enumerate(split_subjects)
            if not group
        ]
        remaining_subjects = len(subjects) - index
        candidates = empty_splits if remaining_subjects == len(empty_splits) else range(3)
        selected = max(
            candidates,
            key=lambda split_index: target_counts[split_index] - split_counts[split_index],
        )
        split_subjects[selected].append(subject)
        split_counts[selected] += len(by_subject[subject])

    return tuple(
        [
            record
            for subject in subjects_for_split
            for record in by_subject[subject]
        ]
        for subjects_for_split in split_subjects
    )


def make_tf_dataset(
    records: Sequence[SampleRecord],
    *,
    image_size: tuple[int, int],
    batch_size: int,
    training: bool,
):
    """Create a streaming TensorFlow dataset; augmentation is train-only."""
    import tensorflow as tf

    if not records:
        raise ValueError("Dataset split is empty.")
    paths = [record.path for record in records]
    labels = [record.label for record in records]
    dataset = tf.data.Dataset.from_tensor_slices((paths, labels))

    def load_image(path, label):
        encoded = tf.io.read_file(path)
        image = tf.io.decode_image(encoded, channels=3, expand_animations=False)
        image.set_shape((None, None, 3))
        image = tf.image.resize(image, image_size)
        image = tf.cast(image, tf.float32)
        if training:
            image = tf.image.random_flip_left_right(image)
            image = tf.image.random_brightness(image, max_delta=16.0)
            image = tf.image.random_contrast(image, lower=0.8, upper=1.2)
            image = tf.clip_by_value(image, 0.0, 255.0)
        return image, tf.cast(label, tf.float32)

    dataset = dataset.map(load_image, num_parallel_calls=tf.data.AUTOTUNE)
    if training:
        dataset = dataset.shuffle(min(len(records), 8192), reshuffle_each_iteration=True)
    return dataset.batch(batch_size).prefetch(tf.data.AUTOTUNE)


def train_mobilenet_binary(
    train_dataset,
    validation_dataset,
    *,
    image_size: tuple[int, int],
    epochs_per_stage: int = 20,
):
    """Train a sigmoid classifier in frozen-head and fine-tuning stages."""
    import tensorflow as tf

    base = tf.keras.applications.MobileNetV2(
        input_shape=(*image_size, 3),
        include_top=False,
        weights="imagenet",
    )
    base.trainable = False
    inputs = tf.keras.Input(shape=(*image_size, 3))
    normalized = tf.keras.layers.Rescaling(1 / 127.5, offset=-1)(inputs)
    features = base(normalized, training=False)
    features = tf.keras.layers.GlobalAveragePooling2D()(features)
    features = tf.keras.layers.Dropout(0.25)(features)
    outputs = tf.keras.layers.Dense(1, activation="sigmoid")(features)
    model = tf.keras.Model(inputs, outputs)
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=1e-3),
        loss="binary_crossentropy",
        metrics=[
            tf.keras.metrics.BinaryAccuracy(name="accuracy"),
            tf.keras.metrics.Precision(name="precision"),
            tf.keras.metrics.Recall(name="recall"),
        ],
    )
    model.fit(
        train_dataset,
        validation_data=validation_dataset,
        epochs=epochs_per_stage,
        callbacks=[
            tf.keras.callbacks.EarlyStopping(
                monitor="val_loss", patience=4, restore_best_weights=True
            )
        ],
    )

    base.trainable = True
    for layer in base.layers[:-30]:
        layer.trainable = False
    for layer in base.layers:
        if isinstance(layer, tf.keras.layers.BatchNormalization):
            layer.trainable = False
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=1e-4),
        loss="binary_crossentropy",
        metrics=[
            tf.keras.metrics.BinaryAccuracy(name="accuracy"),
            tf.keras.metrics.Precision(name="precision"),
            tf.keras.metrics.Recall(name="recall"),
        ],
    )
    model.fit(
        train_dataset,
        validation_data=validation_dataset,
        epochs=epochs_per_stage,
        callbacks=[
            tf.keras.callbacks.EarlyStopping(
                monitor="val_loss", patience=4, restore_best_weights=True
            )
        ],
    )
    return model


def report_binary_metrics(model, test_dataset):
    """Print test precision/recall/F1 and draw confusion matrix and ROC."""
    import matplotlib.pyplot as plt

    actual = np.concatenate([labels.numpy().astype(np.int32) for _, labels in test_dataset])
    probabilities = model.predict(test_dataset, verbose=0).reshape(-1)
    metrics = compute_binary_metrics(actual, probabilities)
    confusion = metrics["confusion_matrix"]
    for label, name in ((0, "negative"), (1, "positive")):
        values = metrics["per_class"][label]
        print(
            f"{name}: precision={values['precision']:.4f}, "
            f"recall={values['recall']:.4f}, F1={values['f1']:.4f}"
        )
    print("Confusion matrix (rows=actual, columns=predicted):\n", confusion)

    false_positive_rates = metrics["false_positive_rates"]
    true_positive_rates = metrics["true_positive_rates"]
    auc = metrics["roc_auc"]

    figure, axes = plt.subplots(1, 2, figsize=(10, 4))
    axes[0].imshow(confusion, cmap="Blues")
    axes[0].set(
        title="Confusion matrix",
        xlabel="Predicted",
        ylabel="Actual",
        xticks=(0, 1),
        yticks=(0, 1),
    )
    for (row, column), value in np.ndenumerate(confusion):
        axes[0].text(column, row, str(value), ha="center", va="center")
    axes[1].plot(false_positive_rates, true_positive_rates, label=f"AUC={auc:.4f}")
    axes[1].plot((0, 1), (0, 1), linestyle="--")
    axes[1].set(
        title="ROC",
        xlabel="False positive rate",
        ylabel="True positive rate",
        xlim=(0, 1),
        ylim=(0, 1),
    )
    axes[1].legend()
    plt.tight_layout()
    plt.show()
    return confusion, auc


def compute_binary_metrics(actual, probabilities):
    """Compute binary metrics and ROC points without plotting dependencies."""
    actual = np.asarray(actual, dtype=np.int32).reshape(-1)
    probabilities = np.asarray(probabilities, dtype=np.float64).reshape(-1)
    if actual.size == 0 or actual.size != probabilities.size:
        raise ValueError("Actual labels and probabilities must be non-empty and aligned.")
    if set(np.unique(actual)) != {0, 1}:
        raise ValueError("Test split cần có mẫu của cả hai lớp để tính ROC.")
    if not np.all(np.isfinite(probabilities)) or np.any(
        (probabilities < 0) | (probabilities > 1)
    ):
        raise ValueError("Probabilities must be finite values in [0, 1].")

    predicted = (probabilities >= 0.5).astype(np.int32)
    confusion = np.zeros((2, 2), dtype=np.int64)
    np.add.at(confusion, (actual, predicted), 1)
    per_class = {}
    for label in (0, 1):
        true_positive = int(confusion[label, label])
        false_positive = int(confusion[1 - label, label])
        false_negative = int(confusion[label, 1 - label])
        precision = true_positive / max(1, true_positive + false_positive)
        recall = true_positive / max(1, true_positive + false_negative)
        f1 = 2 * precision * recall / max(1e-12, precision + recall)
        per_class[label] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
        }

    thresholds = np.linspace(1.0, 0.0, 101)
    true_positive_rates = []
    false_positive_rates = []
    for threshold in thresholds:
        prediction = probabilities >= threshold
        true_positive_rates.append(
            np.sum(prediction & (actual == 1)) / np.sum(actual == 1)
        )
        false_positive_rates.append(
            np.sum(prediction & (actual == 0)) / np.sum(actual == 0)
        )
    roc_auc = float(np.trapz(true_positive_rates, false_positive_rates))
    return {
        "confusion_matrix": confusion,
        "per_class": per_class,
        "false_positive_rates": false_positive_rates,
        "true_positive_rates": true_positive_rates,
        "roc_auc": roc_auc,
    }


def export_tflite(model, output_path: str | Path) -> Path:
    """Export the trained sigmoid model as a float TFLite file."""
    import tensorflow as tf

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    output_path.write_bytes(converter.convert())
    print(f"Đã xuất TFLite: {output_path}")
    return output_path


def extract_yawdd_mouth_crops(
    dataset_root: str | Path,
    output_root: str | Path,
    *,
    label_parser: Callable[[Path, Path], int],
    subject_parser: Callable[[Path, Path], str],
    sample_fps: float = 2.0,
) -> list[SampleRecord]:
    """Extract labeled mouth crops from videos; the notebook supplies parsers."""
    import mediapipe as mp

    dataset_root = Path(dataset_root)
    output_root = Path(output_root)
    if not dataset_root.is_dir():
        raise FileNotFoundError(f"Không tìm thấy YawDD: {dataset_root}")
    if sample_fps <= 0:
        raise ValueError("sample_fps must be greater than zero.")

    videos = sorted(
        path
        for path in dataset_root.rglob("*")
        if path.suffix.lower() in {".avi", ".mp4", ".mov", ".mkv"}
    )
    if not videos:
        raise ValueError(f"Không tìm thấy video trong {dataset_root}")

    records: list[SampleRecord] = []
    output_root.mkdir(parents=True, exist_ok=True)
    with mp.solutions.face_mesh.FaceMesh(
        static_image_mode=False,
        max_num_faces=1,
        refine_landmarks=False,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    ) as face_mesh:
        from core.classifier import extract_mouth_crop

        for video_path in videos:
            label = label_parser(video_path, dataset_root)
            subject_id = subject_parser(video_path, dataset_root)
            if label not in (0, 1) or not subject_id:
                raise ValueError(f"Nhãn/subject không hợp lệ: {video_path}")
            capture = cv2.VideoCapture(str(video_path))
            if not capture.isOpened():
                capture.release()
                raise RuntimeError(f"Không đọc được video: {video_path}")
            fps = capture.get(cv2.CAP_PROP_FPS)
            frame_interval = max(1, round(fps / sample_fps)) if fps > 0 else 1
            frame_index = 0
            video_tag = re.sub(r"[^A-Za-z0-9_-]+", "_", video_path.stem)
            subject_tag = re.sub(r"[^A-Za-z0-9_-]+", "_", subject_id)
            source_tag = hashlib.sha1(
                str(video_path.relative_to(dataset_root)).encode("utf-8")
            ).hexdigest()[:10]
            try:
                while True:
                    success, frame = capture.read()
                    if not success:
                        break
                    if frame_index % frame_interval == 0:
                        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        result = face_mesh.process(rgb)
                        faces = getattr(result, "multi_face_landmarks", None)
                        if faces:
                            landmarks = tuple(
                                (float(point.x), float(point.y), float(point.z))
                                for point in faces[0].landmark
                            )
                            crop = extract_mouth_crop(frame, landmarks)
                            if crop is not None:
                                output_path = output_root / (
                                    f"{subject_tag}_{video_tag}_{source_tag}_{frame_index}.jpg"
                                )
                                if not cv2.imwrite(str(output_path), crop):
                                    raise RuntimeError(
                                        f"Không ghi được crop: {output_path}"
                                    )
                                records.append(
                                    SampleRecord(
                                        str(output_path), int(label), subject_id
                                    )
                                )
                    frame_index += 1
            finally:
                capture.release()
    _require_records(records, output_root)
    return records


def _image_paths(root: Path):
    extensions = {".png", ".jpg", ".jpeg", ".bmp"}
    return (path for path in root.rglob("*") if path.suffix.lower() in extensions)


def _label_from_directories(path: Path, root: Path) -> int | None:
    for parent in path.parents:
        if parent == root:
            break
        name = parent.name.lower().replace("-", "").replace("_", "")
        if name in {"closed", "close", "shut", "eyesclosed"}:
            return 1
        if name in {"open", "opened", "eyesopen"}:
            return 0
    return None


def _require_records(records: Sequence[SampleRecord], root: Path) -> None:
    if not records:
        raise ValueError(f"Không tìm thấy mẫu hợp lệ trong {root}")
    if {record.label for record in records} != {0, 1}:
        raise ValueError("Dataset cần có cả hai lớp âm (0) và dương (1).")

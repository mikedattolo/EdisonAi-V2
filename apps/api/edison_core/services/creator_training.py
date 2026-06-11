"""Multi-GPU SDXL LoRA training for Creator Lab via kohya sd-scripts + accelerate.

Each job runs as its own transient systemd --user unit so a training run survives
an API restart. All datasets stay inside the Creator Studio content guardrails."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from edison_core.schemas import CreatorLabDataset, CreatorTrainingConfig, CreatorTrainingJob
from edison_core.services.creator_studio import creator_guard_reason

SD_SCRIPTS_DIR = Path(os.getenv("EDISON_SD_SCRIPTS_DIR", "/srv/edison-data/training/sd-scripts"))
ACCEL_CONFIG = Path(os.getenv("EDISON_ACCEL_CONFIG", "/srv/edison-data/training/accelerate/multi_gpu.yaml"))
SDXL_BASE_PATH = Path(
    os.getenv(
        "EDISON_SDXL_BASE_PATH",
        "/srv/edison-data/comfyui/ComfyUI/models/checkpoints/sd_xl_base_1.0.safetensors",
    )
)
COMFY_LORA_DIR = Path(
    os.getenv("EDISON_COMFY_LORA_DIR", "/srv/edison-data/comfyui/ComfyUI/models/loras")
)


class CreatorTrainingError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class CreatorTrainingService:
    def __init__(self, lab_root: Path) -> None:
        self.lab_root = Path(lab_root)
        self.outputs_dir = self.lab_root / "outputs"

    def available(self) -> bool:
        return (SD_SCRIPTS_DIR / ".venv" / "bin" / "python").exists()

    # -- public API ---------------------------------------------------------

    def start(self, config: CreatorTrainingConfig, dataset: CreatorLabDataset) -> CreatorTrainingJob:
        if not self.available():
            raise CreatorTrainingError(
                "Training toolchain (kohya sd-scripts) is not installed yet.", status_code=409
            )
        reason = creator_guard_reason(f"{dataset.name} {dataset.trigger_token} {config.lora_name or ''}")
        if reason:
            raise CreatorTrainingError(reason)
        if dataset.image_count < 1 or not dataset.images:
            raise CreatorTrainingError("Add at least one image to the dataset before training.")

        job_id = f"train_{_slug(dataset.name)[:24]}_{_short()}"
        job_dir = self.outputs_dir / job_id
        data_dir = job_dir / "dataset"
        output_dir = job_dir / "output"
        for path in (data_dir, output_dir):
            path.mkdir(parents=True, exist_ok=True)

        repeats = max(1, min(40, round(100 / max(1, dataset.image_count))))
        concept_dir = data_dir / f"{repeats}_{dataset.trigger_token}"
        concept_dir.mkdir(parents=True, exist_ok=True)
        caption = f"{dataset.trigger_token}, a photo of {dataset.trigger_token} persona"
        source_images = (self.lab_root / "datasets" / dataset.id / "images")
        copied = 0
        for image in dataset.images:
            src = source_images / image.filename
            if not src.exists():
                continue
            dest = concept_dir / image.filename
            shutil.copy2(src, dest)
            dest.with_suffix(".txt").write_text(caption, encoding="utf-8")
            copied += 1
        if copied == 0:
            raise CreatorTrainingError("Could not stage any dataset images for training.")

        gpu_ids = config.gpu_ids or self._all_gpu_ids()
        lora_name = _slug(config.lora_name or f"{dataset.trigger_token}_lora")[:60] or "persona_lora"
        log_path = job_dir / "train.log"

        command = self._build_command(config, dataset, data_dir, output_dir, lora_name, gpu_ids)
        unit = f"edison-train-{job_id}"
        self._launch_unit(unit, command, gpu_ids, log_path)

        job = CreatorTrainingJob(
            id=job_id,
            dataset_id=dataset.id,
            status="running",
            total_steps=config.steps,
            gpu_ids=gpu_ids,
            lora_name=lora_name,
            output_path=str(output_dir / f"{lora_name}.safetensors"),
            detail=f"Training on GPU(s) {', '.join(str(g) for g in gpu_ids)} with {copied} image(s) x{repeats} repeats.",
            started_at=_now_iso(),
        )
        self._write_job(job_dir, job, unit)
        return job

    def list_jobs(self) -> list[CreatorTrainingJob]:
        jobs: list[CreatorTrainingJob] = []
        if not self.outputs_dir.exists():
            return jobs
        for child in self.outputs_dir.iterdir():
            if not child.is_dir():
                continue
            job = self._refresh(child)
            if job is not None:
                jobs.append(job)
        jobs.sort(key=lambda item: (item.started_at or ""), reverse=True)
        return jobs

    def get_job(self, job_id: str) -> CreatorTrainingJob:
        job_dir = self.outputs_dir / job_id
        job = self._refresh(job_dir)
        if job is None:
            raise CreatorTrainingError("Training job not found.", status_code=404)
        return job

    def cancel(self, job_id: str) -> CreatorTrainingJob:
        job_dir = self.outputs_dir / job_id
        meta = self._read_meta(job_dir)
        unit = meta.get("unit") if meta else None
        if unit:
            self._systemctl("stop", unit)
        job = self._refresh(job_dir)
        if job is None:
            raise CreatorTrainingError("Training job not found.", status_code=404)
        if job.status in {"running", "preparing", "queued"}:
            job.status = "cancelled"
            job.finished_at = _now_iso()
            self._write_job(job_dir, job, unit or "")
        return job

    # -- command + launch ---------------------------------------------------

    def _build_command(
        self,
        config: CreatorTrainingConfig,
        dataset: CreatorLabDataset,
        data_dir: Path,
        output_dir: Path,
        lora_name: str,
        gpu_ids: list[int],
    ) -> str:
        accelerate = SD_SCRIPTS_DIR / ".venv" / "bin" / "accelerate"
        res = config.resolution
        # Drive GPU selection purely through CUDA_VISIBLE_DEVICES (set on the unit)
        # plus explicit flags. A saved accelerate config with gpu_ids:all would
        # override CUDA_VISIBLE_DEVICES and land training on a busy 16GB card.
        launch = [
            str(accelerate),
            "launch",
            "--num_processes",
            str(len(gpu_ids)),
            "--num_machines",
            "1",
            "--mixed_precision",
            "bf16",
            "--dynamo_backend",
            "no",
        ]
        if len(gpu_ids) > 1:
            launch.append("--multi_gpu")
        args = [
            *launch,
            "sdxl_train_network.py",
            "--pretrained_model_name_or_path",
            str(SDXL_BASE_PATH),
            "--train_data_dir",
            str(data_dir),
            "--output_dir",
            str(output_dir),
            "--output_name",
            lora_name,
            "--resolution",
            f"{res},{res}",
            "--network_module",
            "networks.lora",
            "--network_dim",
            str(config.network_dim),
            "--network_alpha",
            str(max(1, config.network_dim // 2)),
            "--learning_rate",
            str(config.learning_rate),
            "--max_train_steps",
            str(config.steps),
            "--train_batch_size",
            "1",
            "--mixed_precision",
            "bf16",
            "--save_precision",
            "fp16",
            "--optimizer_type",
            "AdamW",
            "--sdpa",
            "--cache_latents",
            "--cache_latents_to_disk",
            # VRAM savers so SDXL LoRA fits alongside the resident LLM/media services:
            # cache the two text encoders then free them, train UNet only, checkpoint activations.
            "--cache_text_encoder_outputs",
            "--cache_text_encoder_outputs_to_disk",
            "--network_train_unet_only",
            "--gradient_checkpointing",
            "--no_half_vae",
            "--enable_bucket",
            "--bucket_reso_steps",
            "64",
            "--save_model_as",
            "safetensors",
            "--caption_extension",
            ".txt",
            "--max_data_loader_n_workers",
            "2",
            "--seed",
            "42",
        ]
        return " ".join(_shquote(part) for part in args)

    def _launch_unit(self, unit: str, command: str, gpu_ids: list[int], log_path: Path) -> None:
        cuda_visible = ",".join(str(g) for g in gpu_ids)
        inner = f"cd {_shquote(str(SD_SCRIPTS_DIR))} && exec {command} > {_shquote(str(log_path))} 2>&1"
        self._systemctl("reset-failed", unit)
        result = subprocess.run(
            [
                "systemd-run",
                "--user",
                f"--unit={unit}",
                "--collect",
                # PCI_BUS_ID makes CUDA device indices match nvidia-smi indices, so
                # CUDA_VISIBLE_DEVICES selects the GPU the user actually picked
                # (default FASTEST_FIRST order would reshuffle the 3090 vs the 16GB cards).
                "--setenv=CUDA_DEVICE_ORDER=PCI_BUS_ID",
                f"--setenv=CUDA_VISIBLE_DEVICES={cuda_visible}",
                "--setenv=PYTHONUNBUFFERED=1",
                "--setenv=PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True",
                "bash",
                "-c",
                inner,
            ],
            capture_output=True,
            text=True,
            env=self._user_env(),
            timeout=30,
        )
        if result.returncode != 0:
            raise CreatorTrainingError(
                f"Failed to launch training: {result.stderr.strip() or result.stdout.strip()}",
                status_code=500,
            )

    # -- status refresh -----------------------------------------------------

    def _refresh(self, job_dir: Path) -> CreatorTrainingJob | None:
        meta = self._read_meta(job_dir)
        if meta is None:
            return None
        job = CreatorTrainingJob(**meta["job"])
        unit = meta.get("unit") or ""
        log_path = job_dir / "train.log"
        log_tail = _tail(log_path, 50)
        job.log_tail = log_tail
        current, total = _parse_progress(log_tail)
        if current is not None:
            job.current_step = current
        if total:
            job.total_steps = total
        if job.total_steps:
            job.progress = round(min(1.0, job.current_step / job.total_steps), 4)

        if job.status in {"running", "preparing", "queued"} and unit:
            active = self._systemctl("is-active", unit).strip()
            if active not in {"active", "activating"}:
                output = Path(job.output_path) if job.output_path else None
                produced = bool(output and output.exists())
                if produced or job.progress >= 0.99 or _log_says_done(log_tail):
                    job.status = "completed"
                    if produced:
                        self._publish_lora(output)
                else:
                    job.status = "failed"
                    job.detail = (job.detail or "") + " | Training process exited early. See log."
                job.finished_at = _now_iso()
                self._write_job(job_dir, job, unit)
        return job

    def _publish_lora(self, output: Path) -> None:
        try:
            COMFY_LORA_DIR.mkdir(parents=True, exist_ok=True)
            target = COMFY_LORA_DIR / output.name
            if not target.exists():
                shutil.copy2(output, target)
        except OSError:
            pass

    # -- helpers ------------------------------------------------------------

    def _all_gpu_ids(self) -> list[int]:
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=index", "--format=csv,noheader"],
                capture_output=True,
                text=True,
                timeout=6,
            )
            return [int(line.strip()) for line in result.stdout.splitlines() if line.strip().isdigit()]
        except (OSError, subprocess.SubprocessError, ValueError):
            return [0]

    def _user_env(self) -> dict:
        env = dict(os.environ)
        uid = os.getuid() if hasattr(os, "getuid") else 1000
        env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{uid}")
        env.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path=/run/user/{uid}/bus")
        return env

    def _systemctl(self, *args: str) -> str:
        try:
            result = subprocess.run(
                ["systemctl", "--user", *args],
                capture_output=True,
                text=True,
                env=self._user_env(),
                timeout=15,
            )
            return result.stdout
        except (OSError, subprocess.SubprocessError):
            return ""

    def _read_meta(self, job_dir: Path) -> dict | None:
        meta_path = job_dir / "job.json"
        if not meta_path.exists():
            return None
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) and "job" in data else None
        except (OSError, json.JSONDecodeError):
            return None

    def _write_job(self, job_dir: Path, job: CreatorTrainingJob, unit: str) -> None:
        job_dir.mkdir(parents=True, exist_ok=True)
        payload = {"unit": unit, "job": json.loads(job.model_dump_json())}
        (job_dir / "job.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _short() -> str:
    return datetime.now(timezone.utc).strftime("%m%d%H%M%S")


def _slug(value: str) -> str:
    token = "".join(char.lower() if char.isalnum() else "_" for char in value)
    return "_".join(part for part in token.split("_") if part)


def _shquote(value: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_@%+=:,./-]+", value):
        return value
    return "'" + value.replace("'", "'\"'\"'") + "'"


def _tail(path: Path, lines: int) -> list[str]:
    if not path.exists():
        return []
    try:
        data = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    return [line for line in data[-lines:] if line.strip()]


def _parse_progress(log_tail: list[str]) -> tuple[int | None, int | None]:
    current: int | None = None
    total: int | None = None
    for line in log_tail:
        for match in re.finditer(r"(\d+)\s*/\s*(\d+)", line):
            current = int(match.group(1))
            total = int(match.group(2))
    return current, total


def _log_says_done(log_tail: list[str]) -> bool:
    text = "\n".join(log_tail).lower()
    return "model saved" in text or "saving checkpoint" in text or "steps: 100%" in text

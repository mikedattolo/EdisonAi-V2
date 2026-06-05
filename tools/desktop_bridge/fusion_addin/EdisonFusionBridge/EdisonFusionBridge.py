import json
import os
import pathlib
import threading
import time
import traceback

import adsk.core
import adsk.fusion


EVENT_ID = "edison.fusion.bridge.job"
_app = None
_ui = None
_event = None
_handler = None
_worker = None
_stop = threading.Event()
_pending = []
_pending_lock = threading.Lock()
_seen = set()


class EdisonFusionJobHandler(adsk.core.CustomEventHandler):
    def notify(self, args):
        while True:
            with _pending_lock:
                if not _pending:
                    break
                path = _pending.pop(0)
            _process_job(path)


def run(context):
    global _app, _ui, _event, _handler, _worker
    try:
        _app = adsk.core.Application.get()
        _ui = _app.userInterface
        _stop.clear()
        _event = _app.registerCustomEvent(EVENT_ID)
        _handler = EdisonFusionJobHandler()
        _event.add(_handler)
        _worker = threading.Thread(target=_poll_loop, daemon=True)
        _worker.start()
        _ui.messageBox("Edison Fusion Bridge is listening for CAD jobs.")
    except Exception:
        if _ui:
            _ui.messageBox("Edison Fusion Bridge failed to start:\n\n" + traceback.format_exc())


def stop(context):
    try:
        _stop.set()
        if _event and _handler:
            _event.remove(_handler)
        if _app:
            _app.unregisterCustomEvent(EVENT_ID)
    except Exception:
        if _ui:
            _ui.messageBox("Edison Fusion Bridge failed to stop cleanly:\n\n" + traceback.format_exc())


def _poll_loop():
    queue_dir = _queue_dir()
    queue_dir.mkdir(parents=True, exist_ok=True)
    while not _stop.is_set():
        try:
            for path in queue_dir.glob("*.json"):
                if path.name.endswith((".running.json", ".done.json", ".error.json")):
                    continue
                path_key = str(path.resolve())
                if path_key in _seen:
                    continue
                _seen.add(path_key)
                with _pending_lock:
                    _pending.append(path)
                if _app:
                    _app.fireCustomEvent(EVENT_ID, path_key)
        except Exception:
            _write_result(
                _results_dir() / "bridge-poll-error.json",
                {"ok": False, "detail": traceback.format_exc()},
            )
        time.sleep(2.0)


def _process_job(path):
    running_path = path.with_name(path.stem + ".running.json")
    done_path = path.with_name(path.stem + ".done.json")
    error_path = path.with_name(path.stem + ".error.json")
    try:
        path.replace(running_path)
        job = json.loads(running_path.read_text(encoding="utf-8"))
        exports_dir = pathlib.Path(job.get("exports_dir") or _exports_dir())
        exports_dir.mkdir(parents=True, exist_ok=True)
        result_path = pathlib.Path(job.get("result_path") or (_results_dir() / f"{job.get('id', running_path.stem)}.result.json"))
        script = str(job.get("script") or "")
        parameters = job.get("parameters") if isinstance(job.get("parameters"), dict) else {}
        result = {
            "ok": True,
            "id": job.get("id", running_path.stem),
            "detail": "Fusion job completed.",
            "exports": [],
        }
        if script:
            namespace = {
                "adsk": adsk,
                "app": _app,
                "ui": _ui,
                "job": job,
                "parameters": parameters,
                "exports_dir": exports_dir,
                "export_active_design": export_active_design,
            }
            exec(script, namespace, namespace)
        elif parameters.get("command") == "box":
            _create_box(parameters)
        else:
            result["detail"] = "Fusion job was acknowledged, but no script or supported command was provided."
        for export in job.get("exports", []):
            if isinstance(export, dict):
                exported = export_active_design(exports_dir, str(export.get("name") or job.get("id") or "edison-design"), str(export.get("format") or "stl"))
                result["exports"].append(str(exported))
        _write_result(result_path, result)
        running_path.replace(done_path)
    except Exception:
        _write_result(
            _results_dir() / f"{path.stem}.result.json",
            {"ok": False, "id": path.stem, "detail": traceback.format_exc()},
        )
        if running_path.exists():
            running_path.replace(error_path)


def _create_box(parameters):
    design = _active_design()
    root = design.rootComponent
    width = float(parameters.get("width_mm") or 20.0) / 10.0
    depth = float(parameters.get("depth_mm") or 20.0) / 10.0
    height = float(parameters.get("height_mm") or 10.0) / 10.0
    sketch = root.sketches.add(root.xYConstructionPlane)
    sketch.sketchCurves.sketchLines.addCenterPointRectangle(
        adsk.core.Point3D.create(0, 0, 0),
        adsk.core.Point3D.create(width / 2.0, depth / 2.0, 0),
    )
    profile = sketch.profiles.item(0)
    distance = adsk.core.ValueInput.createByReal(height)
    root.features.extrudeFeatures.addSimple(profile, distance, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)


def export_active_design(exports_dir, name, export_format="stl"):
    design = _active_design()
    root = design.rootComponent
    safe_name = "".join(char if char.isalnum() or char in ("-", "_") else "-" for char in name).strip("-") or "edison-design"
    extension = export_format.lower().lstrip(".")
    output_path = pathlib.Path(exports_dir) / f"{safe_name}.{extension}"
    export_manager = design.exportManager
    if extension == "stl":
        options = export_manager.createSTLExportOptions(root, str(output_path))
    elif extension == "step":
        options = export_manager.createSTEPExportOptions(str(output_path), root)
    else:
        raise ValueError(f"Unsupported export format: {export_format}")
    export_manager.execute(options)
    return output_path


def _active_design():
    design = adsk.fusion.Design.cast(_app.activeProduct)
    if design:
        return design
    _app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
    design = adsk.fusion.Design.cast(_app.activeProduct)
    if not design:
        raise RuntimeError("No active Fusion design is available.")
    return design


def _queue_dir():
    return pathlib.Path(os.environ.get("EDISON_FUSION_QUEUE_DIR") or _repo_default("projects", "fusion-jobs", "queue"))


def _results_dir():
    return pathlib.Path(os.environ.get("EDISON_FUSION_RESULTS_DIR") or _repo_default("projects", "fusion-jobs", "results"))


def _exports_dir():
    return pathlib.Path(os.environ.get("EDISON_FUSION_EXPORTS_DIR") or _repo_default("projects", "fusion-jobs", "exports"))


def _repo_default(*parts):
    return pathlib.Path.home().joinpath("Documents", "edison v2", "EdisonAi-V2", *parts)


def _write_result(path, payload):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

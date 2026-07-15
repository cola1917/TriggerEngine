from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any


_CONTRACT_SRC = Path(__file__).resolve().parents[3] / "SceneExchangeContracts" / "src"
if str(_CONTRACT_SRC) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(_CONTRACT_SRC))

from scene_exchange_contracts import validate_document


_SCENE_TOKEN = re.compile(r"^[0-9a-f]{32}$")
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SUMMARY_FIELDS = (
    "collision_count",
    "min_ttc",
    "route_progress",
    "hard_brake_count",
    "max_jerk",
    "control_timeout_count",
)


class EvaluationFeedbackError(ValueError):
    """Raised when an evaluation result cannot safely become Trigger feedback."""


class EvaluationFeedbackConflictError(FileExistsError):
    """Raised when a run ID is reused for different evaluation content."""


def build_scenario_feedback(result: dict[str, Any]) -> dict[str, Any]:
    """Convert one ClosedLoopBench terminal result into deterministic feedback."""

    _validate_result(result)
    payload = result["payload"]
    classification = _classification(payload)
    feedback = {
        "schema_version": "scenario_feedback.v1",
        "feedback_id": f"feedback-{payload['run_id']}",
        "source": {
            "protocol_version": result["protocol_version"],
            "schema_version": result["schema_version"],
            "message_id": result["message_id"],
            "message_type": result["message_type"],
            "created_at": result["created_at"],
            "content_sha256": _document_digest(result),
        },
        "identity": {
            "run_id": payload["run_id"],
            "scenario_id": payload["scene_id"],
            "scene_token": payload["scene_id"],
            "scene_version": payload["scene_version"],
            "algorithm": deepcopy(payload["algorithm"]),
            "odd": deepcopy(payload["odd"]),
        },
        "classification": classification,
        "evaluation": {
            "status": payload["status"],
            "runtime_status": payload["runtime_status"],
            "outcome": payload["outcome"],
            "started_at": payload["started_at"],
            "finished_at": payload["finished_at"],
            "duration_sec": payload["duration_sec"],
            "summary": {name: payload["summary"][name] for name in _SUMMARY_FIELDS},
            "warnings": list(payload.get("warnings") or []),
            "error": deepcopy(payload.get("error")),
        },
    }
    validate_document(feedback)
    return feedback


def store_scenario_feedback(
    feedback_root: Path,
    feedback: dict[str, Any],
) -> tuple[Path, bool]:
    """Store feedback immutably by run ID; identical retries are idempotent."""

    _validate_feedback(feedback)
    root = Path(feedback_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    run_id = feedback["identity"]["run_id"]
    target = (root / f"{run_id}.json").resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise EvaluationFeedbackError("feedback path escapes feedback root") from exc

    serialized = json.dumps(feedback, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if target.exists():
        try:
            existing = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EvaluationFeedbackConflictError(
                f"existing feedback is unreadable for run {run_id!r}"
            ) from exc
        if existing != feedback:
            raise EvaluationFeedbackConflictError(
                f"run {run_id!r} already has different feedback"
            )
        return target, False

    staging = root / f".{run_id}.{uuid.uuid4().hex}.tmp"
    try:
        staging.write_text(serialized, encoding="utf-8")
        try:
            os.rename(staging, target)
        except OSError as exc:
            if not target.exists():
                raise
            existing = json.loads(target.read_text(encoding="utf-8"))
            if existing != feedback:
                raise EvaluationFeedbackConflictError(
                    f"run {run_id!r} was concurrently stored with different feedback"
                ) from exc
            return target, False
    finally:
        if staging.exists():
            staging.unlink()
    return target, True


def import_evaluation_result(
    result: dict[str, Any], feedback_root: Path
) -> tuple[dict[str, Any], Path, bool]:
    feedback = build_scenario_feedback(result)
    path, created = store_scenario_feedback(feedback_root, feedback)
    return feedback, path, created


def _classification(payload: dict[str, Any]) -> dict[str, str]:
    completed_runtime = payload["runtime_status"] in {
        "completed",
        "ego_closed_loop",
        "interactive_closed_loop",
    }
    if payload["status"] == "succeeded" and completed_runtime and payload["outcome"] == "pass":
        return {
            "state": "validated",
            "priority": "normal",
            "disposition": "pass",
        }
    if (
        payload["status"] in {"failed", "cancelled"}
        or payload["runtime_status"] == "failed"
        or payload["outcome"] == "fail"
    ):
        return {
            "state": "failed",
            "priority": "high",
            "disposition": "investigate",
        }
    return {
        "state": "incomplete",
        "priority": "normal",
        "disposition": "unknown",
    }


def _validate_result(result: dict[str, Any]) -> None:
    if not isinstance(result, dict):
        raise EvaluationFeedbackError("evaluation result must be a JSON object")
    expected = {
        "protocol_version": "shared_exchange_protocol.v1",
        "schema_version": "evaluation_run_result.v1",
        "message_type": "evaluation.run.result",
    }
    for name, value in expected.items():
        if result.get(name) != value:
            raise EvaluationFeedbackError(f"{name} must be {value!r}")
    for name in ("message_id", "created_at", "payload"):
        if name not in result:
            raise EvaluationFeedbackError(f"missing required field: {name}")
    if not _SAFE_ID.fullmatch(str(result["message_id"])):
        raise EvaluationFeedbackError("invalid message_id")
    payload = result["payload"]
    if not isinstance(payload, dict):
        raise EvaluationFeedbackError("payload must be an object")
    required = {
        "run_id",
        "scene_id",
        "scene_version",
        "status",
        "runtime_status",
        "outcome",
        "algorithm",
        "odd",
        "started_at",
        "finished_at",
        "duration_sec",
        "summary",
        "artifacts",
    }
    missing = sorted(required - payload.keys())
    if missing:
        raise EvaluationFeedbackError("missing payload fields: " + ", ".join(missing))
    if not _SAFE_ID.fullmatch(str(payload["run_id"])):
        raise EvaluationFeedbackError("invalid run_id")
    if not _SCENE_TOKEN.fullmatch(str(payload["scene_id"])):
        raise EvaluationFeedbackError("scene_id must be a 32-character lowercase scene token")
    if payload["status"] not in {"succeeded", "failed", "cancelled"}:
        raise EvaluationFeedbackError("invalid terminal status")
    if payload["runtime_status"] not in {
        "not_run",
        "planned",
        "completed",
        "ego_closed_loop",
        "interactive_closed_loop",
        "failed",
    }:
        raise EvaluationFeedbackError("invalid runtime_status")
    if payload["outcome"] not in {"pass", "fail", "unknown"}:
        raise EvaluationFeedbackError("invalid outcome")
    for name, identity_fields in (
        ("algorithm", ("algorithm_id", "algorithm_version")),
        ("odd", ("odd_id",)),
    ):
        value = payload[name]
        if not isinstance(value, dict) or any(field not in value for field in identity_fields):
            raise EvaluationFeedbackError(f"invalid {name} identity")
    summary = payload["summary"]
    if not isinstance(summary, dict) or any(name not in summary for name in _SUMMARY_FIELDS):
        raise EvaluationFeedbackError("evaluation summary is incomplete")


def _validate_feedback(feedback: dict[str, Any]) -> None:
    if feedback.get("schema_version") != "scenario_feedback.v1":
        raise EvaluationFeedbackError("feedback must use scenario_feedback.v1")
    identity = feedback.get("identity")
    if not isinstance(identity, dict):
        raise EvaluationFeedbackError("feedback identity is missing")
    run_id = str(identity.get("run_id") or "")
    if not _SAFE_ID.fullmatch(run_id):
        raise EvaluationFeedbackError("feedback has invalid run_id")
    token = str(identity.get("scene_token") or "")
    if not _SCENE_TOKEN.fullmatch(token) or identity.get("scenario_id") != token:
        raise EvaluationFeedbackError("feedback scene identity is not canonical")


def _document_digest(document: dict[str, Any]) -> str:
    canonical = json.dumps(
        document, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()

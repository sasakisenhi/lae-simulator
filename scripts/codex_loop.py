"""OpenSpec group orchestrator: Codex implementation, deterministic checks, independent review.

Requires: Python >=3.10, PyYAML, Codex CLI, OpenSpec CLI and project tooling.
Run from the project root, or pass --root. No auto-commit/push/deploy.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    sys.exit("PyYAML が必要: python3 -m pip install pyyaml")


def now() -> str:
    return datetime.now(UTC).isoformat()


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def run(cmd: list[str], cwd: Path, timeout: int, *, stdin: str | None = None,
        log: Path | None = None) -> tuple[int, str, str, bool]:
    """Execute without shell; kill whole process group on timeout."""
    proc = subprocess.Popen(cmd, cwd=cwd, stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            start_new_session=True)
    timed_out = False
    try:
        out, err = proc.communicate(input=stdin, timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        os.killpg(proc.pid, signal.SIGTERM)
        try:
            out, err = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            out, err = proc.communicate()
    if log:
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text("COMMAND: " + shlex.join(cmd[:-1] if stdin is not None else cmd) +
                       "\nSTDOUT:\n" + out + "\nSTDERR:\n" + err, encoding="utf-8")
    return (proc.returncode if proc.returncode is not None else -1, out, err, timed_out)


def progress_fingerprint(root: Path) -> str:
    """Hash tracked changes and untracked file contents, not just git status."""
    parts = []
    for cmd in (["git", "diff", "--binary"], ["git", "diff", "--cached", "--binary"],
                ["git", "ls-files", "--others", "--exclude-standard", "-z"]):
        code, out, err, _ = run(cmd, root, 60)
        if code:
            raise RuntimeError("git fingerprint failure: " + err)
        parts.append(out.encode("utf-8", errors="replace"))
        if "--others" in cmd:
            for name in out.split("\0"):
                if name:
                    path = root / name
                    if path.is_file():
                        parts.append(hashlib.sha256(path.read_bytes()).digest())
    return hashlib.sha256(b"\0".join(parts)).hexdigest()


def git_snapshot(root: Path) -> str:
    code, out, err, _ = run(["git", "status", "--porcelain=v1", "--untracked-files=all"], root, 30)
    if code:
        raise RuntimeError("git status failed: " + err)
    return out


def load_tasks(root: Path, change: str) -> dict[str, dict[str, Any]]:
    """Map OpenSpec tasks by the explicit number in their description.

    OpenSpec may emit sequential JSON IDs ("1", "2", ...) rather than the
    authored task numbers ("6.1", "6.2", ...). The authored task numbers
    remain the stable identifiers in this project's tasks.md and YAML.
    """
    code, out, err, timed_out = run(
        ["openspec", "instructions", "apply", "--change", change, "--json"], root, 90
    )
    if code or timed_out:
        raise RuntimeError("OpenSpec apply failed: " + (err or out)[-3000:])
    data = json.loads(out)
    if (
        data.get("state") == "blocked"
        or not data.get("taskTrackingConfigured")
        or data.get("unavailableTrackingFiles")
    ):
        raise RuntimeError("OpenSpec tracking is unavailable or blocked: " + str(data.get("state")))

    tasks: dict[str, dict[str, Any]] = {}
    for item in data.get("tasks", []):
        description = item.get("description", "")
        if not isinstance(description, str):
            raise TypeError("OpenSpec task has a non-text description")
        # The authored number must be present at the start of each task. Do not
        # confuse an OpenSpec-generated ordinal ID with the authored task ID.
        match = re.match(r"^\s*(\d+\.\d+)(?=\s|$)", description)
        if not match:
            raise RuntimeError(
                "OpenSpec task lacks an authored number (e.g. 6.1): "
                + description[:160]
            )
        authored_id = match.group(1)
        if authored_id in tasks:
            raise RuntimeError("Duplicate authored OpenSpec task ID: " + authored_id)
        tasks[authored_id] = {
            **item,
            "id": authored_id,
            "openspec_id": str(item.get("id", "")),
        }
    return tasks


def quality_checks(root: Path, checks: list[list[str]], timeout: int, log_dir: Path,
                   label: str) -> list[str]:
    failures = []
    for i, cmd in enumerate(checks, 1):
        cmd = [str(x) for x in cmd]
        filename = log_dir / f"{label}-{i:02d}.log"
        try:
            code, out, err, timed_out = run(cmd, root, timeout, log=filename)
            print(f"  CHECK {' '.join(cmd)}: {'TIMEOUT' if timed_out else code}", flush=True)
            if timed_out or code:
                failures.append(f"{' '.join(cmd)} (exit={code}, timeout={timed_out}):\n{(out + err)[-2200:]}")
        except OSError as exc:
            failures.append(f"{' '.join(cmd)}: {exc}")
    return failures


def get_events(text: str) -> list[dict[str, Any]]:
    result = []
    for line in text.splitlines():
        try:
            item = json.loads(line)
            if isinstance(item, dict):
                result.append(item)
        except json.JSONDecodeError:
            pass
    return result


def usage_limit_message(events: list[dict[str, Any]], stderr: str) -> str | None:
    """Classify Codex quota errors separately from implementation failures."""
    texts = [stderr]
    texts.extend(str(e.get("message", "")) for e in events if e.get("type") == "error")
    for message in texts:
        if re.search(r"usage limit|rate limit|quota exceeded|too many requests|利用(?:枠|上限)|使用量の上限", message, re.IGNORECASE):
            return message.strip()[-1200:]
    return None


def codex_exec(root: Path, model: dict[str, Any], prompt: str, mode: str,
               timeout: int, log: Path, schema: Path | None = None,
               output: Path | None = None) -> dict[str, Any]:
    cmd = ["codex", "exec", "--json", "--sandbox", mode, "--model", model["id"]]
    effort = model.get("reasoning_effort")
    if effort:
        cmd += ["-c", f'model_reasoning_effort="{effort}"']
    if schema:
        cmd += ["--output-schema", str(schema)]
    if output:
        cmd += ["--output-last-message", str(output)]
    cmd += ["-"]
    code, out, err, timed_out = run(cmd, root, timeout, stdin=prompt, log=log)
    events = get_events(out)
    usage = {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0, "reasoning_output_tokens": 0}
    for e in events:
        if e.get("type") == "turn.completed":
            for k in usage:
                usage[k] += int(e.get("usage", {}).get(k, 0) or 0)
    messages = [e.get("item", {}).get("text", "") for e in events
                if e.get("type") == "item.completed" and e.get("item", {}).get("type") == "agent_message"]
    success = (code == 0 and not timed_out and
               any(e.get("type") == "turn.completed" for e in events) and
               not any(e.get("type") in {"turn.failed", "error"} for e in events))
    blocked = bool(re.search(r"(?m)^\s*BLOCKED\s*[:：]", "\n".join(messages)))
    quota_error = usage_limit_message(events, err)
    return {"success": success, "blocked": blocked, "rate_limited": quota_error is not None,
            "rate_limit_message": quota_error, "usage": usage,
            "error": (err or out)[-1500:] if not success else "", "log": str(log)}


def read_structured_report(path: Path, allowed: set[str], *, label: str) -> dict[str, Any]:
    """Fail closed on missing, malformed, or contradictory model output."""
    if not path.is_file():
        raise ValueError(f"{label}: structured output is missing: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("status") not in allowed:
        raise ValueError(f"{label}: invalid status")
    if not isinstance(data.get("reason"), str) or not data["reason"].strip():
        raise ValueError(f"{label}: reason is required")
    if not isinstance(data.get("evidence"), list) or not all(
        isinstance(item, str) for item in data["evidence"]
    ):
        raise ValueError(f"{label}: evidence must be a list of strings")
    if data["status"] == "NEEDS_ANALYSIS" and not data.get("question", "").strip():
        raise ValueError(f"{label}: NEEDS_ANALYSIS requires a specific question")
    if data["status"] == "REPAIRABLE" and not data.get("next_action", "").strip():
        raise ValueError(f"{label}: REPAIRABLE requires an actionable next step")
    if data["status"] == "RESOLVED" and not data.get("next_action", "").strip():
        raise ValueError(f"{label}: RESOLVED requires an actionable next step")
    return data


def report_schema(statuses: list[str]) -> dict[str, Any]:
    """Shared JSON schema for the coding model and independent analyst."""
    return {
        "type": "object", "additionalProperties": False,
        "properties": {
            "status": {"type": "string", "enum": statuses},
            "reason": {"type": "string"},
            "evidence": {"type": "array", "items": {"type": "string"}},
            "question": {"type": "string"},
            "next_action": {"type": "string"},
        },
        "required": ["status", "reason", "evidence", "question", "next_action"],
    }


def analysis_prompt(change: str, group: str, task: dict[str, Any], report: dict[str, Any]) -> str:
    return f"""You are an independent READ-ONLY analyst, not an implementer.
OpenSpec change: {change}; group: {group}; task: {task['id']}: {task['description']}
Read the actual specifications, design, code, and tests. The implementer raised:
{json.dumps(report, ensure_ascii=False)[:9500]}
Return structured JSON with status one of:
RESOLVED: Existing written specifications and current code give an unambiguous safe resolution;
           provide concrete next_action with file references and evidence. Do NOT invent requirements.
BLOCKED: A human decision is needed, especially for changed public-access limits,
         authorization, destructive compatibility changes, or conflicting requirements.
INCONCLUSIVE: Insufficient evidence to settle safely; report what is missing.
Never resolve an ambiguity by assuming new permissions or altering stated requirements.
Do not edit files or task checkboxes. Use the supplied JSON schema only.
"""


def tasks_prompt(change: str, group: str, task: dict[str, Any], feedback: str, initial_prompt: str = "") -> str:
    initial_context = (
        "\nInitial user instruction (context for THIS task only; current OpenSpec and "
        "orchestrator safety constraints take precedence):\n"
        + initial_prompt
        + "\nEnd of initial user instruction.\n"
        if initial_prompt else ""
    )
    return f"""OpenSpec change: {change}
Group: {group}
{initial_context}
ONLY Task {task['id']}: {task['description']}

Read the actual OpenSpec tasks/specs/design and repository code. Implement this ONE task now.
Do not stop after planning or describing proposed changes. Write code, add targeted regression tests,
and iterate on test failures. Only mark this task done when its complete acceptance criteria are met.
Preserve pre-existing changes. Do not edit any other task checkbox, G8 or later features.
Never commit, push, deploy, archive, change secrets, or access external services.
Do not modify the orchestrator, its configuration, or disable/remove tests to obtain green checks.

End your run with ONE structured JSON status (using the provided schema):
COMPLETED: You believe the full task is implemented; independent checks will verify.
IN_PROGRESS: The work can safely continue without a new design decision; say the next action.
REPAIRABLE: A specific implementation/test defect exists with a clear corrective action.
NEEDS_ANALYSIS: You cannot safely decide a technical or interpretation question; set question.
BLOCKED: Written specifications conflict, or public-access contract/authorization/destructive
         compatibility decisions require explicit human approval; explain evidence and stop.
Never use IN_PROGRESS merely to conceal a genuine ambiguity or security concern.
Do not claim COMPLETED solely because tests pass when acceptance criteria remain unmet.
Provide evidence using real file locations, tests, or specification references.

Previous external checks/analyst feedback (may be empty):
{feedback[:9000]}
"""


def review_prompt(change: str, group: str, task_ids: list[str], feedback: str) -> str:
    return f"""Independently review OpenSpec change {change}, group {group}, tasks {', '.join(task_ids)}.
Read actual specs, design, tasks, implementation, tests, git diff AND relevant untracked source files.
Treat the implementation agent's own claims as untrusted. Do not edit files or task checkboxes.
Check precise acceptance criteria, regression coverage, privacy leaks via text/IDs/counts/errors,
canonical versus public projection, prior run compatibility, future/unknown information in personal packages,
and search authorization. Flag inadequate evidence, broken tests, and changes outside scope.
Return JSON via the supplied schema: verdict PASS, REVISE, or BLOCKED; findings must be actionable.
PASS only when there are no blocking findings and evidence is sufficient.
BLOCKED for human decisions/contract changes; REVISE for correctable implementation problems.
Do not assert a test ran unless independently verified.\nPrevious review context:\n{feedback[:5000]}\n"""


def validate_config(cfg: dict[str, Any], group: str) -> None:
    assert isinstance(cfg.get("change"), str) and cfg["change"]
    assert group in cfg["groups"], f"unknown group: {group}"
    assert all(k in cfg["models"] for k in ("implementer", "reviewer"))
    for name in ("implementer", "reviewer"):
        assert cfg["models"][name].get("id")
    for g, spec in cfg["groups"].items():
        ids = [str(t["id"]) for t in spec.get("tasks", [])]
        assert len(set(ids)) == len(ids), f"duplicate task in {g}"
        for t in spec.get("tasks", []):
            assert set(map(str, t.get("depends_on", []))).issubset(ids), f"bad dependency in {g}"
    assert int(cfg["execution"]["max_attempts_per_task"]) >= 1
    assert int(cfg["execution"]["max_review_cycles"]) >= 0
    assert cfg["groups"][group].get("review") in {"independent_ai", "human", "independent_acceptance"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=".", help="project repository root")
    ap.add_argument("--config", default="scripts/codex_loop.yaml")
    ap.add_argument("--group", required=True)
    ap.add_argument("--dry-run", action="store_true", help="validate config/tasks, print plan; no model calls")
    ap.add_argument("--allow-review-only", action="store_true", help="rerun review for already completed tasks")
    prompt_args = ap.add_mutually_exclusive_group()
    prompt_args.add_argument("--prompt-file", help="UTF-8 file with initial instructions; used once, on the first implementation call")
    prompt_args.add_argument("--prompt", help="initial instructions passed directly on the command line; used once")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    initial_prompt = ""
    if args.prompt_file:
        prompt_path = Path(args.prompt_file).expanduser()
        if not prompt_path.is_absolute():
            prompt_path = root / prompt_path
        initial_prompt = prompt_path.read_text(encoding="utf-8").strip()
    elif args.prompt is not None:
        initial_prompt = args.prompt.strip()
    if len(initial_prompt) > 60000:
        raise ValueError("Initial prompt too large (max 60000 characters)")
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = root / config_path
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    validate_config(cfg, args.group)
    grp = cfg["groups"][args.group]
    change = cfg["change"]
    task_map = load_tasks(root, change)
    group_tasks = [str(t["id"]) for t in grp["tasks"]]
    for tid in group_tasks:
        if tid not in task_map:
            raise RuntimeError(f"OpenSpec task missing: {tid}")
    for preceding in grp.get("depends_on", []):
        if preceding not in cfg["groups"]:
            raise RuntimeError("Unknown group dependency: " + preceding)
        parent_ids = [str(t["id"]) for t in cfg["groups"][preceding]["tasks"]]
        if any(not task_map.get(tid, {}).get("done") for tid in parent_ids):
            raise RuntimeError(f"Prerequisite group {preceding} has incomplete tasks")
    for t in grp["tasks"]:
        for dep in t.get("depends_on", []):
            assert str(dep) in group_tasks
    check_cfg = cfg["checks"]
    print(f"Group {args.group}: {group_tasks} | models={cfg['models']['implementer']['id']} -> {cfg['models']['reviewer']['id']}", flush=True)
    if args.dry_run:
        if initial_prompt:
            print(f"  Initial prompt: {len(initial_prompt)} characters (first implementation call only)")
        for t in grp["tasks"]:
            print(f"  {t['id']} done={bool(task_map[str(t['id'])]['done'])} depends={t.get('depends_on', [])}")
        print("No Codex execution or mutation (dry run).")
        return 0
    if not shutil.which("codex"):
        raise RuntimeError("codex CLI not found in PATH")
    code, git_root, _, _ = run(["git", "rev-parse", "--show-toplevel"], root, 30)
    if code or Path(git_root.strip()).resolve() != root:
        raise RuntimeError("--root must be the Git repository root")
    state_base = Path(cfg["execution"].get("state_dir", "~/.local/state/lae-codex-loop")).expanduser()
    key = hashlib.sha256(str(root).encode()).hexdigest()[:12]
    state_dir = state_base / key / change / args.group
    state_dir.mkdir(parents=True, exist_ok=True)
    state_file = state_dir / "state.json"
    state = json.loads(state_file.read_text(encoding="utf-8")) if state_file.exists() else {
        "root": str(root), "change": change, "group": args.group, "created_at": now(),
        "attempts": {}, "runs": [], "reviews": [], "status": "running"}
    if state.get("root") != str(root) or state.get("change") != change:
        raise RuntimeError("State does not match repository/change")
    before_status = git_snapshot(root)
    if not state.get("initial_git_status"):
        state["initial_git_status"] = before_status
    state["status"] = "running"
    # Initial instructions are invocation-scoped. The one-shot marker is persisted
    # before Codex executes, so quota pauses and process restarts cannot replay them.
    # A *new* --prompt-file/--prompt on a future invocation starts a new one-shot instruction.
    if initial_prompt:
        state["initial_prompt_digest"] = hashlib.sha256(initial_prompt.encode("utf-8")).hexdigest()
        state["initial_prompt_pending"] = True
    else:
        state["initial_prompt_pending"] = False
    state.pop("reason", None)
    state.pop("stopped_at", None)
    write_json(state_file, state)
    seconds = int(cfg["execution"].get("codex_timeout_seconds", 1200))
    check_timeout = int(cfg["execution"].get("check_timeout_seconds", 300))
    max_attempts = int(cfg["execution"]["max_attempts_per_task"])
    max_cycles = int(cfg["execution"]["max_review_cycles"])
    max_no_progress = int(cfg["execution"].get("max_no_progress_attempts", 2))
    all_usage = {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0, "reasoning_output_tokens": 0}

    def store_result(result: dict[str, Any], kind: str, task: str = "") -> None:
        state["runs"].append({"time": now(), "kind": kind, "task": task, **result})
        for k in all_usage:
            all_usage[k] += result.get("usage", {}).get(k, 0)
        state["latest_session_usage"] = all_usage
        write_json(state_file, state)

    def pause_quota(reason: str) -> int:
        state["status"] = "rate_limited"
        state["reason"] = reason
        state["stopped_at"] = now()
        write_json(state_file, state)
        print("PAUSED (RATE_LIMITED):", reason, "\nState:", state_file, flush=True)
        print("Run the same --group command again after quota renewal. No automatic waiting.", flush=True)
        return 3

    def fail(reason: str) -> int:
        state["status"] = "blocked"
        state["reason"] = reason
        state["stopped_at"] = now()
        write_json(state_file, state)
        print("STOP:", reason, "\nState:", state_file, flush=True)
        return 2

    review_schema = {
        "type": "object", "additionalProperties": False,
        "properties": {
            "verdict": {"type": "string", "enum": ["PASS", "REVISE", "BLOCKED"]},
            "summary": {"type": "string"},
            "findings": {"type": "array", "items": {"type": "string"}},
            "evidence_gaps": {"type": "array", "items": {"type": "string"}},
        }, "required": ["verdict", "summary", "findings", "evidence_gaps"]}
    impl_schema_path = state_dir / "implementation-schema.json"
    analysis_schema_path = state_dir / "analysis-schema.json"
    write_json(impl_schema_path, report_schema([
        "COMPLETED", "IN_PROGRESS", "REPAIRABLE", "NEEDS_ANALYSIS", "BLOCKED"
    ]))
    write_json(analysis_schema_path, report_schema(["RESOLVED", "BLOCKED", "INCONCLUSIVE"]))
    max_analyses = int(cfg["execution"].get("max_analysis_calls_per_task", 1))
    if max_analyses < 0:
        raise ValueError("max_analysis_calls_per_task must not be negative")
    # A prior RATE_LIMITED pause may leave contextual feedback to carry across invocations.
    failed_feedback = str(state.get("pending_feedback", ""))[:9000]

    schema_path = state_dir / "review-schema.json"
    write_json(schema_path, review_schema)

    for cycle in range(max_cycles + 1):
        for entry in grp["tasks"]:
            tid = str(entry["id"])
            current = load_tasks(root, change)
            for dep in entry.get("depends_on", []):
                if not current[str(dep)]["done"]:
                    return fail(f"Task {tid} waits for {dep}")
            if current[tid]["done"]:
                print(f"SKIP checked task {tid} (group-wide checks still follow)", flush=True)
                continue
            stagnant = 0
            analyses = 0
            for attempt in range(max_attempts):
                count = state["attempts"].get(tid, 0) + 1
                state["attempts"][tid] = count
                write_json(state_file, state)
                prior_status = progress_fingerprint(root)
                one_shot = initial_prompt if state.get("initial_prompt_pending", False) else ""
                prompt = tasks_prompt(change, args.group, current[tid], failed_feedback, one_shot)
                if one_shot:
                    state["initial_prompt_pending"] = False
                    state["initial_prompt_sent_to_task"] = tid
                    state["initial_prompt_sent_at"] = now()
                    write_json(state_file, state)
                unique = f"task-{tid}-cycle{cycle}-attempt{count}-{time.time_ns()}"
                log = state_dir / f"{unique}.jsonl.log"
                output = state_dir / f"{unique}.json"
                print(f"IMPLEMENT {tid} attempt={count} with {cfg['models']['implementer']['id']}", flush=True)
                result = codex_exec(root, cfg["models"]["implementer"], prompt,
                                    "workspace-write", seconds, log, impl_schema_path, output)
                store_result(result, "implementation", tid)
                if result["rate_limited"]:
                    state["attempts"][tid] = count - 1
                    state["pending_feedback"] = failed_feedback
                    write_json(state_file, state)
                    return pause_quota(f"Task {tid}: {result['rate_limit_message']} (see {log})")
                if not result["success"]:
                    return fail(f"Task {tid} Codex execution error (see {log}): {result['error'][:300]}")
                try:
                    report = read_structured_report(
                        output, {"COMPLETED", "IN_PROGRESS", "REPAIRABLE", "NEEDS_ANALYSIS", "BLOCKED"},
                        label=f"Task {tid}")
                except (ValueError, KeyError, TypeError) as exc:
                    return fail(f"Task {tid} model status missing or invalid (no blind retry): {exc}")
                state.setdefault("task_reports", []).append(
                    {"time": now(), "task": tid, "report": report, "path": str(output)})
                write_json(state_file, state)
                status = report["status"]
                print(f"  STATUS {status}: {report['reason'][:240]}", flush=True)
                if status == "BLOCKED":
                    return fail(f"Task {tid} requires a human decision: {report['reason'][:700]}")
                if status == "NEEDS_ANALYSIS":
                    if analyses >= max_analyses:
                        return fail(f"Task {tid} needs analysis, but analysis limit reached: {report['question'][:500]}")
                    analyses += 1
                    analysis_id = f"analysis-{tid}-cycle{cycle}-{time.time_ns()}"
                    analysis_log = state_dir / f"{analysis_id}.jsonl.log"
                    analysis_output = state_dir / f"{analysis_id}.json"
                    print(f"ANALYZE {tid} with {cfg['models']['reviewer']['id']} (read-only)", flush=True)
                    analysis_result = codex_exec(
                        root, cfg["models"]["reviewer"],
                        analysis_prompt(change, args.group, current[tid], report),
                        "read-only", seconds, analysis_log, analysis_schema_path, analysis_output)
                    store_result(analysis_result, "analysis", tid)
                    if analysis_result["rate_limited"]:
                        state["pending_feedback"] = (
                            "Unresolved implementer question: " + json.dumps(report, ensure_ascii=False)
                        )[:9000]
                        write_json(state_file, state)
                        return pause_quota(f"Analysis {tid}: {analysis_result['rate_limit_message']} (see {analysis_log})")
                    if not analysis_result["success"]:
                        return fail(f"Task {tid} independent analysis failed: {analysis_log}")
                    try:
                        finding = read_structured_report(
                            analysis_output, {"RESOLVED", "BLOCKED", "INCONCLUSIVE"},
                            label=f"Analysis {tid}")
                    except (ValueError, KeyError, TypeError) as exc:
                        return fail(f"Task {tid} invalid analysis report: {exc}")
                    state.setdefault("analyses", []).append(
                        {"time": now(), "task": tid, "report": finding, "path": str(analysis_output)})
                    write_json(state_file, state)
                    if finding["status"] != "RESOLVED":
                        return fail(f"Task {tid} analysis {finding['status']}: {finding['reason'][:700]}")
                    failed_feedback = ("Independent analysis resolved a question; implement its safe plan:\n"
                                       + json.dumps(finding, ensure_ascii=False))[:9000]
                    state["pending_feedback"] = failed_feedback
                    write_json(state_file, state)
                    # An explicit analysis resolution is required before another coding attempt.
                    continue
                current = load_tasks(root, change)
                test_failures = quality_checks(root, check_cfg["task"], check_timeout,
                                               state_dir / "checks", f"task-{tid}-{count}")
                if current[tid]["done"] and not test_failures and status == "COMPLETED":
                    print(f"TASK {tid}: verified checks and model status COMPLETED", flush=True)
                    failed_feedback = ""
                    state.pop("pending_feedback", None)
                    write_json(state_file, state)
                    break
                # A checked task with failed verification is never treated as complete.
                failed_feedback = (
                    f"Task {tid} status={status}, checked={bool(current[tid]['done'])}. "
                    "Correct remaining issues. Do not claim completion without verifying acceptance criteria.\n"
                    + "Model report: " + json.dumps(report, ensure_ascii=False)[:3000] + "\n"
                    + "External verification failures:\n" + "\n".join(test_failures)
                )[:9000]
                state["pending_feedback"] = failed_feedback
                write_json(state_file, state)
                if progress_fingerprint(root) == prior_status:
                    stagnant += 1
                else:
                    stagnant = 0
                if stagnant >= max_no_progress:
                    return fail(f"Task {tid}: {stagnant} consecutive attempts with no git status change")
            else:
                return fail(f"Task {tid}: reached max attempts ({max_attempts}) without verified completion")

        if any(not load_tasks(root, change)[tid]["done"] for tid in group_tasks):
            return fail("At least one group task remains unchecked")
        print(f"GROUP {args.group}: quality gate", flush=True)
        failures = quality_checks(root, check_cfg["group"], check_timeout,
                                  state_dir / "checks", f"group-cycle{cycle}")
        if failures:
            return fail("Group quality gate failed; no auto-passing. Details: " + " | ".join(failures)[:1500])
        review_mode = grp["review"]
        if review_mode != "independent_ai":
            return fail(f"Group {args.group} requires {review_mode} acceptance; manual approval required")
        output = state_dir / f"review-cycle{cycle}.json"
        log = state_dir / f"review-cycle{cycle}.jsonl.log"
        print(f"REVIEW with {cfg['models']['reviewer']['id']} (read-only)", flush=True)
        result = codex_exec(root, cfg["models"]["reviewer"],
                            review_prompt(change, args.group, group_tasks, failed_feedback),
                            "read-only", seconds, log, schema_path, output)
        store_result(result, "review")
        if result["rate_limited"]:
            return pause_quota(f"Review: {result['rate_limit_message']} (see {log})")
        if not result["success"] or not output.exists():
            return fail("Reviewer failed to produce structured report: " + str(log))
        try:
            report = json.loads(output.read_text(encoding="utf-8"))
            assert report["verdict"] in {"PASS", "REVISE", "BLOCKED"}
            assert isinstance(report["findings"], list) and isinstance(report["evidence_gaps"], list)
        except (ValueError, KeyError, AssertionError) as exc:
            return fail("Invalid reviewer report: " + str(exc))
        state["reviews"].append({"time": now(), "report": report, "path": str(output)})
        write_json(state_file, state)
        if report["verdict"] == "BLOCKED":
            return fail("Reviewer requires human decision: " + report["summary"])
        if report["verdict"] == "PASS" and not report["findings"] and not report["evidence_gaps"]:
            # Prevent accidental success when tasks were modified by the reviewer.
            current = load_tasks(root, change)
            if any(not current[tid]["done"] for tid in group_tasks):
                return fail("Task checkboxes changed during review")
            state["status"] = "review_passed"
            state["completed_at"] = now()
            state["final_git_status"] = git_snapshot(root)
            write_json(state_file, state)
            print(f"REVIEW PASS for {args.group}. No commit/push/deploy/archive performed.\nState: {state_file}", flush=True)
            return 0
        failed_feedback = "Reviewer report (REVISE): " + json.dumps(report, ensure_ascii=False)
        if cycle == max_cycles:
            return fail("Maximum review repair cycles reached: " + str(output))
        # Bounded group-scope repair without changing task checkboxes merely to trigger work.
        # The follow-up review repeats even if all task checkboxes remain checked.
        print("REPAIR reviewer findings using implementer", flush=True)
        fix_prompt = (f"OpenSpec change {change}, group {args.group}, tasks {', '.join(group_tasks)}.\n"
                      "Fix ONLY the actionable findings from the independent read-only review.\n"
                      "Read actual code/specs. Make minimal changes and add regression tests.\n"
                      "Do not change unrelated tasks, orchestration files, or weaken tests.\n"
                      "No commit, push, deploy, archive, or external service calls.\n"
                      "BLOCKED: <reason> if public contract changes or human authorization are required.\n"
                      + failed_feedback[:12000])
        fix_log = state_dir / f"repair-cycle{cycle}.jsonl.log"
        fix_result = codex_exec(root, cfg["models"]["implementer"], fix_prompt,
                                "workspace-write", seconds, fix_log)
        store_result(fix_result, "repair")
        if fix_result["rate_limited"]:
            return pause_quota(f"Repair: {fix_result['rate_limit_message']} (see {fix_log})")
        if fix_result["blocked"] or not fix_result["success"]:
            return fail("Repair blocked or failed: " + str(fix_log))
        # Next iteration performs the quality gate and independent review again.
    return fail("Unexpected control flow")


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, AssertionError, RuntimeError, subprocess.SubprocessError) as exc:
        print("ERROR:", exc, file=sys.stderr)
        sys.exit(2)

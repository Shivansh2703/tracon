"""OpenHands (CodeActAgent) SWE-bench evaluation outputs -> the study's schema.

Source: ``huggingface.co/datasets/OpenHands/openhands-evaluation-outputs``,
``outputs/SWE-bench_Lite-test/CodeActAgent/<model-config>/output.jsonl``. One
JSON object per SWE-bench instance; ``history`` is a flat, ordered list of
events where every action is followed by the observation it caused.

This is the only public corpus found that carries all four fields the study's
three findings need at true per-call granularity:

===========================  ==========================================================
study field                  OpenHands field
===========================  ==========================================================
``duration_ms``              ``observation.timestamp`` - ``action.timestamp``
``name``                     the runtime ``action`` (see judgement 4)
``is_error``                 ``observation.extras.exit_code``, or a marker in the
                             observation body where the tool has no status field
context tokens               ``model_response.usage.{prompt,cache_creation,cache_read}``
===========================  ==========================================================

Five judgements are made here rather than in the analyses, and each one is
stated because each one moves a number:

1. **``finish`` is not a tool call.** OpenHands models "I am done" as a
   function call with no observation. Emitting it as a tool call would add one
   never-returned call per run and swamp the study's extreme-tail metric (25
   such calls in 85,104). It is emitted as a model turn holding no tool use,
   which is what it structurally is: the agent stopping.
2. **Arguments are the model's, not the harness's.** The fingerprint uses the
   literal ``function.arguments`` JSON the model emitted. OpenHands' ``args``
   dict additionally carries ``thought`` (the model's prose) and harness flags
   like ``keep_prompt``; fingerprinting those would make near-every call unique
   and drive the repeat rate to zero by construction.
3. **The editor's error signal is a content prefix, not a flag.** ``run``
   observations carry ``extras.exit_code``; ``run_ipython`` carries nothing,
   and a failed edit is reported only in the body text. Worse, the corpus spans
   two editor generations with different failure vocabularies (``ERROR:`` in
   the v2 ``str_replace_editor``; ``[No exact match found in`` and ``[Your
   proposed edit has introduced new syntax error`` in the v1.9 line editor).
   ``EDITOR_ERROR_MARKERS`` enumerates them, every marker's hits are counted
   separately in the manifest, and ``run``-only figures are reported alongside
   as a sensitivity check — because a heuristic that the headline depends on
   should be one the reader can subtract.
4. **Tool identity is the runtime action, not the function name.** The corpus
   spans OpenHands versions with and without native function calling: the same
   primitive is ``execute_bash`` in one and simply ``run`` in the other. Keying
   on ``tool_call_metadata.function_name`` would split one tool into two and
   silently drop identity for the eight older runs that have no such metadata
   at all. The action (``run`` / ``run_ipython``) is stable across every
   version; the function name rides along as an extra field.
5. **``end_status`` is inferred from how the loop stopped, and does not mean
   what it means in the study.** ``failed`` when the harness recorded an
   ``error``; ``completed`` when the agent called ``finish``; ``killed``
   otherwise. In practice ``killed`` never fires, because this harness records
   even "hit the step cap" as an error — so ``failed`` here is the union of
   step-cap exhaustion, its own stuck-loop detector, context-window overflow
   and crashes, where the study's ``failed`` is a run that reported failure.
   Read the split as "did the loop end on the agent's terms", nothing more.

Unlike the study's own corpus this one carries **ground truth**: SWE-bench
``report.resolved`` says whether the run's patch actually fixed the bug. It is
passed through onto the session event so the replication can ask a question the
original data could not - whether a tool error predicts a *wrong* answer rather
than merely an unfinished one.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from datetime import datetime
from pathlib import Path

from ._emit import ExportWriter, ShapeMode

#: Actions that represent a real tool invocation with an observable result.
TOOL_ACTIONS = {"run", "run_ipython", "edit", "browse", "browse_interactive", "read", "write"}

#: Actions that are model turns, not tool calls. ``finish`` is the agent
#: declaring completion; ``message`` is prose (or, at id 0, the task prompt).
NON_TOOL_ACTIONS = {"finish", "message", "think", "reject"}

#: Fallback argument keys per action, used only when the raw function-call
#: arguments are unavailable (the ``non-fncall`` prompting configs, where the
#: model emits a text-formatted call the harness parses). Deliberately the
#: semantic payload only: no ``thought``, no harness flags.
FALLBACK_ARG_KEYS = {
    "run": ("command",),
    "run_ipython": ("code",),
    "edit": ("path", "content"),
    "browse": ("url",),
    "browse_interactive": ("browser_actions",),
}

#: The file editors report failure as output text rather than a status field.
#: Keyed by a label so the manifest can report which vocabulary fired, and so a
#: reader can see exactly what was counted as an editor failure.
EDITOR_ERROR_MARKERS = {
    # v2 str_replace_editor
    "editor_ERROR_prefix": ("ERROR:",),
    # v1.9 line editor
    "editor_no_exact_match": ("[No exact match found in",),
    "editor_syntax_error": ("[Your proposed edit has introduced new syntax error",),
}

#: An uncaught exception inside a run_ipython cell. IPython prints the frame
#: header or a rule of dashes first. Counted separately because it is the
#: shakiest of these signals and the sensitivity analysis drops it.
TRACEBACK_MARKERS = ("Cell In[", "Traceback (most recent call last)", "-" * 20)


def _parse_ts(value: str | None) -> int | None:
    """ISO-8601 -> epoch milliseconds. Timestamps here are naive local time;
    only *differences* are used, so the missing offset does not matter."""
    if not value:
        return None
    try:
        return int(datetime.fromisoformat(value).timestamp() * 1000)
    except ValueError:
        return None


def _raw_arguments(action: dict) -> dict | None:
    """The literal arguments the model emitted for this call, if recorded.

    Located by matching ``tool_call_id`` inside the model response that carried
    the call — a single response can hold several calls, and taking the first
    would silently mis-attribute arguments in those runs.
    """
    meta = action.get("tool_call_metadata") or {}
    call_id = meta.get("tool_call_id")
    choices = ((meta.get("model_response") or {}).get("choices")) or []
    for choice in choices:
        for call in ((choice.get("message") or {}).get("tool_calls")) or []:
            if call.get("id") != call_id:
                continue
            raw = (call.get("function") or {}).get("arguments")
            if isinstance(raw, str):
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError:
                    return {"_unparsed": raw}
                return parsed if isinstance(parsed, dict) else {"_value": parsed}
            if isinstance(raw, dict):
                return raw
    return None


def tool_arguments(action: dict) -> dict:
    """Semantic arguments for fingerprinting. See judgement 2 in the module doc."""
    raw = _raw_arguments(action)
    if raw is not None:
        return raw
    args = action.get("args") or {}
    keys = FALLBACK_ARG_KEYS.get(action.get("action"), ())
    return {k: args[k] for k in keys if k in args}


def error_signal(observation: dict) -> tuple[bool, str | None]:
    """``(errored, which signal said so)``.

    ``run`` has a real exit status; a null one is *unknown*, not failure, and
    is not counted as an error. ``run_ipython`` has nothing but its output, so
    the answer comes from an enumerated marker list — and the label comes back
    with it so the manifest can show what each headline rests on.
    """
    extras = observation.get("extras") or {}
    if "exit_code" in extras:
        code = extras["exit_code"]
        if code is None:
            return False, "exit_code_null"
        return code != 0, "exit_code"
    body = (observation.get("content") or "").lstrip()
    for label, prefixes in EDITOR_ERROR_MARKERS.items():
        if body.startswith(prefixes):
            return True, label
    if body.startswith(TRACEBACK_MARKERS):
        return True, "cell_traceback"
    return False, None


def is_error(observation: dict) -> bool:
    return error_signal(observation)[0]


def end_status(record: dict, saw_finish: bool) -> str:
    """See judgement 4 in the module docstring."""
    if record.get("error"):
        return "failed"
    return "completed" if saw_finish else "killed"


def _usage(action: dict) -> tuple[str | None, dict, str | None, int]:
    """``(response_id, usage-split, model, tool_use_block_count)``.

    ``prompt_tokens`` from litellm already includes the cached and
    cache-creation input, but the study's loader *sums* its three fields — so
    the fresh count is emitted as the remainder and the total round-trips to
    ``prompt_tokens`` exactly.
    """
    meta = action.get("tool_call_metadata") or {}
    response = meta.get("model_response") or {}
    usage = response.get("usage") or {}
    prompt = usage.get("prompt_tokens")
    cache_read = usage.get("cache_read_input_tokens") or 0
    cache_create = usage.get("cache_creation_input_tokens") or 0
    split: dict = {}
    if prompt is not None:
        split = {
            "in_tokens": max(0, prompt - cache_read - cache_create),
            "cache_read": cache_read,
            "cache_create": cache_create,
        }
    return response.get("id"), split, response.get("model"), meta.get("total_calls_in_response") or 0


def flatten_history(history: object) -> list[dict]:
    """Both history layouts -> one ordered list of event dicts.

    Older runs (OpenHands v1.9-era) store ``[[action, observation], ...]``;
    newer ones store a flat list. Silently skipping the paired form is not a
    hypothetical: the first version of this adapter did exactly that and
    produced a corpus in which 2,398 of 3,895 runs had no tool calls at all,
    with every headline quietly computed from the five newest runs.
    """
    out: list[dict] = []
    for entry in history or []:
        if isinstance(entry, dict):
            out.append(entry)
        elif isinstance(entry, list):
            out.extend(e for e in entry if isinstance(e, dict))
    return out


def convert_record(
    record: dict, writer: ExportWriter, session: str, only_actions: set[str] | None = None
) -> None:
    """One SWE-bench instance -> one stream keyed ``(run, instance_id)``.

    ``only_actions`` restricts which tools are emitted at all. Its purpose is
    the sensitivity check the editor heuristic demands: ``{"run"}`` yields a
    corpus in which every error is a real process exit code, so any finding
    that survives it does not rest on marker-matching output text.
    """
    instance = record.get("instance_id") or "?"
    history = flatten_history(record.get("history"))

    observations_by_cause: dict = {}
    for event in history:
        if "observation" in event and event.get("cause") is not None:
            observations_by_cause.setdefault(event["cause"], event)

    emitted_api: set[str] = set()
    stamps: list[int] = []
    saw_finish = False
    model_name = None

    for event in history:
        if "action" not in event:
            continue
        action = event.get("action")
        ts = _parse_ts(event.get("timestamp"))
        if ts is not None:
            stamps.append(ts)
        response_id, usage_split, model, tool_use_blocks = _usage(event)
        model_name = model_name or model

        if action in NON_TOOL_ACTIONS:
            if action == "finish":
                saw_finish = True
            if event.get("source") != "agent":
                continue  # the task prompt, not a model turn
            # Judgement 1: a model turn that issues no tool use. `finish` is the
            # agent stopping, so it must not read as "kept acting".
            uuid = f"{instance}:turn:{event.get('id')}"
            writer.api_call(
                session, instance, uuid=uuid, ts=ts, model=model,
                tool_use_blocks=0, **usage_split,
            )
            writer.bump(f"model_turn_{action}")
            continue

        if action not in TOOL_ACTIONS:
            writer.bump(f"skipped_action_{action}")
            continue

        if only_actions is not None and action not in only_actions:
            writer.bump(f"filtered_out_{action}")
            continue

        meta = event.get("tool_call_metadata") or {}
        api_uuid = None
        if response_id and usage_split:
            api_uuid = f"{instance}:{response_id}"
            if api_uuid not in emitted_api:
                emitted_api.add(api_uuid)
                writer.api_call(
                    session, instance, uuid=api_uuid, ts=ts, model=model,
                    tool_use_blocks=tool_use_blocks or 1, **usage_split,
                )
        else:
            # No usage block — either an older run with no per-call token
            # accounting at all, or a response that omitted it. The model turn
            # is still emitted, because "after an error, did the model issue
            # another tool?" is answerable without token counts and would
            # otherwise read as "no further model call" for eight of the
            # thirteen runs. The tool call is left unjoined, so the *context*
            # question correctly reports those calls as unjoinable.
            uuid = f"{instance}:{response_id}" if response_id else f"{instance}:turn:{event.get('id')}"
            if uuid not in emitted_api:
                emitted_api.add(uuid)
                writer.api_call(
                    session, instance, uuid=uuid, ts=ts, model=model,
                    tool_use_blocks=tool_use_blocks or 1,
                )
            writer.bump("call_without_token_usage")

        observation = observations_by_cause.get(event.get("id"))
        if observation is None:
            writer.tool_call(
                session, instance,
                id=f"{instance}:{event.get('id')}",
                name=action,
                function_name=meta.get("function_name"),
                args=tool_arguments(event),
                ts=ts, ts_result=None, duration_ms=None,
                api_uuid=api_uuid, status="unmatched",
            )
            writer.bump("unmatched_tool_call")
            continue

        ts_result = _parse_ts(observation.get("timestamp"))
        if ts_result is not None:
            stamps.append(ts_result)
        duration = None
        if ts is not None and ts_result is not None:
            duration = max(0, ts_result - ts)
        errored, signal = error_signal(observation)
        if signal:
            writer.bump(f"error_signal_{signal}" if errored else f"signal_{signal}")
        writer.tool_call(
            session, instance,
            id=f"{instance}:{event.get('id')}",
            name=action,
            function_name=meta.get("function_name"),
            args=tool_arguments(event),
            ts=ts, ts_result=ts_result, duration_ms=duration,
            is_error=errored,
            result_chars=len(observation.get("content") or ""),
            api_uuid=api_uuid,
        )

    report = record.get("report") or {}
    writer.session(
        session, instance,
        t_start=min(stamps) if stamps else None,
        t_end=max(stamps) if stamps else None,
        project=session,
        end_status=end_status(record, saw_finish),
        agent_type=model_name,
        resolved=report.get("resolved"),
        harness_error=record.get("error"),
    )


def iter_records(path: Path) -> Iterator[dict]:
    with Path(path).open() as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def convert(
    inputs: Iterable[Path],
    out_dir: Path,
    *,
    shape_mode: ShapeMode = ShapeMode.SHAPE,
    limit_per_file: int | None = None,
    only_actions: set[str] | None = None,
) -> Path:
    """Convert one or more ``output.jsonl`` files into one export directory.

    Each input file is one model configuration and becomes one ``session``;
    each SWE-bench instance inside it becomes one subagent stream, so the
    study's subagent-scoped analyses (termination, recovery) apply unchanged.
    """
    writer = ExportWriter(out_dir=Path(out_dir), adapter="openhands", shape_mode=shape_mode)
    sources = []
    for path in inputs:
        path = Path(path)
        session = path.stem
        count = 0
        for record in iter_records(path):
            if limit_per_file is not None and count >= limit_per_file:
                break
            convert_record(record, writer, session, only_actions=only_actions)
            count += 1
        sources.append({"file": str(path), "session": session, "instances": count})
    writer.notes.update(
        {
            "dataset": "OpenHands/openhands-evaluation-outputs",
            "url": "https://huggingface.co/datasets/OpenHands/openhands-evaluation-outputs",
            "benchmark": "SWE-bench Lite (test split), CodeActAgent",
            "sources": sources,
            "only_actions": sorted(only_actions) if only_actions else None,
        }
    )
    return writer.write()

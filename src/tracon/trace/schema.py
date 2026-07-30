"""Pinned schema for the raw Claude Code transcript format and the normalized trace events.

The transcript format under ``~/.claude/projects`` is Claude Code's own and undocumented —
it can drift between versions. This module pins exactly what the exporter understands.
Anything outside these allowlists is reported as a schema anomaly and (by default) fails
the export loudly rather than silently dropping signal.

Raw layout walked by the exporter::

    <root>/<project-dir>/<session-uuid>.jsonl              main session transcript
    <root>/<project-dir>/<session-uuid>/subagents/
        agent-<hex>.jsonl + agent-<hex>.meta.json          subagent transcripts
        workflows/wf_*/agent-<hex>.jsonl + .meta.json      workflow-worker transcripts
        workflows/wf_*/journal.jsonl                       SKIPPED (different schema)

Normalized events (one JSON object per line, ``ev`` discriminator; all timestamps are
epoch milliseconds; all content is stripped — lengths and shapes survive, text doesn't):

``session``
    One per transcript file. Main sessions: ``agent`` is null. Subagents: ``agent`` is
    the hex id, with spawn linkage (``spawned_by_tool_use``, ``spawn_depth``,
    ``agent_type``, ``background``, ``workflow``) from the meta file and ``end_status``
    resolved from the parent transcript (sync tool_result → completed; task-notification
    → completed/failed/killed; neither → unknown).

``prompt``
    A human/user turn arrival: user line that is not a tool_result carrier, not meta.

``api_call``
    One model response (assistant lines merged by ``message.id`` — the transcript writes
    one content block per line). Carries model, effort, stop_reason, block counts and
    char sizes, and full token usage including cache splits (``cache_read`` is the
    context-warmth signal).

``tool_call``
    One tool_use/tool_result pair. ``ts`` = issue time (assistant line), ``ts_result``
    = result time, ``duration_ms`` the difference. ``status``: "matched"; "unmatched"
    (no result on disk — session died or still open); or "orphan_result" (the raw
    transcript dropped the issuing assistant line — observed stream-abort/retry gaps,
    ~0.01% of calls — so only the result side exists). For background agent spawns the
    tool_result is a spawn-ack, not completion: ``duration_ms`` is the ack span, the
    agent's runtime lives on its own ``session`` event.

``notification``
    A <task-notification> completion record consumed by the parent session. The gap
    between an agent's last transcript line and this ts is parent idle-wait.

``turn``
    system/turn_duration line: per-turn wall clock, message count, pending background
    agents.

``compact``
    system/compact_boundary line: context compaction (numeric fields only).

``queue_op``
    queue-operation line: user enqueued/dequeued a prompt mid-turn. Arrival-pattern
    signal; content stripped to char length.
"""

SCHEMA_VERSION = 1

# Top-level line types the exporter understands. "Handled" produce events;
# "ignored" are counted per session and never read beyond their type.
HANDLED_LINE_TYPES = frozenset({"user", "assistant", "system", "queue-operation"})
IGNORED_LINE_TYPES = frozenset(
    {
        "attachment",
        "mode",
        "last-prompt",
        "permission-mode",
        "ai-title",
        "bridge-session",
        "file-history-snapshot",
        "file-history-delta",
        "agent-name",
        "frame-link",
        "summary",
        "progress",
    }
)
KNOWN_LINE_TYPES = HANDLED_LINE_TYPES | IGNORED_LINE_TYPES

# system-line subtypes: handled produce events, ignored are counted.
HANDLED_SYSTEM_SUBTYPES = frozenset({"turn_duration", "compact_boundary"})
IGNORED_SYSTEM_SUBTYPES = frozenset(
    {
        "away_summary",
        "local_command",
        "stop_hook_summary",
        "model_refusal_fallback",
        "scheduled_task_fire",
        "informational",
        "bridge_status",
    }
)
KNOWN_SYSTEM_SUBTYPES = HANDLED_SYSTEM_SUBTYPES | IGNORED_SYSTEM_SUBTYPES

# task-notification statuses that end an agent (same set agent-radar pins;
# "killed" is terminal — the agent is over, it just didn't finish its work).
TERMINAL_NOTIF_STATUSES = frozenset({"completed", "failed", "killed"})

EVENT_TYPES = frozenset(
    {
        "session",
        "prompt",
        "api_call",
        "tool_call",
        "notification",
        "turn",
        "compact",
        "queue_op",
    }
)

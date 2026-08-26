"""Where the seconds go in a voice interaction.

Voice is judged on latency more than on any other property: an engineer
holding a phone in the rain will abandon a correct answer that takes eight
seconds and keep using a rougher one that takes two. Optimising that without
measurement is guesswork, so every stage of the server pipeline is timed and
the totals are attached to the command the client already fetches.

Two rules this module exists to keep:

  * **Never the content.** A timing record carries stage names, durations, a
    language tag, and counts. It never carries the transcript, the audio, a
    task name, or a note — voice content is the most sensitive data this
    feature touches, and a log line is the easiest place to leak it by
    accident. Anything a caller passes that is not a number or a short
    identifier does not belong here.

  * **Never the request's success.** Timing is instrumentation. A failure to
    record a measurement must not fail an engineer's field update, so the
    recorder swallows its own errors and the pipeline never branches on it.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from dataclasses import dataclass, field
from time import perf_counter

logger = logging.getLogger("uvicorn.error").getChild("voice.latency")

#: Stage names the client and the logs agree on. A fixed vocabulary, so a
#: dashboard built on these keys does not break when a stage is renamed
#: somewhere in the middle of the pipeline.
TRANSCRIPTION = "transcription"
CONTEXT = "context"
ANALYSIS = "analysis"
#: Covers candidate matching, draft construction, and clarification building.
DRAFTING = "drafting"
TOTAL = "total"


@dataclass
class VoiceLatency:
    """Stage timings for one voice command, in milliseconds."""

    stages: dict[str, int] = field(default_factory=dict)
    _started: float = field(default_factory=perf_counter)

    @contextmanager
    def stage(self, name: str):
        """Time one stage. Re-entering a name accumulates rather than replaces."""
        began = perf_counter()
        try:
            yield
        finally:
            elapsed = int((perf_counter() - began) * 1000)
            self.stages[name] = self.stages.get(name, 0) + elapsed

    def finish(self) -> dict[str, int]:
        """Close the measurement and return the stage map including `total`.

        `total` is wall-clock from construction, not the sum of the stages, so
        time spent between stages — serialization, database round trips, the
        thread pool hand-off — shows up as the gap instead of disappearing.
        That gap is usually where an unexplained second is hiding.
        """
        self.stages[TOTAL] = int((perf_counter() - self._started) * 1000)
        return dict(self.stages)


def record(
    latency: VoiceLatency,
    *,
    command_id,
    project_id,
    language: str | None = None,
    action_count: int | None = None,
) -> dict[str, int]:
    """Log the timings and return them for storage on the command.

    Returned rather than written here so the caller decides persistence — the
    command row is committed on its own schedule, and this must never open a
    transaction of its own.
    """
    stages = latency.finish()
    try:
        logger.info(
            "voice latency command=%s project=%s language=%s actions=%s %s",
            command_id,
            project_id,
            # A BCP-47-ish tag at most; never the speech itself.
            (language or "auto")[:12],
            action_count if action_count is not None else "-",
            " ".join(f"{name}={value}ms" for name, value in sorted(stages.items())),
        )
    except Exception:  # noqa: BLE001 - instrumentation must not break the request
        logger.debug("voice latency logging failed", exc_info=True)
    return stages

"""Which findings are worth interrupting somebody for, and how loudly.

An analysis system that notifies on everything is one people turn off, and a
system nobody reads detects nothing. So the decision to notify is separate from
the decision to record: every finding is stored and reviewable, and only some
of them reach a person unprompted.

The roadmap sets the shape — low confidence informational, medium worth a look,
high urgent — and the important part is what that implies at the bottom end. A
finding the agent is not confident about is **stored and not pushed**. It is
there when someone opens the queue, and it does not wake anybody at seven in
the morning to say something might be wrong.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.services.notification_service import (
    CATEGORY_SYSTEM,
    CATEGORY_WORKFLOW,
    PRIORITY_IMPORTANT,
    PRIORITY_INFO,
    PRIORITY_NORMAL,
)

#: Confidence at or above which a finding is treated as reliable enough to
#: interrupt someone. Below `REVIEW_CONFIDENCE` a finding is recorded only.
URGENT_CONFIDENCE = 0.85
REVIEW_CONFIDENCE = 0.6

#: Severities that justify urgency *when* confidence supports it. A confident
#: finding about something trivial is still trivial.
URGENT_SEVERITIES = frozenset({"HIGH", "CRITICAL"})


@dataclass(frozen=True)
class NotificationDecision:
    """Whether to notify about a finding, how urgently, and why."""

    notify: bool
    priority: str = PRIORITY_NORMAL
    category: str = CATEGORY_SYSTEM
    requires_action: bool = False
    #: The band this fell into, recorded so a reviewer can see why a finding
    #: did or did not reach them.
    band: str = "INFORMATIONAL"
    reason: str = ""

    def as_json(self) -> dict:
        return {
            "notify": self.notify, "priority": self.priority,
            "band": self.band, "requiresAction": self.requires_action,
            "reason": self.reason,
        }


def decide_notification(*, certainty: str, confidence: float, severity: str) -> NotificationDecision:
    """Classify one finding into a notification band.

    `certainty` is checked before confidence because the two say different
    things. An `UNCERTAIN` finding means the agent could not tell — its
    confidence is low *by construction*, and pushing it would turn "I could not
    look" into an alert.
    """
    if certainty == "UNCERTAIN":
        return NotificationDecision(
            notify=False, band="INFORMATIONAL",
            reason=(
                "The agent could not reach a conclusion. Recorded for review; "
                "an inability to assess is not an alert."
            ),
        )

    if certainty == "RECOMMENDATION":
        # A suggested action always needs a person, whatever its confidence —
        # that is the whole point of it being a recommendation.
        return NotificationDecision(
            notify=True, priority=PRIORITY_NORMAL, category=CATEGORY_WORKFLOW,
            requires_action=True, band="REVIEW_RECOMMENDED",
            reason="A recommended action needs a decision from a person.",
        )

    if confidence >= URGENT_CONFIDENCE and severity in URGENT_SEVERITIES:
        return NotificationDecision(
            notify=True, priority=PRIORITY_IMPORTANT, category=CATEGORY_WORKFLOW,
            requires_action=True, band="URGENT",
            reason=(
                f"Confidence {confidence:.2f} and {severity} severity: reliable enough "
                "to act on and serious enough to need attention now."
            ),
        )

    if confidence >= REVIEW_CONFIDENCE:
        return NotificationDecision(
            notify=True, priority=PRIORITY_NORMAL, category=CATEGORY_SYSTEM,
            requires_action=False, band="REVIEW_RECOMMENDED",
            reason=f"Confidence {confidence:.2f}: worth a look, not worth an interruption.",
        )

    return NotificationDecision(
        notify=False, band="INFORMATIONAL",
        reason=(
            f"Confidence {confidence:.2f} is below the {REVIEW_CONFIDENCE} threshold. "
            "Recorded for review rather than pushed."
        ),
    )


def compose_message(*, finding_title: str, description: str, severity: str,
                    confidence: float, recommended_action: str, agent_title: str,
                    location: str | None, evidence_count: int) -> str:
    """The notification body.

    Everything the roadmap asks a notification to carry — what was detected,
    where, from which source, how severe, how confident, how much evidence, and
    what to do next — because a notification that says only "an issue was
    detected" makes the reader open the app to learn whether it mattered.
    """
    lines = [description.strip()]
    if location:
        lines.append(f"Where: {location}")
    lines.append(f"Severity {severity} · confidence {int(round(confidence * 100))}%")
    lines.append(
        f"Based on {evidence_count} source record(s)." if evidence_count
        else "No supporting records were available."
    )
    lines.append(f"Detected by: {agent_title}")
    if recommended_action:
        lines.append(f"Suggested next step: {recommended_action}")
    return "\n".join(lines)

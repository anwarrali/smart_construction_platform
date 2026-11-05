"""Shared backward-compatible insight severity and review semantics."""
SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO")
SEVERITY_ALIASES = {"WARNING": "HIGH", "ATTENTION": "MEDIUM", "SUGGESTION": "LOW",
                    "INFORMATION": "INFO"}
ACTIVE_STATUSES = {"NEW", "OPEN", "UNDER_REVIEW", "ACKNOWLEDGED"}
SETTLED_STATUSES = {"RESOLVED", "DISMISSED", "FALSE_POSITIVE", "ACTIONED", "CONFIRMED", "OUTDATED"}


def severity(value):
    return SEVERITY_ALIASES.get(value.upper(), value.upper())


def status(value):
    return {"UNDER_REVIEW": "ACKNOWLEDGED", "DISMISSED": "FALSE_POSITIVE"}.get(value.upper(), value.upper())

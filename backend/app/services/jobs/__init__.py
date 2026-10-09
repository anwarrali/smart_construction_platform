"""The durable background job queue. See `app.models.background_job`.

Producers call `enqueue` inside the transaction that causes the work; a
`JobRunner` (embedded in the API process, or `python -m app.worker`) claims and
runs it.
"""

from app.services.jobs.queue import enqueue

__all__ = ["enqueue"]

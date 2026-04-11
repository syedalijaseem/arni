"""
Rolling summary scheduler.

SummaryScheduler manages per-meeting APScheduler jobs that call the
POST /ai/summarize endpoint at a configurable interval (default: 10 minutes).

Usage::

    scheduler = SummaryScheduler()
    scheduler.start_for_meeting("meet-1")           # uses AUTO_SUMMARY_INTERVAL_MINUTES
    scheduler.start_for_meeting("meet-2", minutes=5) # override interval
    scheduler.stop_for_meeting("meet-1")
"""

import logging
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import get_settings

logger = logging.getLogger(__name__)

_JOB_ID_PREFIX = "summary_job_"


def _job_id(meeting_id: str) -> str:
    return f"{_JOB_ID_PREFIX}{meeting_id}"


class SummaryScheduler:
    """Manages per-meeting rolling summary jobs."""

    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler()
        self._started = False

    def _ensure_started(self) -> None:
        if not self._started:
            self._scheduler.start()
            self._started = True

    def start_for_meeting(
        self,
        meeting_id: str,
        interval_minutes: Optional[int] = None,
        summarize_fn=None,
    ) -> None:
        """
        Schedule a rolling summary job for ``meeting_id``.

        Args:
            meeting_id: Target meeting identifier.
            interval_minutes: Override for AUTO_SUMMARY_INTERVAL_MINUTES.
            summarize_fn: Async callable to invoke; defaults to the HTTP call.
        """
        self._ensure_started()

        settings = get_settings()
        minutes = interval_minutes if interval_minutes is not None else settings.AUTO_SUMMARY_INTERVAL_MINUTES

        async def _run() -> None:
            """Invoke the summarise function for this meeting."""
            if summarize_fn is not None:
                await summarize_fn(meeting_id)
            else:
                await _default_summarize(meeting_id)

        self._scheduler.add_job(
            _run,
            trigger=IntervalTrigger(minutes=minutes),
            id=_job_id(meeting_id),
            replace_existing=True,
        )
        logger.info("Summary scheduler: started job for meeting=%s (every %d min)", meeting_id, minutes)

    def stop_for_meeting(self, meeting_id: str) -> None:
        """Cancel the rolling summary job for ``meeting_id``."""
        job_id = _job_id(meeting_id)
        try:
            self._scheduler.remove_job(job_id)
            logger.info("Summary scheduler: stopped job for meeting=%s", meeting_id)
        except Exception as exc:
            logger.warning("Summary scheduler: could not stop job %s — %s", job_id, exc)

    def shutdown(self) -> None:
        if self._started:
            self._scheduler.shutdown(wait=False)
            self._started = False


async def _default_summarize(meeting_id: str) -> None:
    """
    Default summarize action: call the /ai/summarize endpoint internally.
    Imports are deferred to avoid circular imports at module load time.
    """
    import httpx
    from app.config import get_settings as _gs

    settings = _gs()
    url = f"http://localhost:8000/ai/summarize"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            await client.post(url, json={"meeting_id": meeting_id})
    except Exception as exc:
        logger.error("Default summarize call failed for meeting=%s: %s", meeting_id, exc)

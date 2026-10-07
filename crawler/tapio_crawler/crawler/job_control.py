"""Operator controls and live progress for a running site job.

A ``JobControl`` is shared between the code that runs a job (which calls
``checkpoint()`` between units of work) and the code that steers it (a signal
handler, a test). Pausing never interrupts a request already in flight; it only
stops the job from starting the next one, so a pause or cancel always leaves
the manifest in a consistent, resumable state.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Literal, Protocol

JobPhase = Literal["pending", "discovery", "render", "done", "incomplete", "cancelled", "failed"]


class RenderCounts(Protocol):
    """The live render counters a progress line reports (``RenderRunSummary`` satisfies this)."""

    @property
    def rendered(self) -> int:
        """Records for which a render completed."""
        ...

    @property
    def saved(self) -> int:
        """Records for which a document was written."""
        ...

    @property
    def failed(self) -> int:
        """Renders that failed outright."""
        ...

    @property
    def retried(self) -> int:
        """Renders scheduled for a later retry."""
        ...


class JobControl:
    """Pause, resume, and cancel signals for one site job."""

    def __init__(self) -> None:
        """Create a control in the running (not paused, not cancelled) state."""
        self._resume = asyncio.Event()
        self._resume.set()
        self._cancelled = asyncio.Event()

    @property
    def paused(self) -> bool:
        """Whether the job is currently held at its next checkpoint."""
        return not self._resume.is_set()

    @property
    def cancelled(self) -> bool:
        """Whether cancellation has been requested."""
        return self._cancelled.is_set()

    def pause(self) -> None:
        """Hold the job at its next checkpoint until ``resume()`` or ``cancel()``."""
        self._resume.clear()

    def resume(self) -> None:
        """Release a paused job."""
        self._resume.set()

    def cancel(self) -> None:
        """Request cancellation; also releases a paused job so it can exit."""
        self._cancelled.set()
        self._resume.set()

    async def wait_cancelled(self) -> None:
        """Block until cancellation is requested."""
        await self._cancelled.wait()

    async def checkpoint(self) -> bool:
        """Wait out any pause, then report whether the job should continue.

        Returns:
            ``True`` to proceed with the next unit of work, ``False`` if the
            job was cancelled.
        """
        await self._resume.wait()
        return not self._cancelled.is_set()


@dataclass
class SiteProgress:
    """Live, read-only-by-observers state of one site job.

    Attributes:
        site_name: Name of the configured source site.
        phase: Where the job currently is.
        due_total: Number of records selected for rendering this run.
        render_summary: The in-flight render summary, once rendering starts.
        current_delay: Effective minimum per-request delay for the host, in
            seconds, once rendering starts.
    """

    site_name: str
    phase: JobPhase = "pending"
    due_total: int = 0
    render_summary: RenderCounts | None = None
    current_delay: float | None = None

    def describe(self, *, paused: bool = False) -> str:
        """Return a one-line, human-readable progress report."""
        label = f"{self.phase} (paused)" if paused and self.phase in ("discovery", "render") else self.phase
        parts = [f"[{self.site_name}] {label}"]
        summary = self.render_summary
        if summary is not None and self.phase in ("render", "done", "incomplete", "cancelled"):
            parts.append(
                f"rendered {summary.rendered}/{self.due_total}; saved {summary.saved}; "
                f"failed {summary.failed}; retried {summary.retried}",
            )
        if self.current_delay is not None and self.phase == "render":
            parts.append(f"delay {self.current_delay:g}s")
        return " | ".join(parts)

"""Tests for operator pause/cancel controls and progress reporting."""

import asyncio

import pytest

from tapio_crawler.crawler.crawler import RenderRunSummary
from tapio_crawler.crawler.job_control import JobControl, SiteProgress


@pytest.mark.asyncio
async def test_checkpoint_passes_when_running() -> None:
    assert await JobControl().checkpoint() is True


@pytest.mark.asyncio
async def test_checkpoint_blocks_while_paused_then_continues_on_resume() -> None:
    control = JobControl()
    control.pause()
    assert control.paused

    waiter = asyncio.ensure_future(control.checkpoint())
    await asyncio.sleep(0.01)
    assert not waiter.done()

    control.resume()
    assert await asyncio.wait_for(waiter, timeout=1) is True
    assert not control.paused


@pytest.mark.asyncio
async def test_cancel_releases_paused_checkpoint_with_false() -> None:
    control = JobControl()
    control.pause()
    waiter = asyncio.ensure_future(control.checkpoint())
    await asyncio.sleep(0.01)

    control.cancel()

    assert await asyncio.wait_for(waiter, timeout=1) is False
    assert control.cancelled
    await asyncio.wait_for(control.wait_cancelled(), timeout=1)


def test_progress_describe_before_render_is_just_phase() -> None:
    progress = SiteProgress(site_name="migri", phase="discovery")

    assert progress.describe() == "[migri] discovery"
    assert progress.describe(paused=True) == "[migri] discovery (paused)"


def test_progress_describe_during_render_includes_counts_and_delay() -> None:
    summary = RenderRunSummary(run_id="r", site_name="migri", rendered=3, saved=2, failed=1, retried=1)
    progress = SiteProgress(
        site_name="migri",
        phase="render",
        due_total=10,
        render_summary=summary,
        current_delay=1.5,
    )

    assert progress.describe() == "[migri] render | rendered 3/10; saved 2; failed 1; retried 1 | delay 1.5s"

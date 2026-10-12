"""The batch slot (session.busy) is released whatever happens to the batch: failure, cancellation or success."""
import asyncio

import pytest

from pista.ui.session import Session


class Runner:
    def __init__(self, run):
        self._run = run

    async def run(self):
        return await self._run()


def claimed() -> tuple[Session, list[bool], list[Exception]]:
    s = Session()
    assert s.begin()
    calls: list[bool] = []
    errors: list[Exception] = []
    return s, calls, errors


def run(s, make_runner, calls, errors):
    def set_busy(value: bool) -> None:
        s.busy = value
        calls.append(value)
    return asyncio.run(s.run_batch(make_runner, set_busy, errors.append))


def test_failure_building_the_runner_releases_the_slot():
    s, calls, errors = claimed()

    def make():
        raise ValueError("bad out dir")
    assert run(s, make, calls, errors) == (None, None)
    assert not s.busy and s.runner is None and calls == [False]
    assert [str(e) for e in errors] == ["bad out dir"]


def test_failure_while_running_releases_the_slot():
    s, calls, errors = claimed()

    async def boom():
        assert s.runner is not None and s.busy  # visible to other pages while it runs
        raise RuntimeError("network")
    runner, summary = run(s, lambda: Runner(boom), calls, errors)
    assert summary is None and not s.busy and s.runner is None and calls == [True, False]
    assert len(errors) == 1


def test_cancellation_releases_the_slot():
    s, calls, errors = claimed()

    async def hang():
        await asyncio.sleep(10)

    async def main():
        def set_busy(value: bool) -> None:
            s.busy = value
            calls.append(value)
        task = asyncio.create_task(s.run_batch(lambda: Runner(hang), set_busy, errors.append))
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(main())
    assert not s.busy and s.runner is None and calls == [True, False] and errors == []


def test_success_leaves_the_slot_to_the_normal_path():
    s, calls, errors = claimed()

    async def ok():
        return "summary"
    r = Runner(ok)
    assert run(s, lambda: r, calls, errors) == (r, "summary")
    assert s.runner is None and s.busy and calls == [True]  # the caller releases it after the summary

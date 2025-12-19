import asyncio
import pytest

from multirig.serial_executor import SerialExecutor


@pytest.mark.asyncio
async def test_serial_executor_runs_in_order():
    ex = SerialExecutor()
    out = []

    async def fn1():
        out.append(1)
        await asyncio.sleep(0)
        out.append(2)
        return "a"

    async def fn2():
        out.append(3)
        return "b"

    r1_task = asyncio.create_task(ex.run(fn1))
    r2_task = asyncio.create_task(ex.run(fn2))
    assert await r1_task == "a"
    assert await r2_task == "b"
    assert out == [1, 2, 3]

    await ex.close()


@pytest.mark.asyncio
async def test_serial_executor_propagates_exception_and_close_stops():
    ex = SerialExecutor()

    async def boom():
        raise ValueError("nope")

    with pytest.raises(ValueError):
        await ex.run(boom)

    await ex.close()

    async def ok():
        return 123

    with pytest.raises(RuntimeError):
        await ex.run(ok)


@pytest.mark.asyncio
async def test_serial_executor_cancelled_future_is_skipped():
    ex = SerialExecutor()

    # Ensure the worker starts.
    await ex.run(lambda: asyncio.sleep(0))

    assert ex._queue is not None

    loop = asyncio.get_running_loop()
    fut = loop.create_future()
    fut.cancel()

    ran = False

    async def fn():
        nonlocal ran
        ran = True
        return 1

    await ex._queue.put((fn, fut))
    await asyncio.sleep(0)

    assert ran is False

    await ex.close()

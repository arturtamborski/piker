"""
Financial signal processing for the peeps.
"""
from typing import AsyncIterator, Callable, Tuple

import trio
import tractor
import numpy as np

from ..log import get_logger
from .. import data
from ._momo import _rsi
from ..data import attach_shm_array, Feed

log = get_logger(__name__)


_fsps = {'rsi': _rsi}


async def latency(
    source: 'TickStream[Dict[str, float]]',  # noqa
    ohlcv: np.ndarray
) -> AsyncIterator[np.ndarray]:
    """Latency measurements, broker to piker.
    """
    # TODO: do we want to offer yielding this async
    # before the rt data connection comes up?

    # deliver zeros for all prior history
    yield np.zeros(len(ohlcv))

    async for quote in source:
        ts = quote.get('broker_ts')
        if ts:
            # This is codified in the per-broker normalization layer
            # TODO: Add more measure points and diffs for full system
            # stack tracing.
            value = quote['brokerd_ts'] - quote['broker_ts']
            yield value


async def increment_signals(
    feed: Feed,
    dst_shm: 'SharedArray',  # noqa
) -> None:
    async for msg in await feed.index_stream():
        array = dst_shm.array
        last = array[-1:].copy()

        # write new slot to the buffer
        dst_shm.push(last)



@tractor.stream
async def cascade(
    ctx: tractor.Context,
    brokername: str,
    src_shm_token: dict,
    dst_shm_token: Tuple[str, np.dtype],
    symbol: str,
    fsp_func_name: str,
) -> AsyncIterator[dict]:
    """Chain streaming signal processors and deliver output to
    destination mem buf.
    """
    src = attach_shm_array(token=src_shm_token)
    dst = attach_shm_array(readonly=False, token=dst_shm_token)

    func: Callable = _fsps[fsp_func_name]

    # open a data feed stream with requested broker
    async with data.open_feed(brokername, [symbol]) as feed:

        assert src.token == feed.shm.token
        # TODO: load appropriate fsp with input args

        async def filter_by_sym(sym, stream):
            async for quotes in stream:
                for symbol, quotes in quotes.items():
                    if symbol == sym:
                        yield quotes

        out_stream = func(
            filter_by_sym(symbol, feed.stream),
            feed.shm,
        )

        # Conduct a single iteration of fsp with historical bars input
        # and get historical output
        history = await out_stream.__anext__()


        # TODO: talk to ``pyqtgraph`` core about proper way to solve this:
        # XXX: hack to get curves aligned with bars graphics: prepend
        # a copy of the first datum..
        dst.push(history[:1])

        # check for data length mis-allignment and fill missing values
        diff = len(src.array) - len(history)
        if diff >= 0:
            for _ in range(diff):
                dst.push(history[:1])

        # compare with source signal and time align
        index = dst.push(history)

        yield index

        async with trio.open_nursery() as n:
            n.start_soon(increment_signals, feed, dst)

            async for processed in out_stream:
                log.info(f"{fsp_func_name}: {processed}")
                index = src.index
                dst.array[-1][fsp_func_name] = processed
                await ctx.send_yield(index)

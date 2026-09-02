"""SSE 队列桥接 — interactive 长请求 (submit/feedback/report) 的流式进度基建。

与 assess/stream (LangGraph stream 逐节点产出) 不同, submit/feedback/report 是
"单函数跑完才算完"的阻塞管线: worker 线程跑重活, emit(event, data) 经队列喂给
同步生成器逐条推送。客户端断开 (生成器被关闭) 置取消事件, worker 在生成循环
检查点感知并停止后续任务 (已在跑的单次 LLM 调用自然收尾)。
"""

import json
import logging
import queue
import threading
import time
from typing import Callable

from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",  # nginx 不缓冲 (开发期无 nginx, 备用)
}


def sse_format(event: str, data: dict) -> str:
    """格式化 SSE 事件: event: <name>\\ndata: <json>\\n\\n (default=str 兜底 datetime 等类型)"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


def sse_stream_response(
    start_data: dict,
    worker_fn: Callable,
    *,
    heartbeat_seconds: int = 15,
) -> StreamingResponse:
    """队列桥接 SSE 响应。

    worker_fn(emit, cancel_check) 在后台 daemon 线程执行, 须自行 emit("done"/"error") 收尾;
    未捕获异常兜底转 error 事件 (HTTP 层保持 200, 错误语义在事件里, status 字段可带 HTTP 码)。
    生成器侧 q.get 带心跳超时: 空闲期发 ping, 同时解决浏览器 60s 无数据看门狗误杀
    与 Electron IPC 侧长静默无反馈两个对向问题。
    """
    q: queue.Queue = queue.Queue()
    cancel_event = threading.Event()
    _SENTINEL = object()

    def emit(event: str, data: dict) -> None:
        q.put(sse_format(event, data))

    def _worker():
        try:
            worker_fn(emit, cancel_event.is_set)
        except Exception as e:  # noqa: BLE001 — worker 兜底: 任何异常都转 error 事件
            logger.error("SSE worker 执行失败", exc_info=True)
            emit("error", {"detail": str(e) or e.__class__.__name__})
        finally:
            q.put(_SENTINEL)

    threading.Thread(target=_worker, daemon=True, name="sse-worker").start()

    def _gen():
        yield sse_format("start", start_data)
        try:
            while True:
                try:
                    item = q.get(timeout=heartbeat_seconds)
                except queue.Empty:
                    yield sse_format("ping", {"ts": time.time()})
                    continue
                if item is _SENTINEL:
                    break
                yield item
        finally:
            # 正常收尾与客户端断开都会走到: 置取消, worker 在检查点尽快停止后续生成
            cancel_event.set()

    return StreamingResponse(_gen(), media_type="text/event-stream", headers=_SSE_HEADERS)

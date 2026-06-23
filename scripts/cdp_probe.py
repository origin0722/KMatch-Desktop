"""
Minimal CDP probe: connect to electron renderer via remote-debugging-port=9222,
run a JS expression in the page, return the result.

Usage:
    python scripts/cdp_probe.py "<JS expression>"
    cat expr.js | python scripts/cdp_probe.py -
"""
import json
import sys
import urllib.request

import websocket  # type: ignore


def pick_renderer_ws() -> str:
    raw = urllib.request.urlopen("http://127.0.0.1:9222/json", timeout=3).read()
    for t in json.loads(raw):
        if t.get("type") == "page" and "localhost" in t.get("url", ""):
            return t["webSocketDebuggerUrl"]
    raise RuntimeError("no renderer page target on 9222")


def run_expr(expr: str) -> dict:
    # Chromium 132+ rejects cross-origin WS upgrades unless --remote-allow-origins
    # is set OR the Origin header matches. Send no Origin (drop the auto one) by
    # passing suppress_origin=True so the handshake skips the cross-origin check.
    ws = websocket.create_connection(
        pick_renderer_ws(),
        timeout=10,
        suppress_origin=True,
    )
    msg = {
        "id": 1,
        "method": "Runtime.evaluate",
        "params": {
            "expression": expr,
            "returnByValue": True,
            "awaitPromise": True,
        },
    }
    ws.send(json.dumps(msg))
    while True:
        reply = json.loads(ws.recv())
        if reply.get("id") == 1:
            ws.close()
            return reply


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "-"
    expr = sys.stdin.read() if arg == "-" else arg
    result = run_expr(expr)
    print(json.dumps(result, ensure_ascii=False, indent=2))

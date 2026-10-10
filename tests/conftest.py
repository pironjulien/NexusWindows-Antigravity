"""Real bridge handlers served on ephemeral ports with a disposable credential."""

import asyncio
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "native-host"))

try:
    import bridge_server
    from bridge_security import load_or_create_token
except ImportError:
    bridge_server = None
    load_or_create_token = None


@pytest.fixture(scope="module", autouse=True)
def isolated_bridge(request, tmp_path_factory):
    if bridge_server is None or not hasattr(request.module, "HTTP_PORT"):
        yield
        return
    token_file = tmp_path_factory.mktemp("bridge") / "token"
    load_or_create_token(token_file)
    patch = pytest.MonkeyPatch()
    patch.setenv("NEXUSAGY_BRIDGE_TOKEN_FILE", str(token_file))
    patch.setattr(bridge_server, "BRIDGE_TOKEN_PATH", token_file)
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()

    async def start():
        http = await asyncio.start_server(
            bridge_server.handle_http, "127.0.0.1", 0, limit=bridge_server.MAX_HEADER_BYTES + 4
        )
        ws = await bridge_server.serve(bridge_server.ws_handler, "127.0.0.1", 0)
        return http, ws

    servers = asyncio.run_coroutine_threadsafe(start(), loop).result(timeout=5)
    port = servers[0].sockets[0].getsockname()[1]
    patch.setattr(request.module, "HTTP_PORT", port, raising=False)
    patch.setattr(request.module, "STATUS_URL", f"http://127.0.0.1:{port}/api/status", raising=False)
    patch.setattr(request.module, "COMMAND_URL", f"http://127.0.0.1:{port}/api/command", raising=False)
    patch.setattr(request.module, "WS_URL", f"ws://127.0.0.1:{servers[1].sockets[0].getsockname()[1]}", raising=False)
    try:
        yield
    finally:

        async def stop():
            for server in servers:
                server.close()
                await server.wait_closed()

        asyncio.run_coroutine_threadsafe(stop(), loop).result(timeout=5)
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=5)
        loop.close()
        patch.undo()

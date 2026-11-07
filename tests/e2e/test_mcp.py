import asyncio
import json
import time

import pytest
import yaml

pytest.importorskip("mcp")

from gruntly import mcp_server  # noqa: E402


def _text(result):
    if getattr(result, "structured_content", None) is not None:
        sc = result.structured_content
        return sc.get("result", sc) if isinstance(sc, dict) else sc
    return json.loads(result.content[0].text)


def test_tools_listed_and_async_run_round_trip(repo, make_spec):
    server = mcp_server.build_server()

    async def go():
        names = {t.name for t in await server.list_tools()}
        assert names == {"gruntly_run", "gruntly_manage"}  # tool schemas sit in context every turn: keep few
        def d(x):
            return x if isinstance(x, dict) else json.loads(x)

        # default: blocks, applies on pass, returns the compact result
        res = d(_text(await server.call_tool("gruntly_run", {"spec_yaml": yaml.safe_dump(make_spec("pass")),
                                                             "repo": str(repo)})))
        assert res["status"] == "passed" and res["applied"] is True
        # async path: queue, poll, read
        (repo / "calc.py").write_text("def add(a, b):\n    return a - b\n")
        started = d(_text(await server.call_tool("gruntly_run", {"spec_yaml": yaml.safe_dump(make_spec("pass")),
                                                                 "repo": str(repo), "wait": False,
                                                                 "apply_on_pass": False})))
        rid = started["run_id"]
        for _ in range(120):
            st = d(_text(await server.call_tool("gruntly_manage", {"run_id": rid, "action": "status", "repo": str(repo)})))
            if st["state"] == "done":
                break
            await asyncio.sleep(0.5)
        res = d(_text(await server.call_tool("gruntly_manage", {"run_id": rid, "action": "result", "repo": str(repo)})))
        assert res["status"] == "passed"
        applied = d(_text(await server.call_tool("gruntly_manage", {"run_id": rid, "action": "apply", "repo": str(repo)})))
        assert applied["applied"] is True

    asyncio.run(go())
    assert "a + b" in (repo / "calc.py").read_text()

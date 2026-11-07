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
        assert {"gruntly_run", "gruntly_status", "gruntly_result", "gruntly_diff", "gruntly_apply",
                "gruntly_discard", "gruntly_continue"} <= names
        started = _text(await server.call_tool("gruntly_run", {"spec_yaml": yaml.safe_dump(make_spec("pass")),
                                                               "repo": str(repo)}))
        started = started if isinstance(started, dict) else json.loads(started)
        assert started["status"] == "queued"
        rid = started["run_id"]
        for _ in range(120):
            st = _text(await server.call_tool("gruntly_status", {"run_id": rid, "repo": str(repo)}))
            st = st if isinstance(st, dict) else json.loads(st)
            if st["state"] == "done":
                break
            await asyncio.sleep(0.5)
        res = _text(await server.call_tool("gruntly_result", {"run_id": rid, "repo": str(repo)}))
        res = res if isinstance(res, dict) else json.loads(res)
        assert res["status"] == "passed"
        applied = _text(await server.call_tool("gruntly_apply", {"run_id": rid, "repo": str(repo)}))
        applied = applied if isinstance(applied, dict) else json.loads(applied)
        assert applied["applied"] is True

    asyncio.run(go())
    assert "a + b" in (repo / "calc.py").read_text()

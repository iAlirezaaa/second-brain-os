"""MCP stdio must survive malformed JSON-RPC requests and serve the next request.

Uses the real shipped server, a disposable root and no host configuration/private notes.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "15_SYSTEM" / "scripts" / "mcp_server.py"


def exchange(messages):
    with tempfile.TemporaryDirectory() as root:
        proc = subprocess.run(
            [sys.executable, str(SERVER), "--root", root],
            input="\n".join(json.dumps(row) for row in messages) + "\n",
            text=True, encoding="utf-8", capture_output=True,
            cwd=str(ROOT), timeout=15,
        )
    replies = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
    return proc, replies


class MalformedWireRequests(unittest.TestCase):
    def test_refuses_bad_shapes_without_losing_the_session(self):
        malformed = [
            ({"jsonrpc": "2.0", "id": 1, "method": 42}, -32600),
            ({"jsonrpc": "2.0", "id": 2, "method": ""}, -32600),
            ({"jsonrpc": "2.0", "id": 3, "method": "initialize", "params": [1]}, -32602),
            ({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": "bad"}, -32602),
            ({"jsonrpc": "2.0", "id": 5, "method": "resources/read",
              "params": {"uri": 42}}, -32602),
            ({"jsonrpc": "2.0", "id": 6, "method": "resources/read",
              "params": []}, -32602),
        ]
        messages = [row for row, _code in malformed] + [
            {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
            {"jsonrpc": "2.0", "id": 7, "method": "ping"},
        ]
        proc, replies = exchange(messages)
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        self.assertEqual(len(malformed) + 1, len(replies), replies)
        for reply, (request, code) in zip(replies, malformed):
            with self.subTest(request=request):
                self.assertEqual(request["id"], reply["id"])
                self.assertEqual(code, reply["error"]["code"])
                self.assertNotIn("result", reply)
        self.assertEqual({"jsonrpc": "2.0", "id": 7, "result": {}}, replies[-1])
        self.assertNotIn("Traceback", proc.stderr)

    def test_valid_initialize_and_tool_listing_still_work(self):
        proc, replies = exchange([
            {"jsonrpc": "2.0", "id": 10, "method": "initialize",
             "params": {"protocolVersion": "2025-06-18"}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 11, "method": "tools/list"},
        ])
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        self.assertEqual([10, 11], [reply.get("id") for reply in replies])
        self.assertEqual("2025-06-18", replies[0]["result"]["protocolVersion"])
        self.assertTrue(replies[1]["result"]["tools"])


if __name__ == "__main__":
    unittest.main()

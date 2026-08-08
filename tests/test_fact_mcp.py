from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from semantic_verifier.fact_mcp import (
    CLIENT_CAPABILITIES_KEY,
    CLIENT_INFO_KEY,
    INVALID_PARAMS,
    INVALID_REQUEST,
    MCP_PROTOCOL_VERSION,
    MCP_TOOL_NAME,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    PROTOCOL_VERSION_KEY,
    SERVER_INFO_KEY,
    UNSUPPORTED_PROTOCOL_VERSION,
    FactMcpServer,
)
from semantic_verifier.fact_queries import FactWorld, QUERY_SCHEMA, read_fact_index


ROOT = Path(__file__).resolve().parents[1]
WORLD_PATH = ROOT / "fixtures" / "facts" / "expected" / "world.fact-index.json"
LIMITATIONS_PATH = (
    ROOT / "fixtures" / "facts" / "expected" / "limitations.fact-index.json"
)
SERVER_TOOL = ROOT / "tools" / "fact_mcp_server.py"
EVIDENCE_PATH = ROOT / "research" / "mcp_fact_query_evidence.json"


def metadata(version: str = MCP_PROTOCOL_VERSION):
    return {
        CLIENT_CAPABILITIES_KEY: {},
        CLIENT_INFO_KEY: {
            "name": "fact-mcp-test",
            "version": "1.0",
        },
        PROTOCOL_VERSION_KEY: version,
    }


def request(identity, method, **params):
    return {
        "id": identity,
        "jsonrpc": "2.0",
        "method": method,
        "params": {
            "_meta": metadata(),
            **params,
        },
    }


class FactMcpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = FactMcpServer(FactWorld(read_fact_index(WORLD_PATH)))

    def decoded(self, payload):
        response = self.server.handle_line(
            json.dumps(
                payload,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        self.assertIsNotNone(response)
        self.assertTrue(response.endswith("\n"))
        self.assertNotIn("\n", response[:-1])
        return json.loads(response)

    def call(self, identity, kind, selector, **arguments):
        return self.decoded(
            request(
                identity,
                "tools/call",
                name=MCP_TOOL_NAME,
                arguments={
                    "kind": kind,
                    "selector": selector,
                    **arguments,
                },
            )
        )

    def run_raw(self, raw: bytes, index: Path = WORLD_PATH):
        return subprocess.run(
            [
                sys.executable,
                str(SERVER_TOOL),
                str(index),
            ],
            cwd=ROOT,
            input=raw,
            capture_output=True,
            check=False,
            timeout=30,
        )

    def test_official_evidence_is_dated_and_freezes_current_profile(self):
        payload = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(
            payload["schema"],
            "codeskeptic.mcp-fact-query-evidence/v1",
        )
        self.assertEqual(payload["reviewed_on"], "2026-08-07")
        self.assertEqual(payload["protocol_version"], MCP_PROTOCOL_VERSION)
        self.assertEqual(
            payload["implementation_profile"]["messages"],
            ["server/discover", "tools/list", "tools/call"],
        )
        self.assertIn(
            "initialize",
            payload["implementation_profile"]["removed_messages"],
        )
        self.assertGreaterEqual(len(payload["requirements"]), 7)
        for source in payload["sources"]:
            self.assertTrue(
                source["url"].startswith(
                    "https://modelcontextprotocol.io/"
                    "specification/2026-07-28/"
                )
            )

    def test_discovery_is_stateless_complete_and_identifies_server(self):
        response = self.decoded(request("discover", "server/discover"))
        self.assertEqual(response["id"], "discover")
        result = response["result"]
        self.assertEqual(result["resultType"], "complete")
        self.assertEqual(
            result["supportedVersions"],
            [MCP_PROTOCOL_VERSION],
        )
        self.assertEqual(
            result["capabilities"],
            {"tools": {"listChanged": False}},
        )
        self.assertEqual(result["cacheScope"], "public")
        self.assertGreater(result["ttlMs"], 0)
        self.assertEqual(
            result["_meta"][SERVER_INFO_KEY]["name"],
            "codeskeptic-fact-query",
        )

        removed = self.decoded(request(1, "initialize"))
        self.assertEqual(removed["error"]["code"], METHOD_NOT_FOUND)

    def test_tool_list_is_deterministic_read_only_and_cacheable(self):
        first_text = self.server.handle_line(
            json.dumps(request(1, "tools/list"), sort_keys=True)
        )
        second_text = self.server.handle_line(
            json.dumps(request(1, "tools/list"), sort_keys=True)
        )
        self.assertEqual(first_text, second_text)
        result = json.loads(first_text)["result"]
        self.assertEqual(result["resultType"], "complete")
        self.assertEqual(result["cacheScope"], "public")
        self.assertGreater(result["ttlMs"], 0)
        self.assertEqual(len(result["tools"]), 1)
        tool = result["tools"][0]
        self.assertEqual(tool["name"], MCP_TOOL_NAME)
        self.assertEqual(
            tool["annotations"],
            {
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
                "readOnlyHint": True,
            },
        )
        self.assertEqual(
            tool["outputSchema"]["properties"]["schema"]["const"],
            QUERY_SCHEMA,
        )

    def test_all_three_queries_return_exact_structured_and_text_content(self):
        callers = self.call(1, "who-calls", "store")["result"]
        self.assertFalse(callers["isError"])
        self.assertEqual(
            callers["structuredContent"]["answer"]["callers"][0]
            ["symbol"]["qualified_name"],
            "pipeline",
        )

        mutators = self.call(
            2,
            "who-mutates",
            "global_total",
        )["result"]
        self.assertFalse(mutators["isError"])
        self.assertEqual(
            mutators["structuredContent"]["answer"]["mutators"][0]
            ["symbol"]["qualified_name"],
            "store",
        )

        neighborhood = self.call(
            3,
            "neighborhood",
            "pipeline",
            depth=2,
        )["result"]
        self.assertFalse(neighborhood["isError"])
        self.assertEqual(
            neighborhood["structuredContent"]["answer"]["depth"],
            2,
        )

        for result in (callers, mutators, neighborhood):
            self.assertEqual(result["resultType"], "complete")
            self.assertEqual(
                json.loads(result["content"][0]["text"]),
                result["structuredContent"],
            )
            self.assertEqual(
                result["structuredContent"]["schema"],
                QUERY_SCHEMA,
            )

    def test_query_failures_are_visible_tool_results_not_fabricated_facts(self):
        ambiguous = self.call(
            1,
            "who-calls",
            "math::normalize",
        )["result"]
        self.assertTrue(ambiguous["isError"])
        self.assertIn("ambiguous", ambiguous["content"][0]["text"])
        self.assertNotIn("structuredContent", ambiguous)

        invalid_depth = self.call(
            2,
            "neighborhood",
            "pipeline",
            depth=9,
        )["result"]
        self.assertTrue(invalid_depth["isError"])
        self.assertIn("between 0 and 8", invalid_depth["content"][0]["text"])

        extra = self.call(
            3,
            "who-calls",
            "store",
            depth=1,
        )["result"]
        self.assertTrue(extra["isError"])
        self.assertIn("only valid", extra["content"][0]["text"])

    def test_protocol_metadata_version_method_and_tool_errors_are_typed(self):
        missing_meta = request(1, "tools/list")
        del missing_meta["params"]["_meta"]
        response = self.decoded(missing_meta)
        self.assertEqual(response["error"]["code"], INVALID_PARAMS)

        wrong_version = request(2, "server/discover")
        wrong_version["params"]["_meta"] = metadata("2025-11-25")
        response = self.decoded(wrong_version)
        self.assertEqual(
            response["error"]["code"],
            UNSUPPORTED_PROTOCOL_VERSION,
        )
        self.assertEqual(
            response["error"]["data"],
            {
                "requested": "2025-11-25",
                "supported": [MCP_PROTOCOL_VERSION],
            },
        )

        unknown_method = self.decoded(request(3, "resources/list"))
        self.assertEqual(
            unknown_method["error"]["code"],
            METHOD_NOT_FOUND,
        )

        unknown_tool = self.decoded(
            request(
                4,
                "tools/call",
                name="unknown",
                arguments={},
            )
        )
        self.assertEqual(unknown_tool["error"]["code"], INVALID_PARAMS)

    def test_malformed_json_requests_and_params_fail_deterministically(self):
        parse = json.loads(self.server.handle_line("{"))
        self.assertEqual(parse["error"]["code"], PARSE_ERROR)
        self.assertNotIn("id", parse)

        non_finite = json.loads(self.server.handle_line('{"value":NaN}'))
        self.assertEqual(non_finite["error"]["code"], PARSE_ERROR)

        not_object = self.decoded([])
        self.assertEqual(not_object["error"]["code"], INVALID_REQUEST)

        invalid_id = {
            "id": True,
            "jsonrpc": "2.0",
            "method": "tools/list",
            "params": {"_meta": metadata()},
        }
        response = self.decoded(invalid_id)
        self.assertEqual(response["error"]["code"], INVALID_REQUEST)
        self.assertNotIn("id", response)

        invalid_params = {
            "id": 1,
            "jsonrpc": "2.0",
            "method": "tools/list",
            "params": [],
        }
        response = self.decoded(invalid_params)
        self.assertEqual(response["error"]["code"], INVALID_PARAMS)

    def test_notifications_never_receive_a_response(self):
        notification = request(1, "notifications/cancelled")
        del notification["id"]
        self.assertIsNone(self.server.handle_message(notification))

        malformed_notification = {
            "jsonrpc": "2.0",
            "method": "tools/list",
            "params": {},
        }
        self.assertIsNone(
            self.server.handle_message(malformed_notification)
        )

    def test_subprocess_discovery_listing_calls_and_eof_are_clean(self):
        messages = [
            request("d", "server/discover"),
            request("l", "tools/list"),
            request(
                "q",
                "tools/call",
                name=MCP_TOOL_NAME,
                arguments={
                    "kind": "who-calls",
                    "selector": "store",
                },
            ),
        ]
        raw = b"".join(
            (
                json.dumps(
                    message,
                    ensure_ascii=True,
                    separators=(",", ":"),
                    sort_keys=True,
                )
                + "\n"
            ).encode("utf-8")
            for message in messages
        )
        first = self.run_raw(raw)
        second = self.run_raw(raw)
        self.assertEqual(first.returncode, 0, first.stderr.decode())
        self.assertEqual(second.returncode, 0, second.stderr.decode())
        self.assertEqual(first.stdout, second.stdout)
        self.assertEqual(first.stderr, b"")
        outputs = [
            json.loads(line)
            for line in first.stdout.decode("utf-8").splitlines()
        ]
        self.assertEqual([item["id"] for item in outputs], ["d", "l", "q"])
        self.assertFalse(outputs[2]["result"]["isError"])

    def test_subprocess_suppresses_notifications_and_separates_parse_errors(self):
        notification = request(1, "notifications/cancelled")
        del notification["id"]
        raw = (
            json.dumps(notification, separators=(",", ":")).encode("utf-8")
            + b"\n"
            + b"\xff\n"
            + json.dumps(request(2, "tools/list")).encode("utf-8")
            + b"\n"
        )
        completed = self.run_raw(raw)
        self.assertEqual(completed.returncode, 0)
        self.assertEqual(completed.stderr, b"")
        outputs = [
            json.loads(line)
            for line in completed.stdout.decode("utf-8").splitlines()
        ]
        self.assertEqual(len(outputs), 2)
        self.assertEqual(outputs[0]["error"]["code"], PARSE_ERROR)
        self.assertEqual(outputs[1]["id"], 2)

    def test_invalid_index_fails_before_protocol_output(self):
        with tempfile.TemporaryDirectory() as directory:
            invalid = Path(directory) / "invalid.json"
            invalid.write_text(
                '{"schema":"wrong"}\n',
                encoding="utf-8",
                newline="\n",
            )
            completed = self.run_raw(b"", invalid)
        self.assertEqual(completed.returncode, 3)
        self.assertEqual(completed.stdout, b"")
        self.assertIn(b"fact-mcp input error", completed.stderr)


if __name__ == "__main__":
    unittest.main()

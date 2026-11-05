import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

from desktop_theming.paths import Paths
from desktop_theming.server import Server


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="desktop-theming-http-")
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.paths = Paths(root, root / "config", root / "state")
        self.server = Server(self.paths)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close)

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def request(self, path="/", method="GET", value=None, *, token=True, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        request_headers = {"Content-Type": "application/json"}
        if token:
            request_headers["X-Desktop-Theming-Token"] = self.server.token
        request_headers.update(headers or {})
        connection.request(method, path, body=json.dumps(value) if value is not None else None,
                           headers=request_headers)
        response = connection.getresponse()
        result = response.status, response.read(), dict(response.getheaders())
        connection.close()
        return result

    def test_opening_dashboard_does_not_write_and_has_local_token(self):
        status, body, headers = self.request()
        self.assertEqual(status, 200)
        self.assertIn(self.server.token.encode(), body)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertFalse(self.paths.config.exists())
        self.assertFalse(self.paths.state.exists())

    def test_api_requires_token_even_for_inventory(self):
        self.assertEqual(self.request("/api/overview", token=False)[0], 403)
        self.assertEqual(self.request("/api/overview")[0], 200)

    def test_cross_origin_mutations_are_rejected(self):
        status, _, _ = self.request("/api/plan", "POST", {},
                                    headers={"Origin": "https://unrelated.example"})
        self.assertEqual(status, 403)
        self.assertFalse(self.paths.config.exists())

    def test_dns_rebinding_host_and_traversal_are_rejected(self):
        self.assertEqual(self.request(headers={"Host": "unrelated.example"})[0], 403)
        self.assertEqual(self.request("/../bin/walltheme")[0], 404)

    def test_unknown_plan_or_missing_approval_cannot_apply(self):
        self.assertEqual(self.request("/api/apply", "POST", {"id": "fake", "approved": True})[0], 400)
        self.assertEqual(self.request("/api/apply", "POST", {"id": "fake"})[0], 400)
        self.assertFalse(self.paths.state.exists())

    def test_full_review_apply_and_undo_workflow(self):
        status, body, _ = self.request("/api/plan", "POST", {"mode": "safe"})
        self.assertEqual(status, 200, body)
        plan = json.loads(body)
        self.assertFalse(self.paths.config.exists())
        self.assertEqual(self.request("/api/apply", "POST", {"id": plan["id"]})[0], 400)
        status, body, _ = self.request("/api/apply", "POST", {"id": plan["id"], "approved": True})
        self.assertEqual(status, 200, body)
        ident = json.loads(body)["id"]
        self.assertTrue(self.paths.profile.exists())
        self.assertEqual(self.request("/api/apply", "POST", {"id": plan["id"], "approved": True})[0], 400)
        status, body, _ = self.request("/api/undo", "POST", {"id": ident, "approved": True})
        self.assertEqual(status, 200, body)
        self.assertFalse(self.paths.profile.exists())

    def test_invalid_json_shapes_are_handled_without_crashing(self):
        for value in ([1], {"components": 1}, {"wallpaper": {}}, {"id": []}):
            with self.subTest(value=value):
                endpoint = "/api/apply" if "id" in value else "/api/plan"
                self.assertEqual(self.request(endpoint, "POST", value)[0], 400)
        self.assertEqual(self.request("/api/overview")[0], 200)


if __name__ == "__main__":
    unittest.main()

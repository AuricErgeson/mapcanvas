"""Offline smoke tests for the Flask UI and render API."""

import io
import unittest
from unittest.mock import patch

import app as webapp
import mapart


class WebAppTests(unittest.TestCase):
    def setUp(self):
        self.client = webapp.app.test_client()

    def test_index_and_frontend_assets(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Create a map poster", response.data)

        for path in ("/static/app.css", "/static/app.js"):
            with self.subTest(path=path):
                with self.client.get(path) as asset:
                    self.assertEqual(asset.status_code, 200)
                    self.assertGreater(len(asset.data), 1000)

    def test_presets(self):
        response = self.client.get("/api/presets")
        self.assertEqual(response.status_code, 200)
        self.assertIn("gallery", response.get_json())

    @patch("app.mapart.render")
    def test_render_success(self, render_mock):
        render_mock.return_value = io.BytesIO(b"\x89PNG\r\n\x1a\nmock")
        response = self.client.post(
            "/api/render",
            json={
                "place": "Berlin, Germany",
                "dist": 2000,
                "preset": "gallery",
                "style": {},
                "size": 1200,
                "circle": True,
                "width_scale": 1.0,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "image/png")
        self.assertTrue(response.data.startswith(b"\x89PNG"))

    @patch("app.mapart.render", side_effect=mapart.RenderError("place not found"))
    def test_render_error(self, _render_mock):
        response = self.client.post(
            "/api/render", json={"place": "missing", "preset": "gallery"}
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {"error": "place not found"})


if __name__ == "__main__":
    unittest.main()

"""End-to-end tests for scripts/ig_publish.py against a local fake Graph API.

Run: python3 -m unittest discover -s tests -v
"""
import io
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ig_publish.py"
TOKEN = "SECRET-TOKEN-123"


def make_jpeg(path, w, h):
    # Minimal JPEG: SOI, APP0, SOF0 (with real size), EOI. Enough for the size parser.
    app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    sof = b"\xff\xc0" + struct.pack(">HBHHB", 11, 8, h, w, 1) + b"\x01\x11\x00"
    path.write_bytes(b"\xff\xd8" + app0 + sof + b"\xff\xd9")


class Fake(BaseHTTPRequestHandler):
    calls = []
    counter = [0]
    status_polls = {}

    def log_message(self, *a):
        pass

    def _send(self, code, obj, ctype="application/json"):
        body = json.dumps(obj).encode() if ctype == "application/json" else b""
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_HEAD(self):
        p = urllib.parse.urlparse(self.path).path
        if p.startswith("/pages/") and p.endswith(".jpg"):
            return self._send(200, None, "image/jpeg")
        if p.startswith("/pages/") and p.endswith(".mp4"):
            return self._send(200, None, "video/mp4")
        return self._send(404, None, "text/html")

    def _params(self):
        u = urllib.parse.urlparse(self.path)
        q = dict(urllib.parse.parse_qsl(u.query))
        if self.command == "POST":
            n = int(self.headers.get("Content-Length", 0))
            q.update(urllib.parse.parse_qsl(self.rfile.read(n).decode()))
        return u.path, q

    def _handle(self):
        path, q = self._params()
        Fake.calls.append((self.command, path, {k: v for k, v in q.items() if k != "access_token"}))
        if q.get("access_token") != TOKEN:
            return self._send(400, {"error": {"type": "OAuthException", "code": 190, "message": "Invalid token"}})
        if path == "/refresh_access_token":
            return self._send(200, {"access_token": "NEW-TOKEN-456", "token_type": "bearer", "expires_in": 5183944})
        parts = path.strip("/").split("/")[1:]  # drop version
        if parts == ["1789"] and q.get("fields") == "username":
            return self._send(200, {"id": "1789", "username": "podredeno.bg"})
        if parts == ["me"]:
            return self._send(200, {"user_id": "1789", "username": "podredeno.bg"})
        if parts == ["1789", "media"] and self.command == "POST":
            Fake.counter[0] += 1
            return self._send(200, {"id": f"c{Fake.counter[0]}"})
        if parts == ["1789", "media_publish"]:
            return self._send(200, {"id": "M999"})
        if len(parts) == 1 and q.get("fields") == "status_code,status":
            n = Fake.status_polls.get(parts[0], 0)
            Fake.status_polls[parts[0]] = n + 1
            return self._send(200, {"status_code": "IN_PROGRESS" if n == 0 else "FINISHED"})
        if parts == ["M999"]:
            return self._send(200, {"permalink": "https://www.instagram.com/p/XYZ/"})
        return self._send(404, {"error": {"message": f"unknown {path}"}})

    do_GET = _handle
    do_POST = _handle


class PublishTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        Fake.calls.clear()
        self.root = Path(tempfile.mkdtemp())
        (self.root / "queue").mkdir()
        (self.root / "published").mkdir()
        d = self.root / "media" / "2026-11-17"
        d.mkdir(parents=True)
        self.files = []
        for i in range(1, 7):
            make_jpeg(d / f"{i:02}.jpg", 1080, 1350)
            self.files.append(f"media/2026-11-17/{i:02}.jpg")

    def tearDown(self):
        shutil.rmtree(self.root)

    def queue(self, entry, date="2026-11-17"):
        (self.root / "queue" / f"{date}.json").write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8")

    def run_script(self, *args, token=TOKEN, ig_user_id=None):
        env = dict(os.environ, GRAPH_BASE=self.base, GRAPH_VERSION="v24.0",
                   PAGES_BASE=self.base + "/pages", IG_ACCESS_TOKEN=token, POLL_INTERVAL="0.01")
        env.pop("GITHUB_ACTIONS", None)
        env.pop("IG_USER_ID", None)
        if ig_user_id:
            env["IG_USER_ID"] = ig_user_id
        return subprocess.run([sys.executable, str(SCRIPT), *args], env=env,
                              capture_output=True, text=True, timeout=60)

    def carousel(self):
        return {"type": "carousel", "files": self.files, "caption": "Подредено ✨ #дом"}

    def test_dry_run_creates_containers_but_does_not_publish(self):
        self.queue(self.carousel())
        r = self.run_script("publish", "--date", "2026-11-17", "--dry-run", "--root", str(self.root))
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertIn("DRY RUN OK", r.stdout)
        posts = [c for c in Fake.calls if c[0] == "POST"]
        self.assertEqual(len(posts), 7)  # 6 items + 1 carousel
        self.assertFalse(any(c[1].endswith("media_publish") for c in Fake.calls))
        self.assertTrue((self.root / "queue" / "2026-11-17.json").exists())
        parent = posts[-1][2]
        self.assertEqual(parent["media_type"], "CAROUSEL")
        self.assertEqual(parent["children"], "c1,c2,c3,c4,c5,c6")
        self.assertEqual(parent["caption"], "Подредено ✨ #дом")
        self.assertTrue(all(p[2].get("is_carousel_item") == "true" for p in posts[:6]))
        self.assertNotIn(TOKEN, r.stdout + r.stderr)

    def test_unified_login_uses_ig_user_id_not_me(self):
        self.queue(self.carousel())
        r = self.run_script("publish", "--date", "2026-11-17", "--dry-run", "--root", str(self.root),
                            ig_user_id="1789")
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertIn("Token OK for @podredeno.bg (id 1789)", r.stdout)
        self.assertFalse(any(c[1].endswith("/me") for c in Fake.calls))
        self.assertIn("DRY RUN OK", r.stdout)

    def test_publish_moves_record_and_is_idempotent(self):
        self.queue(self.carousel())
        r = self.run_script("publish", "--date", "2026-11-17", "--root", str(self.root))
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertFalse((self.root / "queue" / "2026-11-17.json").exists())
        rec = json.loads((self.root / "published" / "2026-11-17.json").read_text(encoding="utf-8"))
        self.assertEqual(rec["media_id"], "M999")
        self.assertEqual(rec["permalink"], "https://www.instagram.com/p/XYZ/")
        self.assertEqual(rec["caption"], "Подредено ✨ #дом")
        self.assertEqual(sum(1 for c in Fake.calls if c[1].endswith("media_publish")), 1)
        # Second run (e.g. the 16:00 UTC schedule) must not post again.
        self.queue(self.carousel())
        Fake.calls.clear()
        r = self.run_script("publish", "--date", "2026-11-17", "--root", str(self.root))
        self.assertEqual(r.returncode, 0)
        self.assertIn("Already published", r.stdout)
        self.assertEqual(Fake.calls, [])

    def test_reel_uses_reels_media_type(self):
        (self.root / "media" / "v.mp4").write_bytes(b"\x00" * 100)
        self.queue({"type": "reel", "files": ["media/v.mp4"], "caption": "r", "thumb_offset": 1500})
        r = self.run_script("publish", "--date", "2026-11-17", "--root", str(self.root))
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        create = [c for c in Fake.calls if c[0] == "POST" and c[1].endswith("/media")]
        self.assertEqual(len(create), 1)
        self.assertEqual(create[0][2]["media_type"], "REELS")
        self.assertTrue(create[0][2]["video_url"].endswith("/pages/media/v.mp4"))
        self.assertEqual(create[0][2]["share_to_feed"], "true")
        self.assertEqual(create[0][2]["thumb_offset"], "1500")
        self.assertEqual(sum(1 for c in Fake.calls if c[1].endswith("media_publish")), 1)

    def test_missing_pages_file_fails_before_api(self):
        make_jpeg(self.root / "media" / "x.jpeg", 1080, 1080)
        self.queue({"type": "image", "files": ["media/x.jpeg"]})  # fake Pages serves only .jpg
        r = self.run_script("publish", "--date", "2026-11-17", "--dry-run", "--root", str(self.root))
        self.assertEqual(r.returncode, 1)
        self.assertIn("HTTP 404", r.stderr)
        self.assertEqual(Fake.calls, [])

    def test_validation_errors(self):
        cases = [
            ({"type": "carousel", "files": self.files[:1], "caption": ""}, "2-10 files"),
            ({"type": "story", "files": self.files[:1]}, "type must be"),
            ({"type": "image", "files": ["media/nope.jpg"]}, "file not found"),
            ({"type": "image", "files": self.files[:1], "caption": "x" * 2201}, "max 2200"),
            ({"type": "image", "files": self.files[:1], "caption": " ".join(f"#t{i}" for i in range(31))}, "hashtags"),
        ]
        for entry, msg in cases:
            with self.subTest(msg=msg):
                self.queue(entry)
                r = self.run_script("publish", "--date", "2026-11-17", "--dry-run", "--root", str(self.root))
                self.assertEqual(r.returncode, 1)
                self.assertIn(msg, r.stderr)

    def test_bad_aspect_ratio(self):
        make_jpeg(self.root / "media" / "wide.jpg", 2000, 1000)  # 2.0 > 1.91
        self.queue({"type": "image", "files": ["media/wide.jpg"]})
        r = self.run_script("publish", "--date", "2026-11-17", "--dry-run", "--root", str(self.root))
        self.assertEqual(r.returncode, 1)
        self.assertIn("aspect", r.stderr)

    def test_bad_token_reported_without_leaking(self):
        self.queue(self.carousel())
        r = self.run_script("publish", "--date", "2026-11-17", "--dry-run", "--root", str(self.root), token="WRONG")
        self.assertEqual(r.returncode, 1)
        self.assertIn("code=190", r.stderr)
        self.assertNotIn("WRONG", r.stdout + r.stderr)

    def test_no_queue_entry_is_noop(self):
        r = self.run_script("publish", "--date", "2026-11-18", "--root", str(self.root))
        self.assertEqual(r.returncode, 0)
        self.assertIn("No queue entry", r.stdout)

    def test_refresh_writes_token_file(self):
        out = self.root / "tok"
        r = self.run_script("refresh", "--out", str(out))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(out.read_text(), "NEW-TOKEN-456")
        self.assertNotIn("NEW-TOKEN-456", r.stdout + r.stderr)
        self.assertEqual(oct(out.stat().st_mode & 0o777), "0o600")
        self.assertEqual(Fake.calls[-1][1], "/refresh_access_token")


if __name__ == "__main__":
    unittest.main()

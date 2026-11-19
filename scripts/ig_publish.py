#!/usr/bin/env python3
"""Publish a queued post to Instagram (Instagram API with Instagram Login).

Subcommands:
  publish  - publish queue/<date>.json (or validate it with --dry-run)
  refresh  - refresh the long-lived access token and write it to a file

Only the Python standard library is used. The access token is read from the
IG_ACCESS_TOKEN environment variable and is never printed.
"""
import argparse
import datetime as dt
import json
import os
import re
import struct
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Sofia")
PUBLISH_HOUR = 18
CATCHUP_DAYS = 2  # a late scheduled run also publishes overdue entries this many days back
# Unified login (system-user token) publishes through graph.facebook.com.
GRAPH_BASE = (os.environ.get("GRAPH_BASE") or "https://graph.facebook.com").rstrip("/")
GRAPH_VERSION = os.environ.get("GRAPH_VERSION") or "v24.0"
PAGES_BASE = os.environ.get("PAGES_BASE", "https://ivoexp1969.github.io/podredeno-media").rstrip("/")
POLL_INTERVAL = float(os.environ.get("POLL_INTERVAL", "5"))
POLL_TIMEOUT = float(os.environ.get("POLL_TIMEOUT", "900"))

IMAGE_EXT = {".jpg", ".jpeg"}
VIDEO_EXT = {".mp4": "video/mp4", ".mov": "video/quicktime"}
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_CAPTION = 2200
MAX_HASHTAGS = 30
MAX_MENTIONS = 20


class PublishError(Exception):
    pass


def log(msg):
    print(msg, flush=True)


# ---------------------------------------------------------------- Graph API

def _token():
    tok = os.environ.get("IG_ACCESS_TOKEN", "").strip()
    if not tok:
        raise PublishError("IG_ACCESS_TOKEN is not set (add it in GitHub Secrets).")
    return tok


def api(method, path, params=None, versioned=True):
    params = dict(params or {})
    params["access_token"] = _token()
    base = f"{GRAPH_BASE}/{GRAPH_VERSION}" if versioned else GRAPH_BASE
    url = f"{base}/{path.lstrip('/')}"
    data = None
    if method == "GET":
        url += "?" + urllib.parse.urlencode(params)
    else:
        data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(url, data=data, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        try:
            err = json.loads(body).get("error", {})
            detail = f"{err.get('type', '')} code={err.get('code')} sub={err.get('error_subcode')}: {err.get('message', '')}"
            if err.get("error_user_msg"):
                detail += f" | {err['error_user_msg']}"
        except ValueError:
            detail = body[:300]
        raise PublishError(f"Graph API {method} {path} -> HTTP {e.code}: {detail}") from None
    except urllib.error.URLError as e:
        raise PublishError(f"Graph API {method} {path} -> network error: {e.reason}") from None


def get_ig_user():
    """Return (instagram user id, username).

    With a Unified login system-user token the Instagram account id is given in
    IG_USER_ID (GitHub Variable or workflow env). Without it, fall back to /me
    (Instagram Login tokens).
    """
    ig_id = os.environ.get("IG_USER_ID", "").strip()
    if ig_id:
        info = api("GET", ig_id, {"fields": "username"})
        return ig_id, info.get("username", "?")
    me = api("GET", "me", {"fields": "user_id,username"})
    uid = me.get("user_id") or me.get("id")
    if not uid:
        raise PublishError(f"Could not read Instagram user id from /me: {me}")
    return str(uid), me.get("username", "?")


def wait_finished(container_id, label):
    deadline = time.monotonic() + POLL_TIMEOUT
    while True:
        st = api("GET", container_id, {"fields": "status_code,status"})
        code = st.get("status_code")
        if code in ("FINISHED", "PUBLISHED"):
            log(f"  {label} {container_id}: {code}")
            return
        if code in ("ERROR", "EXPIRED"):
            raise PublishError(f"{label} {container_id}: {code} ({st.get('status', '')})")
        if time.monotonic() > deadline:
            raise PublishError(f"{label} {container_id}: still {code} after {POLL_TIMEOUT:.0f}s")
        time.sleep(POLL_INTERVAL)


def create_containers(ig_id, entry):
    """Create media container(s); return the id to pass to media_publish."""
    kind = entry["type"]
    caption = entry.get("caption", "")
    urls = [public_url(f) for f in entry["files"]]
    if kind == "image":
        cid = api("POST", f"{ig_id}/media", {"image_url": urls[0], "caption": caption})["id"]
        wait_finished(cid, "image")
        return cid
    if kind == "story":
        key = "video_url" if Path(entry["files"][0]).suffix.lower() in VIDEO_EXT else "image_url"
        cid = api("POST", f"{ig_id}/media", {"media_type": "STORIES", key: urls[0]})["id"]
        wait_finished(cid, "story")
        return cid
    if kind == "reel":
        params = {"media_type": "REELS", "video_url": urls[0], "caption": caption,
                  "share_to_feed": "true" if entry.get("share_to_feed", True) else "false"}
        if "thumb_offset" in entry:
            params["thumb_offset"] = str(int(entry["thumb_offset"]))
        cid = api("POST", f"{ig_id}/media", params)["id"]
        wait_finished(cid, "reel")
        return cid
    # carousel
    children = []
    for i, u in enumerate(urls, 1):
        cid = api("POST", f"{ig_id}/media", {"image_url": u, "is_carousel_item": "true"})["id"]
        wait_finished(cid, f"item {i}/{len(urls)}")
        children.append(cid)
    parent = api("POST", f"{ig_id}/media", {"media_type": "CAROUSEL",
                                            "children": ",".join(children),
                                            "caption": caption})["id"]
    wait_finished(parent, "carousel")
    return parent


# ---------------------------------------------------------------- validation

def public_url(repo_path):
    return f"{PAGES_BASE}/{urllib.parse.quote(repo_path.lstrip('/'))}"


def jpeg_size(path):
    """Return (width, height) of a JPEG file by reading its SOF marker."""
    sof = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
    with open(path, "rb") as f:
        if f.read(2) != b"\xff\xd8":
            raise PublishError(f"{path}: not a JPEG file")
        while True:
            b = f.read(1)
            while b and b != b"\xff":
                b = f.read(1)
            while b == b"\xff":
                b = f.read(1)
            if not b:
                raise PublishError(f"{path}: JPEG size marker not found")
            m = b[0]
            if m == 0x01 or 0xD0 <= m <= 0xD8:
                continue
            seg_len = struct.unpack(">H", f.read(2))[0]
            if m in sof:
                f.read(1)
                h, w = struct.unpack(">HH", f.read(4))
                return w, h
            f.seek(seg_len - 2, 1)


def validate(entry, root):
    """Check a queue entry against Instagram limits. Returns list of warnings."""
    warnings = []
    kind = entry.get("type")
    files = entry.get("files")
    caption = entry.get("caption", "")
    if kind not in ("image", "carousel", "reel", "story"):
        raise PublishError(f"type must be image, carousel, reel or story (got {kind!r})")
    if not isinstance(files, list) or not files or not all(isinstance(f, str) for f in files):
        raise PublishError("files must be a non-empty list of repository paths")
    if not isinstance(caption, str):
        raise PublishError("caption must be a string")
    n = len(files)
    if kind in ("image", "reel", "story") and n != 1:
        raise PublishError(f"{kind} needs exactly 1 file (got {n})")
    if kind == "carousel" and not 2 <= n <= 10:
        raise PublishError(f"carousel needs 2-10 files (got {n})")
    if len(caption) > MAX_CAPTION:
        raise PublishError(f"caption is {len(caption)} chars (max {MAX_CAPTION})")
    if len(re.findall(r"#\w", caption)) > MAX_HASHTAGS:
        raise PublishError(f"caption has more than {MAX_HASHTAGS} hashtags")
    if len(re.findall(r"@\w", caption)) > MAX_MENTIONS:
        raise PublishError(f"caption has more than {MAX_MENTIONS} @mentions")

    ratios = []
    for rel in files:
        p = root / rel
        if not p.is_file():
            raise PublishError(f"file not found in repository: {rel}")
        ext = p.suffix.lower()
        size = p.stat().st_size
        if kind == "reel" or (kind == "story" and ext in VIDEO_EXT):
            if ext not in VIDEO_EXT:
                raise PublishError(f"{rel}: reel must be .mp4 or .mov")
            continue
        if kind == "story":
            if ext not in IMAGE_EXT:
                raise PublishError(f"{rel}: story must be JPEG or .mp4/.mov")
            if size > MAX_IMAGE_BYTES:
                raise PublishError(f"{rel}: {size / 1048576:.1f} MB (max 8 MB)")
            w, h = jpeg_size(p)
            if abs(w / h - 9 / 16) > 0.02:
                warnings.append(f"{rel}: {w}x{h}; stories look best at 1080x1920 (9:16)")
            continue
        if ext not in IMAGE_EXT:
            raise PublishError(f"{rel}: images must be JPEG (.jpg/.jpeg)")
        if size > MAX_IMAGE_BYTES:
            raise PublishError(f"{rel}: {size / 1048576:.1f} MB (max 8 MB)")
        w, h = jpeg_size(p)
        r = w / h
        if not 0.8 - 1e-3 <= r <= 1.91 + 1e-3:
            raise PublishError(f"{rel}: {w}x{h}, aspect {r:.3f} outside 4:5..1.91:1")
        if w > 1440 or w < 320:
            warnings.append(f"{rel}: width {w}px; Instagram rescales to 320-1440px")
        ratios.append(round(r, 3))
    if kind == "carousel" and len(set(ratios)) > 1:
        warnings.append(f"carousel images have different aspect ratios {ratios}; "
                        "Instagram crops them to the first image's ratio")
    return warnings


def check_urls(entry):
    for rel in entry["files"]:
        url = public_url(rel)
        req = urllib.request.Request(url, method="HEAD")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                ctype = resp.headers.get("Content-Type", "")
        except urllib.error.HTTPError as e:
            raise PublishError(f"{url} -> HTTP {e.code} (is GitHub Pages deployed?)") from None
        except urllib.error.URLError as e:
            raise PublishError(f"{url} -> {e.reason}") from None
        ext = Path(rel).suffix.lower()
        expected = "image/jpeg" if ext in IMAGE_EXT else VIDEO_EXT.get(ext, "")
        if not ctype.startswith(expected):
            raise PublishError(f"{url} -> Content-Type {ctype!r}, expected {expected}")
        log(f"  OK {url} ({ctype})")


# ---------------------------------------------------------------- commands

def cmd_publish(args):
    root = Path(args.root).resolve()
    fake_now = os.environ.get("IG_NOW", "")  # tests only: ISO time in Sofia
    now = dt.datetime.fromisoformat(fake_now).replace(tzinfo=TZ) if fake_now else dt.datetime.now(TZ)
    date = args.date or now.date().isoformat()
    try:
        dt.date.fromisoformat(date)
    except ValueError:
        raise PublishError(f"bad date {date!r}, expected YYYY-MM-DD") from None

    dates = [date]
    if args.respect_time and not args.date:
        # GitHub can start scheduled runs hours late, even after midnight.
        # Catch up on recent days whose entries are still in the queue.
        today = now.date()
        dates = [(today - dt.timedelta(days=d)).isoformat() for d in range(CATCHUP_DAYS, 0, -1)]
        if now.hour >= PUBLISH_HOUR:
            dates.append(today.isoformat())
        else:
            log(f"Sofia time is {now:%H:%M}; today's entry waits until {PUBLISH_HOUR}:00.")
    elif args.respect_time and date == now.date().isoformat() and now.hour < PUBLISH_HOUR:
        log(f"Sofia time is {now:%H:%M}; publishing starts at {PUBLISH_HOUR}:00. Nothing to do.")
        return 0

    rc = 0
    if args.respect_time:
        # Automatic runs post only the feed entry. Stories are posted by hand in the
        # Instagram app, because the API cannot add the "Link" sticker.
        names = list(dates)
        for d in dates:
            if (root / "queue" / f"{d}-story.json").exists():
                log(f"queue/{d}-story.json is left for manual posting (auto-publish of stories is off).")
    else:
        names = [n for d in dates for n in (d, f"{d}-story")]
    for name in names:
        try:
            publish_one(args, root, name)
        except PublishError as e:
            print(f"ERROR [{name}]: {e}", file=sys.stderr, flush=True)
            rc = 1
    return rc


def publish_one(args, root, date):
    """Publish queue/<date>.json, where <date> may carry a suffix like -story."""
    qfile = root / "queue" / f"{date}.json"
    pfile = root / "published" / f"{date}.json"
    if pfile.exists():
        log(f"Already published: {pfile.relative_to(root)}. Nothing to do.")
        return 0
    if not qfile.exists():
        log(f"No queue entry {qfile.relative_to(root)}. Nothing to do.")
        return 0

    try:
        entry = json.loads(qfile.read_text(encoding="utf-8"))
    except ValueError as e:
        raise PublishError(f"{qfile.relative_to(root)}: invalid JSON: {e}") from None
    if not isinstance(entry, dict):
        raise PublishError(f"{qfile.relative_to(root)}: must be a JSON object")

    mode = "DRY RUN" if args.dry_run else "PUBLISH"
    log(f"[{mode}] {date}: {entry.get('type')} with {len(entry.get('files') or [])} file(s)")
    for w in validate(entry, root):
        log(f"  WARNING: {w}")
    log("Checking public URLs:")
    check_urls(entry)

    ig_id, username = get_ig_user()
    log(f"Token OK for @{username} (id {ig_id})")
    log("Creating media containers:")
    creation_id = create_containers(ig_id, entry)

    if args.dry_run:
        log(f"DRY RUN OK: container {creation_id} is ready. Not published "
            "(unused containers expire on their own).")
        return 0

    res = api("POST", f"{ig_id}/media_publish", {"creation_id": creation_id})
    media_id = res.get("id")
    if not media_id:
        raise PublishError(f"media_publish returned no id: {res}")
    record = dict(entry)
    record.update({"media_id": media_id,
                   "published_at": dt.datetime.now(TZ).isoformat(timespec="seconds")})
    # Write the record right away so a later failure cannot cause a double post.
    pfile.parent.mkdir(parents=True, exist_ok=True)
    pfile.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    qfile.unlink()
    log(f"PUBLISHED media_id={media_id}")
    try:
        permalink = api("GET", media_id, {"fields": "permalink"}).get("permalink")
        if permalink:
            record["permalink"] = permalink
            pfile.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            log(f"Permalink: {permalink}")
    except PublishError as e:
        log(f"  WARNING: could not read permalink: {e}")
    return 0


def cmd_refresh(args):
    res = api("GET", "refresh_access_token", {"grant_type": "ig_refresh_token"}, versioned=False)
    new = res.get("access_token")
    if not new:
        raise PublishError("refresh_access_token returned no token")
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print(f"::add-mask::{new}", flush=True)
    out = Path(args.out)
    out.write_text(new, encoding="utf-8")
    os.chmod(out, 0o600)
    days = int(res.get("expires_in", 0)) // 86400
    log(f"Token refreshed; valid for about {days} days.")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("publish")
    p.add_argument("--date", default="", help="YYYY-MM-DD (default: today in Sofia)")
    p.add_argument("--dry-run", action="store_true", help="validate and create containers, do not publish")
    p.add_argument("--respect-time", action="store_true", help=f"skip before {PUBLISH_HOUR}:00 Sofia time")
    p.add_argument("--root", default=".", help="repository root")
    r = sub.add_parser("refresh")
    r.add_argument("--out", required=True, help="file to write the new token to")
    args = ap.parse_args(argv)
    try:
        return cmd_publish(args) if args.cmd == "publish" else cmd_refresh(args)
    except PublishError as e:
        print(f"ERROR: {e}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())

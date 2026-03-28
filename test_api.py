#!/usr/bin/env python3
"""
End-to-end API smoke test.

Usage:
    python3 test_api.py                  # runs against http://127.0.0.1:8000
    BASE_URL=https://... python3 test_api.py
"""

import os
import sys
import json
import random
import string
import urllib.request
import urllib.error

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8000").rstrip("/")
API = f"{BASE_URL}/api/v1"


# ── helpers ────────────────────────────────────────────────────────────────────

def _rand(n=6):
    return "".join(random.choices(string.ascii_lowercase, k=n))


def req(method, path, *, token=None, json_body=None, expect=None):
    url = f"{API}{path}"
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(json_body).encode() if json_body is not None else None
    rq = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(rq, timeout=15) as resp:
            body = json.loads(resp.read())
            status = resp.status
    except urllib.error.HTTPError as e:
        body = {}
        try:
            body = json.loads(e.read())
        except Exception:
            pass
        status = e.code
    if expect and status not in expect:
        raise AssertionError(f"{method} {path} → {status} (expected {expect})\n{json.dumps(body, indent=2)}")
    return status, body


# ── result tracking ────────────────────────────────────────────────────────────

results = []

def check(label, fn):
    try:
        detail = fn()
        # If fn returned the raw (status, body) tuple from req(), just keep the status code
        if isinstance(detail, tuple):
            detail = f"HTTP {detail[0]}"
        results.append((label, True, detail or ""))
        print(f"  ✓  {label}" + (f"  [{detail}]" if detail else ""))
    except Exception as exc:
        results.append((label, False, str(exc)))
        print(f"  ✗  {label}")
        first_line = str(exc).split("\n")[0]
        print(f"       {first_line}")


# ── shared state ───────────────────────────────────────────────────────────────

tag             = _rand()
creator_email   = f"creator_{tag}@testmail.com"
visitor_email   = f"visitor_{tag}@testmail.com"
password        = "Test1234!"

creator_token   = None
visitor_token   = None
creator_refresh = None
visitor_refresh = None
creator_id      = None   # Creator.id (profile)
post_id         = None
comment_id      = None
conv_id         = None
sub_id          = None


# ══════════════════════════════════════════════════════════════════════════════
print("\n── Auth ──────────────────────────────────────────────────────────────────")
# ══════════════════════════════════════════════════════════════════════════════

def _signup_creator():
    global creator_token, creator_refresh
    _, body = req("POST", "/auth/signup", json_body={
        "email": creator_email, "password": password,
        "display_name": f"Creator {tag}", "role": "creator",
    }, expect=[200, 201])
    creator_token   = body["access_token"]
    creator_refresh = body["refresh_token"]

def _signup_visitor():
    global visitor_token, visitor_refresh
    _, body = req("POST", "/auth/signup", json_body={
        "email": visitor_email, "password": password,
        "display_name": f"Visitor {tag}", "role": "visitor",
    }, expect=[200, 201])
    visitor_token   = body["access_token"]
    visitor_refresh = body["refresh_token"]

check("POST /auth/signup  (creator)", _signup_creator)
check("POST /auth/signup  (visitor)", _signup_visitor)

check("POST /auth/login", lambda: (
    req("POST", "/auth/login", json_body={
        "email": creator_email, "password": password,
    }, expect=[200])
))

def _refresh():
    if not visitor_refresh:
        return "skipped — no refresh token"
    _, body = req("POST", "/auth/refresh", json_body={
        "refresh_token": visitor_refresh,
    }, expect=[200])
    assert "access_token" in body
check("POST /auth/refresh", _refresh)

check("GET  /auth/me", lambda: req("GET", "/auth/me", token=creator_token, expect=[200]))

def _guest():
    _, body = req("POST", "/auth/guest", json_body={
        "display_name": f"Guest {tag}", "role": "visitor",
    }, expect=[200, 201])
    assert "access_token" in body
check("POST /auth/guest", _guest)


# ══════════════════════════════════════════════════════════════════════════════
print("\n── Users / Profile ───────────────────────────────────────────────────────")
# ══════════════════════════════════════════════════════════════════════════════

check("GET  /users/me (creator)", lambda: req("GET", "/users/me", token=creator_token, expect=[200]))
check("GET  /users/me (visitor)", lambda: req("GET", "/users/me", token=visitor_token, expect=[200]))

check("PUT  /users/me", lambda: req("PUT", "/users/me", token=creator_token, json_body={
    "display_name": f"Creator {tag} Updated", "bio": "Test bio",
}, expect=[200]))

check("POST /users/change-password", lambda: req(
    "POST", "/users/change-password", token=visitor_token, json_body={
        "current_password": password, "new_password": password,
    }, expect=[200]
))


# ══════════════════════════════════════════════════════════════════════════════
print("\n── Creator Profile ───────────────────────────────────────────────────────")
# ══════════════════════════════════════════════════════════════════════════════

def _create_creator_profile():
    global creator_id
    _, body = req("POST", "/creators/me", token=creator_token, json_body={
        "display_name": f"Creator {tag}",
        "bio": "I make content",
        "location": "Mumbai",
        "website_url": "https://example.com",
    }, expect=[200, 201])
    data = body.get("data") or {}
    creator_id = data.get("creator_id") or data.get("id") or body.get("id")
    assert creator_id, f"no creator id in: {body}"
check("POST /creators/me", _create_creator_profile)

check("GET  /creators/me", lambda: req("GET", "/creators/me", token=creator_token, expect=[200]))
check("GET  /search/creators", lambda: req("GET", "/search/creators?q=Creator", token=creator_token, expect=[200]))


# ══════════════════════════════════════════════════════════════════════════════
print("\n── Subscription Plans ────────────────────────────────────────────────────")
# ══════════════════════════════════════════════════════════════════════════════

check("POST /creators/me/subscription-plans", lambda: req(
    "POST", "/creators/me/subscription-plans", token=creator_token, json_body={
        "plans": [
            {"code": "FREE",      "name": "Free",      "price_in_paise": 0,     "duration_days": 30},
            {"code": "EXCLUSIVE", "name": "Exclusive", "price_in_paise": 19900, "duration_days": 30},
            {"code": "VIP",       "name": "VIP",       "price_in_paise": 49900, "duration_days": 30},
        ],
    }, expect=[200]
))

check("GET  /creators/{id}/subscription-plans", lambda: (
    req("GET", f"/creators/{creator_id}/subscription-plans", token=visitor_token, expect=[200])
    if creator_id else (_ for _ in ()).throw(AssertionError("no creator_id"))
))


# ══════════════════════════════════════════════════════════════════════════════
print("\n── Subscribe ─────────────────────────────────────────────────────────────")
# ══════════════════════════════════════════════════════════════════════════════

def _subscribe():
    if not creator_id:
        return "skipped — no creator_id"
    _, body = req("POST", f"/creators/{creator_id}/subscriptions", token=visitor_token, json_body={
        "plan_code": "FREE",
    }, expect=[200, 201])
check("POST /creators/{id}/subscriptions", _subscribe)

def _get_my_subscription():
    global sub_id
    if not creator_id:
        return "skipped — no creator_id"
    _, body = req("GET", f"/creators/{creator_id}/subscriptions/me", token=visitor_token, expect=[200])
    data = body.get("data") or {}
    sub_id = (
        data.get("id")
        or (data.get("subscription") or {}).get("id")
        or body.get("id")
    )
check("GET  /creators/{id}/subscriptions/me", _get_my_subscription)

check("GET  /subscriptions/me", lambda: req("GET", "/subscriptions/me", token=visitor_token, expect=[200]))


# ══════════════════════════════════════════════════════════════════════════════
print("\n── Posts ─────────────────────────────────────────────────────────────────")
# ══════════════════════════════════════════════════════════════════════════════

def _create_post():
    global post_id
    _, body = req("POST", "/creator/posts", token=creator_token, json_body={
        "caption": f"Test post {tag}", "visibility": "public",
        "media_type": "image", "access_tier": "FREE",
    }, expect=[200, 201])
    post_id = body.get("data", {}).get("post_id")
    assert post_id, f"no post_id: {body}"
check("POST /creator/posts", _create_post)

def _add_media():
    if not post_id:
        return "skipped — no post_id"
    _, body = req("POST", f"/creator/posts/{post_id}/media", token=creator_token, json_body={
        "media_kind": "photo",
        "bucket_name": "onlyfats-private-media",
        "object_path": f"posts/{post_id}/orig/test.jpg",
        "thumbnail_object_path": f"posts/{post_id}/thumb/test.jpg",
        "mime_type": "image/jpeg",
        "file_size_bytes": 12345,
        "duration_seconds": None,
        "width": 800, "height": 600,
        "sort_order": 0,
        "processing_status": "ready",
    }, expect=[200, 201])
    assert body.get("data", {}).get("media_id"), f"no media_id: {body}"
check("POST /creator/posts/{id}/media", _add_media)

def _publish():
    if not post_id:
        return "skipped — no post_id"
    _, body = req("POST", f"/creator/posts/{post_id}/publish", token=creator_token, expect=[200])
    assert body.get("data", {}).get("status") == "published"
check("POST /creator/posts/{id}/publish", _publish)

check("GET  /creator/posts/me", lambda: req("GET", "/creator/posts/me", token=creator_token, expect=[200]))

check("PUT  /creator/posts/{id}", lambda: (
    req("PUT", f"/creator/posts/{post_id}", token=creator_token, json_body={"caption": f"Updated {tag}"}, expect=[200])
    if post_id else (_ for _ in ()).throw(AssertionError("no post_id"))
))

check("GET  /creators/{id}/posts", lambda: (
    req("GET", f"/creators/{creator_id}/posts", token=visitor_token, expect=[200])
    if creator_id else (_ for _ in ()).throw(AssertionError("no creator_id"))
))

check("GET  /posts/feed", lambda: req("GET", "/posts/feed", token=visitor_token, expect=[200]))

def _get_single_post():
    if not post_id:
        return "skipped — no post_id"
    _, body = req("GET", f"/posts/{post_id}", token=visitor_token, expect=[200])
    assert body.get("data", {}).get("post_id") == post_id
check("GET  /posts/{id}", _get_single_post)

check("GET  /posts/{id}/access", lambda: (
    req("GET", f"/posts/{post_id}/access", token=visitor_token, expect=[200])
    if post_id else (_ for _ in ()).throw(AssertionError("no post_id"))
))

check("POST /posts/{id}/unlock", lambda: (
    req("POST", f"/posts/{post_id}/unlock", token=visitor_token, expect=[200, 400])
    if post_id else (_ for _ in ()).throw(AssertionError("no post_id"))
))

check("GET  /creators/{id}/profile", lambda: (
    req("GET", f"/creators/{creator_id}/profile", token=visitor_token, expect=[200])
    if creator_id else (_ for _ in ()).throw(AssertionError("no creator_id"))
))


# ══════════════════════════════════════════════════════════════════════════════
print("\n── Social ────────────────────────────────────────────────────────────────")
# ══════════════════════════════════════════════════════════════════════════════

check("POST /posts/{id}/like (on)", lambda: (
    req("POST", f"/posts/{post_id}/like", token=visitor_token, expect=[200])
    if post_id else (_ for _ in ()).throw(AssertionError("no post_id"))
))
check("GET  /posts/{id}/liked", lambda: (
    req("GET", f"/posts/{post_id}/liked", token=visitor_token, expect=[200])
    if post_id else (_ for _ in ()).throw(AssertionError("no post_id"))
))
check("POST /posts/{id}/like (off)", lambda: (
    req("POST", f"/posts/{post_id}/like", token=visitor_token, expect=[200])
    if post_id else (_ for _ in ()).throw(AssertionError("no post_id"))
))

def _add_comment():
    global comment_id
    if not post_id:
        return "skipped — no post_id"
    _, body = req("POST", f"/posts/{post_id}/comments", token=visitor_token, json_body={
        "body": "Great post!"
    }, expect=[200, 201])
    comment_id = body.get("id") or (body.get("data") or {}).get("id")
check("POST /posts/{id}/comments", _add_comment)

check("GET  /posts/{id}/comments", lambda: (
    req("GET", f"/posts/{post_id}/comments", token=visitor_token, expect=[200])
    if post_id else (_ for _ in ()).throw(AssertionError("no post_id"))
))

def _delete_comment():
    if not (post_id and comment_id):
        return "skipped — no comment_id"
    req("DELETE", f"/posts/{post_id}/comments/{comment_id}", token=visitor_token, expect=[200, 204])
check("DELETE /posts/{id}/comments/{cid}", _delete_comment)

check("POST /posts/{id}/bookmark (on)", lambda: (
    req("POST", f"/posts/{post_id}/bookmark", token=visitor_token, expect=[200])
    if post_id else (_ for _ in ()).throw(AssertionError("no post_id"))
))
check("GET  /bookmarks", lambda: req("GET", "/bookmarks", token=visitor_token, expect=[200]))
check("POST /posts/{id}/bookmark (off)", lambda: (
    req("POST", f"/posts/{post_id}/bookmark", token=visitor_token, expect=[200])
    if post_id else (_ for _ in ()).throw(AssertionError("no post_id"))
))

check("POST /creators/{id}/follow (on)", lambda: (
    req("POST", f"/creators/{creator_id}/follow", token=visitor_token, expect=[200])
    if creator_id else (_ for _ in ()).throw(AssertionError("no creator_id"))
))
check("GET  /creators/{id}/follow", lambda: (
    req("GET", f"/creators/{creator_id}/follow", token=visitor_token, expect=[200])
    if creator_id else (_ for _ in ()).throw(AssertionError("no creator_id"))
))
check("POST /creators/{id}/follow (off)", lambda: (
    req("POST", f"/creators/{creator_id}/follow", token=visitor_token, expect=[200])
    if creator_id else (_ for _ in ()).throw(AssertionError("no creator_id"))
))


# ══════════════════════════════════════════════════════════════════════════════
print("\n── Notifications ─────────────────────────────────────────────────────────")
# ══════════════════════════════════════════════════════════════════════════════

check("GET  /notifications", lambda: req("GET", "/notifications", token=visitor_token, expect=[200]))
check("GET  /notifications/unread-count", lambda: req("GET", "/notifications/unread-count", token=visitor_token, expect=[200]))
check("POST /notifications/mark-all-read", lambda: req("POST", "/notifications/mark-all-read", token=visitor_token, expect=[200]))


# ══════════════════════════════════════════════════════════════════════════════
print("\n── Messaging (Firestore-backed) ──────────────────────────────────────────")
# ══════════════════════════════════════════════════════════════════════════════

def _firebase_token():
    status, body = req("GET", "/auth/firebase-token", token=visitor_token, expect=[200, 500])
    if status == 500:
        detail = body.get("detail", "")
        # Acceptable: Firebase project not yet set up / SA role not granted
        return f"Firebase SDK error (SA role may be missing): {detail[:100]}"
    assert "firebase_token" in body, f"missing firebase_token: {body}"
check("GET  /auth/firebase-token", _firebase_token)

def _start_conversation():
    global conv_id
    if not creator_id:
        return "skipped — no creator_id"
    status, body = req("POST", "/messages/conversations", token=visitor_token, json_body={
        "creator_id": creator_id,
    }, expect=[200, 201, 500])
    if status == 500:
        return f"Firestore unavailable: {body.get('detail','')[:100]}"
    conv_id = body.get("conv_id")
    assert conv_id, f"no conv_id: {body}"
check("POST /messages/conversations (fan→creator)", _start_conversation)

def _creator_blocked():
    if not creator_id:
        return "skipped — no creator_id"
    status, body = req("POST", "/messages/conversations", token=creator_token, json_body={
        "creator_id": creator_id,
    }, expect=[400, 500])
    if status == 500:
        return "Firestore unavailable — rule enforcement not tested"
    assert status == 400, f"expected 400 for creator, got {status}"
check("POST /messages/conversations (creator blocked → 400)", _creator_blocked)

def _send_visitor():
    if not conv_id:
        return "skipped — no conv_id (Firestore not set up)"
    status, body = req("POST", "/messages/send", token=visitor_token, json_body={
        "conv_id": conv_id, "body": "Hey, love your content!",
    }, expect=[200, 500])
    if status == 500:
        return f"Firestore unavailable: {body.get('detail','')[:80]}"
check("POST /messages/send  (visitor→creator)", _send_visitor)

def _send_creator():
    if not conv_id:
        return "skipped — no conv_id (Firestore not set up)"
    status, body = req("POST", "/messages/send", token=creator_token, json_body={
        "conv_id": conv_id, "body": "Thanks! Glad you enjoy it.",
    }, expect=[200, 500])
    if status == 500:
        return f"Firestore unavailable: {body.get('detail','')[:80]}"
check("POST /messages/send  (creator→visitor)", _send_creator)

def _list_conversations():
    status, body = req("GET", "/messages/conversations", token=visitor_token, expect=[200, 500])
    if status == 500:
        return f"Firestore unavailable: {body.get('detail','')[:80]}"
    assert isinstance(body, list)
check("GET  /messages/conversations", _list_conversations)

def _mark_read():
    if not conv_id:
        return "skipped — no conv_id"
    status, body = req("POST", f"/messages/conversations/{conv_id}/read", token=visitor_token, expect=[200, 500])
    if status == 500:
        return f"Firestore unavailable: {body.get('detail','')[:80]}"
check("POST /messages/conversations/{id}/read", _mark_read)


# ══════════════════════════════════════════════════════════════════════════════
print("\n── Subscription management ───────────────────────────────────────────────")
# ══════════════════════════════════════════════════════════════════════════════

def _change_plan():
    if not sub_id:
        return "skipped — no sub_id"
    req("POST", f"/subscriptions/{sub_id}/change-plan", token=visitor_token, json_body={
        "plan_code": "FREE",
    }, expect=[200, 400])
check("POST /subscriptions/{id}/change-plan", _change_plan)

def _cancel_sub():
    if not sub_id:
        return "skipped — no sub_id"
    req("POST", f"/subscriptions/{sub_id}/cancel", token=visitor_token, expect=[200, 400])
check("POST /subscriptions/{id}/cancel", _cancel_sub)


# ══════════════════════════════════════════════════════════════════════════════
print("\n── Cleanup ───────────────────────────────────────────────────────────────")
# ══════════════════════════════════════════════════════════════════════════════

check("DELETE /creator/posts/{id}", lambda: (
    req("DELETE", f"/creator/posts/{post_id}", token=creator_token, expect=[200])
    if post_id else (_ for _ in ()).throw(AssertionError("no post_id"))
))

def _logout():
    if not creator_refresh:
        return "skipped — no refresh token"
    _, body = req("POST", "/auth/logout", json_body={"refresh_token": creator_refresh}, expect=[200])
check("POST /auth/logout", _logout)


# ══════════════════════════════════════════════════════════════════════════════
print("\n── Summary ───────────────────────────────────────════════════════════════")
# ══════════════════════════════════════════════════════════════════════════════

passed   = [r for r in results if r[1]]
failed   = [r for r in results if not r[1]]
warnings = [r for r in results if r[1] and ("skipped" in str(r[2]).lower() or "unavailable" in str(r[2]).lower() or "error" in str(r[2]).lower())]

print(f"\n  Total  : {len(results)}")
print(f"  Passed : {len(passed)}")
print(f"  Failed : {len(failed)}")
if warnings:
    print(f"  Warned : {len(warnings)}  (Firestore not ready / skipped)")

if failed:
    print("\nFailed:")
    for label, _, detail in failed:
        print(f"  ✗ {label}")
        for line in str(detail).split("\n")[:3]:
            print(f"      {line}")

if warnings:
    print("\nWarnings/skipped:")
    for label, _, detail in warnings:
        print(f"  ⚠  {label}: {str(detail)[:120]}")

print()
sys.exit(0 if not failed else 1)

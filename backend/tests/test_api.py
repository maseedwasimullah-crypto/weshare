import pytest
from fastapi.testclient import TestClient

from app.main import app

from conftest import STRONG_PASSWORD, auth_headers, login, register


def test_public_and_private_routes_are_registered():
    paths = {route.path for route in app.routes}
    assert "/api/feed" in paths
    assert "/api/auth/register" in paths
    assert "/api/admin/users" in paths


def test_health_endpoint(client: TestClient):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_registration_and_login_flow(client: TestClient):
    data = register(client, "flow@example.com")
    assert data["username"]
    assert data["verification_email_sent"] is False

    token = login(client, "flow@example.com")
    assert token

    me = client.get("/api/auth/me", headers=auth_headers(token))
    assert me.status_code == 200
    assert me.json()["email"] == "flow@example.com"


def test_registration_rejects_weak_password(client: TestClient):
    response = client.post(
        "/api/auth/register",
        json={"email": "weak@example.com", "password": "password", "confirm_password": "password"},
    )
    assert response.status_code == 422


def test_registration_rejects_mismatched_confirmation(client: TestClient):
    response = client.post(
        "/api/auth/register",
        json={
            "email": "mismatch@example.com",
            "password": STRONG_PASSWORD,
            "confirm_password": STRONG_PASSWORD + "x",
        },
    )
    assert response.status_code == 422


def test_duplicate_email_is_rejected(client: TestClient):
    register(client, "duplicate@example.com")
    response = client.post(
        "/api/auth/register",
        json={
            "email": "duplicate@example.com",
            "password": STRONG_PASSWORD,
            "confirm_password": STRONG_PASSWORD,
        },
    )
    assert response.status_code == 409


def test_login_with_wrong_password_is_rejected(client: TestClient):
    register(client, "wrongpass@example.com")
    response = client.post(
        "/api/auth/login", json={"email": "wrongpass@example.com", "password": "not-the-password"}
    )
    assert response.status_code == 401


def test_login_of_unknown_user_is_rejected(client: TestClient):
    response = client.post(
        "/api/auth/login", json={"email": "nobody@example.com", "password": STRONG_PASSWORD}
    )
    assert response.status_code == 401


def test_unauthenticated_requests_are_rejected(client: TestClient):
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/posts", json={"content": "hello"}).status_code == 401
    assert client.post("/api/posts/1/comments", json={"content": "hello"}).status_code == 401
    assert client.get("/api/admin/stats").status_code == 401
    assert client.get("/api/admin/users").status_code == 401


def test_invalid_bearer_token_is_rejected(client: TestClient):
    response = client.get("/api/auth/me", headers=auth_headers("not-a-real-token"))
    assert response.status_code == 401


def test_non_admin_cannot_reach_admin_endpoints(client: TestClient):
    register(client, "plain@example.com")
    token = login(client, "plain@example.com")
    headers = auth_headers(token)
    assert client.get("/api/admin/stats", headers=headers).status_code == 403
    assert client.get("/api/admin/users", headers=headers).status_code == 403
    assert client.get("/api/admin/content", headers=headers).status_code == 403
    assert client.get("/api/admin/moderation", headers=headers).status_code == 403
    assert client.delete("/api/admin/posts/1", headers=headers).status_code == 403
    assert client.delete("/api/admin/comments/1", headers=headers).status_code == 403


def test_posting_requires_verified_email(client: TestClient):
    register(client, "unverified@example.com", verify=False)
    token = login(client, "unverified@example.com")
    response = client.post(
        "/api/posts", json={"content": "hello world"}, headers=auth_headers(token)
    )
    assert response.status_code == 403


def test_post_and_comment_round_trip(client: TestClient):
    register(client, "author@example.com")
    token = login(client, "author@example.com")
    headers = auth_headers(token)

    created = client.post("/api/posts", json={"content": "Breaking news"}, headers=headers)
    assert created.status_code == 201, created.text
    post = created.json()
    assert post["content"] == "Breaking news"
    assert post["comment_count"] == 0

    comment = client.post(
        f"/api/posts/{post['id']}/comments", json={"content": "Nice one"}, headers=headers
    )
    assert comment.status_code == 201, comment.text

    feed = client.get("/api/feed?limit=50&offset=0")
    assert feed.status_code == 200
    items = feed.json()["items"]
    target = next(item for item in items if item["id"] == post["id"])
    assert target["comment_count"] == 1
    assert target["comments"][0]["content"] == "Nice one"


def test_post_length_limit_is_enforced_by_the_api(client: TestClient):
    register(client, "length@example.com")
    token = login(client, "length@example.com")
    headers = auth_headers(token)

    ok = client.post("/api/posts", json={"content": "x" * 1000}, headers=headers)
    assert ok.status_code == 201

    too_long = client.post("/api/posts", json={"content": "x" * 1001}, headers=headers)
    assert too_long.status_code == 422


def test_comment_length_limit_is_enforced_by_the_api(client: TestClient):
    register(client, "clength@example.com")
    token = login(client, "clength@example.com")
    headers = auth_headers(token)

    post = client.post("/api/posts", json={"content": "A post to comment on"}, headers=headers).json()

    ok = client.post(
        f"/api/posts/{post['id']}/comments", json={"content": "y" * 100}, headers=headers
    )
    assert ok.status_code == 201

    too_long = client.post(
        f"/api/posts/{post['id']}/comments", json={"content": "y" * 101}, headers=headers
    )
    assert too_long.status_code == 422


def test_empty_and_blank_line_posts_are_rejected(client: TestClient):
    register(client, "blank@example.com")
    token = login(client, "blank@example.com")
    headers = auth_headers(token)

    assert client.post("/api/posts", json={"content": ""}, headers=headers).status_code == 422
    assert client.post("/api/posts", json={"content": "   "}, headers=headers).status_code == 422
    assert (
        client.post("/api/posts", json={"content": "a\n\nb"}, headers=headers).status_code == 422
    )
    assert (
        client.post("/api/posts", json={"content": "a\n   \nb"}, headers=headers).status_code == 422
    )


def test_empty_and_blank_line_comments_are_rejected(client: TestClient):
    register(client, "cblank@example.com")
    token = login(client, "cblank@example.com")
    headers = auth_headers(token)

    post = client.post("/api/posts", json={"content": "Comment target"}, headers=headers).json()

    assert (
        client.post(
            f"/api/posts/{post['id']}/comments", json={"content": ""}, headers=headers
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/posts/{post['id']}/comments", json={"content": "  "}, headers=headers
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/posts/{post['id']}/comments", json={"content": "a\n\nb"}, headers=headers
        ).status_code
        == 422
    )


def test_comment_on_missing_post_returns_404(client: TestClient):
    register(client, "missing@example.com")
    token = login(client, "missing@example.com")
    response = client.post(
        "/api/posts/999999/comments", json={"content": "hello"}, headers=auth_headers(token)
    )
    assert response.status_code == 404


def test_feed_is_public(client: TestClient):
    response = client.get("/api/feed")
    assert response.status_code == 200
    body = response.json()
    assert "items" in body and "has_more" in body


def test_feed_pagination_bounds(client: TestClient):
    response = client.get("/api/feed?limit=9999&offset=-5")
    assert response.status_code == 200
    body = response.json()
    assert body["limit"] == 50
    assert body["offset"] == 0


def test_admin_dashboard_and_actions(client: TestClient, promote_admin):
    register(client, "root@example.com")
    promote_admin("root@example.com")
    admin_token = login(client, "root@example.com")
    headers = auth_headers(admin_token)

    stats = client.get("/api/admin/stats", headers=headers)
    assert stats.status_code == 200
    assert stats.json()["users"] >= 1

    users = client.get("/api/admin/users", headers=headers)
    assert users.status_code == 200
    assert any(u["email"] == "root@example.com" for u in users.json())

    search = client.get("/api/admin/users?search=root", headers=headers)
    assert search.status_code == 200
    assert len(search.json()) == 1

    register(client, "target@example.com")
    target_token = login(client, "target@example.com")
    target_headers = auth_headers(target_token)
    post = client.post("/api/posts", json={"content": "Removable"}, headers=target_headers).json()
    comment = client.post(
        f"/api/posts/{post['id']}/comments", json={"content": "Also removable"}, headers=target_headers
    ).json()

    content = client.get("/api/admin/content", headers=headers)
    assert content.status_code == 200
    assert any(p["id"] == post["id"] for p in content.json()["posts"])

    moderation = client.get("/api/admin/moderation", headers=headers)
    assert moderation.status_code == 200
    assert any(row["decision"] == "approved" for row in moderation.json())

    assert client.delete(f"/api/admin/comments/{comment['id']}", headers=headers).status_code == 204
    assert client.delete(f"/api/admin/posts/{post['id']}", headers=headers).status_code == 204

    target_user = next(
        u
        for u in client.get("/api/admin/users?search=target", headers=headers).json()
        if u["email"] == "target@example.com"
    )
    deactivate = client.patch(
        f"/api/admin/users/{target_user['id']}", json={"is_active": False}, headers=headers
    )
    assert deactivate.status_code == 200
    assert deactivate.json()["is_active"] is False

    blocked_login = client.post(
        "/api/auth/login", json={"email": "target@example.com", "password": STRONG_PASSWORD}
    )
    assert blocked_login.status_code == 403

    delete = client.delete(f"/api/admin/users/{target_user['id']}", headers=headers)
    assert delete.status_code == 204

    gone = client.get("/api/admin/users?search=target", headers=headers)
    assert gone.status_code == 200
    assert all(u["id"] != target_user["id"] for u in gone.json())


def test_admin_cannot_delete_or_deactivate_own_account(client: TestClient, promote_admin):
    register(client, "selfadmin@example.com")
    promote_admin("selfadmin@example.com")
    token = login(client, "selfadmin@example.com")
    headers = auth_headers(token)

    me = client.get("/api/auth/me", headers=headers).json()
    assert client.delete(f"/api/admin/users/{me['id']}", headers=headers).status_code == 400
    assert (
        client.patch(
            f"/api/admin/users/{me['id']}", json={"is_active": False}, headers=headers
        ).status_code
        == 400
    )


def test_deactivated_user_token_is_rejected(client: TestClient, promote_admin):
    register(client, "deactivate@example.com")
    token = login(client, "deactivate@example.com")
    headers = auth_headers(token)

    register(client, "boss@example.com")
    promote_admin("boss@example.com")
    admin_token = login(client, "boss@example.com")
    users = client.get("/api/admin/users", headers=auth_headers(admin_token)).json()
    target = next(u for u in users if u["email"] == "deactivate@example.com")

    client.patch(
        f"/api/admin/users/{target['id']}", json={"is_active": False}, headers=auth_headers(admin_token)
    )

    response = client.get("/api/auth/me", headers=headers)
    assert response.status_code == 401


def test_blocked_terms_are_rejected_by_the_api(client: TestClient, use_blocked_terms):
    register(client, "moderated@example.com")
    token = login(client, "moderated@example.com")
    response = client.post(
        "/api/posts",
        json={"content": "this text has forbiddenterm inside"},
        headers=auth_headers(token),
    )
    assert response.status_code == 422

    history = client.get("/api/admin/moderation")
    assert history.status_code == 401

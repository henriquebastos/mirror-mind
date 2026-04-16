"""Tests for xdigest.send — email sending via gws gmail."""

import base64
import json
import pytest

from xdigest.send import build_rfc2822, build_gws_command, send_digest


def test_build_rfc2822_structure():
    msg = build_rfc2822(
        to="user@example.com",
        from_addr="mirror@example.com",
        subject="X Digest — 13 abr 2026",
        html_body="<h1>Hello</h1>",
    )

    assert "To: user@example.com" in msg
    assert "From: mirror@example.com" in msg
    assert "Subject:" in msg
    assert "Content-Type: text/html" in msg
    # Body is base64 encoded by MIMEText
    import base64
    assert base64.b64decode(msg.split("\n\n", 1)[1]).decode("utf-8") == "<h1>Hello</h1>"


def test_build_rfc2822_base64_encodable():
    msg = build_rfc2822(
        to="test@test.com",
        from_addr="from@test.com",
        subject="Test",
        html_body="<p>Test</p>",
    )
    # Should be base64url-encodable without errors
    encoded = base64.urlsafe_b64encode(msg.encode("utf-8")).decode("ascii")
    assert len(encoded) > 0
    # No padding issues
    assert "=" in encoded or len(encoded) % 4 == 0


def test_build_gws_command():
    cmd, payload = build_gws_command(
        raw_b64="dGVzdA==",
    )

    assert "gws" in cmd
    assert "gmail" in cmd
    assert "users" in cmd
    assert "messages" in cmd
    assert "send" in cmd
    assert payload["raw"] == "dGVzdA=="


def test_send_digest_calls_gws():
    calls = []

    def fake_run(cmd, input_data=None, **kwargs):
        calls.append({"cmd": cmd, "input": input_data})
        return json.dumps({"id": "msg123", "threadId": "thread456"})

    result = send_digest(
        html="<h1>Digest</h1>",
        to="user@example.com",
        from_addr="mirror@example.com",
        subject="X Digest — 13 abr 2026",
        run_command=fake_run,
    )

    assert len(calls) == 1
    assert result["id"] == "msg123"


def test_send_digest_raises_on_failure():
    def failing_run(cmd, input_data=None, **kwargs):
        raise Exception("gws failed")

    with pytest.raises(Exception, match="gws failed"):
        send_digest(
            html="<h1>Fail</h1>",
            to="test@test.com",
            from_addr="from@test.com",
            subject="Test",
            run_command=failing_run,
        )

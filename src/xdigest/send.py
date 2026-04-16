"""Send HTML email digest via gws gmail CLI."""

import base64
import json
import subprocess
from email.mime.text import MIMEText
from email.header import Header
from typing import Callable


GWS_BIN = "gws"


def build_rfc2822(to: str, from_addr: str, subject: str, html_body: str) -> str:
    """Build an RFC 2822 email message with proper MIME encoding."""
    msg = MIMEText(html_body, "html", "utf-8")
    msg["To"] = to
    msg["From"] = from_addr
    msg["Subject"] = Header(subject, "utf-8")
    return msg.as_string()


def build_gws_command(raw_b64: str) -> tuple[str, dict]:
    """Build the gws gmail send command and payload.

    Returns (command_string, payload_dict).
    """
    cmd = f"{GWS_BIN} gmail users messages send --params '{{\"userId\": \"me\"}}'"
    payload = {"raw": raw_b64}
    return cmd, payload


def _default_run_command(cmd: str, input_data: str | None = None, **kwargs) -> str:
    """Run a shell command, optionally piping input."""
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True,
        input=input_data, **kwargs,
    )
    result.check_returncode()
    return result.stdout


def send_digest(
    html: str,
    to: str,
    from_addr: str,
    subject: str,
    run_command: Callable = _default_run_command,
) -> dict:
    """Send an HTML email digest via gws gmail.

    Args:
        html: The HTML content of the email
        to: Recipient email
        from_addr: Sender email
        subject: Email subject
        run_command: Callable(cmd, input_data=None) -> str. Injected for testing.

    Returns:
        Gmail API response dict with message id and thread id.
    """
    # Build RFC 2822 message
    message = build_rfc2822(to, from_addr, subject, html)

    # Base64url encode
    raw_b64 = base64.urlsafe_b64encode(message.encode("utf-8")).decode("ascii")

    # Build command
    payload = {"raw": raw_b64}
    cmd = (
        f"{GWS_BIN} gmail users messages send"
        f" --params '{{\"userId\": \"me\"}}'"
        f" --json '{json.dumps(payload)}'"
    )

    response_text = run_command(cmd, input_data=None)
    return json.loads(response_text)

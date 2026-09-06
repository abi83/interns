"""GitHub App Manifest flow.

Mints an App from a manifest: serve a self-submitting form, let the operator
click "Create GitHub App" once, catch the redirect on a localhost callback,
hand the code back for conversion.

https://docs.github.com/en/apps/sharing-github-apps/registering-a-github-app-from-a-manifest
"""

from __future__ import annotations

import html
import json
import secrets
import threading
import urllib.parse
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer

# Permission matrix is fixed by the pipeline's needs (see README / #10):
# push branches, open and review PRs, edit issues and labels, read check runs.
APP_PERMISSIONS = {
    "contents": "write",
    "pull_requests": "write",
    "issues": "write",
    "checks": "read",
    "metadata": "read",
}


@dataclass
class AppSpec:
    key: str            # "reviewer" / "coder"
    default_name: str   # "interns-reviewer" / "interns-coder"
    id_var: str         # "INTERNS_REVIEWER_APP_ID"
    key_secret: str     # "INTERNS_REVIEWER_APP_PRIVATE_KEY"
    description: str


APPS = [
    AppSpec(
        key="reviewer",
        default_name="interns-reviewer",
        id_var="INTERNS_REVIEWER_APP_ID",
        key_secret="INTERNS_REVIEWER_APP_PRIVATE_KEY",
        description="submits PR reviews for the interns pipeline (claude[bot] can't approve its own PR)",
    ),
    AppSpec(
        key="coder",
        default_name="interns-coder",
        id_var="INTERNS_CODER_APP_ID",
        key_secret="INTERNS_CODER_APP_PRIVATE_KEY",
        description="coder-side pushes, PRs, comments and label edits for the interns pipeline",
    ),
]


def build_manifest(name: str, redirect_url: str, description: str) -> dict:
    return {
        "name": name,
        "url": "https://github.com/abi83/interns",
        "description": description,
        "redirect_url": redirect_url,
        "public": False,
        "default_events": [],
        "default_permissions": APP_PERMISSIONS,
    }


def settings_new_url(repo_owner: str, is_org: bool) -> str:
    if is_org:
        return f"https://github.com/organizations/{repo_owner}/settings/apps/new"
    return "https://github.com/settings/apps/new"


def settings_app_url(repo_owner: str, is_org: bool, slug: str) -> str:
    """Settings page of an existing App — where its App ID is shown and a new
    private key can be generated."""
    if is_org:
        return f"https://github.com/organizations/{repo_owner}/settings/apps/{slug}"
    return f"https://github.com/settings/apps/{slug}"


class _Handler(BaseHTTPRequestHandler):
    server_version = "interns-install/0.1"

    def log_message(self, *args):  # noqa: D401 - silence stdlib request logging
        pass

    def do_GET(self):  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        if parsed.path == "/":
            self._send_html(200, self.server.form_page)
            return
        if parsed.path == "/callback":
            code = params.get("code", [None])[0]
            state = params.get("state", [None])[0]
            if not code or state != self.server.state:
                self._send_html(400, "<p>Bad callback (state mismatch). You can close this tab.</p>")
                return
            self.server.code = code
            self._send_html(
                200,
                "<p>App created. Return to your terminal — you can close this tab.</p>",
            )
            self.server.done.set()
            return
        self._send_html(404, "<p>Not found.</p>")

    def _send_html(self, status: int, body: str):
        payload = f"<!doctype html><meta charset=utf-8><body>{body}</body>".encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class ManifestServer:
    """Context manager around a one-shot localhost callback server."""

    def __init__(self, action_url: str, make_manifest):
        """make_manifest(redirect_url) -> manifest dict. Called once the
        callback port is known."""
        self.state = secrets.token_urlsafe(24)
        self._httpd = HTTPServer(("127.0.0.1", 0), _Handler)
        self._httpd.state = self.state
        self._httpd.code = None
        self._httpd.done = threading.Event()
        redirect_url = f"http://127.0.0.1:{self.port}/callback"
        self.manifest = make_manifest(redirect_url)
        self._httpd.form_page = self._render_form(action_url, self.manifest)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)

    @property
    def port(self) -> int:
        return self._httpd.server_address[1]

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/"

    def _render_form(self, action_url: str, manifest: dict) -> str:
        manifest_json = html.escape(json.dumps(manifest), quote=True)
        return (
            "<!doctype html><meta charset=utf-8><body>"
            "<p>Redirecting you to GitHub to create the App…</p>"
            f'<form id=f action="{html.escape(action_url)}?state={self.state}" method=post>'
            f'<input type=hidden name=manifest value="{manifest_json}">'
            "<noscript><button type=submit>Continue to GitHub</button></noscript>"
            "</form><script>document.getElementById('f').submit()</script>"
            "</body>"
        )

    def __enter__(self):
        self._thread.start()
        return self

    def wait_for_code(self, timeout: float = 600.0) -> str:
        if not self._httpd.done.wait(timeout):
            raise TimeoutError("timed out waiting for the GitHub App creation callback")
        return self._httpd.code

    def __exit__(self, *exc):
        self._httpd.shutdown()
        self._httpd.server_close()

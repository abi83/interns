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
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer

from . import gh
from .console import Console

# Permission matrix is fixed by the pipeline's needs (see README / #10):
# push branches, open and review PRs, edit issues and labels, read check runs.
APP_PERMISSIONS = {
    "contents": "write",
    "pull_requests": "write",
    "issues": "write",
    "checks": "read",
    "metadata": "read",
}

# The triage App only ever edits issue labels (see #89) -- no repo contents or
# PR access needed.
TRIAGE_APP_PERMISSIONS = {
    "issues": "write",
    "metadata": "read",
}


@dataclass
class AppSpec:
    key: str            # "reviewer" / "coder" / "triage"
    name_base: str      # "interns-reviewer" / "interns-coder" / "interns-triage"
    client_id_var: str  # "INTERNS_REVIEWER_CLIENT_ID"
    key_secret: str     # "INTERNS_REVIEWER_APP_PRIVATE_KEY"
    description: str
    permissions: dict[str, str] | None = None  # None = APP_PERMISSIONS

    def name_for(self, owner: str) -> str:
        """GitHub App names are globally unique, so the minted name carries the
        owning account: two accounts each get their own `interns-<role>-<acct>`
        instead of racing for one global `interns-<role>`."""
        return f"{self.name_base}-{owner.lower()}"


APPS = [
    AppSpec(
        key="reviewer",
        name_base="interns-reviewer",
        client_id_var="INTERNS_REVIEWER_CLIENT_ID",
        key_secret="INTERNS_REVIEWER_APP_PRIVATE_KEY",
        description="submits PR reviews for the interns pipeline (claude[bot] can't approve its own PR)",
    ),
    AppSpec(
        key="coder",
        name_base="interns-coder",
        client_id_var="INTERNS_CODER_CLIENT_ID",
        key_secret="INTERNS_CODER_APP_PRIVATE_KEY",
        description="coder-side pushes, PRs, comments and label edits for the interns pipeline",
    ),
    AppSpec(
        key="triage",
        name_base="interns-triage",
        client_id_var="INTERNS_TRIAGE_CLIENT_ID",
        key_secret="INTERNS_TRIAGE_APP_PRIVATE_KEY",
        description="applies status:refined so the estimate phase actually triggers "
                     "(GITHUB_TOKEN-authored label edits never fire new workflow runs)",
        permissions=TRIAGE_APP_PERMISSIONS,
    ),
]


def build_manifest(name: str, repo_slug: str, redirect_url: str, description: str,
                    permissions: dict[str, str] | None = None) -> dict:
    return {
        "name": name,
        "url": f"https://github.com/{repo_slug}",
        "description": description,
        "redirect_url": redirect_url,
        "public": False,
        "default_events": [],
        "default_permissions": permissions or APP_PERMISSIONS,
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


def _forget(secret: str) -> None:  # noqa: ARG001 - see docstring
    """Called once a decoded secret (a PEM) is no longer needed. This does
    *not* scrub the string from memory -- in CPython, strings are immutable
    and may already be copied or interned, so dropping a reference is not a
    real mitigation. It exists only to make "we're done with this secret"
    explicit at the call site."""


def use_existing_app(con: Console, repo: gh.Repo, spec: AppSpec,
                     client_id: str | None, slug: str,
                     existing_secrets: list[str] | None) -> None:
    """Reuse an account-wide App: write this repo's Client-ID variable and
    private key secret, and prompt to install it here. Never mints, never
    reads a key back — the operator pastes a PEM (reused from another repo,
    or freshly generated on the App's settings page; adding a key does not
    revoke others).
    """
    settings_url = settings_app_url(repo.owner, repo.is_org, slug)
    have_key = existing_secrets is not None and spec.key_secret in existing_secrets

    if con.dry_run:
        con.say(f"existing {spec.key} App — {settings_url}")
        con.mutation(f"set variable {spec.client_id_var} (existing {spec.key} App)")
        if not have_key:
            con.mutation(f"{gh.secret_verb(spec.key_secret, existing_secrets)} "
                         f"secret {spec.key_secret} (pasted PEM)")
        con.note_manual(f"install the existing {spec.key} App on {repo.slug}")
        return

    if client_id is None:
        con.say(f"its Client ID (and 'Generate a private key') is on: {settings_url}")
        if con.assume_yes:
            con.note_manual(f"pass --{spec.key}-client-id (from {settings_url}) and set "
                            f"{spec.key_secret}, then install the App on {repo.slug}")
            return
        client_id = con.prompt(f"{spec.client_id_var} — the App's Client ID, "
                               f"e.g. 'Iv23li...' (blank to skip):")
        if not client_id:
            con.note_manual(f"set {spec.client_id_var} / {spec.key_secret} for the existing "
                            f"{spec.key} App, then install it on {repo.slug}")
            return
    else:
        con.say(f"reusing {spec.key} App {client_id} — {settings_url}")

    if con.mutation(f"set variable {spec.client_id_var} = {client_id}"):
        gh.set_variable(repo.slug, spec.client_id_var, client_id)

    if have_key:
        con.say(f"{spec.key_secret} is already set — leaving it (its key stays valid; "
                "keys held by other repos are unaffected)")
    elif con.assume_yes:
        con.note_manual(f"set the {spec.key_secret} secret (a PEM private key for "
                        f"'{slug}')")
    else:
        pem = con.prompt_multiline_secret(
            f"Paste a private key (PEM) for the '{slug}' App. This repo needs its "
            f"own copy in {spec.key_secret}; GitHub Actions secrets aren't shared "
            f"between repos. Reuse a .pem you saved for another repo, or generate "
            f"one at {settings_url}. Blank to set the secret yourself later:")
        if pem and con.mutation(
                f"{gh.secret_verb(spec.key_secret, existing_secrets)} secret {spec.key_secret}"):
            gh.set_secret(repo.slug, spec.key_secret, pem)
        elif not pem:
            con.note_manual(f"set the {spec.key_secret} secret (PEM private key)")
        _forget(pem)

    install_url = f"https://github.com/apps/{slug}/installations/new"
    con.note_manual(f"confirm the {spec.key} App is installed on {repo.slug}: {install_url}")
    if not con.assume_yes:
        con.say(f"opening your browser to install '{slug}' on {repo.slug} — "
                "pick the repo and click Install")
        webbrowser.open(install_url)


def provision_app(con: Console, repo: gh.Repo, spec: AppSpec,
                  client_id: str | None,
                  existing_secrets: list[str] | None) -> None:
    name = spec.name_for(repo.owner)
    con.step(f"GitHub App: {name} ({spec.key})")

    if client_id is not None:
        con.say(f"--{spec.key}-client-id given — reusing App {client_id}, skipping the mint")
        use_existing_app(con, repo, spec, client_id, name, existing_secrets)
        return

    # GitHub's Apps API only resolves *public* Apps by name; this installer
    # always mints private ones (see build_manifest), and GET /apps/{slug}
    # 404s on those even for the owning account's own token -- confirmed
    # hands-on, not a scope/rate-limit fluke. There is no automated way to
    # tell whether you already own '{name}', so ask instead of guessing and
    # walking into a mint that GitHub will reject as a name collision. Under
    # --yes there's no one to ask -- pass --{spec.key}-client-id instead. Ask
    # this before "create a new one?" -- "Set up now? [Y/n]" read as "create
    # a new App", and answering "n" (meaning "no, I have one already") ended
    # up skipping the App entirely instead of reaching the reuse question.
    if not con.assume_yes:
        settings_url = settings_app_url(repo.owner, repo.is_org, name)
        if con.confirm(f"Do you already have a GitHub App named '{name}'? "
                       f"(check {settings_url} if unsure)", default=False):
            use_existing_app(con, repo, spec, None, name, existing_secrets)
            return

    if not con.confirm(f"Create a new App '{name}' now?", default=True):
        con.note_manual(f"create the {spec.key} App (or point at an existing one with "
                        f"--{spec.key}-client-id) and set {spec.client_id_var} / {spec.key_secret}")
        return

    action_url = settings_new_url(repo.owner, repo.is_org)

    if con.dry_run:
        con.mutation(f"open {action_url} to create App '{name}' via manifest")
        con.mutation(f"{gh.secret_verb(spec.key_secret, existing_secrets)} secret {spec.key_secret}")
        con.mutation(f"set variable {spec.client_id_var}")
        con.note_manual(f"install the {spec.key} App on {repo.slug}")
        return

    with ManifestServer(action_url, lambda redirect: build_manifest(
        name, repo.slug, redirect, spec.description, spec.permissions)) as server:
        con.say(f"opening your browser to create '{name}' — "
                "click 'Create GitHub App'")
        con.say(f"if nothing opened, visit: {server.base_url}")
        webbrowser.open(server.base_url)
        code = server.wait_for_code()

    conv = gh.convert_manifest(code)
    client_id = str(conv["client_id"])
    slug = conv.get("slug", name)
    pem = conv["pem"]

    # Resilient ordering: the private key is returned exactly once, so it goes
    # straight into the secret before we do anything else.
    if con.mutation(f"{gh.secret_verb(spec.key_secret, existing_secrets)} secret {spec.key_secret}"):
        gh.set_secret(repo.slug, spec.key_secret, pem)
    _forget(pem)

    if con.mutation(f"set variable {spec.client_id_var} = {client_id}"):
        gh.set_variable(repo.slug, spec.client_id_var, client_id)

    con.say(f"App '{slug}' created (client id {client_id})")
    install_url = f"https://github.com/apps/{slug}/installations/new"
    con.note_manual(f"install the {spec.key} App on {repo.slug}: {install_url}")
    if not con.assume_yes:
        con.say(f"opening your browser to install '{slug}' on {repo.slug} — "
                "pick the repo and click Install")
        webbrowser.open(install_url)

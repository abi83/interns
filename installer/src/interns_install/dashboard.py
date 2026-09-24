"""Renders the interns metrics dashboard HTML, embedding the target repo slug."""

from importlib.resources import files

PATH = "interns-metrics/index.html"
_PLACEHOLDER = "{{REPO}}"


def render(repo: str) -> str:
    """Return dashboard HTML with `repo` (owner/name) embedded."""
    template = files(__package__).joinpath("dashboard.html").read_text(encoding="utf-8")
    return template.replace(_PLACEHOLDER, repo)

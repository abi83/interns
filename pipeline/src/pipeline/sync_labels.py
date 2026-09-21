"""Sync the versioned label manifest (.github/labels.json) into a repo,
idempotently: create labels that are missing, update colour/description
when they've drifted, leave everything else alone.

Additive by design -- a label that isn't in the manifest is never deleted,
so a consumer's own labels survive a sync. Re-running with no manifest
changes is a no-op.
"""

from __future__ import annotations

import json
import os
import sys

from . import cli, gh


class ManifestError(ValueError):
    pass


def _load_manifest(path: str) -> dict:
    if not os.path.isfile(path):
        raise ManifestError(f"no such manifest: {path}")
    with open(path) as f:
        data = json.load(f)
    if not isinstance(data.get("version"), (int, float)) or not isinstance(data.get("labels"), list):
        raise ManifestError(f"malformed manifest: {path}")
    return data


def sync_labels(repo: str, manifest_path: str) -> str:
    manifest = _load_manifest(manifest_path)
    existing = {label["name"]: label for label in gh.label_list(repo)}

    created = updated = unchanged = 0
    for entry in manifest["labels"]:
        name, color = entry["name"], entry["color"]
        description = entry.get("description", "")
        current = existing.get(name)

        if current is None:
            gh.label_create(repo, name, color, description)
            created += 1
        elif (current.get("color") or "").lower() == color.lower() and (current.get("description") or "") == description:
            unchanged += 1
        else:
            gh.label_edit(repo, name, color, description)
            updated += 1

    return (f"sync-labels: manifest v{manifest['version']} -> {repo}: "
            f"{created} created, {updated} updated, {unchanged} unchanged")


def _main(argv: list[str]) -> int:
    manifest_path = argv[0] if argv else ".github/labels.json"

    repo = os.environ.get("GITHUB_REPOSITORY")
    if not repo:
        print("sync-labels: GITHUB_REPOSITORY unset", file=sys.stderr)
        return 1
    if not os.environ.get("GH_TOKEN"):
        print("sync-labels: GH_TOKEN unset", file=sys.stderr)
        return 1

    try:
        print(sync_labels(repo, manifest_path))
    except ManifestError as exc:
        print(f"sync-labels: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(cli.run(_main))

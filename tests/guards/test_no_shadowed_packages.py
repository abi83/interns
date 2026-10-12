"""No top-level repo directory shares its name with an installed top-level package, so the repo root on `sys.path` can never shadow a dependency."""

from importlib.metadata import packages_distributions
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_no_top_level_directory_shadows_an_installed_package():
    installed = set(packages_distributions())
    directories = {p.name for p in ROOT.iterdir() if p.is_dir() and not p.name.startswith(".")}
    assert not directories & installed, f"rename: {sorted(directories & installed)}"

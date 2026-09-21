import unittest
from unittest import mock

from interns_install import gh_admin, install_files
from interns_install.install_files import collect_missing_files


def _repo():
    return gh_admin.Repo(owner="acme", name="widgets", is_org=False)


class CollectMissingFilesTests(unittest.TestCase):
    def test_collect_only_missing_files(self):
        present = {".github/workflows/issue-pipeline.yml", ".github/interns.yml", "Makefile"}
        src_for_dest = {dest: src for src, dest in install_files.INSTALL_FILES.items()}

        def existing(repo, path, ref):
            return (f"body:{src_for_dest[path]}", "sha-1") if path in present else None

        with mock.patch.object(install_files.gh_admin, "path_exists",
                               side_effect=lambda r, p, ref: p in present), \
             mock.patch.object(install_files.gh_admin, "get_existing_file", side_effect=existing), \
             mock.patch.object(install_files.gh_admin, "get_file", side_effect=lambda r, p, ref: f"body:{p}"):
            wanted = collect_missing_files(_repo(), "main", issue_templates=False)

        self.assertEqual(set(wanted), {
            ".github/workflows/install.yml",
            ".github/workflows/code-pipeline.yml",
        })
        self.assertIsNone(wanted[".github/workflows/install.yml"][1])

    def test_collect_flags_drifted_wrapper_file(self):
        """A wrapper file that's present but stale is re-synced, not skipped --
        this is the #88 fix: presence alone used to mean "nothing to do"."""
        src_for_dest = {dest: src for src, dest in install_files.INSTALL_FILES.items()}

        def existing(repo, path, ref):
            if path == ".github/workflows/install.yml":
                return ("stale content", "sha-old")
            return (f"body:{src_for_dest[path]}", "sha-1")

        with mock.patch.object(install_files.gh_admin, "path_exists", return_value=True), \
             mock.patch.object(install_files.gh_admin, "get_existing_file", side_effect=existing), \
             mock.patch.object(install_files.gh_admin, "get_file", side_effect=lambda r, p, ref: f"body:{p}"):
            wanted = collect_missing_files(_repo(), "main", issue_templates=False)

        self.assertEqual(set(wanted), {".github/workflows/install.yml"})
        content, sha = wanted[".github/workflows/install.yml"]
        self.assertEqual(content, "body:templates/workflows/install.yml")
        self.assertEqual(sha, "sha-old")

    def test_collect_never_overwrites_existing_config_files(self):
        """interns.yml/Makefile carry consumer-local edits -- only added when
        absent, regardless of content drift from the template."""
        with mock.patch.object(install_files.gh_admin, "path_exists", return_value=True), \
             mock.patch.object(install_files.gh_admin, "get_existing_file",
                               return_value=("body:templates/workflows/install.yml", "sha-1")), \
             mock.patch.object(install_files.gh_admin, "get_file", side_effect=lambda r, p, ref: f"body:{p}"):
            wanted = collect_missing_files(_repo(), "main", issue_templates=False)

        self.assertNotIn(".github/interns.yml", wanted)
        self.assertNotIn("Makefile", wanted)

    def test_collect_substitutes_ref_placeholder(self):
        tmpl = "uses: abi83/interns/.github/workflows/install.yml@__INTERNS_REF__"
        with mock.patch.object(install_files.gh_admin, "path_exists", return_value=False), \
             mock.patch.object(install_files.gh_admin, "get_existing_file", return_value=None), \
             mock.patch.object(install_files.gh_admin, "get_file", return_value=tmpl), \
             mock.patch.object(install_files, "INTERNS_REF", "v9.9.9"):
            wanted = collect_missing_files(_repo(), "main", issue_templates=False)

        for content, _sha in wanted.values():
            self.assertNotIn("__INTERNS_REF__", content)
            self.assertIn("@v9.9.9", content)

    def test_collect_pulls_issue_templates_when_dir_absent(self):
        with mock.patch.object(install_files.gh_admin, "path_exists", return_value=False), \
             mock.patch.object(install_files.gh_admin, "get_existing_file", return_value=None), \
             mock.patch.object(install_files.gh_admin, "list_dir", return_value=["bug.md", "config.yml"]), \
             mock.patch.object(install_files.gh_admin, "get_file", side_effect=lambda r, p, ref: f"body:{p}"):
            wanted = collect_missing_files(_repo(), "main", issue_templates=True)

        self.assertIn(".github/ISSUE_TEMPLATE/bug.md", wanted)
        self.assertIn(".github/ISSUE_TEMPLATE/config.yml", wanted)


if __name__ == "__main__":
    unittest.main()

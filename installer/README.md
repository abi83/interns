# interns-install

The local CLI that provisions a repo for [interns](../README.md): Apps, secrets, branch
protection, then a handoff to `install.yml`. Python, stdlib only.

Guide: [docs/install.md](../docs/install.md). Flags: `interns-install --help`.

```sh
uvx --from git+https://github.com/abi83/interns.git@v0#subdirectory=installer interns-install
```

Tests, coverage floors and lint run from the repo root: [docs/test-guide.md](../docs/test-guide.md).

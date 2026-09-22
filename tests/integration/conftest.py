import os


def pytest_configure(config):
    os.environ.setdefault("INTERNS_COVERAGE", "1")

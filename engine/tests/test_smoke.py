"""Package import smoke test."""

import engine


def test_version():
    assert engine.__version__ == "0.1.0"

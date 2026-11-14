import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from engine.network import load_network  # noqa: E402
from engine.synthetic import write_synthetic  # noqa: E402


@pytest.fixture(scope="session")
def synth_dir(tmp_path_factory):
    return write_synthetic(tmp_path_factory.mktemp("silver"))


@pytest.fixture(scope="session")
def net(synth_dir):
    return load_network(synth_dir)

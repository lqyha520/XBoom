import re

import pytest

from src.ai_write_x.main import EntryPointError, replay, train
from src.ai_write_x.version import get_version, get_version_with_prefix


def test_version_uses_semantic_version_shape():
    version = get_version()
    assert re.fullmatch(r"\d+\.\d+\.\d+", version)
    assert get_version_with_prefix() == f"v{version}"


@pytest.mark.parametrize("entrypoint", [train, replay])
def test_unimplemented_console_commands_fail_explicitly(entrypoint):
    with pytest.raises(EntryPointError):
        entrypoint()

"""Public copy only (written by the export step, not in the private repository).

foreground_lock.py, garde_fous.py and garde-fous.json are vendored in client/ from the author's private shared
folder (nexus-shared at a8e28ba). In the private layout they live in ../shared; here they are found in client/,
which the tests already put on sys.path. The one test that asserts the private layout is skipped.
"""

import pytest

PRIVATE_LAYOUT_TESTS = {"test_policy_is_the_shared_file"}


def pytest_collection_modifyitems(config, items):
    skip = pytest.mark.skip(reason="private layout only: the policy is vendored in client/ in the public copy")
    for item in items:
        if item.name in PRIVATE_LAYOUT_TESTS:
            item.add_marker(skip)

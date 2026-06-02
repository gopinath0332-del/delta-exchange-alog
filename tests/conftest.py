import os
import shutil
from pathlib import Path
import pytest

@pytest.fixture(scope="session", autouse=True)
def clean_test_state_dir():
    """Ensure the test state directory is clean before running tests."""
    project_root = Path(__file__).parent.parent
    state_test_dir = project_root / "data" / "state_test"
    if state_test_dir.exists():
        try:
            shutil.rmtree(state_test_dir)
            print(f"\nCleaned up test state directory at {state_test_dir}")
        except Exception as e:
            print(f"\nFailed to clean up test state directory: {e}")
    yield
    if state_test_dir.exists():
        try:
            shutil.rmtree(state_test_dir)
            print(f"\nCleaned up test state directory after session at {state_test_dir}")
        except Exception as e:
            pass

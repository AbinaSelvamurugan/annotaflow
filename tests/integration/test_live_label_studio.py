"""External infrastructure: opt in with ANNOTAFLOW_LIVE=1 and credentials.

Only reads an existing deployment; never generates fake human labels.
"""
import os
import pytest
from annotaflow.label_studio import LabelStudioAPI


@pytest.mark.live
def test_live_authenticated_connection():
    if os.getenv("ANNOTAFLOW_LIVE") != "1":
        pytest.skip("Opt in with ANNOTAFLOW_LIVE=1 and real Label Studio credentials")
    response = LabelStudioAPI().connect()
    assert isinstance(response, dict)

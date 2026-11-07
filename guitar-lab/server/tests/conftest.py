import pytest


@pytest.fixture(autouse=True)
def _basic_pitch_unless_a_test_chooses(monkeypatch):
    """Riley is the app's default when installed, but these tests exercise the Basic Pitch
    paths (tone thresholds, onset maps, refinement) and must not depend on which optional
    models happen to be installed. Tests about the default clear this themselves."""
    monkeypatch.setenv('FRETWORK_TRANSCRIBER', 'basic_pitch')

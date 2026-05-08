from src.webui.routers import system


def test_is_newer_version_detects_patch_update() -> None:
    assert system._is_newer_version("1.0.7", "1.0.6") is True


def test_is_newer_version_ignores_same_version_with_shorter_parts() -> None:
    assert system._is_newer_version("1.0.0", "1.0") is False


def test_is_newer_version_handles_unknown_current_version() -> None:
    assert system._is_newer_version("1.0.7", "unknown") is False

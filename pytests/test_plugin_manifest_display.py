from src.plugin_runtime.runner.manifest_validator import ManifestValidator


def _build_manifest(**overrides):
    manifest = {
        "manifest_version": 2,
        "version": "1.0.0",
        "name": "Demo Plugin",
        "description": "测试插件",
        "author": {
            "name": "tester",
            "url": "https://example.com/tester",
        },
        "license": "MIT",
        "urls": {
            "repository": "https://example.com/demo",
        },
        "host_application": {
            "min_version": "1.0.0",
            "max_version": "1.0.0",
        },
        "sdk": {
            "min_version": "2.0.0",
            "max_version": "2.99.99",
        },
        "dependencies": [],
        "capabilities": [],
        "i18n": {
            "default_locale": "zh-CN",
            "supported_locales": ["zh-CN"],
        },
        "id": "test.demo-plugin",
    }
    manifest.update(overrides)
    return manifest


def test_manifest_accepts_plugin_type_and_display_icon() -> None:
    validator = ManifestValidator(validate_python_package_dependencies=False)

    parsed = validator.parse_manifest(
        _build_manifest(
            plugin_type="data",
            display={
                "icon": {
                    "type": "local",
                    "value": "assets/icon.png",
                    "fallback": "package",
                    "background": "#1f2937",
                }
            },
        )
    )

    assert parsed is not None
    assert parsed.plugin_type == "data"
    assert parsed.display is not None
    assert parsed.display.icon is not None
    assert parsed.display.icon.value == "assets/icon.png"


def test_manifest_rejects_local_icon_outside_plugin_dir() -> None:
    validator = ManifestValidator(validate_python_package_dependencies=False)

    parsed = validator.parse_manifest(
        _build_manifest(
            display={
                "icon": {
                    "type": "local",
                    "value": "../icon.png",
                }
            },
        )
    )

    assert parsed is None
    assert any("local 图标路径" in error for error in validator.errors)


def test_manifest_rejects_url_icon_type() -> None:
    validator = ManifestValidator(validate_python_package_dependencies=False)

    parsed = validator.parse_manifest(
        _build_manifest(
            display={
                "icon": {
                    "type": "url",
                    "value": "https://example.com/icon.png",
                }
            },
        )
    )

    assert parsed is None
    assert any("display.icon.type" in error for error in validator.errors)

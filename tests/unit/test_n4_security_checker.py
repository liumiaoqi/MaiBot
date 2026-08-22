"""N4 安全门禁检查器单元测试 — 5 类检查 × 3 样本（缺陷/白名单/修复）。

验证漏报控制（缺陷样本必报）+ 误报控制（白名单样本不报）+ 修复幂等（修复样本不报）。
测试用真实文件系统调用 _scan_file_n4，走生产路径（接线四连问第 4 问）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.n4_security_checker import (
    WhitelistRule,
    _scan_file_n4,
    _ALL_CHECKS,
)


# ── 辅助：构造 fixture 文件并扫描 ──────────────────────────


def _write_fixture(tmp_path: Path, name: str, content: str) -> Path:
    """写入 fixture .py 文件，返回路径。"""
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _scan_n4(path: Path, checks: set[str] | None = None, whitelist: list | None = None) -> list:
    """对单个文件运行 N4 检查，返回违反列表。"""
    return _scan_file_n4(path, checks or _ALL_CHECKS, whitelist or [])


def _make_whitelist(path_substr: str, check_id: str, names: list[str] | None = None) -> list[WhitelistRule]:
    """构造单条白名单规则。"""
    return [WhitelistRule(path_substr=path_substr, checks=[check_id], names=names)]


# ── N4-1：端点无认证（P0）──────────────────────────────────


class TestNoAuth:
    """检查 n4-no-auth：router 级无 dependencies + 端点函数体无认证调用。"""

    _DEFECT = '''\
from fastapi import APIRouter

router = APIRouter(prefix="/test", tags=["test"])

@router.get("/items")
async def list_items():
    return {"items": []}

@router.post("/items")
async def create_item():
    return {"ok": True}
'''

    _FIXED = '''\
from fastapi import APIRouter, Depends
from src.webui.dependencies import require_auth

router = APIRouter(prefix="/test", tags=["test"], dependencies=[Depends(require_auth)])

@router.get("/items")
async def list_items():
    return {"items": []}
'''

    def test_no_auth_defect(self, tmp_path):
        """缺陷样本：router 无 dependencies + 端点无认证调用 → 报 P0。"""
        p = _write_fixture(tmp_path, "routers/test.py", self._DEFECT)
        violations = _scan_n4(p, checks={"n4-no-auth"})
        auth_violations = [v for v in violations if v.check_id == "n4-no-auth"]
        assert len(auth_violations) == 2
        assert all(v.severity == "P0" for v in auth_violations)

    def test_no_auth_whitelisted(self, tmp_path):
        """白名单样本：缺陷 + 白名单含端点名 → 报 0 条。"""
        p = _write_fixture(tmp_path, "routers/test.py", self._DEFECT)
        wl = _make_whitelist("routers/test.py", "n4-no-auth", names=["list_items", "create_item"])
        violations = _scan_n4(p, checks={"n4-no-auth"}, whitelist=wl)
        auth_violations = [v for v in violations if v.check_id == "n4-no-auth"]
        assert len(auth_violations) == 0

    def test_no_auth_fixed(self, tmp_path):
        """修复样本：router 有 dependencies=[Depends(require_auth)] → 报 0 条。"""
        p = _write_fixture(tmp_path, "routers/test.py", self._FIXED)
        violations = _scan_n4(p, checks={"n4-no-auth"})
        auth_violations = [v for v in violations if v.check_id == "n4-no-auth"]
        assert len(auth_violations) == 0


# ── N4-2：SSRF 候选（P1）──────────────────────────────────


class TestSSRF:
    """检查 n4-ssrf：端点有 url 参数 + 外部 HTTP 调用 + 无 allowlist 校验。"""

    _DEFECT = '''\
from fastapi import APIRouter
import requests

router = APIRouter(prefix="/test", tags=["test"])

@router.get("/fetch")
async def fetch_url(url: str):
    resp = requests.get(url)
    return {"data": resp.text}
'''

    _FIXED = '''\
from fastapi import APIRouter
import requests

router = APIRouter(prefix="/test", tags=["test"])

@router.get("/fetch")
async def fetch_url(url: str):
    if not is_safe_url(url):
        return {"error": "blocked"}
    resp = requests.get(url)
    return {"data": resp.text}
'''

    def test_ssrf_defect(self, tmp_path):
        """缺陷样本：url 参数 + requests.get + 无 allowlist → 报 P1。"""
        p = _write_fixture(tmp_path, "routers/test.py", self._DEFECT)
        violations = _scan_n4(p, checks={"n4-ssrf"})
        ssrf_violations = [v for v in violations if v.check_id == "n4-ssrf"]
        assert len(ssrf_violations) == 1
        assert ssrf_violations[0].severity == "P1"

    def test_ssrf_whitelisted(self, tmp_path):
        """白名单样本：缺陷 + 白名单含端点名 → 报 0 条。"""
        p = _write_fixture(tmp_path, "routers/test.py", self._DEFECT)
        wl = _make_whitelist("routers/test.py", "n4-ssrf", names=["fetch_url"])
        violations = _scan_n4(p, checks={"n4-ssrf"}, whitelist=wl)
        ssrf_violations = [v for v in violations if v.check_id == "n4-ssrf"]
        assert len(ssrf_violations) == 0

    def test_ssrf_fixed(self, tmp_path):
        """修复样本：有 is_safe_url 校验 → 报 0 条。"""
        p = _write_fixture(tmp_path, "routers/test.py", self._FIXED)
        violations = _scan_n4(p, checks={"n4-ssrf"})
        ssrf_violations = [v for v in violations if v.check_id == "n4-ssrf"]
        assert len(ssrf_violations) == 0


# ── N4-3：XFF 伪造风险（P1）──────────────────────────────


class TestXFF:
    """检查 n4-xff：端点函数体读 X-Forwarded-For 用于限流/鉴权。"""

    _DEFECT = '''\
from fastapi import APIRouter, Request

router = APIRouter(prefix="/test", tags=["test"])

@router.get("/rate")
async def rate_limit(request: Request):
    client_ip = request.headers["X-Forwarded-For"]
    return {"ip": client_ip}
'''

    _FIXED = '''\
from fastapi import APIRouter, Request

router = APIRouter(prefix="/test", tags=["test"])

@router.get("/rate")
async def rate_limit(request: Request):
    client_ip = request.client.host
    return {"ip": client_ip}
'''

    def test_xff_defect(self, tmp_path):
        """缺陷样本：读 request.headers["X-Forwarded-For"] → 报 P1。"""
        p = _write_fixture(tmp_path, "routers/test.py", self._DEFECT)
        violations = _scan_n4(p, checks={"n4-xff"})
        xff_violations = [v for v in violations if v.check_id == "n4-xff"]
        assert len(xff_violations) == 1
        assert xff_violations[0].severity == "P1"

    def test_xff_whitelisted(self, tmp_path):
        """白名单样本：缺陷 + 白名单含端点名 → 报 0 条。"""
        p = _write_fixture(tmp_path, "routers/test.py", self._DEFECT)
        wl = _make_whitelist("routers/test.py", "n4-xff", names=["rate_limit"])
        violations = _scan_n4(p, checks={"n4-xff"}, whitelist=wl)
        xff_violations = [v for v in violations if v.check_id == "n4-xff"]
        assert len(xff_violations) == 0

    def test_xff_fixed(self, tmp_path):
        """修复样本：用 request.client.host 替代 XFF → 报 0 条。"""
        p = _write_fixture(tmp_path, "routers/test.py", self._FIXED)
        violations = _scan_n4(p, checks={"n4-xff"})
        xff_violations = [v for v in violations if v.check_id == "n4-xff"]
        assert len(xff_violations) == 0


# ── N4-4：异常信息泄露（P1）──────────────────────────────


class TestInfoLeak:
    """检查 n4-info-leak：except handler 含 HTTPException(detail=str(e))。"""

    _DEFECT = '''\
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/test", tags=["test"])

@router.get("/items/{item_id}")
async def get_item(item_id: int):
    try:
        item = load_item(item_id)
        return {"item": item}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
'''

    _FIXED = '''\
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/test", tags=["test"])

@router.get("/items/{item_id}")
async def get_item(item_id: int):
    try:
        item = load_item(item_id)
        return {"item": item}
    except Exception:
        raise HTTPException(status_code=500, detail="内部错误")
'''

    def test_info_leak_defect(self, tmp_path):
        """缺陷样本：HTTPException(detail=str(e)) → 报 P1。"""
        p = _write_fixture(tmp_path, "routers/test.py", self._DEFECT)
        violations = _scan_n4(p, checks={"n4-info-leak"})
        leak_violations = [v for v in violations if v.check_id == "n4-info-leak"]
        assert len(leak_violations) == 1
        assert leak_violations[0].severity == "P1"

    def test_info_leak_whitelisted(self, tmp_path):
        """白名单样本：缺陷 + 白名单含端点名 → 报 0 条。"""
        p = _write_fixture(tmp_path, "routers/test.py", self._DEFECT)
        wl = _make_whitelist("routers/test.py", "n4-info-leak", names=["get_item"])
        violations = _scan_n4(p, checks={"n4-info-leak"}, whitelist=wl)
        leak_violations = [v for v in violations if v.check_id == "n4-info-leak"]
        assert len(leak_violations) == 0

    def test_info_leak_fixed(self, tmp_path):
        """修复样本：HTTPException(detail="内部错误") 不含 str(e) → 报 0 条。"""
        p = _write_fixture(tmp_path, "routers/test.py", self._FIXED)
        violations = _scan_n4(p, checks={"n4-info-leak"})
        leak_violations = [v for v in violations if v.check_id == "n4-info-leak"]
        assert len(leak_violations) == 0


# ── N4-5：api_key 空切片（P1）────────────────────────────


class TestApiKeyEmpty:
    """检查 n4-apikey-empty：api_key[:N] 前无长度判断。"""

    _DEFECT = '''\
from fastapi import APIRouter

router = APIRouter(prefix="/test", tags=["test"])

@router.get("/key")
async def get_key():
    api_key = get_config_key()
    masked = api_key[:8]
    return {"masked": masked}
'''

    _FIXED = '''\
from fastapi import APIRouter

router = APIRouter(prefix="/test", tags=["test"])

@router.get("/key")
async def get_key():
    api_key = get_config_key()
    if not api_key:
        return {"masked": ""}
    masked = api_key[:8]
    return {"masked": masked}
'''

    def test_apikey_empty_defect(self, tmp_path):
        """缺陷样本：api_key[:8] 前无长度判断 → 报 P1。"""
        p = _write_fixture(tmp_path, "routers/test.py", self._DEFECT)
        violations = _scan_n4(p, checks={"n4-apikey-empty"})
        key_violations = [v for v in violations if v.check_id == "n4-apikey-empty"]
        assert len(key_violations) == 1
        assert key_violations[0].severity == "P1"

    def test_apikey_empty_whitelisted(self, tmp_path):
        """白名单样本：缺陷 + 白名单含路径 → 报 0 条。"""
        p = _write_fixture(tmp_path, "routers/test.py", self._DEFECT)
        wl = _make_whitelist("routers/test.py", "n4-apikey-empty")
        violations = _scan_n4(p, checks={"n4-apikey-empty"}, whitelist=wl)
        key_violations = [v for v in violations if v.check_id == "n4-apikey-empty"]
        assert len(key_violations) == 0

    def test_apikey_empty_fixed(self, tmp_path):
        """修复样本：if not api_key 长度判断 → 报 0 条。"""
        p = _write_fixture(tmp_path, "routers/test.py", self._FIXED)
        violations = _scan_n4(p, checks={"n4-apikey-empty"})
        key_violations = [v for v in violations if v.check_id == "n4-apikey-empty"]
        assert len(key_violations) == 0
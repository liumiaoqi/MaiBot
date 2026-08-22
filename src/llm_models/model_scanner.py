"""模型目录惰性扫描 + 落库索引（ZG-12，对标 ComfyUI folder_paths）。

⚠️ 未接线原型（ZG-12 模型扫描）——计划阶段，有设计价值对标 ComfyUI，暂不接入生产路径。

ComfyUI 借鉴的取舍（调研结论）：
- 借鉴：多搜索根目录 + 惰性扫描 + mtime 失效缓存、列表期与解析期解耦
- 不照搬：目录即注册只作发现层，MaiBot 无人值守需**扫描后落库索引**
  （SQLite scanned_models：大小/校验和/元数据），目录发现只是同步入口

本地模型部署约束（用户明确）：本地模型都不在 docker 跑——
本扫描器只登记模型文件位置（供外置服务/挂载目录使用），不管理模型进程。
"""

import hashlib
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from src.common.logger import get_logger
from src.llm_models.model_requirement import ModelEntry

logger = get_logger("llm_models.model_scanner")

_SCAN_DIRS: dict[str, list[str]] = {}
"""category → 搜索目录列表（add_model_folder_path 注册）"""

_DEFAULT_CATEGORY_DIRS: dict[str, list[str]] = {
    "llm": ["models/llm"],
    "embedding": ["models/embedding"],
    "voice": ["models/voice"],
}

# SQLite 落库（数据目录）
_SCANNED_DB_PATH = "data/scanned_models.db"

_SCANNED_MODELS_SCHEMA = """
CREATE TABLE IF NOT EXISTS scanned_models (
    category TEXT NOT NULL,
    name TEXT NOT NULL,
    model_identifier TEXT NOT NULL,
    api_provider TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    scan_mtime REAL NOT NULL,
    checksum TEXT NOT NULL,
    PRIMARY KEY (category, name)
)
"""


@dataclass(frozen=True, slots=True)
class ScannedModel:
    """扫描到的模型文件记录（落库前/后的统一形态）。"""

    category: str
    name: str
    model_identifier: str
    api_provider: str
    file_path: str
    file_size: int
    scan_mtime: float
    checksum: str


class ModelNotFoundError(FileNotFoundError):
    """模型文件不存在（加载期兜底，对标 ComfyUI get_full_path_or_raise）。"""

    def __init__(self, category: str, name: str) -> None:
        self.category = category
        self.name = name
        super().__init__(f"模型 ({category}, {name}) 在目录中不存在")


def add_model_folder_path(category: str, path: str) -> None:
    """注册一个模型搜索目录（对标 ComfyUI add_model_folder_path）。

    目录即注册：注册后 get_filename_list/get_full_path 即可发现。
    """
    normalized = os.path.normpath(path)
    _SCAN_DIRS.setdefault(category, [])
    if normalized not in _SCAN_DIRS[category]:
        _SCAN_DIRS[category].append(normalized)


class ModelScanner:
    """模型目录扫描器 — 惰性扫描 + mtime 失效缓存 + SQLite 落库索引。

    用法：
        scanner = ModelScanner()
        entries = scanner.scan_category("llm")          # 扫描 + 落库
        names = scanner.get_filename_list("llm")        # 缓存列表（mtime 未变不重扫）
        path = scanner.get_full_path("llm", "bge-zh")   # 加载期复验
    """

    def __init__(self, db_path: str = _SCANNED_DB_PATH) -> None:
        self._db_path = db_path
        self._filename_cache: dict[str, list[str]] = {}
        self._dir_mtimes: dict[str, dict[str, float]] = {}
        self._scan_results: dict[str, list[ScannedModel]] = {}

    # ── 扫描 ─────────────────────────────────────────────────────

    def scan_category(self, category: str) -> list[ModelEntry]:
        """扫描某类别的搜索目录，结果落库 SQLite。

        目录 = 搜索目录列表（add_model_folder_path 注册的 + 默认目录）。
        mtime 未变的目录跳过重扫（惰性失效缓存）。

        Args:
            category: 模型类别（llm/embedding/voice）

        Returns:
            扫描得到的模型条目列表（已落库）
        """
        search_dirs = self._get_search_dirs(category)
        scanned: list[ScannedModel] = []
        dir_states: dict[str, float] = {}
        for search_dir in search_dirs:
            if not os.path.isdir(search_dir):
                continue
            dir_mtime = self._dir_mtime(search_dir)
            dir_states[search_dir] = dir_mtime
            if self._is_cache_fresh(category, search_dir, dir_mtime):
                continue
            for found in self._walk_files(search_dir, category):
                scanned.append(found)

        self._dir_mtimes[category] = dir_states
        if scanned:
            self._save_scanned(scanned)
            # 更新内存缓存
            category_cache = self._filename_cache.setdefault(category, [])
            for item in scanned:
                if item.name not in category_cache:
                    category_cache.append(item.name)
            self._scan_results[category] = self._load_scanned(category)
        return self._to_model_entries(self._load_scanned(category))

    def get_filename_list(self, category: str) -> list[str]:
        """返回某类别的模型名列表（mtime 未变则返回缓存，不重扫）。"""
        if category not in self._filename_cache or not self._cache_all_fresh(category):
            self.scan_category(category)
        return list(self._filename_cache.get(category, []))

    def get_full_path(self, category: str, name: str) -> str:
        """按名字在搜索目录中复验完整路径（加载期解析，不做扫描）。

        对标 ComfyUI get_full_path：逐个目录 os.path.isfile 找，
        找不到抛 ModelNotFoundError（结构化错误，含 category/name）。

        Args:
            category: 模型类别
            name: 模型文件名（如 "bge-large-zh-v1.5.onnx"）

        Returns:
            完整文件路径

        Raises:
            ModelNotFoundError: 所有搜索目录中均不存在
        """
        for search_dir in self._get_search_dirs(category):
            candidate = os.path.join(search_dir, name)
            if os.path.isfile(candidate):
                return candidate
        raise ModelNotFoundError(category, name)

    # ── 内部工具 ────────────────────────────────────────────────

    def _get_search_dirs(self, category: str) -> list[str]:
        return list(_SCAN_DIRS.get(category, [])) + list(_DEFAULT_CATEGORY_DIRS.get(category, []))

    @staticmethod
    def _dir_mtime(search_dir: str) -> float:
        return max(
            (os.path.getmtime(os.path.join(search_dir, entry))
             for entry in os.listdir(search_dir)),
            default=0.0,
        )

    def _is_cache_fresh(self, category: str, search_dir: str, dir_mtime: float) -> bool:
        cached = self._dir_mtimes.get(category, {}).get(search_dir)
        return cached is not None and cached == dir_mtime

    def _cache_all_fresh(self, category: str) -> bool:
        for search_dir in self._get_search_dirs(category):
            if not os.path.isdir(search_dir):
                continue
            if not self._is_cache_fresh(category, search_dir, self._dir_mtime(search_dir)):
                return False
        return True

    def _walk_files(self, search_dir: str, category: str) -> list[ScannedModel]:
        found: list[ScannedModel] = []
        for root, dirs, files in os.walk(search_dir):
            dirs[:] = [d for d in dirs if d != ".git"]
            for filename in sorted(files):
                file_path = os.path.join(root, filename)
                try:
                    file_size = os.path.getsize(file_path)
                    mtime = os.path.getmtime(file_path)
                except OSError as exc:
                    # P0-6: getsize/getmtime 失败出声（debug 防刷屏，跳过）（ZG-31）
                    logger.debug("model file stat 失败，跳过 %s: %s", file_path, exc)
                    continue
                found.append(ScannedModel(
                    category=category,
                    name=filename,
                    model_identifier=filename,
                    api_provider="",
                    file_path=file_path,
                    file_size=file_size,
                    scan_mtime=mtime,
                    checksum=self._checksum(file_path),
                ))
        return found

    @staticmethod
    def _checksum(file_path: str) -> str:
        """文件校验和（前 1MB 采样 + 大小，避免大模型全量哈希）。"""
        hasher = hashlib.sha256()
        try:
            with open(file_path, "rb") as fh:
                hasher.update(fh.read(1024 * 1024))
        except OSError as exc:
            logger.debug("计算文件校验和失败: %s: %s", file_path, exc)
            return ""
        hasher.update(str(os.path.getsize(file_path)).encode())
        return hasher.hexdigest()[:16]

    # ── SQLite 落库 ─────────────────────────────────────────────

    def _save_scanned(self, scanned: list[ScannedModel]) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(_SCANNED_MODELS_SCHEMA)
            conn.executemany(
                """INSERT OR REPLACE INTO scanned_models
                   (category, name, model_identifier, api_provider, file_path,
                    file_size, scan_mtime, checksum)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                [(s.category, s.name, s.model_identifier, s.api_provider, s.file_path,
                  s.file_size, s.scan_mtime, s.checksum) for s in scanned],
            )

    def _load_scanned(self, category: str) -> list[ScannedModel]:
        if not os.path.exists(self._db_path):
            return []
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                "SELECT category, name, model_identifier, api_provider, file_path,"
                " file_size, scan_mtime, checksum FROM scanned_models WHERE category = ?",
                (category,),
            ).fetchall()
        return [ScannedModel(*row) for row in rows]

    @staticmethod
    def _to_model_entries(scanned: list[ScannedModel]) -> list[ModelEntry]:
        return [
            ModelEntry(
                category=s.category,
                name=s.name,
                model_identifier=s.model_identifier,
                api_provider=s.api_provider,
                capabilities=frozenset(),
                extra_params={"file_path": s.file_path, "file_size": s.file_size,
                              "scan_mtime": s.scan_mtime, "checksum": s.checksum},
            )
            for s in scanned
        ]

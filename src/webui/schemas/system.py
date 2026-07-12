from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

class RestartResponse(BaseModel):
    """重启响应"""

    success: bool
    message: str

class StatusResponse(BaseModel):
    """状态响应"""

    running: bool
    uptime: float
    version: str
    start_time: str

class CacheDirectoryStats(BaseModel):
    """本地缓存目录统计。"""

    key: str
    label: str
    path: str
    exists: bool
    file_count: int
    total_size: int
    db_records: int = 0

class DatabaseFileStats(BaseModel):
    """数据库文件统计。"""

    path: str
    exists: bool
    size: int

class DatabaseTableStats(BaseModel):
    """数据库表统计。"""

    name: str
    rows: int
    size: int = 0
    size_source: Literal["dbstat", "estimated"] = "estimated"
    label: str = ""
    category: str = "其他"
    description: str = ""
    cleanup_supported: bool = False
    cleanup_date_column: str | None = None

class DatabaseStorageStats(BaseModel):
    """数据库存储统计。"""

    files: list[DatabaseFileStats]
    tables: list[DatabaseTableStats]
    total_size: int
    page_size: int = 0
    page_count: int = 0
    freelist_count: int = 0
    free_size: int = 0

class LocalCacheStatsResponse(BaseModel):
    """本地缓存统计响应。"""

    directories: list[CacheDirectoryStats]
    database: DatabaseStorageStats

class LocalCacheImageItem(BaseModel):
    """本地缓存图片文件条目。"""

    relative_path: str
    file_name: str
    full_path: str
    size: int
    modified_time: float
    format: str
    db_id: int | None = None
    image_hash: str | None = None
    description: str = ""
    is_registered: bool | None = None
    is_banned: bool | None = None
    no_file_flag: bool | None = None

class LocalCacheImageDateGroup(BaseModel):
    """本地缓存图片日期分组。"""

    date: str
    file_count: int
    total_size: int

class LocalCacheImageListResponse(BaseModel):
    """本地缓存图片列表响应。"""

    success: bool
    target: CacheImageTarget
    total: int
    page: int
    page_size: int
    total_size: int
    data: list[LocalCacheImageItem]
    date_groups: list[LocalCacheImageDateGroup] = Field(default_factory=list)

class LocalCacheLogDirectoryItem(BaseModel):
    """本地日志目录条目。"""

    relative_path: str
    name: str
    full_path: str
    depth: int
    file_count: int
    total_size: int
    modified_time: float
    root_files_only: bool = False

class LocalCacheLogDirectoryListResponse(BaseModel):
    """本地日志目录列表响应。"""

    success: bool
    total: int
    data: list[LocalCacheLogDirectoryItem]

class LocalCacheDataEntry(BaseModel):
    """data 目录中的文件或文件夹条目。"""

    relative_path: str
    name: str
    full_path: str
    kind: Literal["file", "directory"]
    file_count: int
    total_size: int
    modified_time: float
    protected: bool = False
    protection_reason: str | None = None

class LocalCacheDataEntriesResponse(BaseModel):
    """data 目录浏览响应。"""

    success: bool
    root_path: str
    relative_path: str
    current_path: str
    parent_path: str | None = None
    file_count: int
    total_size: int
    total: int
    data: list[LocalCacheDataEntry]

class LocalCacheCleanupRequest(BaseModel):
    """本地缓存清理请求。"""

    target: Literal["images", "emoji", "log_files", "database_logs"]
    tables: list[str] = Field(default_factory=list)
    database_mode: DatabaseCleanupMode = "all"
    older_than_days: int | None = Field(default=None, ge=1)
    vacuum_after_cleanup: bool = True

class LocalCacheCleanupResponse(BaseModel):
    """本地缓存清理响应。"""

    success: bool
    message: str
    target: str
    removed_files: int = 0
    removed_bytes: int = 0
    removed_records: int = 0
    vacuumed: bool = False
    database_size_before: int | None = None
    database_size_after: int | None = None
    reclaimed_bytes: int = 0

class LocalCacheDatabaseVacuumResponse(BaseModel):
    """数据库 VACUUM 维护响应。"""

    success: bool
    message: str
    database_size_before: int
    database_size_after: int
    reclaimed_bytes: int
    checkpoint_busy: int = 0
    checkpoint_log: int = 0
    checkpointed: int = 0

class LocalCacheImageDeleteRequest(BaseModel):
    """本地缓存单张图片删除请求。"""

    target: CacheImageTarget
    relative_path: str

class LocalCacheImageBulkDeleteRequest(BaseModel):
    """本地缓存图片批量删除请求。"""

    target: CacheImageTarget
    mode: Literal["date_range", "older_than_recent_days"]
    start_date: str | None = None
    end_date: str | None = None
    keep_recent_days: Literal[1, 7, 30] | None = None

class LocalCacheLogDirectoryDeleteRequest(BaseModel):
    """本地日志目录清理请求。"""

    relative_path: str

class LocalCacheDataEntryDeleteRequest(BaseModel):
    """data 目录条目删除请求。"""

    relative_path: str


class SystemResourcesResponse(BaseModel):
    """系统资源使用情况。"""

    cpu_percent: float = Field(0.0, description="CPU 使用率百分比")
    memory_percent: float = Field(0.0, description="内存使用率百分比")
    memory_used: int = Field(0, description="已用内存（字节）")
    memory_total: int = Field(0, description="总内存（字节）")
    disk_percent: float = Field(0.0, description="磁盘使用率百分比")
    disk_used: int = Field(0, description="已用磁盘（字节）")
    disk_total: int = Field(0, description="总磁盘（字节）")
    database_size: int = Field(0, description="数据库大小（字节）")
    timestamp: float = Field(0.0, description="采集时间戳")

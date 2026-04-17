from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import argparse
import json
import mimetypes
import time
import webbrowser


DEFAULT_LOG_DIR = Path("logs") / "maisaka_reply_effect"
DEFAULT_MANUAL_DIR = Path("logs") / "maisaka_reply_effect_manual"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def normalize_name(value: str) -> str:
    normalized = "".join(char if char.isalnum() or char in "._-" else "_" for char in str(value or "").strip())
    normalized = normalized.strip("._")
    return normalized or "unknown"


def load_json_file(file_path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(file_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def write_json_file(file_path: Path, payload: dict[str, Any]) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = file_path.with_name(f".{file_path.name}.tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    temp_path.replace(file_path)


class ReplyEffectRepository:
    def __init__(self, log_dir: Path, manual_dir: Path) -> None:
        self.log_dir = log_dir
        self.manual_dir = manual_dir

    def list_chats(self) -> list[dict[str, Any]]:
        chats: list[dict[str, Any]] = []
        if not self.log_dir.exists():
            return chats

        for chat_dir in sorted(path for path in self.log_dir.iterdir() if path.is_dir()):
            records = list(chat_dir.glob("*.json"))
            annotated_count = sum(1 for record_file in records if self._annotation_path(chat_dir.name, record_file).exists())
            finalized_count = 0
            pending_count = 0
            for record_file in records:
                payload = load_json_file(record_file)
                if payload.get("status") == "finalized":
                    finalized_count += 1
                else:
                    pending_count += 1
            chats.append(
                {
                    "chat_id": chat_dir.name,
                    "record_count": len(records),
                    "finalized_count": finalized_count,
                    "pending_count": pending_count,
                    "annotated_count": annotated_count,
                }
            )
        return chats

    def list_records(
        self,
        *,
        chat_id: str | None = None,
        status: str = "",
        annotated: str = "",
    ) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for record_file in self._iter_record_files(chat_id):
            payload = load_json_file(record_file)
            if not payload:
                continue
            summary = self._build_record_summary(record_file, payload)
            if status and summary["status"] != status:
                continue
            if annotated == "yes" and summary["manual"] is None:
                continue
            if annotated == "no" and summary["manual"] is not None:
                continue
            records.append(summary)
        return sorted(records, key=lambda item: str(item.get("created_at") or ""), reverse=True)

    def get_record(self, chat_id: str, effect_id: str) -> dict[str, Any]:
        record_file = self._find_record_file(chat_id, effect_id)
        if record_file is None:
            return {}
        payload = load_json_file(record_file)
        if not payload:
            return {}
        payload["_manual"] = self.get_annotation(chat_id, effect_id)
        payload["_record_path"] = str(record_file)
        return payload

    def get_annotation(self, chat_id: str, effect_id: str) -> dict[str, Any] | None:
        annotation_path = self._annotation_path(chat_id, effect_id)
        if not annotation_path.exists():
            return None
        payload = load_json_file(annotation_path)
        return payload or None

    def save_annotation(self, payload: dict[str, Any]) -> dict[str, Any]:
        chat_id = normalize_name(str(payload.get("chat_id") or ""))
        effect_id = normalize_name(str(payload.get("effect_id") or ""))
        if not chat_id or chat_id == "unknown" or not effect_id or effect_id == "unknown":
            raise ValueError("缺少 chat_id 或 effect_id")
        if self._find_record_file(chat_id, effect_id) is None:
            raise ValueError("找不到对应的回复效果记录")

        manual_score = payload.get("manual_score")
        manual_score_5 = payload.get("manual_score_5")
        normalized_score: float | None = None
        normalized_score_5: int | None = None
        if manual_score_5 not in {None, ""}:
            try:
                normalized_score_5 = int(manual_score_5)
            except (TypeError, ValueError):
                raise ValueError("manual_score_5 必须是 1-5 的整数") from None
            if normalized_score_5 < 1 or normalized_score_5 > 5:
                raise ValueError("manual_score_5 必须是 1-5 的整数")
            normalized_score = round((normalized_score_5 - 1) / 4 * 100, 2)
        elif manual_score not in {None, ""}:
            try:
                normalized_score = max(0.0, min(100.0, float(manual_score)))
            except (TypeError, ValueError):
                raise ValueError("manual_score 必须是 0-100 的数字") from None
        else:
            raise ValueError("缺少人工评分")

        annotation = {
            "schema_version": 1,
            "chat_id": chat_id,
            "effect_id": effect_id,
            "manual_score": round(normalized_score, 2),
            "manual_score_5": normalized_score_5,
            "manual_label": str(payload.get("manual_label") or "").strip(),
            "evaluator": str(payload.get("evaluator") or "manual").strip() or "manual",
            "notes": str(payload.get("notes") or "").strip(),
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
        write_json_file(self._annotation_path(chat_id, effect_id), annotation)
        return annotation

    def _iter_record_files(self, chat_id: str | None = None) -> list[Path]:
        if not self.log_dir.exists():
            return []
        if chat_id:
            chat_dir = self.log_dir / normalize_name(chat_id)
            if not chat_dir.exists() or not chat_dir.is_dir():
                return []
            return sorted(chat_dir.glob("*.json"))

        record_files: list[Path] = []
        for chat_dir in self.log_dir.iterdir():
            if chat_dir.is_dir():
                record_files.extend(chat_dir.glob("*.json"))
        return record_files

    def _find_record_file(self, chat_id: str, effect_id: str) -> Path | None:
        normalized_effect_id = normalize_name(effect_id)
        for record_file in self._iter_record_files(chat_id):
            payload = load_json_file(record_file)
            if normalize_name(str(payload.get("effect_id") or "")) == normalized_effect_id:
                return record_file
        return None

    def _annotation_path(self, chat_id: str, record_file_or_effect_id: Path | str) -> Path:
        if isinstance(record_file_or_effect_id, Path):
            payload = load_json_file(record_file_or_effect_id)
            effect_id = str(payload.get("effect_id") or record_file_or_effect_id.stem).strip()
        else:
            effect_id = str(record_file_or_effect_id or "").strip()
        return self.manual_dir / normalize_name(chat_id) / f"{normalize_name(effect_id)}.json"

    def _build_record_summary(self, record_file: Path, payload: dict[str, Any]) -> dict[str, Any]:
        chat_id = record_file.parent.name
        effect_id = str(payload.get("effect_id") or record_file.stem)
        scores = payload.get("scores") if isinstance(payload.get("scores"), dict) else {}
        reply = payload.get("reply") if isinstance(payload.get("reply"), dict) else {}
        target_user = payload.get("target_user") if isinstance(payload.get("target_user"), dict) else {}
        manual = self.get_annotation(chat_id, effect_id)
        return {
            "chat_id": chat_id,
            "effect_id": effect_id,
            "status": str(payload.get("status") or ""),
            "created_at": str(payload.get("created_at") or ""),
            "finalize_reason": str(payload.get("finalize_reason") or ""),
            "asi": scores.get("asi"),
            "behavior_score": scores.get("behavior_score"),
            "relational_score": scores.get("relational_score"),
            "friction_score": scores.get("friction_score"),
            "manual": manual,
            "reply_preview": self._truncate(str(reply.get("reply_text") or ""), 160),
            "target_message_id": str(reply.get("target_message_id") or ""),
            "target_user": target_user,
            "followup_count": len(payload.get("followup_messages") or []),
            "file_name": record_file.name,
        }

    @staticmethod
    def _truncate(text: str, limit: int) -> str:
        normalized_text = " ".join(str(text or "").split())
        if len(normalized_text) <= limit:
            return normalized_text
        return f"{normalized_text[: limit - 1]}…"


class ReplyEffectPreviewHandler(BaseHTTPRequestHandler):
    repository: ReplyEffectRepository

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send_html(INDEX_HTML_V3)
            return
        if parsed.path == "/api/chats":
            self._send_json({"chats": self.repository.list_chats()})
            return
        if parsed.path == "/api/records":
            query = parse_qs(parsed.query)
            records = self.repository.list_records(
                chat_id=self._first(query, "chat_id"),
                status=self._first(query, "status"),
                annotated=self._first(query, "annotated"),
            )
            self._send_json({"records": records})
            return
        if parsed.path == "/api/record":
            query = parse_qs(parsed.query)
            record = self.repository.get_record(
                normalize_name(self._first(query, "chat_id")),
                normalize_name(self._first(query, "effect_id")),
            )
            if not record:
                self._send_json({"error": "record not found"}, status=404)
                return
            self._send_json({"record": record})
            return
        if parsed.path == "/api/image":
            query = parse_qs(parsed.query)
            self._send_image(self._first(query, "path"))
            return
        if parsed.path == "/api/image_hash":
            query = parse_qs(parsed.query)
            self._send_image_by_hash(self._first(query, "hash"), self._first(query, "kind"))
            return
        self._send_json({"error": "not found"}, status=404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/annotations":
            self._send_json({"error": "not found"}, status=404)
            return
        try:
            payload = self._read_json_body()
            annotation = self.repository.save_annotation(payload)
        except ValueError as exc:
            self._send_json({"error": str(exc)}, status=400)
            return
        self._send_json({"annotation": annotation})

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _send_html(self, content: str) -> None:
        body = content.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_image_by_hash(self, image_hash: str, kind: str = "") -> None:
        image_hash = str(image_hash or "").strip()
        if not image_hash:
            self._send_json({"error": "missing image hash"}, status=400)
            return
        image_path = self._resolve_image_path_by_hash(image_hash, kind)
        if image_path is None:
            self._send_json({"error": "image hash not found"}, status=404)
            return
        self._send_image(str(image_path))

    @staticmethod
    def _resolve_image_path_by_hash(image_hash: str, kind: str = "") -> Path | None:
        try:
            from sqlmodel import select

            from src.common.database.database import get_db_session
            from src.common.database.database_model import Images, ImageType

            preferred_types = []
            if kind == "emoji":
                preferred_types.append(ImageType.EMOJI)
            elif kind == "image":
                preferred_types.append(ImageType.IMAGE)
            preferred_types.extend(image_type for image_type in (ImageType.IMAGE, ImageType.EMOJI) if image_type not in preferred_types)

            with get_db_session() as db:
                for image_type in preferred_types:
                    statement = select(Images).filter_by(image_hash=image_hash, image_type=image_type).limit(1)
                    image_record = db.exec(statement).first()
                    if image_record is None or image_record.no_file_flag:
                        continue
                    image_path = Path(str(image_record.full_path or "")).expanduser().resolve()
                    if image_path.is_file():
                        return image_path
        except Exception:
            return None
        return None

    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_image(self, raw_path: str) -> None:
        try:
            image_path = Path(raw_path).expanduser().resolve()
            if not image_path.is_file():
                raise FileNotFoundError(raw_path)
            mime_type = mimetypes.guess_type(str(image_path))[0] or "application/octet-stream"
            if not mime_type.startswith("image/"):
                self._send_json({"error": "not an image"}, status=400)
                return
            body = image_path.read_bytes()
        except OSError:
            self._send_json({"error": "image not found"}, status=404)
            return

        self.send_response(200)
        self.send_header("Content-Type", mime_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        raw_body = self.rfile.read(length).decode("utf-8")
        payload = json.loads(raw_body or "{}")
        if not isinstance(payload, dict):
            raise ValueError("请求体必须是 JSON 对象")
        return payload

    @staticmethod
    def _first(query: dict[str, list[str]], key: str) -> str:
        values = query.get(key) or [""]
        return values[0]


INDEX_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Maisaka 回复效果评分预览</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f7f7f4;
      --panel: #ffffff;
      --line: #deded7;
      --text: #202124;
      --muted: #686b70;
      --accent: #0f766e;
      --danger: #b42318;
      --warn: #b7791f;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
      background: var(--bg);
      color: var(--text);
    }
    header {
      height: 56px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 18px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
    }
    h1 { font-size: 18px; margin: 0; }
    main {
      display: grid;
      grid-template-columns: 280px minmax(420px, 1fr) 420px;
      height: calc(100vh - 56px);
      min-height: 560px;
    }
    aside, section {
      overflow: auto;
      border-right: 1px solid var(--line);
      background: var(--panel);
    }
    .sidebar { padding: 14px; }
    .content { padding: 14px; background: var(--bg); }
    .detail { padding: 14px; border-right: none; }
    .toolbar {
      display: flex;
      gap: 8px;
      align-items: center;
      margin-bottom: 12px;
      flex-wrap: wrap;
    }
    input, select, textarea, button {
      font: inherit;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--text);
    }
    input, select { height: 34px; padding: 0 9px; }
    textarea { width: 100%; min-height: 86px; padding: 8px; resize: vertical; }
    button {
      height: 34px;
      padding: 0 12px;
      cursor: pointer;
      background: var(--accent);
      color: white;
      border-color: var(--accent);
    }
    button.secondary {
      background: white;
      color: var(--text);
      border-color: var(--line);
    }
    .chat-item, .record-card {
      border: 1px solid var(--line);
      background: #fff;
      border-radius: 8px;
      padding: 10px;
      margin-bottom: 10px;
      cursor: pointer;
    }
    .chat-item.active, .record-card.active { border-color: var(--accent); box-shadow: 0 0 0 2px rgba(15, 118, 110, 0.14); }
    .chat-id, .record-title { font-weight: 650; word-break: break-all; }
    .meta { color: var(--muted); font-size: 12px; line-height: 1.6; }
    .metrics { display: flex; gap: 8px; flex-wrap: wrap; margin: 8px 0; }
    .pill {
      display: inline-flex;
      align-items: center;
      min-height: 24px;
      padding: 2px 8px;
      border-radius: 999px;
      background: #eef5f4;
      color: #155e57;
      font-size: 12px;
      border: 1px solid #d1e7e3;
    }
    .pill.pending { background: #fff7ed; color: var(--warn); border-color: #fed7aa; }
    .pill.bad { background: #fef3f2; color: var(--danger); border-color: #fecdca; }
    .preview {
      white-space: pre-wrap;
      line-height: 1.55;
      margin: 8px 0 0;
    }
    .block {
      border: 1px solid var(--line);
      background: #fff;
      border-radius: 8px;
      padding: 12px;
      margin-bottom: 12px;
    }
    .block h2 { font-size: 15px; margin: 0 0 10px; }
    pre {
      white-space: pre-wrap;
      word-break: break-word;
      background: #f5f5f2;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 10px;
      max-height: 260px;
      overflow: auto;
    }
    label { display: block; font-size: 13px; color: var(--muted); margin: 10px 0 4px; }
    .empty { color: var(--muted); padding: 18px; text-align: center; }
  </style>
</head>
<body>
  <header>
    <h1>Maisaka 回复效果评分预览</h1>
    <button class="secondary" onclick="reloadAll()">刷新</button>
  </header>
  <main>
    <aside class="sidebar">
      <div class="toolbar">
        <input id="chatSearch" placeholder="筛选聊天流" oninput="renderChats()" />
      </div>
      <div id="chatList"></div>
    </aside>
    <section class="content">
      <div class="toolbar">
        <select id="statusFilter" onchange="loadRecords()">
          <option value="">全部状态</option>
          <option value="finalized">已完成</option>
          <option value="pending">观察中</option>
        </select>
        <select id="annotationFilter" onchange="loadRecords()">
          <option value="">全部标注</option>
          <option value="yes">已人工评分</option>
          <option value="no">未人工评分</option>
        </select>
      </div>
      <div id="recordList"></div>
    </section>
    <section class="detail">
      <div id="detailPane" class="empty">选择一条记录查看详情</div>
    </section>
  </main>
  <script>
    let chats = [];
    let records = [];
    let selectedChat = "";
    let selectedEffect = "";

    async function api(path, options) {
      const res = await fetch(path, options);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "请求失败");
      return data;
    }

    async function reloadAll() {
      const data = await api("/api/chats");
      chats = data.chats || [];
      if (!selectedChat && chats.length) selectedChat = chats[0].chat_id;
      renderChats();
      await loadRecords();
    }

    function renderChats() {
      const q = document.getElementById("chatSearch").value.trim().toLowerCase();
      const list = document.getElementById("chatList");
      const shown = chats.filter(c => !q || c.chat_id.toLowerCase().includes(q));
      list.innerHTML = shown.map(chat => `
        <div class="chat-item ${chat.chat_id === selectedChat ? "active" : ""}" onclick="selectChat('${escapeAttr(chat.chat_id)}')">
          <div class="chat-id">${escapeHtml(chat.chat_id)}</div>
          <div class="meta">记录 ${chat.record_count} | 完成 ${chat.finalized_count} | 观察中 ${chat.pending_count} | 人工 ${chat.annotated_count}</div>
        </div>
      `).join("") || `<div class="empty">没有聊天流</div>`;
    }

    async function selectChat(chatId) {
      selectedChat = chatId;
      selectedEffect = "";
      renderChats();
      await loadRecords();
      document.getElementById("detailPane").innerHTML = "选择一条记录查看详情";
    }

    async function loadRecords() {
      const params = new URLSearchParams();
      if (selectedChat) params.set("chat_id", selectedChat);
      const status = document.getElementById("statusFilter").value;
      const annotated = document.getElementById("annotationFilter").value;
      if (status) params.set("status", status);
      if (annotated) params.set("annotated", annotated);
      const data = await api(`/api/records?${params.toString()}`);
      records = data.records || [];
      renderRecords();
    }

    function renderRecords() {
      const list = document.getElementById("recordList");
      list.innerHTML = records.map(record => {
        const asi = record.asi === null || record.asi === undefined ? "N/A" : Number(record.asi).toFixed(1);
        const manual = record.manual ? Number(record.manual.manual_score).toFixed(1) : "未评";
        return `
          <div class="record-card ${record.effect_id === selectedEffect ? "active" : ""}" onclick="loadDetail('${escapeAttr(record.chat_id)}','${escapeAttr(record.effect_id)}')">
            <div class="record-title">${escapeHtml(record.created_at || record.file_name)}</div>
            <div class="metrics">
              <span class="pill ${record.status === "pending" ? "pending" : ""}">${escapeHtml(record.status || "unknown")}</span>
              <span class="pill">ASI ${asi}</span>
              <span class="pill">人工 ${manual}</span>
              <span class="pill">${escapeHtml(record.finalize_reason || "未结算")}</span>
            </div>
            <div class="meta">目标用户：${escapeHtml((record.target_user && (record.target_user.cardname || record.target_user.nickname || record.target_user.user_id)) || "未知")} | 后续 ${record.followup_count}</div>
            <div class="preview">${escapeHtml(record.reply_preview || "")}</div>
          </div>
        `;
      }).join("") || `<div class="empty">没有记录</div>`;
    }

    async function loadDetail(chatId, effectId) {
      selectedChat = chatId;
      selectedEffect = effectId;
      renderChats();
      renderRecords();
      const data = await api(`/api/record?chat_id=${encodeURIComponent(chatId)}&effect_id=${encodeURIComponent(effectId)}`);
      renderDetail(data.record);
    }

    function renderDetail(record) {
      const scores = record.scores || {};
      const reply = record.reply || {};
      const manual = record._manual || {};
      const followups = record.followup_messages || [];
      document.getElementById("detailPane").innerHTML = `
        <div class="block">
          <h2>自动评分</h2>
          <div class="metrics">
            <span class="pill">ASI ${fmt(scores.asi)}</span>
            <span class="pill">行为 ${fmt(scores.behavior_score)}</span>
            <span class="pill">感知 ${fmt(scores.relational_score)}</span>
            <span class="pill">摩擦 ${fmt(scores.friction_score)}</span>
          </div>
          <div class="meta">完成原因：${escapeHtml(record.finalize_reason || "未完成")}</div>
          <div class="meta">${escapeHtml(record.confidence_note || "")}</div>
        </div>
        <div class="block">
          <h2>人工评分</h2>
          <label>人工分数 0-100</label>
          <input id="manualScore" type="number" min="0" max="100" step="1" value="${manual.manual_score ?? ""}" />
          <label>标签</label>
          <select id="manualLabel">
            ${["", "good", "neutral", "bad", "uncertain"].map(v => `<option value="${v}" ${manual.manual_label === v ? "selected" : ""}>${v || "未选择"}</option>`).join("")}
          </select>
          <label>评价人</label>
          <input id="evaluator" value="${escapeAttr(manual.evaluator || "manual")}" />
          <label>备注</label>
          <textarea id="manualNotes">${escapeHtml(manual.notes || "")}</textarea>
          <div class="toolbar"><button onclick="saveManual('${escapeAttr(record.session.platform_type_id)}','${escapeAttr(record.effect_id)}')">保存人工评分</button></div>
        </div>
        <div class="block">
          <h2>回复内容</h2>
          <pre>${escapeHtml(reply.reply_text || "")}</pre>
        </div>
        <div class="block">
          <h2>后续消息</h2>
          <pre>${escapeHtml(followups.map((m, i) => `${i + 1}. ${m.is_target_user ? "[目标]" : "[其他]"} ${m.visible_text || m.plain_text || ""}`).join("\n\n") || "暂无")}</pre>
        </div>
        <div class="block">
          <h2>完整 JSON</h2>
          <pre>${escapeHtml(JSON.stringify(record, null, 2))}</pre>
        </div>
      `;
    }

    async function saveManual(chatId, effectId) {
      const payload = {
        chat_id: chatId,
        effect_id: effectId,
        manual_score: document.getElementById("manualScore").value,
        manual_label: document.getElementById("manualLabel").value,
        evaluator: document.getElementById("evaluator").value,
        notes: document.getElementById("manualNotes").value,
      };
      try {
        await api("/api/annotations", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify(payload),
        });
        await reloadAll();
        await loadDetail(chatId, effectId);
      } catch (err) {
        alert(err.message);
      }
    }

    function fmt(v) {
      return v === null || v === undefined || v === "" ? "N/A" : Number(v).toFixed(2);
    }
    function escapeHtml(value) {
      return String(value ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
    }
    function escapeAttr(value) {
      return escapeHtml(value).replace(/`/g, "&#96;");
    }
    reloadAll();
  </script>
</body>
</html>
"""


INDEX_HTML_V2 = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Maisaka 回复效果评分预览</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f7f7f4;
      --panel: #ffffff;
      --line: #deded7;
      --text: #202124;
      --muted: #686b70;
      --accent: #0f766e;
      --accent-soft: #eef5f4;
      --danger: #b42318;
      --warn: #b7791f;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
      background: var(--bg);
      color: var(--text);
    }
    header {
      height: 56px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 0 18px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
    }
    h1 { font-size: 18px; margin: 0; }
    main {
      display: grid;
      grid-template-columns: 280px minmax(420px, 1fr) 460px;
      height: calc(100vh - 56px);
      min-height: 560px;
    }
    aside, section {
      overflow: auto;
      border-right: 1px solid var(--line);
      background: var(--panel);
    }
    .sidebar { padding: 14px; }
    .content { padding: 14px; background: var(--bg); }
    .detail { padding: 14px; border-right: none; }
    .toolbar {
      display: flex;
      gap: 8px;
      align-items: center;
      margin-bottom: 12px;
      flex-wrap: wrap;
    }
    .header-tools { margin-bottom: 0; justify-content: flex-end; }
    input, select, textarea, button {
      font: inherit;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--text);
    }
    input, select { height: 34px; padding: 0 9px; }
    textarea { width: 100%; min-height: 86px; padding: 8px; resize: vertical; }
    button {
      height: 34px;
      padding: 0 12px;
      cursor: pointer;
      background: var(--accent);
      color: white;
      border-color: var(--accent);
    }
    button.secondary {
      background: white;
      color: var(--text);
      border-color: var(--line);
    }
    button.tab-button {
      background: white;
      color: var(--text);
      border-color: var(--line);
    }
    button.tab-button.active {
      background: var(--accent);
      color: white;
      border-color: var(--accent);
    }
    button.score-button {
      width: 44px;
      height: 44px;
      border-radius: 8px;
      font-weight: 700;
      background: white;
      color: var(--text);
      border-color: var(--line);
    }
    button.score-button.active {
      background: var(--accent);
      color: white;
      border-color: var(--accent);
    }
    .hidden { display: none; }
    .chat-item, .record-card {
      border: 1px solid var(--line);
      background: #fff;
      border-radius: 8px;
      padding: 10px;
      margin-bottom: 10px;
      cursor: pointer;
    }
    .chat-item.active, .record-card.active {
      border-color: var(--accent);
      box-shadow: 0 0 0 2px rgba(15, 118, 110, 0.14);
    }
    .chat-id, .record-title { font-weight: 650; word-break: break-all; }
    .meta { color: var(--muted); font-size: 12px; line-height: 1.6; }
    .metrics { display: flex; gap: 8px; flex-wrap: wrap; margin: 8px 0; }
    .pill {
      display: inline-flex;
      align-items: center;
      min-height: 24px;
      padding: 2px 8px;
      border-radius: 999px;
      background: var(--accent-soft);
      color: #155e57;
      font-size: 12px;
      border: 1px solid #d1e7e3;
    }
    .pill.pending { background: #fff7ed; color: var(--warn); border-color: #fed7aa; }
    .pill.bad { background: #fef3f2; color: var(--danger); border-color: #fecdca; }
    .preview {
      white-space: pre-wrap;
      line-height: 1.55;
      margin: 8px 0 0;
    }
    .block {
      border: 1px solid var(--line);
      background: #fff;
      border-radius: 8px;
      padding: 12px;
      margin-bottom: 12px;
    }
    .block h2 { font-size: 15px; margin: 0 0 10px; }
    .score-grid {
      display: grid;
      grid-template-columns: repeat(5, 44px);
      gap: 8px;
      margin: 8px 0 12px;
    }
    .kv {
      display: grid;
      grid-template-columns: 92px minmax(0, 1fr);
      gap: 6px 10px;
      font-size: 13px;
      line-height: 1.6;
    }
    .kv div:nth-child(odd) { color: var(--muted); }
    pre {
      white-space: pre-wrap;
      word-break: break-word;
      background: #f5f5f2;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 10px;
      max-height: 300px;
      overflow: auto;
    }
    label { display: block; font-size: 13px; color: var(--muted); margin: 10px 0 4px; }
    .empty { color: var(--muted); padding: 18px; text-align: center; }
  </style>
</head>
<body>
  <header>
    <h1>Maisaka 回复效果评分预览</h1>
    <div class="toolbar header-tools">
      <button id="browseTab" class="tab-button active" onclick="setMode('browse')">浏览</button>
      <button id="rateTab" class="tab-button" onclick="setMode('rate')">逐条评分</button>
      <button class="secondary" onclick="reloadAll()">刷新</button>
    </div>
  </header>
  <main>
    <aside class="sidebar">
      <div class="toolbar">
        <input id="chatSearch" placeholder="筛选聊天流" oninput="renderChats()" />
      </div>
      <div id="chatList"></div>
    </aside>
    <section class="content">
      <div id="browsePanel">
        <div class="toolbar">
          <select id="statusFilter" onchange="loadRecords()">
            <option value="">全部状态</option>
            <option value="finalized">已完成</option>
            <option value="pending">观察中</option>
          </select>
          <select id="annotationFilter" onchange="loadRecords()">
            <option value="">全部标注</option>
            <option value="yes">已人工评分</option>
            <option value="no">未人工评分</option>
          </select>
        </div>
        <div id="recordList"></div>
      </div>
      <div id="ratingPanel" class="hidden">
        <div class="toolbar">
          <button onclick="loadRatingQueue()">刷新队列</button>
          <button class="secondary" onclick="moveRating(-1)">上一条</button>
          <button class="secondary" onclick="moveRating(1)">下一条</button>
        </div>
        <div id="ratingQueueInfo" class="meta"></div>
        <div id="ratingQueueList"></div>
      </div>
    </section>
    <section class="detail">
      <div id="detailPane" class="empty">选择一条记录查看详情</div>
    </section>
  </main>
  <script>
    let chats = [];
    let records = [];
    let ratingQueue = [];
    let ratingIndex = 0;
    let selectedChat = "";
    let selectedEffect = "";
    let activeMode = "browse";
    let selectedFivePointScore = 0;
    let currentTargetMessageId = "";

    async function api(path, options) {
      const res = await fetch(path, options);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "请求失败");
      return data;
    }

    async function reloadAll() {
      const data = await api("/api/chats");
      chats = data.chats || [];
      if (!selectedChat && chats.length) selectedChat = chats[0].chat_id;
      renderChats();
      if (activeMode === "rate") {
        await loadRatingQueue();
      } else {
        await loadRecords();
      }
    }

    function setMode(mode) {
      activeMode = mode;
      document.getElementById("browseTab").classList.toggle("active", mode === "browse");
      document.getElementById("rateTab").classList.toggle("active", mode === "rate");
      document.getElementById("browsePanel").classList.toggle("hidden", mode !== "browse");
      document.getElementById("ratingPanel").classList.toggle("hidden", mode !== "rate");
      if (mode === "rate") {
        loadRatingQueue();
      } else {
        loadRecords();
      }
    }

    function renderChats() {
      const q = document.getElementById("chatSearch").value.trim().toLowerCase();
      const list = document.getElementById("chatList");
      const shown = chats.filter(c => !q || c.chat_id.toLowerCase().includes(q));
      list.innerHTML = shown.map(chat => `
        <div class="chat-item ${chat.chat_id === selectedChat ? "active" : ""}"
          onclick="selectChat('${escapeAttr(chat.chat_id)}')">
          <div class="chat-id">${escapeHtml(chat.chat_id)}</div>
          <div class="meta">
            记录 ${chat.record_count} | 完成 ${chat.finalized_count}
            | 观察中 ${chat.pending_count} | 人工 ${chat.annotated_count}
          </div>
        </div>
      `).join("") || `<div class="empty">没有聊天流</div>`;
    }

    async function selectChat(chatId) {
      selectedChat = chatId;
      selectedEffect = "";
      renderChats();
      document.getElementById("detailPane").innerHTML = "选择一条记录查看详情";
      if (activeMode === "rate") {
        await loadRatingQueue();
      } else {
        await loadRecords();
      }
    }

    async function loadRecords() {
      const params = new URLSearchParams();
      if (selectedChat) params.set("chat_id", selectedChat);
      const status = document.getElementById("statusFilter").value;
      const annotated = document.getElementById("annotationFilter").value;
      if (status) params.set("status", status);
      if (annotated) params.set("annotated", annotated);
      const data = await api(`/api/records?${params.toString()}`);
      records = data.records || [];
      renderRecords();
    }

    function renderRecords() {
      const list = document.getElementById("recordList");
      list.innerHTML = records.map(record => {
        const asi = scoreText(record.asi);
        const manual = manualScoreText(record.manual);
        const target = userName(record.target_user);
        return `
          <div class="record-card ${record.effect_id === selectedEffect ? "active" : ""}"
            onclick="loadDetail('${escapeAttr(record.chat_id)}','${escapeAttr(record.effect_id)}')">
            <div class="record-title">${escapeHtml(record.created_at || record.file_name)}</div>
            <div class="metrics">
              <span class="pill ${record.status === "pending" ? "pending" : ""}">
                ${escapeHtml(record.status || "unknown")}
              </span>
              <span class="pill">ASI ${asi}</span>
              <span class="pill">人工 ${manual}</span>
              <span class="pill">${escapeHtml(record.finalize_reason || "未结算")}</span>
            </div>
            <div class="meta">目标用户：${escapeHtml(target)} | 后续 ${record.followup_count}</div>
            <div class="preview">${escapeHtml(record.reply_preview || "")}</div>
          </div>
        `;
      }).join("") || `<div class="empty">没有记录</div>`;
    }

    async function loadDetail(chatId, effectId) {
      selectedChat = chatId;
      selectedEffect = effectId;
      renderChats();
      renderRecords();
      const data = await api(`/api/record?chat_id=${encodeURIComponent(chatId)}&effect_id=${encodeURIComponent(effectId)}`);
      renderDetail(data.record);
    }

    function renderDetail(record) {
      const scores = record.scores || {};
      const reply = record.reply || {};
      const manual = record._manual || {};
      const followups = record.followup_messages || [];
      document.getElementById("detailPane").innerHTML = `
        <div class="block">
          <h2>自动评分</h2>
          <div class="metrics">
            <span class="pill">ASI ${fmt(scores.asi)}</span>
            <span class="pill">行为 ${fmt(scores.behavior_score)}</span>
            <span class="pill">感知 ${fmt(scores.relational_score)}</span>
            <span class="pill">摩擦 ${fmt(scores.friction_score)}</span>
          </div>
          <div class="meta">完成原因：${escapeHtml(record.finalize_reason || "未完成")}</div>
          <div class="meta">${escapeHtml(record.confidence_note || "")}</div>
        </div>
        <div class="block">
          <h2>人工评分</h2>
          <label>人工分数 0-100</label>
          <input id="manualScore" type="number" min="0" max="100" step="1"
            value="${manual.manual_score ?? ""}" />
          <label>标签</label>
          <select id="manualLabel">
            ${["", "good", "neutral", "bad", "uncertain"].map(v => `
              <option value="${v}" ${manual.manual_label === v ? "selected" : ""}>
                ${v || "未选择"}
              </option>
            `).join("")}
          </select>
          <label>评价人</label>
          <input id="evaluator" value="${escapeAttr(manual.evaluator || "manual")}" />
          <label>备注</label>
          <textarea id="manualNotes">${escapeHtml(manual.notes || "")}</textarea>
          <div class="toolbar">
            <button onclick="saveManual('${escapeAttr(record.session.platform_type_id)}','${escapeAttr(record.effect_id)}')">
              保存人工评分
            </button>
          </div>
        </div>
        <div class="block">
          <h2>回复内容</h2>
          <pre>${escapeHtml(reply.reply_text || "")}</pre>
        </div>
        <div class="block">
          <h2>后续消息</h2>
          <pre>${escapeHtml(formatFollowups(followups))}</pre>
        </div>
        <div class="block">
          <h2>完整 JSON</h2>
          <pre>${escapeHtml(JSON.stringify(record, null, 2))}</pre>
        </div>
      `;
    }

    async function loadRatingQueue() {
      const params = new URLSearchParams();
      if (selectedChat) params.set("chat_id", selectedChat);
      params.set("status", "finalized");
      params.set("annotated", "no");
      const data = await api(`/api/records?${params.toString()}`);
      ratingQueue = data.records || [];
      ratingIndex = 0;
      renderRatingQueue();
      if (ratingQueue.length) {
        await loadRatingDetail(0);
      } else {
        document.getElementById("detailPane").innerHTML = `
          <div class="empty">当前聊天流没有待人工评分的已完成记录</div>
        `;
      }
    }

    function renderRatingQueue() {
      const info = document.getElementById("ratingQueueInfo");
      const list = document.getElementById("ratingQueueList");
      info.textContent = selectedChat
        ? `当前聊天流：${selectedChat}，待评分 ${ratingQueue.length} 条`
        : `全部聊天流待评分 ${ratingQueue.length} 条`;
      list.innerHTML = ratingQueue.map((record, index) => `
        <div class="record-card ${index === ratingIndex ? "active" : ""}"
          onclick="loadRatingDetail(${index})">
          <div class="record-title">${escapeHtml(record.created_at || record.file_name)}</div>
          <div class="metrics">
            <span class="pill">ASI ${scoreText(record.asi)}</span>
            <span class="pill">${escapeHtml(record.chat_id)}</span>
          </div>
          <div class="preview">${escapeHtml(record.reply_preview || "")}</div>
        </div>
      `).join("") || `<div class="empty">没有待评分记录</div>`;
    }

    async function loadRatingDetail(index) {
      if (!ratingQueue.length) return;
      ratingIndex = Math.max(0, Math.min(index, ratingQueue.length - 1));
      const item = ratingQueue[ratingIndex];
      selectedChat = item.chat_id;
      selectedEffect = item.effect_id;
      selectedFivePointScore = 0;
      renderChats();
      renderRatingQueue();
      const data = await api(`/api/record?chat_id=${encodeURIComponent(item.chat_id)}&effect_id=${encodeURIComponent(item.effect_id)}`);
      renderRatingDetail(data.record);
    }

    function moveRating(offset) {
      if (!ratingQueue.length) return;
      loadRatingDetail(ratingIndex + offset);
    }

    function renderRatingDetail(record) {
      const scores = record.scores || {};
      const reply = record.reply || {};
      const target = record.target_user || {};
      const followups = record.followup_messages || [];
      const context = record.context_snapshot || {};
      document.getElementById("detailPane").innerHTML = `
        <div class="block">
          <h2>逐条评分</h2>
          <div class="kv">
            <div>聊天流</div><div>${escapeHtml(record.session?.platform_type_id || "")}</div>
            <div>记录 ID</div><div>${escapeHtml(record.effect_id || "")}</div>
            <div>创建时间</div><div>${escapeHtml(record.created_at || "")}</div>
            <div>完成原因</div><div>${escapeHtml(record.finalize_reason || "")}</div>
            <div>目标用户</div><div>${escapeHtml(userName(target))}</div>
          </div>
          <div class="metrics">
            <span class="pill">ASI ${fmt(scores.asi)}</span>
            <span class="pill">行为 ${fmt(scores.behavior_score)}</span>
            <span class="pill">感知 ${fmt(scores.relational_score)}</span>
            <span class="pill">摩擦 ${fmt(scores.friction_score)}</span>
          </div>
        </div>
        <div class="block">
          <h2>上下文</h2>
          <pre>${escapeHtml(JSON.stringify(context, null, 2))}</pre>
        </div>
        <div class="block">
          <h2>Bot 回复</h2>
          <pre>${escapeHtml(reply.reply_text || "")}</pre>
        </div>
        <div class="block">
          <h2>后续消息</h2>
          <pre>${escapeHtml(formatFollowups(followups))}</pre>
        </div>
        <div class="block">
          <h2>人工五点评分</h2>
          <div class="meta">1=很差，2=较差，3=一般，4=较好，5=很好</div>
          <div class="score-grid">
            ${[1, 2, 3, 4, 5].map(score => `
              <button class="score-button" id="scoreButton${score}" onclick="selectFivePointScore(${score})">
                ${score}
              </button>
            `).join("")}
          </div>
          <label>标签</label>
          <select id="ratingManualLabel">
            <option value="">未选择</option>
            <option value="good">good</option>
            <option value="neutral">neutral</option>
            <option value="bad">bad</option>
            <option value="uncertain">uncertain</option>
          </select>
          <label>评价人</label>
          <input id="ratingEvaluator" value="manual" />
          <label>备注</label>
          <textarea id="ratingNotes"></textarea>
          <div class="toolbar">
            <button onclick="saveFivePointManual('${escapeAttr(record.session.platform_type_id)}','${escapeAttr(record.effect_id)}')">
              保存并下一条
            </button>
          </div>
        </div>
      `;
    }

    function selectFivePointScore(score) {
      selectedFivePointScore = score;
      [1, 2, 3, 4, 5].forEach(item => {
        const button = document.getElementById(`scoreButton${item}`);
        if (button) button.classList.toggle("active", item === score);
      });
    }

    async function saveFivePointManual(chatId, effectId) {
      if (!selectedFivePointScore) {
        alert("请先选择 1-5 的人工评分");
        return;
      }
      const payload = {
        chat_id: chatId,
        effect_id: effectId,
        manual_score_5: selectedFivePointScore,
        manual_label: document.getElementById("ratingManualLabel").value,
        evaluator: document.getElementById("ratingEvaluator").value,
        notes: document.getElementById("ratingNotes").value,
      };
      try {
        await api("/api/annotations", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify(payload),
        });
        await reloadAll();
      } catch (err) {
        alert(err.message);
      }
    }

    async function saveManual(chatId, effectId) {
      const payload = {
        chat_id: chatId,
        effect_id: effectId,
        manual_score: document.getElementById("manualScore").value,
        manual_label: document.getElementById("manualLabel").value,
        evaluator: document.getElementById("evaluator").value,
        notes: document.getElementById("manualNotes").value,
      };
      try {
        await api("/api/annotations", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify(payload),
        });
        await reloadAll();
        await loadDetail(chatId, effectId);
      } catch (err) {
        alert(err.message);
      }
    }

    function manualScoreText(manual) {
      if (!manual) return "未评";
      if (manual.manual_score_5) return `${manual.manual_score_5}/5`;
      return scoreText(manual.manual_score);
    }

    function userName(user) {
      if (!user) return "未知";
      return user.cardname || user.nickname || user.user_id || "未知";
    }

    function formatFollowups(followups) {
      if (!followups || !followups.length) return "暂无";
      return followups.map((message, index) => {
        const tag = message.is_target_user ? "[目标]" : "[其他]";
        const text = message.visible_text || message.plain_text || "";
        return `${index + 1}. ${tag} ${text}`;
      }).join("\n\n");
    }

    function scoreText(v) {
      return v === null || v === undefined || v === "" ? "N/A" : Number(v).toFixed(1);
    }

    function fmt(v) {
      return v === null || v === undefined || v === "" ? "N/A" : Number(v).toFixed(2);
    }

    function escapeHtml(value) {
      return String(value ?? "").replace(/[&<>"']/g, c => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      }[c]));
    }

    function escapeAttr(value) {
      return escapeHtml(value).replace(/`/g, "&#96;");
    }

    reloadAll();
  </script>
</body>
</html>
"""

INDEX_HTML_V3 = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Maisaka 回复效果评分预览</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f7f7f4;
      --panel: #ffffff;
      --line: #deded7;
      --text: #202124;
      --muted: #686b70;
      --accent: #0f766e;
      --accent-soft: #eef5f4;
      --danger: #b42318;
      --warn: #b7791f;
      --self: #e9f7f3;
      --other: #ffffff;
      --tool: #f3f1ea;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
      background: var(--bg);
      color: var(--text);
    }
    header {
      height: 56px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 0 16px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
    }
    h1 { font-size: 18px; margin: 0; }
    main {
      display: grid;
      grid-template-columns: 220px 340px minmax(520px, 1fr);
      height: calc(100vh - 56px);
      min-height: 560px;
    }
    body.rate-mode main {
      grid-template-columns: 320px minmax(0, 1fr);
    }
    body.rate-mode .sidebar { display: none; }
    body.rate-mode .content { border-right: 1px solid var(--line); }
    body.rate-mode .detail { display: block; }
    body.rate-drawer-collapsed main { grid-template-columns: 44px minmax(0, 1fr); }
    body.rate-drawer-collapsed #ratingPanel > :not(.drawer-toggle-row) { display: none; }
    aside, section {
      overflow: auto;
      border-right: 1px solid var(--line);
      background: var(--panel);
    }
    .sidebar { padding: 12px; }
    .content { padding: 12px; background: var(--bg); }
    .detail { padding: 14px; border-right: none; }
    .toolbar {
      display: flex;
      gap: 8px;
      align-items: center;
      margin-bottom: 12px;
      flex-wrap: wrap;
    }
    .header-tools { margin-bottom: 0; justify-content: flex-end; }
    input, select, textarea, button {
      font: inherit;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--text);
    }
    input, select { height: 34px; padding: 0 9px; max-width: 100%; }
    textarea { width: 100%; min-height: 86px; padding: 8px; resize: vertical; }
    button {
      height: 34px;
      padding: 0 12px;
      cursor: pointer;
      background: var(--accent);
      color: white;
      border-color: var(--accent);
      white-space: nowrap;
    }
    button.secondary,
    button.tab-button {
      background: white;
      color: var(--text);
      border-color: var(--line);
    }
    button.tab-button.active {
      background: var(--accent);
      color: white;
      border-color: var(--accent);
    }
    button.icon-button {
      width: 34px;
      padding: 0;
      font-weight: 700;
    }
    button.score-button {
      width: 44px;
      height: 44px;
      border-radius: 8px;
      font-weight: 700;
      background: white;
      color: var(--text);
      border-color: var(--line);
    }
    button.score-button.active {
      background: var(--accent);
      color: white;
      border-color: var(--accent);
    }
    .hidden { display: none; }
    .chat-item, .record-card {
      border: 1px solid var(--line);
      background: #fff;
      border-radius: 8px;
      padding: 10px;
      margin-bottom: 10px;
      cursor: pointer;
    }
    .chat-item.active, .record-card.active {
      border-color: var(--accent);
      box-shadow: 0 0 0 2px rgba(15, 118, 110, 0.14);
    }
    .chat-id, .record-title { font-weight: 650; word-break: break-all; }
    .meta { color: var(--muted); font-size: 12px; line-height: 1.6; }
    .metrics { display: flex; gap: 8px; flex-wrap: wrap; margin: 8px 0; }
    .pill {
      display: inline-flex;
      align-items: center;
      min-height: 24px;
      padding: 2px 8px;
      border-radius: 999px;
      background: var(--accent-soft);
      color: #155e57;
      font-size: 12px;
      border: 1px solid #d1e7e3;
    }
    .pill.pending { background: #fff7ed; color: var(--warn); border-color: #fed7aa; }
    .pill.bad { background: #fef3f2; color: var(--danger); border-color: #fecdca; }
    .preview {
      white-space: pre-wrap;
      line-height: 1.55;
      margin: 8px 0 0;
    }
    .block {
      border: 1px solid var(--line);
      background: #fff;
      border-radius: 8px;
      padding: 12px;
      margin-bottom: 12px;
    }
    .block h2 { font-size: 15px; margin: 0 0 10px; }
    .score-grid {
      display: grid;
      grid-template-columns: repeat(5, 44px);
      gap: 8px;
      margin: 8px 0 12px;
    }
    .kv {
      display: grid;
      grid-template-columns: 92px minmax(0, 1fr);
      gap: 6px 10px;
      font-size: 13px;
      line-height: 1.6;
    }
    .kv div:nth-child(odd) { color: var(--muted); }
    .rate-top {
      position: sticky;
      top: -14px;
      z-index: 2;
      margin: -14px -14px 12px;
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.96);
    }
    .rate-top select { min-width: 260px; }
    .message-card {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 8px 10px;
      background: var(--other);
      max-width: 78%;
    }
    .message-row {
      display: flex;
      justify-content: flex-start;
      margin-bottom: 7px;
    }
    .message-row.bot {
      justify-content: flex-end;
    }
    .message-row.bot .message-card {
      background: var(--self);
      border-color: #cde9e1;
    }
    .message-row.user .message-card {
      background: var(--other);
    }
    .message-card.assistant,
    .message-card.guided_reply { background: var(--self); border-color: #cde9e1; }
    .message-card.tool,
    .message-card.continue { background: var(--tool); }
    .message-card.target { border-color: var(--accent); box-shadow: inset 3px 0 0 var(--accent); }
    .message-head {
      display: flex;
      justify-content: space-between;
      gap: 8px;
      margin-bottom: 4px;
      color: var(--muted);
      font-size: 12px;
    }
    .message-name { font-weight: 650; color: var(--text); }
    .message-text { white-space: pre-wrap; word-break: break-word; line-height: 1.45; }
    .message-attachments {
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
      margin-top: 6px;
    }
    .message-image {
      display: block;
      max-width: 180px;
      max-height: 180px;
      border-radius: 6px;
      border: 1px solid var(--line);
      object-fit: contain;
      background: #fff;
    }
    .message-image-caption {
      max-width: 180px;
      color: var(--muted);
      font-size: 11px;
      line-height: 1.35;
      margin-top: 3px;
      word-break: break-word;
    }
    .reply-focus {
      border: 1px solid #cde9e1;
      background: var(--self);
      border-radius: 8px;
      padding: 14px;
      margin-bottom: 12px;
      font-size: 16px;
      line-height: 1.65;
      white-space: pre-wrap;
    }
    pre {
      white-space: pre-wrap;
      word-break: break-word;
      background: #f5f5f2;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 10px;
      max-height: 300px;
      overflow: auto;
    }
    label { display: block; font-size: 13px; color: var(--muted); margin: 10px 0 4px; }
    .empty { color: var(--muted); padding: 18px; text-align: center; }
  </style>
</head>
<body>
  <header>
    <h1>Maisaka 回复效果评分预览</h1>
    <div class="toolbar header-tools">
      <button id="browseTab" class="tab-button active" onclick="setMode('browse')">浏览</button>
      <button id="rateTab" class="tab-button" onclick="setMode('rate')">逐条评分</button>
      <button class="secondary" onclick="reloadAll()">刷新</button>
    </div>
  </header>
  <main>
    <aside class="sidebar">
      <div class="toolbar">
        <input id="chatSearch" placeholder="筛选聊天流" oninput="renderChats()" />
      </div>
      <div id="chatList"></div>
    </aside>
    <section class="content">
      <div id="browsePanel">
        <div class="toolbar">
          <select id="statusFilter" onchange="loadRecords()">
            <option value="">全部状态</option>
            <option value="finalized">已完成</option>
            <option value="pending">观察中</option>
          </select>
          <select id="annotationFilter" onchange="loadRecords()">
            <option value="">全部标注</option>
            <option value="yes">已人工评分</option>
            <option value="no">未人工评分</option>
          </select>
        </div>
        <div id="recordList"></div>
      </div>
      <div id="ratingPanel" class="hidden">
        <div class="drawer-toggle-row toolbar">
          <button class="secondary icon-button" onclick="toggleRatingDrawer()">☰</button>
          <button onclick="loadRatingQueue()">刷新</button>
        </div>
        <div class="toolbar">
          <button class="secondary" onclick="moveRating(-1)">上一条</button>
          <button class="secondary" onclick="moveRating(1)">下一条</button>
        </div>
        <div id="ratingQueueInfo" class="meta"></div>
        <div id="ratingQueueList"></div>
      </div>
    </section>
    <section class="detail">
      <div id="detailPane" class="empty">选择一条记录查看详情</div>
    </section>
  </main>
  <script>
    let chats = [];
    let records = [];
    let ratingQueue = [];
    let ratingIndex = 0;
    let selectedChat = "";
    let selectedEffect = "";
    let activeMode = "browse";
    let selectedFivePointScore = 0;

    async function api(path, options) {
      const res = await fetch(path, options);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "请求失败");
      return data;
    }

    async function reloadAll() {
      const data = await api("/api/chats");
      chats = data.chats || [];
      if (!selectedChat && chats.length) selectedChat = chats[0].chat_id;
      renderChats();
      renderRateChatSelect();
      if (activeMode === "rate") {
        await loadRatingQueue();
      } else {
        await loadRecords();
      }
    }

    function setMode(mode) {
      activeMode = mode;
      document.body.classList.toggle("rate-mode", mode === "rate");
      document.getElementById("browseTab").classList.toggle("active", mode === "browse");
      document.getElementById("rateTab").classList.toggle("active", mode === "rate");
      document.getElementById("browsePanel").classList.toggle("hidden", mode !== "browse");
      document.getElementById("ratingPanel").classList.toggle("hidden", mode !== "rate");
      if (mode === "rate") {
        loadRatingQueue();
      } else {
        document.body.classList.remove("rate-drawer-collapsed");
        loadRecords();
      }
    }

    function toggleRatingDrawer() {
      document.body.classList.toggle("rate-drawer-collapsed");
    }

    function renderChats() {
      const q = document.getElementById("chatSearch").value.trim().toLowerCase();
      const list = document.getElementById("chatList");
      const shown = chats.filter(c => !q || c.chat_id.toLowerCase().includes(q));
      list.innerHTML = shown.map(chat => `
        <div class="chat-item ${chat.chat_id === selectedChat ? "active" : ""}"
          onclick="selectChat('${escapeAttr(chat.chat_id)}')">
          <div class="chat-id">${escapeHtml(chat.chat_id)}</div>
          <div class="meta">记录 ${chat.record_count} | 完成 ${chat.finalized_count} | 人工 ${chat.annotated_count}</div>
        </div>
      `).join("") || `<div class="empty">没有聊天流</div>`;
    }

    function renderRateChatSelect() {
      const select = document.getElementById("rateChatSelect");
      if (!select) return;
      select.innerHTML = chats.map(chat => `
        <option value="${escapeAttr(chat.chat_id)}" ${chat.chat_id === selectedChat ? "selected" : ""}>
          ${escapeHtml(chat.chat_id)} (${chat.annotated_count}/${chat.record_count})
        </option>
      `).join("");
    }

    async function selectChat(chatId) {
      selectedChat = chatId;
      selectedEffect = "";
      renderChats();
      renderRateChatSelect();
      document.getElementById("detailPane").innerHTML = "选择一条记录查看详情";
      if (activeMode === "rate") {
        await loadRatingQueue();
      } else {
        await loadRecords();
      }
    }

    async function selectRateChat() {
      const select = document.getElementById("rateChatSelect");
      if (!select) return;
      await selectChat(select.value);
    }

    async function loadRecords() {
      const params = new URLSearchParams();
      if (selectedChat) params.set("chat_id", selectedChat);
      const status = document.getElementById("statusFilter").value;
      const annotated = document.getElementById("annotationFilter").value;
      if (status) params.set("status", status);
      if (annotated) params.set("annotated", annotated);
      const data = await api(`/api/records?${params.toString()}`);
      records = data.records || [];
      renderRecords();
    }

    function renderRecords() {
      const list = document.getElementById("recordList");
      list.innerHTML = records.map(record => {
        const asi = scoreText(record.asi);
        const manual = manualFivePointText(record.manual);
        const target = userName(record.target_user);
        return `
          <div class="record-card ${record.effect_id === selectedEffect ? "active" : ""}"
            onclick="loadDetail('${escapeAttr(record.chat_id)}','${escapeAttr(record.effect_id)}')">
            <div class="record-title">${escapeHtml(record.created_at || record.file_name)}</div>
            <div class="metrics">
              <span class="pill ${record.status === "pending" ? "pending" : ""}">${escapeHtml(record.status || "unknown")}</span>
              <span class="pill">ASI ${asi}</span>
              <span class="pill">人工 ${manual}</span>
              <span class="pill">${escapeHtml(record.finalize_reason || "未结算")}</span>
            </div>
            <div class="meta">目标用户：${escapeHtml(target)} | 后续 ${record.followup_count}</div>
            <div class="preview">${escapeHtml(record.reply_preview || "")}</div>
          </div>
        `;
      }).join("") || `<div class="empty">没有记录</div>`;
    }

    async function loadDetail(chatId, effectId) {
      selectedChat = chatId;
      selectedEffect = effectId;
      renderChats();
      renderRecords();
      const data = await api(`/api/record?chat_id=${encodeURIComponent(chatId)}&effect_id=${encodeURIComponent(effectId)}`);
      renderDetail(data.record);
    }

    function renderDetail(record) {
      const scores = record.scores || {};
      const reply = record.reply || {};
      const manual = record._manual || {};
      const followups = record.followup_messages || [];
      selectedFivePointScore = Number(manual.manual_score_5 || score100ToFive(manual.manual_score) || 0);
      document.getElementById("detailPane").innerHTML = `
        <div class="block">
          <h2>自动评分</h2>
          <div class="metrics">
            <span class="pill">ASI ${fmt(scores.asi)}</span>
            <span class="pill">行为 ${fmt(scores.behavior_score)}</span>
            <span class="pill">感知 ${fmt(scores.relational_score)}</span>
            <span class="pill">摩擦 ${fmt(scores.friction_score)}</span>
          </div>
          <div class="meta">完成原因：${escapeHtml(record.finalize_reason || "未完成")}</div>
          <div class="meta">${escapeHtml(record.confidence_note || "")}</div>
        </div>
        <div class="block">
          <h2>人工五点评分</h2>
          <div class="score-grid">
            ${[1, 2, 3, 4, 5].map(score => `
              <button class="score-button ${score === selectedFivePointScore ? "active" : ""}"
                id="scoreButton${score}" onclick="selectFivePointScore(${score})">${score}</button>
            `).join("")}
          </div>
          <label>评价人</label>
          <input id="evaluator" value="${escapeAttr(manual.evaluator || "manual")}" />
          <label>备注</label>
          <textarea id="manualNotes">${escapeHtml(manual.notes || "")}</textarea>
          <div class="toolbar">
            <button onclick="saveFivePointManual('${escapeAttr(record.session.platform_type_id)}','${escapeAttr(record.effect_id)}', false)">
              保存人工评分
            </button>
          </div>
        </div>
        <div class="block">
          <h2>回复内容</h2>
          ${renderBotReplyCard(reply.reply_text || "")}
        </div>
        <div class="block">
          <h2>后续消息</h2>
          ${renderFollowupCards(followups)}
        </div>
        <div class="block">
          <h2>完整 JSON</h2>
          <pre>${escapeHtml(JSON.stringify(record, null, 2))}</pre>
        </div>
      `;
    }

    async function loadRatingQueue() {
      const params = new URLSearchParams();
      if (selectedChat) params.set("chat_id", selectedChat);
      params.set("status", "finalized");
      params.set("annotated", "no");
      const data = await api(`/api/records?${params.toString()}`);
      ratingQueue = data.records || [];
      ratingIndex = 0;
      renderRatingQueue();
      if (ratingQueue.length) {
        await loadRatingDetail(0);
      } else {
        renderEmptyRatingDetail();
      }
    }

    function renderRatingQueue() {
      const info = document.getElementById("ratingQueueInfo");
      const list = document.getElementById("ratingQueueList");
      info.textContent = selectedChat ? `当前聊天流待评分 ${ratingQueue.length} 条` : `全部聊天流待评分 ${ratingQueue.length} 条`;
      list.innerHTML = ratingQueue.map((record, index) => `
        <div class="record-card ${index === ratingIndex ? "active" : ""}" onclick="loadRatingDetail(${index})">
          <div class="record-title">${escapeHtml(shortTime(record.created_at || record.file_name))}</div>
          <div class="metrics">
            <span class="pill">ASI ${scoreText(record.asi)}</span>
            <span class="pill">${escapeHtml(manualFivePointText(record.manual))}</span>
          </div>
          <div class="preview">${escapeHtml(record.reply_preview || "")}</div>
        </div>
      `).join("") || `<div class="empty">没有待评分记录</div>`;
    }

    async function loadRatingDetail(index) {
      if (!ratingQueue.length) return;
      ratingIndex = Math.max(0, Math.min(index, ratingQueue.length - 1));
      const item = ratingQueue[ratingIndex];
      selectedChat = item.chat_id;
      selectedEffect = item.effect_id;
      selectedFivePointScore = 0;
      renderChats();
      renderRatingQueue();
      const data = await api(`/api/record?chat_id=${encodeURIComponent(item.chat_id)}&effect_id=${encodeURIComponent(item.effect_id)}`);
      renderRatingDetail(data.record);
    }

    function moveRating(offset) {
      if (!ratingQueue.length) return;
      loadRatingDetail(ratingIndex + offset);
    }

    function renderEmptyRatingDetail() {
      document.getElementById("detailPane").innerHTML = `
        <div class="rate-top toolbar">
          <label>聊天流</label>
          <select id="rateChatSelect" onchange="selectRateChat()"></select>
        </div>
        <div class="empty">当前聊天流没有待人工评分的已完成记录</div>
      `;
      renderRateChatSelect();
    }

    function renderRatingDetail(record) {
      const scores = record.scores || {};
      const reply = record.reply || {};
      const target = record.target_user || {};
      const followups = record.followup_messages || [];
      currentTargetMessageId = String(reply.target_message_id || "");
      const context = normalizeContextMessages(record.context_snapshot || []);
      document.getElementById("detailPane").innerHTML = `
        <div class="rate-top">
          <div class="toolbar">
            <label>聊天流</label>
            <select id="rateChatSelect" onchange="selectRateChat()"></select>
            <button class="secondary" onclick="moveRating(-1)">上一条</button>
            <button class="secondary" onclick="moveRating(1)">下一条</button>
          </div>
          <div class="metrics">
            <span class="pill">第 ${ratingIndex + 1}/${ratingQueue.length} 条</span>
            <span class="pill">ASI ${fmt(scores.asi)}</span>
            <span class="pill">行为 ${fmt(scores.behavior_score)}</span>
            <span class="pill">感知 ${fmt(scores.relational_score)}</span>
            <span class="pill">摩擦 ${fmt(scores.friction_score)}</span>
          </div>
          <div class="meta">
            目标用户：${escapeHtml(userName(target))}
            | 完成原因：${escapeHtml(record.finalize_reason || "")}
            | 记录：${escapeHtml(record.effect_id || "")}
          </div>
        </div>
        <div class="block">
          <h2>上下文</h2>
          ${renderMessageCards(context)}
        </div>
        <div class="block">
          <h2>Bot 回复</h2>
          ${renderBotReplyCard(reply.reply_text || "")}
        </div>
        <div class="block">
          <h2>后续消息</h2>
          ${renderFollowupCards(followups)}
        </div>
        <div class="block">
          <h2>人工五点评分</h2>
          <div class="meta">1=很差，2=较差，3=一般，4=较好，5=很好</div>
          <div class="score-grid">
            ${[1, 2, 3, 4, 5].map(score => `
              <button class="score-button" id="scoreButton${score}" onclick="selectFivePointScore(${score})">${score}</button>
            `).join("")}
          </div>
          <label>评价人</label>
          <input id="ratingEvaluator" value="manual" />
          <label>备注</label>
          <textarea id="ratingNotes"></textarea>
          <div class="toolbar">
            <button onclick="saveFivePointManual('${escapeAttr(record.session.platform_type_id)}','${escapeAttr(record.effect_id)}', true)">
              保存并下一条
            </button>
          </div>
        </div>
      `;
      renderRateChatSelect();
    }

    function selectFivePointScore(score) {
      selectedFivePointScore = score;
      [1, 2, 3, 4, 5].forEach(item => {
        const button = document.getElementById(`scoreButton${item}`);
        if (button) button.classList.toggle("active", item === score);
      });
    }

    async function saveFivePointManual(chatId, effectId, moveNext = true) {
      if (!selectedFivePointScore) {
        alert("请先选择 1-5 的人工评分");
        return;
      }
      const payload = {
        chat_id: chatId,
        effect_id: effectId,
        manual_score_5: selectedFivePointScore,
        manual_label: "",
        evaluator: valueOf("ratingEvaluator") || valueOf("evaluator") || "manual",
        notes: valueOf("ratingNotes") || valueOf("manualNotes"),
      };
      try {
        await api("/api/annotations", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify(payload),
        });
        if (activeMode === "rate" && moveNext) {
          await loadRatingQueue();
        } else {
          await reloadAll();
          await loadDetail(chatId, effectId);
        }
      } catch (err) {
        alert(err.message);
      }
    }

    function normalizeContextMessages(context) {
      const items = Array.isArray(context) ? context : [];
      return items.filter(item => !isToolContextMessage(item)).map((item, index) => {
        const parsed = parseVisibleText(item.text || "");
        return {
          index,
          role: item.role || parsed.role || "message",
          source: item.source || "",
          timestamp: item.timestamp || parsed.time || "",
          name: parsed.name || roleName(item.role, item.source),
          messageId: parsed.messageId || "",
          text: cleanMessageText(parsed.content || item.text || ""),
          attachments: Array.isArray(item.attachments) ? item.attachments : [],
          isTarget: parsed.messageId && String(parsed.messageId) === String(selectedTargetMessageId()),
        };
      });
    }

    function isToolContextMessage(item) {
      const role = String(item.role || "").toLowerCase();
      const source = String(item.source || "").toLowerCase();
      if (role === "assistant") return true;
      if (role === "tool") return true;
      if (source === "continue") return true;
      if (source === "tool" || source.includes("tool")) return true;
      return false;
    }

    function parseVisibleText(text) {
      const value = String(text || "");
      const pattern = /^(?<time>\d{1,2}:\d{2}:\d{2})?(?:\[msg_id:(?<messageId>[^\]]+)\])?(?:\[(?<name>[^\]]+)\])?(?<content>[\s\S]*)$/;
      const match = value.match(pattern);
      if (!match || !match.groups) return { content: value };
      return {
        time: match.groups.time || "",
        messageId: match.groups.messageId || "",
        name: match.groups.name || "",
        content: (match.groups.content || "").trim(),
      };
    }

    function selectedTargetMessageId() {
      return currentTargetMessageId;
    }

    function renderMessageCards(messages) {
      if (!messages.length) return `<div class="empty">暂无上下文</div>`;
      return messages.map(message => {
        const side = isBotContextMessage(message) ? "bot" : "user";
        return renderChatMessageCard({
          side,
          role: message.role,
          source: message.source,
          name: message.name,
          timestamp: message.timestamp,
          messageId: message.messageId,
          text: message.text,
          attachments: message.attachments,
          isTarget: message.isTarget,
        });
      }).join("");
    }

    function renderBotReplyCard(text) {
      return renderChatMessageCard({
        side: "bot",
        role: "assistant",
        source: "guided_reply",
        name: "Bot",
        timestamp: "本次回复",
        messageId: "",
        text,
        attachments: [],
        isTarget: false,
      });
    }

    function renderFollowupCards(followups) {
      if (!followups || !followups.length) return `<div class="empty">暂无</div>`;
      return followups.map(message => `
        ${renderChatMessageCard({
          side: "user",
          role: "user",
          source: "followup",
          name: `${userName(message)}${message.is_target_user ? " · 目标用户" : ""}`,
          timestamp: message.timestamp || "",
          messageId: message.message_id || "",
          text: cleanMessageText(message.visible_text || message.plain_text || ""),
          attachments: Array.isArray(message.attachments) ? message.attachments : [],
          isTarget: message.is_target_user,
        })}
      `).join("");
    }

    function renderChatMessageCard(message) {
      const messageIdText = message.messageId ? ` · ${escapeHtml(message.messageId)}` : "";
      const textHtml = message.text ? `<div class="message-text">${escapeHtml(message.text)}</div>` : "";
      return `
        <div class="message-row ${escapeAttr(message.side || "user")}">
          <div class="message-card ${escapeAttr(message.role || "")} ${escapeAttr(message.source || "")} ${message.isTarget ? "target" : ""}">
            <div class="message-head">
              <span class="message-name">${escapeHtml(message.name || "消息")}</span>
              <span>${escapeHtml(message.timestamp || "")}${messageIdText}</span>
            </div>
            ${textHtml}
            ${renderAttachments(message.attachments || [])}
          </div>
        </div>
      `;
    }

    function renderAttachments(attachments) {
      const shown = (attachments || []).filter(item => attachmentUrl(item));
      if (!shown.length) return "";
      return `
        <div class="message-attachments">
          ${shown.map(item => `
            <div>
              <img class="message-image" src="${escapeAttr(attachmentUrl(item))}" alt="${escapeAttr(item.content || item.kind || "图片")}" loading="lazy" />
              ${item.content ? `<div class="message-image-caption">${escapeHtml(item.content)}</div>` : ""}
            </div>
          `).join("")}
        </div>
      `;
    }

    function attachmentUrl(item) {
      if (!item) return "";
      if (item.data_url) return item.data_url;
      if (item.path) return `/api/image?path=${encodeURIComponent(item.path)}`;
      if (item.hash) return `/api/image_hash?hash=${encodeURIComponent(item.hash)}&kind=${encodeURIComponent(item.kind || "")}`;
      return "";
    }

    function cleanMessageText(text) {
      return String(text || "")
        .replace(/\[图片\]/g, "")
        .replace(/\[表情包?\]/g, "")
        .trim();
    }

    function isBotContextMessage(message) {
      const role = String(message.role || "").toLowerCase();
      const source = String(message.source || "").toLowerCase();
      return role === "assistant" || source === "guided_reply";
    }

    function roleName(role, source) {
      if (source === "guided_reply") return "Bot 已发送";
      if (role === "assistant") return "Bot 思考";
      if (role === "tool") return "工具";
      if (role === "user") return "用户";
      return source || role || "消息";
    }

    function manualFivePointText(manual) {
      if (!manual) return "未评";
      if (manual.manual_score_5) return `${manual.manual_score_5}/5`;
      const score = score100ToFive(manual.manual_score);
      return score ? `${score}/5` : "未评";
    }

    function score100ToFive(value) {
      const number = Number(value);
      if (!Number.isFinite(number)) return 0;
      return Math.max(1, Math.min(5, Math.round(number / 25 + 1)));
    }

    function userName(user) {
      if (!user) return "未知";
      return user.cardname || user.nickname || user.user_id || "未知";
    }

    function shortTime(value) {
      return String(value || "").replace("T", " ").replace("+08:00", "");
    }

    function valueOf(id) {
      const element = document.getElementById(id);
      return element ? element.value : "";
    }

    function scoreText(v) {
      return v === null || v === undefined || v === "" ? "N/A" : Number(v).toFixed(1);
    }

    function fmt(v) {
      return v === null || v === undefined || v === "" ? "N/A" : Number(v).toFixed(2);
    }

    function escapeHtml(value) {
      return String(value ?? "").replace(/[&<>"']/g, c => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      }[c]));
    }

    function escapeAttr(value) {
      return escapeHtml(value).replace(/`/g, "&#96;");
    }

    reloadAll();
  </script>
</body>
</html>
"""


def build_handler(repository: ReplyEffectRepository) -> type[ReplyEffectPreviewHandler]:
    class ConfiguredHandler(ReplyEffectPreviewHandler):
        pass

    ConfiguredHandler.repository = repository
    return ConfiguredHandler


def main() -> None:
    parser = argparse.ArgumentParser(description="预览 Maisaka 回复效果评分，并记录人工评分。")
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"监听地址，默认 {DEFAULT_HOST}")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"监听端口，默认 {DEFAULT_PORT}")
    parser.add_argument("--log-dir", type=Path, default=DEFAULT_LOG_DIR, help="回复效果 JSON 日志目录")
    parser.add_argument("--manual-dir", type=Path, default=DEFAULT_MANUAL_DIR, help="人工评分 JSON 保存目录")
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    args = parser.parse_args()

    mimetypes.add_type("text/html", ".html")
    repository = ReplyEffectRepository(args.log_dir, args.manual_dir)
    server = ThreadingHTTPServer((args.host, args.port), build_handler(repository))
    url = f"http://{args.host}:{args.port}/"
    print(f"Maisaka 回复效果评分预览已启动: {url}")
    print(f"自动评分目录: {args.log_dir}")
    print(f"人工评分目录: {args.manual_dir}")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n正在关闭预览服务...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

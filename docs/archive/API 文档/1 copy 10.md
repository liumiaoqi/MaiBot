本文介绍 Qwen-Audio-3.0-ASR-Flash-Streaming/Fun-ASR-Realtime 实时语音识别服务通过 WebSocket 推送给客户端的服务端事件，包括 task-started、result-generated、task-finished、task-failed 四类事件的数据结构与字段含义。

**用户指南：**关于模型介绍和选型建议请参见[语音识别](https://help.aliyun.com/zh/model-studio/asr-model/)。

**事件交互流程**：如需了解事件交互时序，请参见[WebSocket API](https://help.aliyun.com/zh/model-studio/fun-asr-realtime-websocket-api)。

## **task-started**

**说明**：任务启动成功，客户端可开始发送音频数据。

| **header** `*object*` **属性** **task\\_id** `*string*` 客户端生成的任务 ID（UUID 格式）。 **event** `*string*` 事件类型，固定为 `task-started`。 **attributes** `*object*` 附加属性（通常为空）。 | ``` { "header": { "task_id": "2bf83b9a-baeb-4fda-8d9a-xxxxxxxxxxxx", "event": "task-started", "attributes": {} }, "payload": {} } ``` |
| --- | --- |
| **payload** `*object*` 固定为`{}`。 |

## **result-generated**

**说明**：识别结果，包含中间结果（sentence\_end=false）和最终结果（sentence\_end=true）。

| **header** `*object*` **属性** **task\\_id** `*string*` 客户端生成的任务 ID（UUID 格式）。 **event** `*string*` 事件类型，固定为 `result-generated`。 | ``` { "header": { "task_id": "2bf83b9a-baeb-4fda-8d9a-xxxxxxxxxxxx", "event": "result-generated", "attributes": {} }, "payload": { "output": { "sentence": { "begin_time": 170, "end_time": 920, "text": "好，我知道了", "heartbeat": false, "sentence_end": true, "sentence_id": 1, "words": [ { "begin_time": 170, "end_time": 295, "text": "好", "punctuation": "，" }, { "begin_time": 295, "end_time": 503, "text": "我", "punctuation": "" }, { "begin_time": 503, "end_time": 711, "text": "知道", "punctuation": "" }, { "begin_time": 711, "end_time": 920, "text": "了", "punctuation": "" } ] } }, "usage": { "duration": 3 } } } ``` |
| --- | --- |
| **payload** `*object*` **属性** **output** `*object*` **属性** **usage** `*object*` 当`payload.output.sentence.sentence_end`为`false`（当前句子未结束）时，`usage`为`null`。 当`payload.output.sentence.sentence_end`为`true`（当前句子已结束）时，`usage.duration`为当前任务计费时长。 **属性** **duration** `*integer*` 任务计费时长（s）。 **属性** **sentence** `*object*` **属性** **begin\\_time** `*integer*` 句子开始时间（ms）。 **end\\_time** `*integer*` 句子结束时间（ms）。 **text** `*string*` 识别文本。 **heartbeat** `*boolean*` 若为 true，可跳过该结果（心跳包）。 **sentence\\_end** `*boolean*` 是否句子结束（true=最终结果，false=中间结果）。 **sentence\\_id** `*integer*` 句子的序号标识。正常识别结果中，sentence\\_id 从 1 开始递增。当 heartbeat 为 true 时（即心跳包），sentence\\_id 固定为 0。 **words** `*array[object]*` 字时间戳信息。 **属性** **begin\\_time** `*integer*` 字开始时间（ms）。 **end\\_time** `*integer*` 字结束时间（ms）。 **text** `*string*` 识别文本。 **punctuation** `*string*` 标点符号。 |

## **task-finished**

**说明**：任务正常结束，可关闭连接或复用连接。

| **header** `*object*` **属性** **task\\_id** `*string*` 客户端生成的任务 ID（UUID 格式）。 **event** `*string*` 事件类型，固定为 `task-finished`。 **attributes** `*object*` 附加属性（通常为空）。 | ``` { "header": { "task_id": "2bf83b9a-baeb-4fda-8d9a-xxxxxxxxxxxx", "event": "task-finished", "attributes": {} }, "payload": { "output": {}, "usage": null } } ``` |
| --- | --- |
| **payload** `*object*` 无需关注其中内容，通常为`{}`。 |

## **task-failed**

**说明**：任务失败，连接会被关闭，无法复用。

| **header** `*object*` **属性** **task\\_id** `*string*` 客户端生成的任务 ID（UUID 格式）。 **event** `*string*` 事件类型，固定为 `task-failed`。 **error\\_code** `*string*` 错误类型描述。 **error\\_message** `*string*` 具体错误原因。 **attributes** `*object*` 附加属性（通常为空）。 | ``` { "header": { "task_id": "2bf83b9a-baeb-4fda-8d9a-xxxxxxxxxxxx", "event": "task-failed", "error_code": "CLIENT_ERROR", "error_message": "request timeout after 23 seconds.", "attributes": {} }, "payload": {} } ``` |
| --- | --- |
| **payload** `*object*` 固定为`{}`。 |

.aliyun-docs-content .one-codeblocks pre { max-height: calc(80vh - 136px) !important; height: auto; } .tab-item { font-size: 12px !important; /\* 你可以根据需要调整字体大小 \*/ padding: 0px 5px !important; } .expandable-content { border-left: none !important; border-right: none !important; border-bottom: none !important; } .one-codeblocks.stick-top.section { overflow: hidden !important; }

.table-wrapper { overflow: visible !important; } /\* 调整 table 宽度 \*/ .aliyun-docs-content table.medium-width { max-width: 1018px; width: 100%; } .aliyun-docs-content table.table-no-border tr td:first-child { padding-left: 0; } .aliyun-docs-content table.table-no-border tr td:last-child { padding-right: 0; } /\* 支持吸顶 \*/ div:has(.aliyun-docs-content), .aliyun-docs-content .markdown-body { overflow: visible; } .stick-top { position: sticky; top: 46px; } /\*\*代码块字体\*\*/ /\* 减少表格中的代码块 margin，让表格信息显示更紧凑 \*/ .unionContainer .markdown-body table .help-code-block { margin: 0 !important; } /\* 减少表格中的代码块字号，让表格信息显示更紧凑 \*/ .unionContainer .markdown-body .help-code-block pre { font-size: 12px !important; } /\* 减少表格中的代码块字号，让表格信息显示更紧凑 \*/ .unionContainer .markdown-body .help-code-block pre code { font-size: 12px !important; } /\*\* API Reference 表格 \*\*/ .aliyun-docs-content table.api-reference tr td:first-child { margin: 0px; border-bottom: 1px solid #d8d8d8; } .aliyun-docs-content table.api-reference tr:last-child td:first-child { border-bottom: none; } .aliyun-docs-content table.api-reference p { color: #6e6e80; } .aliyun-docs-content table.api-reference b, i { color: #181818; } .aliyun-docs-content table.api-reference .collapse { border: none; margin-top: 4px; margin-bottom: 4px; } .aliyun-docs-content table.api-reference .collapse .expandable-title-bold { padding: 0; } .aliyun-docs-content table.api-reference .collapse .expandable-title { padding: 0; } .aliyun-docs-content table.api-reference .collapse .expandable-title-bold .title { margin-left: 16px; } .aliyun-docs-content table.api-reference .collapse .expandable-title .title { margin-left: 16px; } .aliyun-docs-content table.api-reference .collapse .expandable-title-bold i.icon { position: absolute; color: #777; font-weight: 100; } .aliyun-docs-content table.api-reference .collapse .expandable-title i.icon { position: absolute; color: #777; font-weight: 100; } .aliyun-docs-content table.api-reference .collapse.expanded .expandable-content { padding: 10px 14px 10px 14px !important; margin: 0; border: 1px solid #e9e9e9; } .aliyun-docs-content table.api-reference .collapse .expandable-title-bold b { font-size: 13px; font-weight: normal; color: #6e6e80; } .aliyun-docs-content table.api-reference .collapse .expandable-title b { font-size: 13px; font-weight: normal; color: #6e6e80; } .aliyun-docs-content table.api-reference .tabbed-content-box { border: none; } .aliyun-docs-content table.api-reference .tabbed-content-box section { padding: 8px 0 !important; } .aliyun-docs-content table.api-reference .tabbed-content-box.mini .tab-box { /\* position: absolute; left: 40px; right: 0; \*/ } .aliyun-docs-content .margin-top-33 { margin-top: 33px !important; } .aliyun-docs-content .two-codeblocks pre { max-height: calc(50vh - 136px) !important; height: auto; } .expandable-content section { border-bottom: 1px solid #e9e9e9; padding-top: 6px; padding-bottom: 4px; } .expandable-content section:last-child { border-bottom: none; } .expandable-content section:first-child { padding-top: 0; }
---
name: clawshire-doc-extract-engine
description: ClawShire 通用文档提取技能 - 用户上传 PDF（单个或多个），通过自然语言设计 Schema、执行结构化提取与多轮迭代修正；对接平台 /api/v1/doc-extract-engine，不依赖公告 met_uuid
---

# ClawShire 通用文档提取引擎技能

使用 ClawShire 平台封装的 **doc-extract-engine** 能力：上传自备 PDF → Schema 对话 → 创建 Session → 提取 → 可选批次对话修正 → 归档。适用于合同、研报、说明书等任意 PDF，**不是**对公告库内已提取 JSON 的二次迭代。

**服务地址：** `https://api.clawshire.cn`
**依赖：** 平台已启用文档提取插件（`MEME_PLUGIN_REFLECT_ENGINE_ENABLED`）。

---

## 前置检查

1. **`CLAWSHIRE_API_KEY`** 必须已设置。不得在输出中泄露 key。
2. 安装脚本依赖：`pip install httpx`。
3. 可选：`export CLAWSHIRE_API_BASE_URL=http://localhost:8452` 用于本地网关调试。

**API Key 格式说明：**

| 环境 | 格式 | 示例 |
| --- | --- | --- |
| 生产环境 | `sk-` 开头（短横线） | `sk-xxxxxxxxxxxxxxxx` |
| 本地测试 | `sk_` 开头（下划线） | `sk_5c2d43ccfdb5d248...` |

本地测试时若返回 401，优先检查 key 格式是否与环境匹配。

---

## 认证

```http
Authorization: Bearer $CLAWSHIRE_API_KEY
```

---

## 平台 API 路径前缀

`/api/v1/doc-extract-engine`

---

## 标准工作流

每步骤都会返回一个 ID，需传入下一步，链路如下：

```text
upload → document_id
  └→ schema-create(document_id) → conversation_id
       └→ schema-chat(conversation_id) → schema JSON（需保存为文件）
            └→ session-create(schema文件, document_id) → session_id
                 └→ extract(session_id, document_id) → batch_id + results
                      └→ batch-chat(batch_id) → 修正（可多轮，可选）
                           └→ batch-end(batch_id) → 归档
```

---

### 步骤 1：上传 PDF

`POST .../upload`，`multipart/form-data`，字段名 **`files`**（可多个）。

响应：`{"document_ids": ["uuid1", ...], "count": N}`

> 保存 `document_ids` 用于后续所有步骤。

---

### 步骤 2：开启 Schema 设计对话

`POST .../schema-conversations`，body：`{"document_ids": ["uuid1"]}`

响应：`{"conversation_id": <int>}`

---

### 步骤 3：描述提取需求（可多轮）

`POST .../schema-conversations/{conversation_id}/chat`，body：`{"message": "请提取甲方、乙方、合同金额、签署日期"}`

> **耗时提示：** 此步骤通常需要 30 秒～3 分钟，请告知用户等待。

响应为服务端聚合 SSE 后的 JSON，关键字段：

```json
{
  "conversation_id": 2,
  "schema": { "type": "object", "properties": { ... } },
  "messages": ["..."],
  "results": []
}
```

若 `schema` 字段为空，用 `schema-get {conversation_id}` 单独拉取。

**⚠️ 关键步骤：** `schema-chat` 返回的 `schema` 字段需手动保存为 JSON 文件，才能传给 `session-create`：

```bash
# 将 schema-chat 输出中的 schema 字段内容保存到文件
# 例：从输出 JSON 中提取 .schema 部分写入 schema.json
python -c "
import json, sys
data = json.load(sys.stdin)
with open('schema.json', 'w') as f:
    json.dump(data['schema'], f, ensure_ascii=False, indent=2)
" < schema_chat_output.json
```

或手动复制 `schema` 字段内容到 `schema.json`。

---

### 步骤 4：创建提取 Session

`POST .../sessions`，body：

```json
{
  "session_name": "财务总监辞职任命提取",
  "extraction_schema": { "type": "object", "properties": { ... } },
  "document_ids": ["uuid1"]
}
```

响应：`{"session_id": <int>}`

---

### 步骤 5：执行提取

`POST .../extract`，body：`{"session_id": 1, "document_ids": ["uuid1"]}`

> **耗时提示：** 此步骤通常需要 1～5 分钟，请告知用户等待。

响应包含 `batch_id` 和 `results`：

```json
{
  "batch_id": 2,
  "results": [
    {
      "document_id": "uuid1",
      "data": { ... }
    }
  ]
}
```

---

### 步骤 6：迭代修正（可选）

`POST .../batches/{batch_id}/chat`，body：`{"message": "把金额统一成数字，去掉货币符号"}`

> **耗时提示：** 同上，需 1～3 分钟。可重复多轮，每轮均返回修正后的完整 `results`。

---

### 步骤 7：归档

`POST .../batches/{batch_id}/end`

**何时调用：** 提取结果已确认无需修正时调用，标记批次完成。若只是临时测试可跳过，但正式任务建议归档以便后续通过 `history` 接口查询。

---

## 完整端到端示例

以「财务总监辞职暨聘任公告」PDF 提取辞职人、任命人信息为例：

```bash
export CLAWSHIRE_API_KEY="sk_your_local_key"
export CLAWSHIRE_API_BASE_URL="http://localhost:8452"  # 本地测试时设置

SCRIPT="python skills/clawshire-doc-extract-engine/scripts/clawshire_doc_extract_client.py"

# 1. 上传 PDF，记录 document_id
$SCRIPT upload ./公告.pdf
# → {"document_ids": ["fef11765-b827-486a-a2be-a6aeae617105"], "count": 1}
DOC_ID="fef11765-b827-486a-a2be-a6aeae617105"

# 2. 创建 Schema 对话，记录 conversation_id
$SCRIPT schema-create --doc-ids "$DOC_ID"
# → {"conversation_id": 2}

# 3. 描述提取需求（等待 30s～3min）
$SCRIPT schema-chat 2 "提取辞职人姓名、职务、辞职原因，以及新任命人姓名、职务、任命日期、任职期限"
# → 返回含 schema 字段的 JSON，手动将 schema 保存为 schema.json

# 4. 创建 Session
$SCRIPT session-create --name "辞职任命提取" --schema-file schema.json --doc-ids "$DOC_ID"
# → {"session_id": 2}

# 5. 执行提取（等待 1～5min）
$SCRIPT extract --session-id 2 --doc-ids "$DOC_ID"
# → {"batch_id": 2, "results": [...]}

# 6. 可选：修正
$SCRIPT batch-chat 2 "辞职生效日期补充具体日期，若文中未提及则填'文件送达即生效'"

# 7. 归档
$SCRIPT batch-end 2
```

---

## 辅助接口

| 说明 | 方法 | 路径 |
| --- | --- | --- |
| 连通性检测 | GET | `/status` |
| 引擎 Session 列表 | GET | `/sessions` |
| Session 历史 | GET | `/sessions/{session_id}/history` |
| 引擎账号绑定信息 | GET | `/token-info` |

---

## 与公告数据的关系

- **不需要** `met_uuid`、不调用公告提取查询即可完成全流程。
- 若用户只有公告链接：可先用 **clawshire-data-query** 查看结构化结果；若要对**用户手头的另一份 PDF** 做通用提取，仍用本技能的 upload 流程即可。

---

## 错误处理

| 情况 | 处理 |
| --- | --- |
| 401 | 检查 API Key 及格式（本地 `sk_` / 生产 `sk-`） |
| 413 | 单文件超过平台 `MAX_UPLOAD_MB` |
| 503 | 插件未启用或未配置引擎 URL |
| 502 | 引擎超时或 SSE 报错，稍后重试 |

`schema-chat` / `extract` / `batch-chat` 均为耗时操作（30s～5min），执行前应提前告知用户。

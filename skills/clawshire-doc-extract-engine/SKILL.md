---
name: clawshire-doc-extract-engine
description: ClawShire 通用文档提取技能 - 用户上传 PDF（单个或多个），通过自然语言设计 Schema、执行结构化提取与多轮迭代修正；支持历史 schema 记忆复用，同类文档无需重复设计；对接平台 /api/v1/doc-extract-engine，不依赖公告 met_uuid
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

## 工作流选择

```text
收到新文档
    ↓
① sessions-summary 查看历史任务
    ↓
  ┌──────────────────────┬────────────────────────────┐
  │ 有相似历史任务         │ 全新文档类型                │
  ↓                      ↓
② 记忆复用流程            首次完整流程
  （跳过 schema-chat）    （schema-create → chat）
```

---

## 记忆复用流程（有历史任务时优先）

### 第一步：查看历史任务及 schema 预览

```bash
python clawshire_doc_extract_client.py sessions-summary
```

输出示例：

```text
────────────────────────────────────────────────────────────────
  历史提取任务（共 2 条）
────────────────────────────────────────────────────────────────

  [1] 合同提取-项目A  2026-03-10  文档数: 3
       字段: 甲方, 乙方, 合同金额, 签署日期, 有效期

  [2] 财务总监辞职任命提取  2026-03-20  文档数: 1
       字段: resignation_info.name, resignation_info.position,
             appointment_info.name, appointment_info.position ... (共 12 个字段)

  复用方式: session-create --name <名称> --from-session <id> --doc-ids <ids>
────────────────────────────────────────────────────────────────
```

根据字段预览判断：

- **字段完全匹配** → 直接 `--from-session` 复用
- **字段基本符合但需微调** → `schema-export` 导出后修改，再用 `--schema-file` 创建
- **完全不同** → 走首次完整流程

### 第二步：上传新文档

```bash
python clawshire_doc_extract_client.py upload ./新文档.pdf
# → {"document_ids": ["new-doc-uuid"], "count": 1}
```

### 第三步：复用历史 schema 直接创建 Session

```bash
# 直接复用 session 2 的 schema（跳过 schema-chat）
python clawshire_doc_extract_client.py session-create \
  --name "辞职任命提取-批次2" \
  --from-session 2 \
  --doc-ids "new-doc-uuid"
# → {"session_id": 3}
```

### 第四步：执行提取

```bash
python clawshire_doc_extract_client.py extract \
  --session-id 3 --doc-ids "new-doc-uuid"
```

### 导出并修改 schema 后复用

```bash
# 导出历史 schema 到文件
python clawshire_doc_extract_client.py schema-export 2 --out my_schema.json

# 手动编辑 my_schema.json 后创建新 session
python clawshire_doc_extract_client.py session-create \
  --name "调整版任务" --schema-file my_schema.json --doc-ids "new-doc-uuid"
```

---

## 首次完整流程（全新文档类型）

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

### 步骤 1：上传 PDF

`POST .../upload`，`multipart/form-data`，字段名 **`files`**（可多个）。

响应：`{"document_ids": ["uuid1", ...], "count": N}`

### 步骤 2：开启 Schema 设计对话

`POST .../schema-conversations`，body：`{"document_ids": ["uuid1"]}`

响应：`{"conversation_id": <int>}`

### 步骤 3：描述提取需求（可多轮）

`POST .../schema-conversations/{conversation_id}/chat`，body：`{"message": "请提取甲方、乙方、合同金额、签署日期"}`

> **耗时提示：** 此步骤通常需要 30 秒～3 分钟，请告知用户等待。

响应关键字段：

```json
{
  "conversation_id": 2,
  "schema": { "type": "object", "properties": { ... } },
  "messages": ["..."],
  "results": []
}
```

**⚠️ 关键步骤：** `schema-chat` 返回的 `schema` 字段需手动保存为 JSON 文件，再传给 `session-create --schema-file`。

### 步骤 4：创建提取 Session

```bash
python clawshire_doc_extract_client.py session-create \
  --name "任务名" --schema-file schema.json --doc-ids "uuid1"
```

响应：`{"session_id": <int>}`

### 步骤 5：执行提取

```bash
python clawshire_doc_extract_client.py extract \
  --session-id 1 --doc-ids "uuid1"
```

> **耗时提示：** 此步骤通常需要 1～5 分钟，请告知用户等待。

响应包含 `batch_id` 和 `results`。

### 步骤 6：迭代修正（可选）

```bash
python clawshire_doc_extract_client.py batch-chat 2 "把金额统一成数字，去掉货币符号"
```

可重复多轮，每轮返回修正后的完整 `results`。

### 步骤 7：归档

```bash
python clawshire_doc_extract_client.py batch-end 2
```

**何时调用：** 结果已确认无需修正时归档，正式任务建议执行以便 `history` 接口查询。

---

## 辅助接口

| 说明 | 方法 | CLI 命令 |
| --- | --- | --- |
| 连通性检测 | GET /status | `status` |
| 历史任务预览（复用入口） | GET /sessions + history | `sessions-summary` |
| 导出历史 schema | GET /sessions/{id}/history | `schema-export <id>` |
| 原始 Session 列表 | GET /sessions | `sessions` |
| Session 历史详情 | GET /sessions/{id}/history | `history <id>` |

---

## 完整端到端示例

以「财务总监辞职暨聘任公告」PDF 为例：

```bash
export CLAWSHIRE_API_KEY="sk_your_local_key"
export CLAWSHIRE_API_BASE_URL="http://localhost:8452"

SCRIPT="python skills/clawshire-doc-extract-engine/scripts/clawshire_doc_extract_client.py"

# 0. 先检查是否有可复用的历史任务
$SCRIPT sessions-summary

# --- 若无相似历史任务，走完整流程 ---

# 1. 上传 PDF
$SCRIPT upload ./公告.pdf
# → {"document_ids": ["fef11765-..."], "count": 1}

# 2. 创建 Schema 对话
$SCRIPT schema-create --doc-ids "fef11765-..."
# → {"conversation_id": 2}

# 3. 描述提取需求（等待 30s～3min）
$SCRIPT schema-chat 2 "提取辞职人姓名、职务、辞职原因，以及新任命人姓名、职务、任命日期、任职期限"
# → 手动将返回 JSON 中的 schema 字段保存为 schema.json

# 4. 创建 Session
$SCRIPT session-create --name "辞职任命提取" --schema-file schema.json --doc-ids "fef11765-..."
# → {"session_id": 2}

# 5. 执行提取（等待 1～5min）
$SCRIPT extract --session-id 2 --doc-ids "fef11765-..."
# → {"batch_id": 2, "results": [...]}

# 6. 归档
$SCRIPT batch-end 2

# --- 下次遇到同类公告，直接复用 ---
$SCRIPT upload ./新公告.pdf
$SCRIPT session-create --name "辞职任命-批次2" --from-session 2 --doc-ids "new-uuid"
$SCRIPT extract --session-id 3 --doc-ids "new-uuid"
```

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

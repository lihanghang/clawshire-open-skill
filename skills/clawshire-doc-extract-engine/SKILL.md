---
name: clawshire-doc-extract-engine
description: ClawShire 通用文档提取技能 - 用户上传 PDF（单个或多个），通过自然语言设计 Schema、执行结构化提取与多轮迭代修正；对接平台 /api/v1/doc-extract-engine，不依赖公告 met_uuid
---

# ClawShire 通用文档提取引擎技能

上传自备 PDF → 用自然语言描述要提取的字段 → 拿到结构化 JSON。适用于合同、研报、说明书等任意 PDF。

**服务地址：** `https://api.clawshire.cn`
**前置条件：** 设置 `CLAWSHIRE_API_KEY`，安装 `pip install httpx`。

---

## 快速开始（三步完成一次提取）

```bash
export CLAWSHIRE_API_KEY="sk-..."
SCRIPT="python skills/clawshire-doc-extract-engine/scripts/clawshire_doc_extract_client.py"

# 第一步：上传 PDF，记下返回的 document_id
$SCRIPT upload 合同.pdf

# 第二步：设计提取字段（一句话描述即可）
$SCRIPT schema-create --doc-ids <document_id>
$SCRIPT schema-chat <conversation_id> "提取甲方、乙方、合同金额、签署日期" --save-as 合同

# 第三步：创建 Session 并提取，结果写入文件
$SCRIPT session-create --name "合同提取" --from-lib 合同 --doc-ids <document_id>
$SCRIPT extract --session-id <session_id> --doc-ids <document_id> --out result.json --auto-end --quiet
```

> `--auto-end` 自动归档并触发平台经验学习；`--quiet` 仅打印字段覆盖率概要，不把完整 JSON 输出到终端。

---

## 标准工作流（完整 7 步 API）

### 1. 上传 PDF

`POST /api/v1/doc-extract-engine/upload`，`multipart/form-data`，字段名 **`files`**（可多个）。

响应：`{"document_ids": [...], "count": N}`

### 2. 开启 Schema 设计对话

`POST .../schema-conversations`，body：`{"document_ids": ["id1","id2"]}`

响应：`{"conversation_id": <int>}`

### 3. 用自然语言描述提取需求

`POST .../schema-conversations/{conversation_id}/chat`，body：`{"message": "请提取甲方、乙方、合同金额、签署日期"}`

响应为服务端聚合 SSE 后的 JSON，含 `schema`、`messages`、`results` 等字段（以实际返回为准）。

若响应未带完整 schema：`GET .../schema-conversations/{conversation_id}` 拉取当前状态。

### 4. 创建提取 Session

`POST .../sessions`，body：

```json
{
  "session_name": "合同-项目A",
  "extraction_schema": { "type": "object", "properties": { ... } },
  "document_ids": ["id1", "id2"]
}
```

响应：`{"session_id": <int>}`

### 5. 执行提取

`POST .../extract`，body：`{"session_id": 1, "document_ids": ["id1","id2"]}`

响应含 `batch_id`、`results` 等。

### 6. 迭代修正（可选）

`POST .../batches/{batch_id}/chat`，body：`{"message": "把金额统一成数字，去掉货币符号"}`

可重复多轮。

### 7. 归档

`POST .../batches/{batch_id}/end`

---

## 高级用法：省 Token & 省额度

### 省 Token 选项

| 选项 | 作用 |
|------|------|
| `extract --quiet` | 不打印完整 JSON，仅显示字段覆盖率 + 首条预览 |
| `batch-result --summary` | 同上，查询已有批次时使用 |
| `batch-chat --quiet` | 修正后不打印完整响应 |

### 省额度：本地提取缓存

首次提取会自动写入 `~/.clawshire/cache.json`（按 **API Key + BaseURL + session_id + doc_ids** 四维隔离，切换环境不会污染）。

```bash
# 首次提取（写入缓存）
$SCRIPT extract --session-id 1 --doc-ids id1,id2 --out result.json --quiet

# 再次访问同一批文档，命中缓存则不消耗额度
$SCRIPT extract --session-id 1 --doc-ids id1,id2 --use-cache --quiet
```

> **注意**：`--use-cache` 未命中时会打印明确提示后执行真实提取；缓存命中但该 batch 已被 `--auto-end` 归档时，会显示"归档快照"警告。

### 省 schema-chat：本地 Schema 库

Schema 保存到 `~/.clawshire/schemas.json`，跨 API Key 复用，无需重复 schema-chat。

```bash
# 查询已有 schema（支持关键字过滤）
$SCRIPT schema-lib-list
$SCRIPT schema-lib-list --search 合同

# schema-chat 时自动保存（同名已存在时跳过，不静默覆盖）
$SCRIPT schema-chat 1 "提取甲方、乙方、金额" --save-as 合同 --description "合同通用 schema"

# 手动保存（允许覆盖已有 schema，会提示原保存时间）
$SCRIPT schema-lib-save --name 合同 --file schema.json

# 跳过 schema-chat，直接从库创建 Session
$SCRIPT session-create --name "批量任务" --from-lib 合同 --doc-ids id1,id2,id3
```

---

## CLI 完整参数参考

```bash
# 连通性检查
$SCRIPT status

# 上传（本地路径 或 http/https URL，可混用）
$SCRIPT upload a.pdf "https://example.com/b.pdf"

# Schema 流程
$SCRIPT schema-create --doc-ids id1,id2
$SCRIPT schema-chat <conv_id> "描述需求" [--save-as 名称] [--description 描述]
$SCRIPT schema-get <conv_id>

# Session 流程
$SCRIPT session-create --name 名称 (--schema-file schema.json | --from-lib 名称) --doc-ids id1,id2
$SCRIPT sessions
$SCRIPT history <session_id>

# 提取
$SCRIPT extract --session-id <sid> --doc-ids id1,id2 \
  [--out [path.json]] [--auto-end] [--quiet] [--use-cache]

# Batch 操作
$SCRIPT batch-result <batch_id> [--out [path.json]] [--summary]
$SCRIPT batch-chat <batch_id> "修正说明" [--out [path.json]] [--quiet]
$SCRIPT batch-end <batch_id>

# Schema 库管理
$SCRIPT schema-lib-list [--search 关键字]
$SCRIPT schema-lib-save --name 名称 --file schema.json [--description 描述]
$SCRIPT schema-lib-delete 名称
```

---

## 辅助说明

**认证**：`Authorization: Bearer $CLAWSHIRE_API_KEY`
**本地调试**：`export CLAWSHIRE_API_BASE_URL=http://localhost:8452`
**依赖**：平台需启用 `MEME_PLUGIN_REFLECT_ENGINE_ENABLED`
**耗时**：`extract` / `schema-chat` / `batch-chat` 可能耗时数分钟，应告知用户等待

**与公告数据的关系**：本技能**不需要** `met_uuid`，适合对用户手头的任意 PDF 做通用提取；若只有公告链接，使用 `clawshire-data-query` 查看已有结构化结果。

| 错误码 | 处理 |
|--------|------|
| 401 | 检查 `CLAWSHIRE_API_KEY` |
| 413 | 单文件超过平台 `MAX_UPLOAD_MB` |
| 503 | 插件未启用或未配置引擎 URL |
| 502 | 引擎超时或 SSE 报错，稍后重试 |

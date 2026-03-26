# ClawShire 文档提取引擎 - 快速上手指南

基于实际测试案例，5 分钟学会用自然语言从 PDF 中提取结构化数据。

---

## 前置准备

```bash
# 1. 安装依赖
pip install httpx

# 2. 设置 API Key
export CLAWSHIRE_API_KEY="sk-your-api-key"

# 3. 进入 skill 目录
cd skills/clawshire-doc-extract-engine
```

---

## 案例一：董事监事辞职公告提取

### 场景
从《靖远煤电：关于公司董事、监事辞职的公告》中提取辞职人员信息。

### 步骤

**1. 上传文档（5秒）**

```bash
python scripts/clawshire_doc_extract_client.py upload "/path/to/辞职公告.pdf"
```

返回：
```json
{
  "document_ids": ["ec7f7fa4-1073-4506-aa3f-8f82484d2d5f"],
  "count": 1
}
```

**2. 创建 Schema 对话（5秒）**

```bash
python scripts/clawshire_doc_extract_client.py schema-create \
  --doc-ids "ec7f7fa4-1073-4506-aa3f-8f82484d2d5f"
```

返回：
```json
{"conversation_id": 2}
```

**3. 描述提取需求（30秒～3分钟）**

```bash
python scripts/clawshire_doc_extract_client.py schema-chat 2 \
  "提取董事和监事的辞职信息：姓名、职务、辞职原因、辞职日期"
```

> ⏳ 这一步会调用 AI 分析文档并设计 Schema，需要等待 30秒～3分钟。
> 如遇 504 超时，脚本会自动重试 2 次。

**4. 保存 Schema 到文件**

```bash
# 从上一步的返回中提取 schema 字段
python scripts/clawshire_doc_extract_client.py schema-chat 2 \
  "提取董事和监事的辞职信息：姓名、职务、辞职原因、辞职日期" \
  | python3 -c "import sys, json; d=json.load(sys.stdin); \
    print(json.dumps(d['schema'], ensure_ascii=False, indent=2))" \
  > /tmp/resignation_schema.json
```

**5. 创建提取 Session（5秒）**

```bash
python scripts/clawshire_doc_extract_client.py session-create \
  --name "董事监事辞职提取" \
  --schema-file /tmp/resignation_schema.json \
  --doc-ids "ec7f7fa4-1073-4506-aa3f-8f82484d2d5f"
```

返回：
```json
{"session_id": 1}
```

**6. 执行提取（1～5分钟）**

```bash
python scripts/clawshire_doc_extract_client.py extract \
  --session-id 1 \
  --doc-ids "ec7f7fa4-1073-4506-aa3f-8f82484d2d5f" \
  --out result.json
```

> ⏳ 这一步会执行实际提取，需要等待 1～5分钟。
> 结果自动保存到 `result.json`。

**7. 查看结果**

```json
{
  "company_name": "甘肃靖远煤电股份有限公司",
  "announcement_date": "2023年3月7日",
  "director_resignations": [
    {
      "name": "苟小弟",
      "position": "董事、董事长及董事会专门委员会相关职务",
      "resignation_reason": "因工作调整",
      "resignation_date": "2023年3月7日"
    }
  ],
  "supervisor_resignations": [
    {
      "name": "高小明",
      "position": "监事会主席",
      "resignation_reason": "因工作调整",
      "resignation_date": "2023年3月7日"
    }
  ]
}
```

**8. 补充提取（可选）**

如果需要补充信息，使用 `batch-chat`：

```bash
python scripts/clawshire_doc_extract_client.py batch-chat 1 \
  "补充提取：每位辞职人员辞职后是否仍在公司担任其他职务" \
  --out updated_result.json
```

---

## 案例二：财务总监辞职暨聘任公告

### 场景
从《关于财务总监辞职暨聘任财务总监的公告》中提取辞职和新聘任信息。

### 关键点

这类公告包含**辞职 + 聘任**两部分信息，需要设计更全面的 Schema：

```json
{
  "resignations": [
    {
      "name": "李国政",
      "position": "财务总监",
      "reason": "个人原因",
      "remaining_positions": "不在公司担任任何职务"
    }
  ],
  "appointments": [
    {
      "name": "汪周波",
      "position": "财务总监",
      "date": "2017年9月5日",
      "term": "至第四届董事会任期届满日止",
      "resume": "1985年生，安徽财经大学会计学本科..."
    }
  ]
}
```

### 提取步骤

```bash
# 1. 上传
python scripts/clawshire_doc_extract_client.py upload "/path/to/财务总监辞职公告.pdf"

# 2. 创建对话
python scripts/clawshire_doc_extract_client.py schema-create --doc-ids "<doc_id>"

# 3. 描述需求（注意包含辞职和聘任两部分）
python scripts/clawshire_doc_extract_client.py schema-chat <conv_id> \
  "提取辞职信息（姓名、职务、原因、辞职后是否担任其他职务）和新聘任信息（姓名、职务、聘任日期、任职期限、简历）"

# 4-6. 保存 schema、创建 session、执行提取（同案例一）
```

---

## 案例三：分红公告提取

### 场景
从分红公告中提取：分红总额、股权登记日、除权除息日、分红基准股本、利润分配方案。

### 特殊情况：不分红公告

```bash
# 描述需求时要考虑"不分红"的情况
python scripts/clawshire_doc_extract_client.py schema-chat <conv_id> \
  "提取分红信息：分红总额、股权登记日、除权除息日、分红基准股本、利润分配具体方案"
```

提取结果（不分红案例）：

```json
{
  "has_dividend": false,
  "no_dividend_reason": "公司2025年度归属于母公司所有者的净利润为负",
  "profit_distribution_plan": "2025年度拟不进行利润分配，不以资本公积金转增股本",
  "dividend_total_amount": null,
  "record_date": null,
  "ex_dividend_date": null
}
```

---

## 批量提取：复用 Schema

### 场景
已经提取过一份辞职公告，现在要提取第二份同类公告。

### 方法一：使用已保存的 Schema 文件

```bash
# 直接复用之前保存的 schema 文件
python scripts/clawshire_doc_extract_client.py session-create \
  --name "辞职提取-批次2" \
  --schema-file /tmp/resignation_schema.json \
  --doc-ids "<new_doc_id>"
```

### 方法二：使用本地 Schema 库（推荐）

```bash
# 第一次提取时保存到本地库
python scripts/clawshire_doc_extract_client.py schema-chat <conv_id> \
  "提取董事监事辞职信息" \
  --save-as "辞职公告"

# 后续直接从本地库复用
python scripts/clawshire_doc_extract_client.py session-create \
  --name "辞职提取-批次2" \
  --from-lib "辞职公告" \
  --doc-ids "<new_doc_id>"

# 查看本地库
python scripts/clawshire_doc_extract_client.py schema-lib-list
```

---

## 常见问题

### Q1: 遇到 504 超时怎么办？

**A:** 脚本已内置重试机制，会自动重试 2 次。如果仍然失败：
- `schema-chat` 和 `extract` 是耗时操作，属于正常现象
- 稍后重试，或简化提取需求

### Q2: 如何从 URL 上传 PDF？

**A:** 先下载到本地再上传：

```bash
curl -o /tmp/doc.pdf "http://example.com/file.pdf"
python scripts/clawshire_doc_extract_client.py upload /tmp/doc.pdf
```

### Q3: 提取结果不准确怎么办？

**A:** 使用 `batch-chat` 迭代修正：

```bash
python scripts/clawshire_doc_extract_client.py batch-chat <batch_id> \
  "把日期统一成 YYYY-MM-DD 格式" \
  --out fixed.json
```

可以多轮修正，直到满意为止。

### Q4: 如何查看历史提取任务？

```bash
# 查看所有 session
python scripts/clawshire_doc_extract_client.py sessions

# 查看某个 session 的详情
python scripts/clawshire_doc_extract_client.py history <session_id>
```

---

## 最佳实践

1. **Schema 设计要具体**
   - ❌ "提取所有信息"
   - ✅ "提取姓名、职务、辞职原因、辞职日期"

2. **考虑边界情况**
   - 分红公告：考虑"不分红"的情况
   - 辞职公告：考虑"辞职后是否担任其他职务"

3. **善用本地 Schema 库**
   - 第一次提取时用 `--save-as` 保存
   - 后续用 `--from-lib` 快速复用

4. **结果保存**
   - 始终使用 `--out` 保存结果到文件
   - 文件名会自动生成时间戳

5. **耐心等待**
   - `schema-chat`: 30秒～3分钟
   - `extract`: 1～5分钟
   - 这是 AI 分析文档的正常耗时

---

## 完整示例脚本

```bash
#!/bin/bash
set -e

export CLAWSHIRE_API_KEY="sk-your-key"
SCRIPT="python scripts/clawshire_doc_extract_client.py"

# 上传
DOC_ID=$($SCRIPT upload "/path/to/doc.pdf" | jq -r '.document_ids[0]')
echo "Document ID: $DOC_ID"

# 创建对话
CONV_ID=$($SCRIPT schema-create --doc-ids "$DOC_ID" | jq -r '.conversation_id')
echo "Conversation ID: $CONV_ID"

# 设计 Schema
$SCRIPT schema-chat $CONV_ID "提取关键信息" --save-as "我的模板"

# 创建 Session
SESSION_ID=$($SCRIPT session-create --name "提取任务" --from-lib "我的模板" --doc-ids "$DOC_ID" | jq -r '.session_id')
echo "Session ID: $SESSION_ID"

# 执行提取
$SCRIPT extract --session-id $SESSION_ID --doc-ids "$DOC_ID" --out result.json

echo "✅ 提取完成，结果保存在 result.json"
```

---

## 总结

通过三个真实案例，你已经掌握了：

✅ 基础流程：上传 → 设计 Schema → 提取
✅ Schema 复用：本地库 / 文件复用
✅ 结果修正：batch-chat 迭代优化
✅ 特殊场景：辞职+聘任、不分红等

现在可以开始提取你自己的文档了！

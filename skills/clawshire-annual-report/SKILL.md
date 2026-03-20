---
name: clawshire-annual-report
description: ClawShire 年报数据查询技能 - 北交所上市公司年度报告结构化提取结果查询，支持按证券代码、年份检索营收、利润、分红、战略要点等标准字段
---

# ClawShire 年报数据查询技能

北交所上市公司年度报告结构化提取结果查询服务。覆盖证券代码 4/8/9 开头的北交所上市公司，返回营收、利润、分红、战略要点等标准化字段，供 Agent 直接推理。

**服务地址：** `https://api.clawshire.cn`

---

## 前置检查

在执行任何 API 调用前，必须检查 `CLAWSHIRE_API_KEY` 环境变量是否存在。
- 只判断是否存在，**不得**在输出中明文显示 key 内容
- 若不存在，引导用户注册获取：`https://clawshire.cn`

---

## 认证方式

所有请求头携带：

```
Authorization: Bearer $CLAWSHIRE_API_KEY
```

---

## 北交所说明

北交所上市公司证券代码特征：
- `4` 开头：北交所股票（如 430000 段）
- `8` 开头：北交所股票（如 830000 段）
- `9` 开头：北交所股票（如 920000 段）

年报查询时 `infotype` 固定为 `年报`，无需用户指定。

---

## 工作流

### 工作流 1：按证券代码查询年报

适用场景：用户想查某家北交所公司的年度报告提取结果。

**步骤：**
1. 确认北交所证券代码（4/8/9 开头的6位代码）
2. 可选：指定年份范围（`start_date`、`end_date`）
3. 调用 `GET /api/v1/stock/{sec_code}/announcements`，固定 `infotype=年报`
4. 展示结果：公司名、年报期间、营收、利润、分红、战略要点等提取字段

**示例：**
```
查询九典制药（833359）2024 年报
→ GET /api/v1/stock/833359/announcements?infotype=年报&start_date=2024-01-01&end_date=2025-12-31
```

---

### 工作流 2：按年份查询北交所全市场年报

适用场景：用户想查某年度北交所所有公司的年报提取结果。

**步骤：**
1. 确认年份（如 2024）
2. 将年份转换为日期范围：`start_date={year}-01-01`，`end_date={year+1}-12-31`
3. 调用 `GET /api/v1/announcements`，固定 `infotype=年报`
4. 展示结果列表，包含公司名、证券代码、营收、利润等核心提取字段

**注意：** 北交所年报通常集中在次年 3～4 月披露，如查 2024 年报应将 `end_date` 设为 2025-06-30。

---

### 工作流 3：按公告链接查询年报

适用场景：用户有北交所年报的原文链接，想获取结构化提取结果。

**步骤：**
1. 获取用户提供的年报原文链接
2. 调用 `GET /api/v1/met_link?met_link=<url_encoded_link>&infotype=年报`
3. 展示完整结构化提取内容

---

### 工作流 4：获取 API Key

**步骤：**
1. 引导用户登录控制台：`https://clawshire.cn`
2. 在控制台创建 API Key
3. 设置环境变量：
   ```bash
   export CLAWSHIRE_API_KEY="sk-xxxxxxxx"
   ```

---

### 工作流 5：财务风险分析（需认证）

适用场景：用户需要对上市公司年报进行深度风险评估。调用 25+ 条分析规则，输出整体风险评级（低/中/高）和各规则详细分析。

**前置条件：**
- 需要有效的 `CLAWSHIRE_API_KEY`
- 财务分析 API 需要在控制台开通权限（即将支持）

**步骤：**
1. 获取目标公司的年报 PDF 文件路径（或下载年报 URL 对应的 PDF）
2. 调用 `POST /api/v1/financial-analysis/jobs` 上传 PDF
3. 用返回的 `job_id` 轮询 `GET /api/v1/financial-analysis/jobs/{job_id}`
4. 分析完成后，展示风险评级和高/中风险规则列表

**注意：**
- 财务分析 API 托管于 `https://api.clawshire.cn`，与公告数据 API 共享认证
- 分析通常耗时 2-8 分钟，PDF 最大 100MB
- 查看所有可用规则：`GET /api/v1/financial-analysis/rules`

**示例：**
```
上传年报 PDF 进行风险分析
→ POST /api/v1/financial-analysis/jobs (file=年报.pdf)
← {"id": "job_xxxxx", "status": "pending", ...}

轮询获取结果
→ GET /api/v1/financial-analysis/jobs/job_xxxxx
← {"status": "completed", "overall_risk_level": "medium", "rule_results": [...]}
```

**使用脚本：**
```bash
# 分析 PDF 文件（需要 CLAWSHIRE_API_KEY）
python scripts/financial_analysis_client.py analyze path/to/年报.pdf

# 或指定语言（默认中文）
python scripts/financial_analysis_client.py analyze path/to/年报.pdf --lang en

# 查看所有分析规则
python scripts/financial_analysis_client.py rules
```

---

## 结果展示规范

每条年报结果优先展示以下字段（若存在）：

- **公司**：`{sec_name}（{sec_code}）`
- **报告期**：提取字段中的报告年度
- **营业收入**：收入相关字段
- **净利润**：利润相关字段
- **分红方案**：股息、分红相关字段
- **战略要点**：主营业务、发展战略等
- **原文链接**：`met_link`

`extracted_info` 中的所有字段均应完整展示，不做裁剪。

---

## 表格输出规范

当用户要求「导出 CSV」「生成 Excel」「输出表格」时：

1. 调用 API 获取数据（同上述工作流）
2. 将每条年报的 `extracted_info` 字段**扁平化**为一行：
   - 固定列：`证券代码`、`公司名称`、`公告标题`、`公告日期`、`原文链接`
   - 动态列：`extracted_info` 中所有 key（跨条目取并集，缺失填空）
3. 使用 `clawshire_annual_client.py --output csv` 或 `--output excel` 参数直接生成文件
4. 告知用户文件保存路径

**示例指令：**
```bash
# 输出 CSV
python clawshire_annual_client.py list --year 2024 --output csv

# 输出 Excel（需要 openpyxl）
python clawshire_annual_client.py list --year 2024 --output excel

# 单公司年报导出
python clawshire_annual_client.py stock 833359 --output excel
```

**字段扁平化规则：**
- `extracted_info` 为列表时，取第一条（主要提取结果）
- 嵌套字典展开为 `父key_子key` 格式
- 数值保留原始字符串，不做单位转换

---

## 调用限制

- **免费账户**：每个 API Key 共 100 次调用额度
- 年报数据按条计费（每份年报 = 1 次）
- 单次查询建议 `page_size` 不超过 20
- 年报通常每家公司每年 1 份，总量有限，无需分页也可取全

---

## 错误处理

| 错误码 | 含义 | 处理方式 |
|:------:|------|----------|
| 400 | 参数错误 | 检查日期格式（YYYY-MM-DD）和证券代码格式 |
| 401 | API Key 无效 | 提示用户检查 `CLAWSHIRE_API_KEY` 环境变量 |
| 402 | 额度不足 | 提示用户登录控制台充值或申请提额 |
| 404 | 资源不存在 | 确认证券代码是否为北交所（4/8/9 开头），或该公司年报尚未提取 |
| 500 | 服务器错误 | 稍后重试，或访问 https://clawshire.cn 查看服务状态 |

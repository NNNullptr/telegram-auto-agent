# telegram-auto-agent

基于 LLM 的 Telegram 智能 Agent，支持自动客服回复与记账。

## 功能特性

- **智能客服**：LLM 自动识别用户意图，全天候自动答疑与引导
- **快捷记账**：自动提取账目，同步至 SQLite / Notion
- **上下文记忆**：多轮对话逻辑，Agent 回复更贴合语境
- **Excel 导出**：使用 `/export` 命令导出账目为 Excel 文件
- **自动生成订单**：订单确认后转发到管理员
- **自由切换人工/AI模式**: 使用/takeover <chat_id> ,/release <chat_id>	命令切换
- **模块化设计**：支持接入任意 OpenAI 兼容 API（DeepSeek、Ollama、通义千问等）

## 环境准备

- Python 3.10+
- Telegram Bot Token（通过 [@BotFather](https://t.me/botfather) 获取）
- ADMIN_ID (管理员 ID):在 Telegram 中搜索机器人 @userinfobot,向它发送任何消息获得
- OpenAI 兼容 API Key

## 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/NNNullptr/telegram-auto-agent.git
cd telegram-auto-agent
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 填入你的 Token, API Key,Telegram Bot Token 和 ADMIN_ID 
```

### 4. 启动

```bash
python main.py
```

### Docker 部署

```bash
cp .env.example .env
# 编辑 .env
docker compose up -d
```

## Bot 命令

| 命令 | 说明 |
|------|------|
| `/start` | 查看欢迎信息和使用说明 |
| `/export` | 导出单个客户账单记录为 Excel |
| `/exportall` | 导出所有客户账单记录为 Excel |
| takeover <chat_id>  |	手动接管某用户对话 |
| release <chat_id>  |	释放，切回 AI 模式 |
| reply <chat_id>  | <消息>	手动发消息（Reply 不可用时的备选） |
| 自然语言 | 自动识别为客服问答或记账 |

## 配置说明

| 环境变量 | 说明 | 默认值/当前配置 |
|----------|------|-----------------|
| `TELEGRAM_BOT_TOKEN` | Telegram Bot Token | (必填) |
| `LLM_PROVIDER` | LLM 服务商 |  (必填)(默认为openai,支持接入任意 OpenAI 兼容 API,openai, claude, deepseek等)|
| `LLM_API_KEY` | LLM API Key | (必填) |
| `LLM_BASE_URL` | API 地址 |  (必填)`https://api.openai.com/v1` |
| `LLM_MODEL_NAME` | 模型名称 |  (必填)`gpt-4o-mini` |
| `NOTION_ENABLED` | 启用 Notion 同步 | `false` |
| `NOTION_API_KEY` | Notion API Key | - |
| `NOTION_DATABASE_ID` | Notion 数据库 ID | - |
| `MAX_CONTEXT_TURNS` | 最大上下文轮数 | `10` |
| `CONTEXT_EXPIRE_MINUTES` | 上下文过期时间(分钟) | `30` |
| `ADMIN_ID` | 管理员个人 Telegram ID | `0` (必填) |
| `CONFIDENCE_THRESHOLD` | 自动接管置信度阈值 | `默认为0.6,可填0.0到1.0` |
| `ACCOUNTING_BACKENDS` | 记账数据存储后端 | `sqlite` |
| `LOG_LEVEL` | 日志级别 | `INFO` |

## 开源协议

[MIT License](LICENSE)


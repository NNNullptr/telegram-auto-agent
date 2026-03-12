正在完善中
# telegram-auto-agent

基于 LLM 的 Telegram 智能 Agent，支持自动客服回复与自然语言记账。

## 功能特性

- **智能客服**：LLM 自动识别用户意图，全天候自动答疑与引导
- **快捷记账**：自动提取账目，同步至 SQLite / Notion
- **上下文记忆**：多轮对话逻辑，Agent 回复更贴合语境
- **Excel 导出**：使用 `/export` 命令导出账目为 Excel 文件
- **模块化设计**：支持接入任意 OpenAI 兼容 API（DeepSeek、Ollama、通义千问等）

## 环境准备

- Python 3.10+
- Telegram Bot Token（通过 [@BotFather](https://t.me/botfather) 获取）
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
# 编辑 .env 填入你的 Token 和 API Key
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
| `/export` | 导出记账记录为 Excel |
| 自然语言 | 自动识别为客服问答或记账 |

## 配置说明

| 环境变量 | 说明 | 默认值 |
|----------|------|--------|
| `TELEGRAM_BOT_TOKEN` | Telegram Bot Token | (必填) |
| `LLM_API_KEY` | LLM API Key | (必填) |
| `LLM_BASE_URL` | API 地址 | `https://api.openai.com/v1` |
| `LLM_MODEL_NAME` | 模型名称 | `gpt-4o-mini` |
| `NOTION_ENABLED` | 启用 Notion 同步 | `false` |
| `NOTION_API_KEY` | Notion API Key | - |
| `NOTION_DATABASE_ID` | Notion 数据库 ID | - |

## 开源协议

[MIT License](LICENSE)

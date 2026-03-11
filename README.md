# telegram-auto-agent
An LLM-powered Telegram Agent featuring autonomous customer support and natural language financial tracking.基于 LLM 的 Telegram 智能 Agent，支持自动回复客服消息与自然语言记账功能。

# telegram-auto-agent

一个轻量级的 Telegram 智能 Agent，集成了**自动客服回复**与**随手记账**功能。

## 🚀 功能特性

* **智能客服**：基于 LLM 自动识别用户意图，实现全天候自动答疑与引导。
* **快捷记账**：通过自然语言输入（如“午饭 30 元”）自动提取账目并同步至数据库/记账系统。
* **上下文记忆**：支持多轮对话逻辑，使 Agent 回复更贴合语境。
* **易于扩展**：采用模块化设计，方便接入不同的 AI 模型或第三方 API。

## 🛠️ 环境准备

* Python 3.10+
* WSL2 (Ubuntu/Debian) 环境（推荐）
* Telegram Bot Token (通过 [@BotFather](https://t.me/botfather) 获取)

## 📦 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/NNNullptr/telegram-auto-agent.git
cd telegram-auto-agent

```

### 2. 安装依赖

建议使用 `conda` 或 `pyenv` 创建独立环境：

```bash
pip install -r requirements.txt

```

### 3. 配置环境变量

复制 `.env.example` 并重命名为 `.env`，填入你的 API 密钥：

```env
TELEGRAM_BOT_TOKEN=your_token_here
LLM_API_KEY=your_api_key_here
# 其他数据库或记账服务配置

```

### 4. 启动项目

```bash
python main.py

```

## 📂 项目结构

```text
├── src/
│   ├── agents/          # Agent 逻辑核心
│   ├── handlers/        # Telegram 消息处理器
│   ├── services/        # 记账与客服外部服务对接
│   └── utils/           # 工具函数
├── config/              # 配置文件
├── main.py              # 入口文件
└── requirements.txt

```

## 📝 TODO

* [ ] 支持多端账单同步（如 Notion/Excel）
* [ ] 增加图片账单 OCR 识别
* [ ] 优化客服知识库匹配精度

## 📄 开源协议

本项目遵循 [MIT License](https://www.google.com/search?q=LICENSE)。

---

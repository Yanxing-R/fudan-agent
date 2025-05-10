# 复旦校园助手 Agent (Fudan Campus Assistant Agent) - "旦旦学姐"

## 项目简介

本项目是一个基于 Python Flask、阿里云大模型 API 和微信公众号平台的智能问答与服务助手——“旦旦学姐”，旨在为复旦大学新生及在校师生提供便利、友好的校园信息服务和日常对话。Agent 采用可扩展的工具调用（MCP）架构，支持动态知识学习，并能灵活选用不同 LLM 模型。

**目标用户:** 复旦大学新生、在校师生及对校园信息感兴趣的用户。

## 主要功能

1.  **核心知识问答 (通过工具调用实现):**
    * **静态知识查询 (`StaticKnowledgeBaseQueryTool`):**
        * 校园“黑话”解释 (如“旦旦”、“本北”)。
        * 美食推荐 (可按校区/地点筛选)。
        * 未来可扩展至：校园常用地点信息、服务指南、住宿规定、交通信息等。
    * **动态知识学习与查询:**
        * **学习新知识 (`LearnNewInfoTool`):** Agent 能够记住用户明确教授的新信息、问答对或特定主题的知识。
        * **查询已学知识 (`QueryDynamicKnowledgeTool`):** 用户可以查询之前教给 Agent 的信息。
    * **知识库未找到处理:** 当查询的知识在静态或动态库中均未找到时，由 LLM 以“学姐”口吻给出“不清楚/找不到”的友好回复。

2.  **LLM 驱动的对话与决策:**
    * **智能规划与工具选择:** 中心 LLM (Planner) 分析用户意图、对话历史和可用工具列表，决策是调用工具、直接回复还是向用户澄清。
    * **通用对话能力:** 对于无法由特定工具处理的输入，以及日常问候、闲聊等，由 LLM 使用“旦旦学姐”人设进行开放式、自然的对话回复。
    * **上下文感知:** 通过维护对话历史，Agent 能在一定程度上理解多轮对话的上下文。

3.  **生动的表达风格:**
    * **“旦旦学姐”人设:** 通过精心设计的 Prompt，引导 LLM 在所有回复中扮演热情、友善、乐于助人的复旦学姐角色。
    * **Emoji 使用:** LLM 被鼓励在回复中适当使用 Emoji 表情符号，增加对话的生动性和亲和力。

4.  **微信集成:**
    * 作为微信公众号（测试号）后端运行，用户通过向公众号发送消息进行交互。
    * 处理新用户关注事件，发送欢迎语。

5.  **可扩展架构:**
    * **MCP (Multi-Capability Platform) 核心:** 所有功能（包括知识查询）均封装为可拔插的“工具”。
    * **工具注册:** 使用装饰器 (`@register_tool`) 动态注册工具，方便扩展。
    * **多 LLM 支持:** 允许为不同任务（规划、回复生成、知识学习）配置和调用不同的 LLM 模型。
    * **A2A (Agent-to-Agent) 预留接口:** 将与其他 Agent 的交互也视为一种特殊工具，为未来集成做好准备。

## 技术栈

* **后端框架:** Python, Flask
* **核心 AI 引擎:** 阿里云大模型 API (DashScope / 通义千问系列)
    * 用于任务规划、工具选择、自然语言理解、回复生成、知识结构化等。
* **微信交互:** `wechatpy` 库
* **工具与知识库:**
    * 自定义工具模块 (`tools.py`)
    * 本地知识库模块 (`knowledge_base.py`)
    * 静态知识存储: JSON 文件 (位于 `data/` 目录)
    * 动态知识存储: JSON 文件 (位于 `data/` 目录，如 `dynamic_learned_kb.json`)
* **部署环境:**
    * 阿里云轻量应用服务器 (示例配置: 2vCPU, 4GiB RAM)
    * Miniconda (用于在服务器上管理独立的 Python 环境)
    * Python 3.11 (或更高，通过 Miniconda 安装)
* **WSGI 服务器:** Gunicorn
* **版本控制:** Git, GitHub

## 项目结构

fudan_agent/├── app.py             # Flask 主应用，核心编排逻辑，处理 Web 请求和微信回调├── llm_interface.py   # 封装与阿里云 DashScope API 交互，支持多LLM调用├── tools.py           # 定义和注册 Agent 可用的工具 (使用装饰器)├── knowledge_base.py # 加载和查询静态/动态知识库的函数├── prompts.py         # 存放指导 LLM 进行规划、回复生成等的 Prompt 模板├── requirements.txt   # Python 依赖库列表├── data/              # 存放知识库文件│   ├── slang.json     # 黑话词条 (静态)│   ├── food.json      # 美食信息 (静态)│   └── dynamic_learned_kb.json # 用户教授的知识 (动态)└── flask_app.log      # (运行时生成) Gunicorn 应用日志文件
## 安装与设置

**1. 服务器环境准备 (以已安装 Miniconda 的 Linux 服务器为例)**

* **创建/激活 Conda 环境:**
    ```bash
    conda create --name fudan_assistant python=3.11 # 如果是首次创建
    conda activate fudan_assistant
    ```
* **克隆/上传项目代码:**
    * 推荐使用 Git:
        ```bash
        # 在服务器上 (如果首次部署)
        # git clone [https://github.com/YourUsername/fudan-agent.git](https://github.com/YourUsername/fudan-agent.git) /path/to/deploy/fudan_agent
        # cd /path/to/deploy/fudan_agent
        # 如果是更新
        # git pull origin master # 或你的主分支名
        ```
    * 或者使用 `scp` 上传本地更新后的代码。
* **安装依赖:**
    ```bash
    pip install -r requirements.txt
    ```

**2. 配置**

* **阿里云 API Key:**
    * 在服务器上设置环境变量 `DASHSCOPE_API_KEY` 为你的阿里云 API Key。
    * (可选) 设置 `PLANNER_LLM_MODEL`, `RESPONSE_LLM_MODEL`, `LEARNER_LLM_MODEL` 环境变量以指定不同任务的 LLM 模型。
* **微信 Token:**
    * 在服务器上设置环境变量 `WECHAT_TOKEN` 为你自定义的微信 Token 字符串。
    * 或者，直接在 `app.py` 中修改 `WECHAT_TOKEN` 的默认值（但不推荐硬编码敏感信息）。
* **知识库文件 (`data/` 目录):**
    * 确保 `slang.json`, `food.json` 存在并包含初始数据。
    * `dynamic_learned_kb.json` 会在 Agent 学习新知识时自动创建/更新。

**3. 防火墙**

* 确保阿里云服务器防火墙（安全组）允许 **TCP 端口 80** 的入站连接。

## 运行

* **确保 Conda 环境已激活:** `conda activate fudan_assistant`
* **确保 API Key 和微信 Token 环境变量已设置。**
* **使用 Gunicorn 启动 (后台运行):**
    ```bash
    nohup gunicorn -w 2 -b 0.0.0.0:80 app:app > flask_app.log 2>&1 &
    ```
    * 使用 `tail -f flask_app.log` 查看实时日志。

## 微信公众号对接

1.  **获取微信测试号。**
2.  **配置服务器:**
    * 在测试号管理页面的“接口配置信息”栏：
        * **URL:** `http://<你的服务器公网IP>/wechat`
        * **Token:** 与你环境变量或 `app.py` 中设置的 `WECHAT_TOKEN` 完全一致。
    * 提交验证，检查服务器日志确认。
    * 启用服务器配置。

## 使用说明

* 关注配置好的微信公众号。
* 直接发送文本消息进行交互，例如：
    * “你好呀，旦旦学姐！”
    * “毛概是什么意思？”
    * “邯郸校区附近有什么好吃的？”
    * “复旦的猫多吗？”
    * “教你个事，明天可能会下雨。”
    * “我上次教你我最喜欢的书是什么来着？”

## 注意事项

* **API Key 安全:** 优先使用环境变量管理敏感凭证。
* **知识库质量:** Agent 的核心价值很大程度上依赖于静态知识库的质量和动态知识库的学习效果。
* **Prompt 工程:** `prompts.py` 中的 Prompt 设计对 LLM 的行为至关重要，需要持续优化。
* **对话历史:** 当前使用简单的内存对话历史，服务器重启会丢失。生产环境可考虑 Redis 等持久化方案。
* **错误处理与健壮性:** 当前错误处理较为基础，可进一步完善。
* **并发与性能:** 关注 Gunicorn worker 数量和阿里云 API 的调用限制。

---


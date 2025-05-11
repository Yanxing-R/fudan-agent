# 复旦校园助手 Agent (Fudan Campus Assistant Agent) - "旦旦学姐"

## 项目简介

本项目是一个基于 Python Flask、大型语言模型 (LLM) API (例如阿里云 DashScope 通义千问系列) 和可选的微信公众号平台的智能问答与服务助手——“旦旦学姐”。它旨在为复旦大学的学生及对校园信息感兴趣的用户提供便利、友好的校园信息服务和日常对话。

Agent 采用多 Agent 协作架构，定义在 `multi_agent_system.py` 中。系统支持通过 `agent_tools.py` 中定义的、可扩展的工具集进行功能扩展，通过 `knowledge_base.py` 实现动态知识学习与查询，并能通过 `llm_interface.py` 灵活选用不同 LLM 模型。项目还引入了内容审核机制以确保交互的友好性。

**目标用户**: 复旦大学学生、教职工及对复旦校园信息感兴趣的任何人。

## 主要功能

1.  **多 Agent 协作系统 (定义于 `multi_agent_system.py`)**:
    * **`FudanUserProxyAgent`**: 作为用户与系统交互的直接接口，负责接收用户输入和返回最终答案。
    * **`ReviewAgent`**: 对用户输入进行内容审核，判断是否包含不当言论，确保对话环境的友好性。
    * **`FudanPlannerAgent`**: 系统的“大脑”，在用户输入通过审核后，分析用户意图、对话历史和可用工具列表，决策是直接回复、请求用户澄清，还是制定一个详细的计划来调用一个或多个专长 Agent。
    * **专长 Agents (Specialist Agents)**:
        * **`KnowledgeAgent`**: 专责处理与复旦大学相关的知识问答（静态和动态）和学习新知识。它内部调用 `agent_tools.py` 中定义的知识相关工具。
        * **`UtilityAgent`**: 专责执行通用的辅助工具，如获取时间、计算、查询天气等。它内部调用 `agent_tools.py` 中定义的通用工具。
    * **`Orchestrator`**: 系统的调度核心，管理 Agent 之间的消息传递、会话状态以及计划的执行流程。采用单例模式 (`get_orchestrator()`) 获取实例。

2.  **核心知识问答与服务 (通过 `agent_tools.py` 中定义的工具实现)**:
    * **静态知识查询 (`StaticKnowledgeBaseQueryTool`)**:
        * 校园“黑话”解释 (例如，“毛概”、“本北”)。
        * 美食推荐 (可按校区/地点筛选，或随机推荐)。
        * 校园官方信息查询 (如图书馆开放时间)。
        * *工具返回结构化结果 (包含 `status` 和 `data`)*。
    * **动态知识学习与查询**:
        * **学习新知识 (`LearnNewInfoTool`)**: Agent 能够记住用户明确教授的新信息、问答对或特定主题的知识，并存入该用户的个人知识笔记中（按类别区分，需要 `user_id`）。*操作结果返回结构化信息*。
        * **查询已学知识 (`QueryDynamicKnowledgeTool`)**: 用户可以查询之前教给 Agent 的、存储在其个人笔记或共享动态知识库中的信息（需要 `user_id`）。系统会优先查找个人笔记，然后查找共享动态知识。*查询结果返回结构化信息，包含来源和状态*。
    * **其他实用工具**:
        * 获取当前时间 (`GetCurrentTimeTool`)。
        * 简单计算器 (`CalculatorTool`)。
        * 天气预报 (`GetWeatherForecastTool`) (当前为模拟数据)。
        * *这些工具同样返回结构化结果*。

3.  **LLM 驱动的对话与决策 (`llm_interface.py` & `prompts.py`)**:
    * **智能规划与工具选择**: `FudanPlannerAgent` 利用 LLM (通过 `get_llm_decision`) 分析用户意图，并参考 `Orchestrator` 提供的专长 Agent 及其内部工具描述，来决定最合适的行动 (直接回复、澄清或制定执行计划)。
    * **上下文感知与个性化**: 通过维护对话历史 (由 `app.py` 管理) 和用户专属的个人知识笔记 (需要 `user_id` 传递至相关工具)，Agent 能在一定程度上理解多轮对话的上下文并提供更个性化的服务。
    * **最终答案生成**: `FudanPlannerAgent` 综合各步骤执行结果 (现在是结构化的字典)，并结合原始问题，调用 LLM (通过 `get_final_response`) 生成具有“旦旦学姐”人设的最终回复。`get_final_response` 现在可以接收 `task_outcome_status` 参数，以更准确地选择回复模板（如 `PERSONA_NOT_FOUND_TEMPLATE`）。
    * **内容审核**: `ReviewAgent` 调用 LLM (通过 `check_input_appropriateness`) 对用户输入进行审查。

4.  **生动的表达风格**:
    * **“旦旦学姐”人设**: 通过 `prompts.py` 中精心设计的 Prompt，引导 LLM 在所有回复中扮演热情、友善、乐于助人的复旦学姐角色。
    * **Emoji 使用**: LLM 被鼓励在回复中适当使用 Emoji 表情符号，增加对话的生动性和亲和力。

5.  **微信集成 (可选, `app.py`)**:
    * 可作为微信公众号（例如测试号）后端运行，用户通过向公众号发送消息进行交互。
    * 处理新用户关注事件，发送欢迎语。

6.  **可扩展架构**:
    * **统一工具定义**: 所有功能均封装为 `agent_tools.py` 中定义的、继承自 `Tool` 基类的工具类，并通过 `@tool` 装饰器自动注册。工具的 `execute` 方法现在返回结构化的字典。
    * **模块化设计**: 清晰分离了应用逻辑 (`app.py`)、LLM接口 (`llm_interface.py`)、多Agent系统 (`multi_agent_system.py`)、工具 (`agent_tools.py`)、知识库 (`knowledge_base.py`) 和提示 (`prompts.py`)。
    * **多LLM模型支持**: `llm_interface.py` 中可以为不同任务（规划、回复生成、审核）配置和调用不同的 LLM 模型。

## 技术栈

* **后端框架**: Python, Flask
* **核心 AI 引擎**: 大型语言模型 API (如阿里云 DashScope / 通义千问系列)
    * 用于任务规划、工具选择、自然语言理解、回复生成、内容审核、知识结构化等。
* **微信交互 (可选)**: `wechatpy` 库
* **工具与知识库**:
    * 自定义工具模块: `agent_tools.py`
    * 知识库模块: `knowledge_base.py`
    * 静态知识存储: JSON 文件 (位于 `data/` 目录, 例如 `static_slang.json`, `static_food.json`)
    * 共享动态知识存储: JSON 文件 (位于 `data/` 目录, 例如 `dynamic_shared_slang.json`)
    * 个人动态知识存储: JSON 文件 (位于 `data/personal_kbs/{user_id}/{category}.json`)
* **并发处理**: `threading` (用于 Orchestrator 的会话完成事件和单例锁)
* **部署环境 (示例)**:
    * Linux 服务器 (例如阿里云 ECS, 轻量应用服务器)
    * Python 3.9+ (推荐使用 Conda 或 venv 管理环境)
    * WSGI 服务器 (推荐生产环境): Gunicorn, uWSGI
* **版本控制**: Git, GitHub

## 项目结构
fudan_agent/
├── app.py                     # Flask 主应用，微信回调，HTTP接口，应用初始化
├── multi_agent_system.py      # 定义 Agent 基类、所有具体 Agent 和 Orchestrator (权威来源)
├── agent_tools.py             # 定义和注册所有可用的工具类
├── knowledge_base.py          # 加载和管理静态、共享动态、个人动态知识库的函数
├── llm_interface.py           # 封装与 LLM API 的交互，支持多LLM模型配置
├── prompts.py                 # 存放指导 LLM 进行规划、回复生成、审核等的 Prompt 模板
├── requirements.txt           # Python 依赖库列表
├── data/                      # 存放知识库文件
│   ├── static_slang.json      # 示例：黑话词条 (静态)
│   ├── static_food.json       # 示例：美食信息 (静态)
│   ├── static_campus_info.json # 示例：校园官方信息 (静态)
│   ├── dynamic_shared_slang.json # 示例：共享动态知识-黑话
│   └── personal_kbs/          # 存放个人知识库的目录
│       └── {user_id}/         # 每个用户的个人知识库
│           └── my_notes.json  # 示例：某用户的个人笔记
└── logs/                      # (可选) 存放应用日志的目录 (例如 gunicorn_error.log)
## 安装与设置

1.  **环境准备** (以已安装 Conda 的 Linux 服务器为例)
    * 创建/激活 Conda 环境:
        ```bash
        conda create --name fudan_agent_env python=3.10 # 推荐 Python 3.9+
        conda activate fudan_agent_env
        ```
    * 克隆项目代码:
        ```bash
        git clone <your_repository_url> fudan_agent
        cd fudan_agent
        ```
    * 安装依赖:
        ```bash
        pip install -r requirements.txt
        ```

2.  **配置环境变量**
    在服务器上设置以下环境变量。推荐使用 `.env` 文件配合 `python-dotenv` 库进行管理（需自行添加该库到 `requirements.txt` 并修改 `app.py` 以加载），或者直接在启动脚本中设置。
    * `DASHSCOPE_API_KEY`: (**必须**) 你的 LLM 服务提供商的 API Key (例如阿里云 DashScope API Key)。
    * `WECHAT_TOKEN`: (可选, 用于微信集成) 你在微信公众号后台配置的 Token 字符串。
    * `FLASK_ENV`: (可选, 推荐) 设置为 `development` 或 `production`。
    * `MAX_HISTORY_TURNS`: (可选) 对话历史保留的轮次，默认为3 (在 `app.py` 中设置)。
    * LLM 模型配置 (可选, 在 `llm_interface.py` 中有默认值，可通过环境变量覆盖):
        * `PLANNER_LLM_MODEL`
        * `RESPONSE_LLM_MODEL`
        * `MODERATOR_LLM_MODEL`

3.  **初始化知识库目录和文件**
    * 确保 `data/` 目录存在。
    * 如果需要，可以预先创建 `data/personal_kbs/` 目录。
    * 根据 `knowledge_base.py` 中 `STATIC_KB_CONFIG` 的定义，在 `data/` 目录下放置初始的静态知识库 JSON 文件 (如 `static_slang.json`, `static_food.json`, `static_campus_info.json`)。如果文件不存在，系统会尝试使用默认空数据加载。
    * 共享动态知识库文件（如 `dynamic_shared_slang.json`）如果不存在，系统也会在首次加载时尝试创建空结构。

4.  **(可选) 防火墙配置**
    如果通过公网访问，确保服务器防火墙（安全组）允许应用运行端口（例如 Flask 默认的 5000 或 Gunicorn 配置的 80/8000 端口）的入站连接。

## 运行

1.  **开发模式** (使用 Flask 内置服务器):
    * 确保 Conda 环境已激活。
    * 确保必要的环境变量已设置。
    * 在项目根目录下运行：
        ```bash
        export FLASK_APP=app.py # 或者 python -m flask run
        export FLASK_ENV=development
        flask run --host=0.0.0.0 --port=5000
        ```
    应用将在 `http://0.0.0.0:5000` 上运行。

2.  **生产模式** (推荐使用 Gunicorn):
    * 确保 Conda 环境已激活。
    * 确保必要的环境变量已设置。
    * 使用 Gunicorn 启动 (示例):
        ```bash
        # 确保 logs 目录存在
        mkdir -p logs 
        gunicorn -w 4 -b 0.0.0.0:8000 "app:app" --log-level info --access-logfile logs/gunicorn_access.log --error-logfile logs/gunicorn_error.log --daemon
        ```
        * `-w 4`: 启动4个 worker 进程 (根据服务器CPU核心数调整)。
        * `-b 0.0.0.0:8000`: 绑定到所有网络接口的8000端口。
        * `"app:app"`: 指定 Flask 应用实例 (文件名 `app.py` 中的 `app` 对象)。
        * `--log-level info`: 设置日志级别。
        * `--access-logfile` 和 `--error-logfile`: 指定日志文件路径。
        * `--daemon`: 后台运行。
    * 可以使用 `tail -f logs/gunicorn_error.log` 查看实时错误日志。

## 使用说明

1.  **HTTP 接口测试** (通过 `/chat_text` 路由):
    * 可以使用 Postman 或 curl 等工具向 `http://<服务器地址>:<端口>/chat_text` 发送 POST 请求，请求体为纯文本用户输入。
    * 示例:
        ```bash
        curl -X POST -H "Content-Type: text/plain; charset=utf-8" --data "你好呀，旦旦学姐！" http://localhost:5000/chat_text
        curl -X POST -H "Content-Type: text/plain; charset=utf-8" --data "江湾校区有什么好吃的？" http://localhost:5000/chat_text
        ```

2.  **微信公众号交互**:
    * 申请一个微信测试号或已认证的服务号/订阅号。
    * 在微信公众号后台的“基本配置”或“开发设置”中：
        * **服务器地址(URL)**: `http://<你的服务器公网IP或域名>:<端口号>/wechat` (例如 `http://yourdomain.com/wechat` 或 `http://xx.xx.xx.xx:8000/wechat`)。
        * **令牌(Token)**: 与你环境变量 `WECHAT_TOKEN` 中设置的值完全一致。
        * **消息加解密方式**: 根据需要选择（当前代码示例未使用加密）。
    * 提交配置。微信服务器会向你的 URL 发送一个 GET 请求进行验证。确保你的应用正在运行并且能够正确响应此验证请求。
    * 验证通过后，启用服务器配置。
    * 关注配置好的微信公众号，直接发送文本消息进行交互，例如：
        * “你好呀，旦旦学姐！”
        * “毛概是什么意思？”
        * “邯郸校区附近有什么好吃的？”
        * “复旦的伙食怎么样？”
        * “教你个新东西：复旦的猫咪都很可爱！” (触发学习工具)
        * “我上次教你的关于复旦猫咪的事情是什么来着？” (触发动态知识查询)

## 注意事项与未来工作

* **API Key 安全**: 优先使用环境变量或更安全的密钥管理服务来管理敏感凭证。
* **知识库质量与维护**: Agent 的核心价值很大程度上依赖于知识库的质量、覆盖面和更新频率。`knowledge_base.py` 中的 `review_and_promote_knowledge` 函数目前仅为示例，实际应用中需要更完善的知识审核和晋升机制。
* **Prompt 工程**: `prompts.py` 中的 Prompt 设计对 LLM 的行为至关重要，可能需要根据实际效果持续迭代优化。
* **对话历史持久化**: 当前使用简单的内存对话历史 (`app.py` 中的 `conversation_history`)，服务器重启会丢失。生产环境可考虑使用 Redis、数据库等持久化方案。
* **错误处理与健壮性**: 当前错误处理已有所增强，但仍可进一步完善，例如更细致的异常捕获和用户友好的错误提示。
* **并发与性能**: 关注 Gunicorn worker 数量、LLM API 的调用限制和响应时间。对于高并发场景，可能需要异步任务队列（如 Celery）。
* **异步工具执行**: 对于耗时较长的工具，可以考虑将其执行过程异步化，避免阻塞主处理流程。
* **更复杂的计划执行**: 当前计划是顺序执行的。未来可以考虑支持并行步骤或更复杂的依赖关系。
* **ReviewAgent 增强**: `ReviewAgent` 目前主要用于内容审核，未来可以扩展其能力，例如对用户教授的知识进行事实性校验或质量评估，再决定是否将其提升到共享动态知识库。
* **测试覆盖**: 增加单元测试和集成测试，确保各模块和整体流程的正确性。


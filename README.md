# 复旦校园助手 Agent (Fudan Campus Assistant Agent)

## 项目简介

本项目是一个基于 Python Flask、阿里云大模型 API 和微信公众号平台的智能问答助手，旨在为复旦大学新生提供便利服务。主要功能包括解释复旦校园“黑话”和推荐校园周边的美食信息。

**目标用户:** 复旦大学新生及对校园信息感兴趣的用户。

## 主要功能

* **校园“黑话”解释 (`ask_slang_explanation`)**:

    * **接收:** 用户通过微信发送包含复旦特定“黑话”（如“旦旦”、“本北”、“毛概”等）的问题。
    * **理解:** 利用**阿里云大模型 API (通义千问)** 进行自然语言理解（NLU），识别出用户的意图是想查询黑话，并提取出具体的“黑话词条”（`slang_term`）。
    * **查询:** 在你预先准备好的**知识库**（`data/slang.json` 文件）中查找这个词条。
    * **回复:** 如果找到对应的解释，就将解释内容通过微信回复给用户；如果知识库里没有收录这个词，会回复一个类似“抱歉，我还不知道……”的提示。

* **校园周边美食推荐 (`ask_food_recommendation`)**:

    * **接收:** 用户发送关于寻找美食的请求，可能包含地点信息（如“邯郸校区附近”、“江湾食堂”）。
    * **理解:** 同样通过**阿里云 LLM API** 进行 NLU，识别意图为美食推荐，并提取地点（`location`）等实体信息。
    * **交互/查询:**
        * 如果用户没有提供明确地点，Agent 会反问用户想在哪附近寻找。
        * 如果提供了地点，Agent 会查询你准备好的**美食知识库**（`data/food.json` 或 `data/food.csv` 文件），根据地点筛选合适的餐馆、食堂窗口或外卖信息。
    * **回复:** 将筛选出的美食信息（如名称、简介、大致位置等）通过微信回复给用户；如果对应地点没有数据，则回复未找到。
    * **效果依赖:** 这个功能的推荐质量**完全取决于**你和组员收集录入的美食数据的**丰富程度和准确性**。

* **基本对话能力:**
    * **问候 (`greet`)**: 能回应用户的问好，例如回复“你好！有什么可以帮你的吗？”。
    * **告别 (`goodbye`)**: 能回应用户的告别语，例如回复“再见！”。
    * **未知意图处理 (`unknown`/`fallback`)**: 当用户的输入无法被 NLU 理解为上述任何一种意图时，会给出一个通用的回复，表明自己暂时无法理解，并提示可以问关于黑话或美食的问题。
    * **关注欢迎 (Event Handling)**: 当有新用户关注公众号时，会自动发送一条欢迎语（我们在代码里加入了这个处理）。

## 技术栈

* **后端框架:** Python, Flask
* **自然语言理解 (NLU):** 阿里云大模型 API (DashScope / 通义千问)
* **微信交互:** `wechatpy` 库
* **HTTP 请求:** `requests` 库 (或由 `dashscope` SDK 内部处理)
* **数据处理 (可能):** `pandas` (如果使用 CSV 作为知识库)
* **部署环境:**
    * 阿里云轻量应用服务器 (示例配置: 2vCPU, 4GiB RAM)
    * Miniconda (用于在服务器上管理独立的 Python 环境)
    * Python 3.11 (通过 Miniconda 安装)
* **WSGI 服务器:** Gunicorn (或 Waitress)

## 项目结构

fudan_agent/
├── app.py             # Flask 主应用，处理 Web 请求和微信消息回调
├── llm_interface.py   # 封装与阿里云 DashScope API 交互的逻辑 (NLU)
├── knowledge_base.py # 加载和查询本地知识库 (黑话、美食) 的函数
├── prompts.py         # 存放用于指导 LLM 进行 NLU 的 Prompt 模板
├── requirements.txt   # Python 依赖库列表
├── data/              # 存放知识库文件
│   ├── slang.json     # 黑话词条及其解释 (示例)
│   └── food.json      # 美食信息 (示例，或使用 food.csv)
└── flask_app.log      # (运行时生成) Gunicorn 应用日志文件
## 安装与设置

**1. 服务器环境准备 (以已安装 Miniconda 的 Linux 服务器为例)**

* **创建 Conda 环境:**
    ```bash
    conda create --name fudan_assistant python=3.11
    conda activate fudan_assistant
    ```
* **克隆/上传项目代码:**
    ```bash
    # 如果使用 Git
    # git clone <your-repo-url> /path/to/deploy/fudan_agent
    # cd /path/to/deploy/fudan_agent

    # 如果使用 scp (在本地运行)
    # scp -r ./fudan_agent user@<server_ip>:/path/to/deploy/
    # ssh user@<server_ip>
    # cd /path/to/deploy/fudan_agent
    ```
* **安装依赖:**
    ```bash
    # 确保 fudan_assistant 环境已激活
    pip install -r requirements.txt
    ```

**2. 配置**

* **阿里云 API Key:**
    * 获取你的阿里云 DashScope API Key。
    * 在**服务器上**设置环境变量 `DASHSCOPE_API_KEY`。推荐将 `export DASHSCOPE_API_KEY='sk-yourkey'` 添加到 `~/.bashrc` 并执行 `source ~/.bashrc`。
* **微信 Token:**
    * 选择一个自定义的、安全的字符串作为你的微信 Token (例如: `MyFudanWechatToken123`)。
    * 编辑服务器上的 `app.py` 文件，找到 `WECHAT_TOKEN = "..."` 这一行，将你的 Token 填入引号中。
* **知识库文件 (`data/` 目录):**
    * 根据 `knowledge_base.py` 的实现，准备 `slang.json` 和 `food.json` (或 `food.csv`) 文件。
    * **必须填充有效数据**，否则黑话解释和美食推荐功能无法返回实际内容。参考示例格式填充复旦相关信息。

**3. 防火墙**

* 确保你的阿里云服务器防火墙（安全组）允许 **TCP 端口 80** 的入站连接。

## 运行

* **确保 Conda 环境已激活:** `conda activate fudan_assistant`
* **确保 API Key 环境变量已设置。**
* **使用 Gunicorn 启动 (后台运行):**
    ```bash
    # 将日志输出到 flask_app.log 文件
    nohup gunicorn -w 2 -b 0.0.0.0:80 app:app > flask_app.log 2>&1 &
    ```
    * 可以使用 `tail -f flask_app.log` 查看实时日志。
    * 使用 `ps aux | grep gunicorn` 查看进程，`kill <pid>` 停止进程。
    * (推荐使用 `screen` 或 `tmux` 管理后台会话)

## 微信公众号对接

1.  **获取微信测试号:** 访问 `https://mp.weixin.qq.com/debug/cgi-bin/sandbox?t=sandbox/login`。
2.  **配置服务器:**
    * 在测试号管理页面的“接口配置信息”栏：
        * **URL:** 填写 `http://<你的服务器公网IP>/wechat` (必须是公网 IP，路径为 `/wechat`)。
        * **Token:** 填写你在 `app.py` 中设置的**完全相同**的 `WECHAT_TOKEN` 字符串。
    * 点击“提交”进行验证。检查服务器日志 (`flask_app.log`) 确认收到 GET 请求且无签名错误。
    * 验证成功后，点击“启用”服务器配置。
3.  **测试:** 关注测试号二维码，发送消息进行交互。

## 使用说明

* 关注配置好的微信公众号（测试号）。
* 直接在对话框发送文本消息即可与 Agent 交互。
    * 示例：“你好”
    * 示例：“旦旦是什么意思”
    * 示例：“本部北区附近有什么好吃的”

## 注意事项

* **API Key 安全:** 切勿将阿里云 API Key 硬编码在代码中或泄露。使用环境变量是推荐做法。
* **知识库:** Agent 的核心价值在于 `data/` 目录下的知识库内容，需要持续维护和更新。
* **错误处理:** 当前的错误处理比较基础，生产环境可能需要更详细的日志记录和错误恢复机制。
* **并发性能:** Gunicorn 的 worker 数量可以根据服务器负载调整。阿里云 API 本身也可能有调用频率限制。
* **HTTPS:** 微信**正式**公众号通常要求使用 HTTPS (443 端口)。如需升级，需要在服务器上配置 SSL 证书（如使用 Let's Encrypt）并可能需要 Nginx 等反向代理。测试号使用 HTTP (80 端口) 即可。


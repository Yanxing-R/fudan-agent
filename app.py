# app.py
from flask import Flask, request, abort, jsonify
from wechatpy import parse_message, create_reply
from wechatpy.utils import check_signature
from wechatpy.exceptions import InvalidSignatureException

# 确保在 multi_agent_system 之前导入 agent_tools，以便工具先注册
import agent_tools 
import llm_interface
import knowledge_base
import multi_agent_system # 现在应该从这里导入 Agent 类和 Orchestrator
import json
import traceback
import os

app = Flask(__name__)
# 将 app 实例传递给 multi_agent_system 模块，以便 Orchestrator 可以回调
# 这需要在 multi_agent_system.py 中有一个全局变量 app_instance = None
# 并在 Orchestrator 初始化或 set_app_context 时使用它
if hasattr(multi_agent_system, 'orchestrator_instance') and multi_agent_system.orchestrator_instance:
    if hasattr(multi_agent_system.orchestrator_instance, 'set_app_context'):
        multi_agent_system.orchestrator_instance.set_app_context(app)
    else:
        # 如果 Orchestrator 实例已存在但没有 set_app_context, 也可以直接赋值
        # 但更好的方式是 Orchestrator 提供一个方法来设置
        # multi_agent_system.orchestrator_instance.app_context = app
        print("警告: Orchestrator 实例已存在，但缺少 set_app_context 方法。尝试直接设置 app_context。")
        # setattr(multi_agent_system.orchestrator_instance, 'app_context', app) # 这种方式不太好
elif hasattr(multi_agent_system, 'get_orchestrator'): # 如果是通过函数获取单例
    # 确保在 get_orchestrator 内部或之后设置 app_context
    pass 
else:
    print("警告: multi_agent_system.py 中设置 app_context 的机制可能不兼容。")


# --- 微信配置 ---
WECHAT_TOKEN = os.getenv("WECHAT_TOKEN", "YourDefaultWechatTokenInAppPy")
if WECHAT_TOKEN == "YourDefaultWechatTokenInAppPy":
    print("警告：微信 Token 使用了 app.py 中的默认值，请检查环境变量。")

# --- 对话历史 ---
conversation_history = {} 
MAX_HISTORY_TURNS = int(os.getenv("MAX_HISTORY_TURNS", 3))

def get_user_chat_history_for_agent(user_id: str) -> str:
    history = conversation_history.get(user_id, [])
    if not history: return "无之前的对话内容。"
    formatted_parts = []
    for turn in history[-MAX_HISTORY_TURNS:]:
        formatted_parts.append(f"用户: {turn['user']}")
        formatted_parts.append(f"学姐: {turn['assistant']}")
    return "\n".join(formatted_parts)

def add_to_user_history(user_id: str, user_msg: str, assistant_msg: str):
    if user_id not in conversation_history: conversation_history[user_id] = []
    conversation_history[user_id].append({"user": user_msg, "assistant": assistant_msg})
    if len(conversation_history[user_id]) > MAX_HISTORY_TURNS:
        conversation_history[user_id].pop(0)

# --- 应用组件初始化 ---
main_orchestrator = None
user_proxy_agent = None
_app_components_initialized = False

def initialize_app_components():
    global main_orchestrator, user_proxy_agent, _app_components_initialized
    if _app_components_initialized: return

    print("--- 应用组件初始化开始 ---")
    knowledge_base.load_all_data()
    main_orchestrator = multi_agent_system.get_orchestrator() # 这会创建 Orchestrator 和所有内部 Agent
    
    if main_orchestrator and hasattr(main_orchestrator, 'set_app_context'):
        main_orchestrator.set_app_context(app) 
        print("Orchestrator 应用上下文已成功设置。")
    
    user_proxy_agent = main_orchestrator.agents.get("FudanUserProxyAgent")
    
    if not user_proxy_agent:
        print("严重错误: FudanUserProxyAgent 未能在 Orchestrator 中正确初始化。")
    else:
        print("FudanUserProxyAgent 已获取。")
    
    # PlannerAgent 的 tools_description_for_llm 应该在 Orchestrator._initialize_agents 中设置
    # 因为它依赖于所有 Specialist Agents (包括新的 KnowledgeAgent 和 UtilityAgent) 都已创建
    # 并且 Orchestrator 的 get_specialist_agent_capabilities_description 方法可以访问它们
    
    print("--- 应用组件初始化完成 ---")
    _app_components_initialized = True

# 使用 @app.cli.command("init-mas") 可以在 Flask CLI 中手动初始化
# 或者在第一次请求前初始化 (对于开发服务器)
# 对于生产环境的 Gunicorn，初始化应该在 worker 启动时进行，
# 通常意味着在模块级别执行或通过 app factory 模式。
# 为了简单，我们继续使用 before_first_request 的替代方式。
# Flask 2.3+ 中 @app.before_request 可以用 if not _app_components_initialized: 来模拟
# 或者更简单的方式是在每个请求处理函数开始时检查并调用。

def ensure_initialized():
    """确保核心组件已初始化"""
    if not _app_components_initialized:
        initialize_app_components()
    if not main_orchestrator or not user_proxy_agent:
        # 如果在请求处理中发现未初始化，这是一个严重问题
        print("严重错误：核心 Agent 组件在请求时仍未初始化！")
        # 可以考虑抛出异常或返回一个标准的服务器错误
        abort(503, description="Agent 系统正在初始化，请稍后重试。")


# --- /chat_text 路由 (用于本地测试) ---
@app.route('/chat_text', methods=['POST'])
def chat_text_endpoint():
    ensure_initialized()
    try:
        user_input = request.data.decode('utf-8')
        if not user_input: return jsonify({"response": "学弟/学妹你想问点什么呀？🤔"}), 400
        user_id = "local_test_user_chat_text" 
        session_id = user_proxy_agent.initiate_task(user_id, user_input)
        final_reply = main_orchestrator.run_session_until_completion(session_id, timeout_seconds=180)
        add_to_user_history(user_id, user_input, final_reply)
        print(f"--- Debug App (Text): Replying to {user_id} with: {final_reply!r} ---")
        return jsonify({"response": final_reply})
    except UnicodeDecodeError as e: print(f"--- Error App (Text): Decode failed: {e} ---"); traceback.print_exc(); return jsonify({"response": "学姐我这边好像有点乱码了，你发的是文字吗？😵"}), 400
    except Exception as e: print(f"--- Error App (Text): Top level processing failed: {e} ---"); traceback.print_exc(); return jsonify({"response": "呜呜，系统好像出了点大问题，学姐我先去看看，你稍等一下下哈~ 🛠️"}), 500

# --- /wechat 路由 (微信公众号回调) ---
@app.route('/wechat', methods=['GET', 'POST'])
def wechat_webhook():
    ensure_initialized()
    signature = request.args.get('signature', ''); timestamp = request.args.get('timestamp', ''); nonce = request.args.get('nonce', '')
    try: check_signature(WECHAT_TOKEN, signature, timestamp, nonce)
    except InvalidSignatureException: print("微信签名校验失败！"); abort(403)
    if request.method == 'GET': print("微信服务器验证成功。"); return request.args.get('echostr', '')
    elif request.method == 'POST':
        msg = None; user_id = "unknown_wechat_user"
        try:
            msg = parse_message(request.data); user_id = msg.source 
            print(f"--- 微信消息收到 --- 类型: {msg.type}, 来自: {user_id}")
            final_reply_text = "学姐暂时无法处理你的请求哦，请稍后再试~ 😥" 
            if not user_proxy_agent: print("错误: /wechat - UserProxyAgent 未初始化!"); final_reply_text = "抱歉，旦旦学姐的系统正在维护中，请稍后再来哦！"
            elif msg.type == 'text':
                user_input = msg.content
                session_id = user_proxy_agent.initiate_task(user_id, user_input)
                final_reply_text = main_orchestrator.run_session_until_completion(session_id, timeout_seconds=180)
                add_to_user_history(user_id, user_input, final_reply_text)
            elif msg.type == 'event' and msg.event == 'subscribe':
                welcome_input = "一个新朋友刚刚关注了我，请给TA一个热情的欢迎语！"
                session_id = user_proxy_agent.initiate_task(user_id, welcome_input)
                final_reply_text = main_orchestrator.run_session_until_completion(session_id, timeout_seconds=180)
                add_to_user_history(user_id, "(新用户关注)", final_reply_text)
            else:
                other_type_input = f"我收到了一个类型为 {msg.type} 的消息（不是文字），我应该怎么礼貌地告诉用户我主要处理文字呢？"
                session_id = user_proxy_agent.initiate_task(user_id, other_type_input)
                final_reply_text = main_orchestrator.run_session_until_completion(session_id, timeout_seconds=180)
                add_to_user_history(user_id, f"(收到 {msg.type} 消息)", final_reply_text)
            if final_reply_text:
                print(f"--- 微信回复给 {user_id} 内容: {final_reply_text!r} ---")
                reply = create_reply(final_reply_text, message=msg); return reply.render()
            return "success"
        except Exception as e:
            print(f"--- 微信 POST 请求处理错误 for {user_id}: {e} ---"); traceback.print_exc()
            try:
                if msg: error_reply = create_reply("呜呜，系统好像出了点小故障，学姐我先去看看，你稍等一下下哈~ 🛠️", message=msg); return error_reply.render()
            except Exception as e_reply: print(f"--- 微信错误回复也失败了: {e_reply} ---")
            return "success"

# --- 应用启动 ---
if __name__ == '__main__':
    print("--- 复旦校园助手 Agent (MAS - 分离 Specialist Agents) 启动中 ---")
    initialize_app_components() # 在主程序块中调用初始化
    if not main_orchestrator or not user_proxy_agent: print("严重错误: 应用组件未能成功初始化。程序退出。"); exit(1)
    print(f"微信 Token (可能来自环境变量或默认值): {WECHAT_TOKEN[:5]}...")
    print(f"对话历史将保留最近 {MAX_HISTORY_TURNS} 轮。")
    if main_orchestrator and hasattr(main_orchestrator, 'agents'):
        if "KnowledgeAgent" in main_orchestrator.agents:
            ksa = main_orchestrator.agents["KnowledgeAgent"]
            if hasattr(ksa, 'knowledge_tools_map'): print(f"KnowledgeAgent 已加载知识工具: {list(ksa.knowledge_tools_map.keys())}")
        if "UtilityAgent" in main_orchestrator.agents:
            usa = main_orchestrator.agents["UtilityAgent"]
            if hasattr(usa, 'utility_tools_map'): print(f"UtilityAgent 已加载通用工具: {list(usa.utility_tools_map.keys())}")
    app.run(host='0.0.0.0', port=5000, debug=True)

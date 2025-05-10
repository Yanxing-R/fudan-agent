# app.py
from flask import Flask, request, abort, jsonify
from wechatpy import parse_message, create_reply
from wechatpy.utils import check_signature
from wechatpy.exceptions import InvalidSignatureException

import llm_interface    # LLM 调用 (被 Agents 使用)
import knowledge_base   # 知识库 (被 Agents 使用)
# import tools          # 工具定义现在更像是 Specialist Agent 的内部实现
import multi_agent_system # 导入新的多Agent系统模块
import json
import traceback
import os

app = Flask(__name__)
app_instance = app # 用于 multi_agent_system 中获取对话历史

# --- 微信配置 ---
WECHAT_TOKEN = os.getenv("WECHAT_TOKEN", "YourDefaultWechatTokenIfNotSetInApp")
if WECHAT_TOKEN == "YourDefaultWechatTokenIfNotSetInApp":
    print("警告：微信 Token 使用了 app.py 中的默认值，请检查环境变量。")

# --- 对话历史 (保持简单内存实现，供 Orchestrator 通过 app_instance 回调获取) ---
conversation_history = {} 
MAX_HISTORY_TURNS = int(os.getenv("MAX_HISTORY_TURNS", 3))

def get_user_chat_history_for_agent(user_id: str) -> str:
    """供 Orchestrator 调用的函数，获取格式化的用户对话历史字符串"""
    history = conversation_history.get(user_id, [])
    if not history:
        return "无之前的对话内容。"
    formatted_parts = []
    for turn in history[-MAX_HISTORY_TURNS:]:
        formatted_parts.append(f"用户: {turn['user']}")
        formatted_parts.append(f"学姐: {turn['assistant']}")
    return "\n".join(formatted_parts)
app.get_user_chat_history_for_agent = get_user_chat_history_for_agent # 挂载到 app 实例

def add_to_user_history(user_id: str, user_msg: str, assistant_msg: str):
    """添加一轮对话到历史"""
    if user_id not in conversation_history:
        conversation_history[user_id] = []
    conversation_history[user_id].append({"user": user_msg, "assistant": assistant_msg})
    if len(conversation_history[user_id]) > MAX_HISTORY_TURNS:
        conversation_history[user_id].pop(0)

# --- 应用启动时初始化 Orchestrator ---
# main_orchestrator = multi_agent_system.Orchestrator()
# user_proxy_agent = main_orchestrator.agents.get("FudanUserProxyAgent")
main_orchestrator = multi_agent_system.get_orchestrator() # 使用 get_orchestrator 获取单例
user_proxy_agent = main_orchestrator.agents.get("FudanUserProxyAgent")

if not user_proxy_agent:
    print("严重错误: FudanUserProxyAgent 未能在 Orchestrator 中初始化!")
    # 实际应用中可能需要退出或采取其他措施

# --- /chat_text 路由 (用于本地测试) ---
@app.route('/chat_text', methods=['POST'])
def chat_text_endpoint():
    try:
        user_input_bytes = request.data
        user_input = user_input_bytes.decode('utf-8')
        if not user_input:
            return jsonify({"response": "学弟/学妹你想问点什么呀？🤔"}), 400

        user_id = "local_test_user" # 本地测试用固定 user_id

        if not user_proxy_agent: # 再次检查
            return jsonify({"response": "抱歉，Agent系统好像还没准备好..."}), 503

        # 1. 通过 UserProxyAgent 发起任务
        session_id = user_proxy_agent.initiate_task(user_id, user_input)
        
        # 2. 运行 Orchestrator 的消息循环直到此会话完成 (阻塞等待)
        final_reply = main_orchestrator.run_session_until_completion(session_id)

        # 3. 添加到对话历史 (注意，最终回复可能来自澄清请求)
        add_to_user_history(user_id, user_input, final_reply)
        
        print(f"--- Debug App (Text): Replying to {user_id} with: {final_reply!r} ---")
        return jsonify({"response": final_reply})

    except UnicodeDecodeError as e:
        print(f"--- Error App (Text): Decode failed: {e} ---")
        return jsonify({"response": "学姐我这边好像有点乱码了，你发的是文字吗？😵"}), 400
    except Exception as e:
        print(f"--- Error App (Text): Top level processing failed: {e} ---")
        traceback.print_exc()
        return jsonify({"response": "呜呜，系统好像出了点大问题，学姐我先去看看，你稍等一下下哈~ 🛠️"}), 500


# --- /wechat 路由 (微信公众号回调) ---
@app.route('/wechat', methods=['GET', 'POST'])
def wechat_webhook():
    signature = request.args.get('signature', '')
    timestamp = request.args.get('timestamp', '')
    nonce = request.args.get('nonce', '')
    try:
        check_signature(WECHAT_TOKEN, signature, timestamp, nonce)
    except InvalidSignatureException:
        print("微信签名校验失败！")
        abort(403)

    if request.method == 'GET':
        print("微信服务器验证成功。")
        return request.args.get('echostr', '')

    elif request.method == 'POST':
        msg = None
        user_id = "unknown_wechat_user"
        try:
            msg = parse_message(request.data)
            user_id = msg.source 
            print(f"--- 微信消息收到 --- 类型: {msg.type}, 来自: {user_id}")

            final_reply_text = "学姐暂时无法处理你的请求哦，请稍后再试~ 😥" 

            if msg.type == 'text':
                user_input = msg.content
                if not user_proxy_agent:
                     final_reply_text = "抱歉，Agent系统好像还没准备好..."
                else:
                    session_id = user_proxy_agent.initiate_task(user_id, user_input)
                    final_reply_text = main_orchestrator.run_session_until_completion(session_id)
                add_to_user_history(user_id, user_input, final_reply_text)

            elif msg.type == 'event' and msg.event == 'subscribe':
                # 关注事件，可以直接由 UserProxyAgent 生成或通过 LLM 生成问候
                # 为了简化，这里我们用一个固定的或通过 LLM 生成的简单回复
                # 注意：这里的 user_input 是我们构造的，不直接来自用户
                constructed_user_input_for_welcome = "一个新朋友刚刚关注了我，请热情地欢迎TA！"
                session_id = user_proxy_agent.initiate_task(user_id, constructed_user_input_for_welcome)
                final_reply_text = main_orchestrator.run_session_until_completion(session_id)
                # 欢迎语通常不记录为 user_input，但可以记录 assistant_reply
                add_to_user_history(user_id, "(新用户关注)", final_reply_text)


            else: # 其他非文本消息
                constructed_input_for_other_types = f"我收到了一个类型为 {msg.type} 的消息（不是文字），我应该怎么礼貌地告诉用户我主要处理文字呢？"
                session_id = user_proxy_agent.initiate_task(user_id, constructed_input_for_other_types)
                final_reply_text = main_orchestrator.run_session_until_completion(session_id)
                add_to_user_history(user_id, f"(收到 {msg.type} 消息)", final_reply_text)
            
            if final_reply_text:
                print(f"--- 微信回复给 {user_id} 内容: {final_reply_text!r} ---")
                reply = create_reply(final_reply_text, message=msg)
                return reply.render()
            return "success"

        except Exception as e:
            print(f"--- 微信 POST 请求处理错误 for {user_id}: {e} ---")
            traceback.print_exc()
            try:
                if msg:
                    error_reply = create_reply("呜呜，系统好像出了点小故障，学姐我先去看看，你稍等一下下哈~ 🛠️", message=msg)
                    return error_reply.render()
            except Exception as e_reply:
                print(f"--- 微信错误回复也失败了: {e_reply} ---")
            return "success"


# --- 应用启动 ---
if __name__ == '__main__':
    print("--- 复旦校园助手 Agent (多Agent版) 启动中 ---")
    knowledge_base.load_all_data() # 加载所有知识库
    main_orchestrator = multi_agent_system.get_orchestrator() # 确保 Orchestrator 已初始化
    user_proxy_agent = main_orchestrator.agents.get("FudanUserProxyAgent") # 获取 UserProxyAgent 实例
    
    if not user_proxy_agent: # 增加启动时检查
        print("严重错误: FudanUserProxyAgent 未能在 Orchestrator 中正确初始化。应用无法启动。")
        exit(1)

    print(f"微信 Token (可能来自环境变量或默认值): {WECHAT_TOKEN[:5]}...")
    print(f"对话历史将保留最近 {MAX_HISTORY_TURNS} 轮。")
    print(f"支持的动态知识类别: {knowledge_base.SUPPORTED_DYNAMIC_CATEGORIES}")
    
    # 打印 Orchestrator 中注册的 Agent
    if main_orchestrator and hasattr(main_orchestrator, 'agents'):
        print(f"Orchestrator 中已注册的 Agent ({len(main_orchestrator.agents)} 个): {list(main_orchestrator.agents.keys())}")
    
    app.run(host='0.0.0.0', port=5000, debug=True) # debug=True 仅用于开发



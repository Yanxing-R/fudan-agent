from flask import Flask, request, abort, jsonify # 确保导入 abort
# 从 wechatpy 导入所需模块
from wechatpy import parse_message, create_reply
from wechatpy.utils import check_signature
from wechatpy.exceptions import InvalidSignatureException, InvalidAppIdException

# 导入你现有的模块
import llm_interface
import knowledge_base
import json # 可能需要导入 json
import traceback

app = Flask(__name__)

# --- 添加微信配置 ---
WECHAT_TOKEN = "fudanAssistantToken2025" # !! 非常重要：与微信后台填写的 Token 保持一致 !!
WECHAT_APPID = "你的公众号AppID" # 可选，主要用于更高级的 API 调用
WECHAT_APPSECRET = "你的公众号AppSecret" # 可选，同上，注意保密

# --- 你现有的 / 和 /chat_text 路由可以保留用于其他测试 ---
@app.route('/')
def home():
    return "Fudan Agent is running!"

# --- 更新后的 /chat_text 路由 ---
@app.route('/chat_text', methods=['POST'])
def chat_text():
    response_text = "" # 初始化回复文本
    try:
        # 1. 获取并解码输入
        user_input_bytes = request.data
        print(f"--- Debug App (Text): Raw bytes: {user_input_bytes!r} ---")
        user_input = user_input_bytes.decode('utf-8')
        print(f"--- Debug App (Text): Decoded input: {user_input!r} ---")

        if not user_input:
            print("--- Warning App (Text): Empty input ---")
            return jsonify({"response": "请输入你想问的问题。"}), 400

        # -------- 核心逻辑 (与 /wechat 类似) --------
        # 2. 先尝试 NLU 识别特定意图
        nlu_result = llm_interface.get_llm_nlu(user_input)
        intent = nlu_result.get('intent', 'unknown') # 默认为 unknown
        entities = nlu_result.get('entities', {})
        print(f"--- Debug App (Text): NLU result: intent='{intent}', entities={entities} ---")

        # 3. 根据意图处理
        if intent == 'ask_slang_explanation':
            term = entities.get('slang_term')
            if term:
                response_text = knowledge_base.get_slang_definition(term)
            else:
                response_text = "你想问哪个黑话词呢？"
        elif intent == 'ask_food_recommendation':
            location = entities.get('location')
            if not location:
                 response_text = "你想在哪附近找好吃的呀？比如邯郸校区、江湾或者五角场？"
            else:
                 response_text = knowledge_base.find_food(location=location)
                 if not response_text:
                     response_text = f"嗯，关于“{location}”附近的美食我还在学习中，暂时找不到推荐呢。"
        elif intent == 'greet':
            response_text = "你好！有什么可以帮你的吗？我是复旦校园助手。"
        elif intent == 'goodbye':
            response_text = "再见！后会有期！"
        elif intent == 'error':
            response_text = "抱歉，我在理解你的问题时遇到了一点小麻烦，请稍后再试。"
            print(f"NLU Error details: {entities.get('message')}")
        elif intent == 'unknown':
            print(f"--- Intent 'unknown', attempting general chat response ---")
            general_response = llm_interface.get_general_response(user_input)
            if general_response:
                response_text = general_response
            else:
                response_text = "嗯...这个问题有点超出我的知识范围了呢。"
        else: # 处理其他未预期的 intent 值
            print(f"--- Unhandled intent '{intent}', attempting general chat response ---")
            general_response = llm_interface.get_general_response(user_input)
            if general_response:
                response_text = general_response
            else:
                response_text = "让我想想...好像有点不明白你的意思。"
        # -------- 核心逻辑结束 --------

    except UnicodeDecodeError as e:
        print(f"--- Error App (Text): Decode failed: {e} ---")
        response_text = "抱歉，你的输入好像有点问题，我无法理解。"
        return jsonify({"response": response_text}), 400 # 返回错误状态码
    except Exception as e:
        # 捕获处理过程中的其他异常
        print(f"--- Error App (Text): Processing failed: {e} ---")
        traceback.print_exc() # 打印详细错误堆栈
        response_text = "抱歉，处理你的请求时出现了一些内部错误。"
        return jsonify({"response": response_text}), 500 # 返回服务器内部错误状态码

    # 4. 返回 JSON 响应
    print(f"--- Debug App (Text): Replying with: {response_text!r} ---")
    return jsonify({"response": response_text})


# --- 新增处理微信请求的路由 ---
@app.route('/wechat', methods=['GET', 'POST'])
def wechat_webhook():
    # 从请求参数中获取微信加密签名相关信息
    signature = request.args.get('signature', '')
    timestamp = request.args.get('timestamp', '')
    nonce = request.args.get('nonce', '')

    try:
        # 1. 校验签名
        check_signature(WECHAT_TOKEN, signature, timestamp, nonce)
    except InvalidSignatureException:
        # 签名校验失败，拒绝请求
        print("--- WeChat Error: Invalid signature ---")
        abort(403) # HTTP 403 Forbidden

    # ------------------ 处理 GET 请求 (用于微信服务器验证) ------------------
    if request.method == 'GET':
        # 微信服务器会发送 GET 请求来验证你的服务器URL是否有效
        echostr = request.args.get('echostr', '')
        print(f"--- WeChat Verification OK, returning echostr ---")
        return echostr # 校验成功，原样返回 echostr

    # ------------------ 处理 POST 请求 (用户发送的消息) ------------------
    elif request.method == 'POST':
        try:
            # 1. 解析微信发送过来的 XML 消息体
            msg = parse_message(request.data)
            print(f"--- WeChat Message Received --- Type: {msg.type}, From: {msg.source}, To: {msg.target}")

            # 2. 处理不同类型的消息
            if msg.type == 'text':
                # 用户发送了文本消息
                user_input = msg.content
                print(f"--- WeChat User Input: {user_input!r} ---")

                # -------- 核心逻辑修改 --------
                # 1. 先尝试 NLU 识别特定意图
                nlu_result = llm_interface.get_llm_nlu(user_input)
                intent = nlu_result.get('intent', 'unknown') # 默认为 unknown
                entities = nlu_result.get('entities', {})
                print(f"--- WeChat NLU result: intent='{intent}', entities={entities} ---")

                # 2. 根据意图处理
                if intent == 'ask_slang_explanation':
                    term = entities.get('slang_term')
                    if term:
                        response_text = knowledge_base.get_slang_definition(term)
                    else:
                        # 如果 NLU 识别了意图但没提取出实体，可以提示用户
                        response_text = "你想问哪个黑话词呢？"
                elif intent == 'ask_food_recommendation':
                    location = entities.get('location')
                    if not location:
                         response_text = "你想在哪附近找好吃的呀？比如邯郸校区、江湾或者五角场？"
                    else:
                         response_text = knowledge_base.find_food(location=location)
                         # 如果 find_food 返回 None 或空字符串，可以设置默认回复
                         if not response_text:
                             response_text = f"嗯，关于“{location}”附近的美食我还在学习中，暂时找不到推荐呢。"
                elif intent == 'greet':
                    # 保留简单的固定回复
                    response_text = "你好！有什么可以帮你的吗？我是复旦校园助手。"
                elif intent == 'goodbye':
                    # 保留简单的固定回复
                    response_text = "再见！后会有期！"
                elif intent == 'error':
                    # NLU 过程出错
                    response_text = "抱歉，我在理解你的问题时遇到了一点小麻烦，请稍后再试。"
                    # 可以考虑记录更详细的错误信息 entities.get('message')
                    print(f"NLU Error details: {entities.get('message')}")

                # 关键: 如果意图是 unknown 或未被上面处理
                elif intent == 'unknown':
                    print(f"--- Intent 'unknown', attempting general chat response ---")
                    # 调用新的通用回复函数
                    general_response = llm_interface.get_general_response(user_input)
                    if general_response:
                        response_text = general_response
                    else:
                        # 如果通用回复也失败了，给一个最终的 fallback
                        response_text = "嗯...这个问题有点超出我的知识范围了呢。"

                else: # 处理其他未预期的 intent 值（理论上不应发生，但也 fallback）
                    print(f"--- Unhandled intent '{intent}', attempting general chat response ---")
                    general_response = llm_interface.get_general_response(user_input)
                    if general_response:
                        response_text = general_response
                    else:
                        response_text = "让我想想...好像有点不明白你的意思。"

                # -------- 核心逻辑修改结束 --------
            elif msg.type == 'event' and msg.event == 'subscribe':
                # 用户关注事件 (保持不变)
                print(f"--- WeChat Event: User {msg.source} subscribed ---")
                response_text = "欢迎关注复旦校园助手！发送你想了解的复旦“黑话”或者问我附近的美食吧~"
            else:
                # 其他未处理类型 (保持不变)
                print(f"--- WeChat Received unhandled message type: {msg.type} ---")
                response_text = '抱歉，我现在只能听懂文字消息哦~'

            # 创建并渲染回复
            if response_text: # 确保有回复内容
                print(f"--- WeChat Replying With: {response_text!r} ---")
                reply = create_reply(response_text, message=msg)
                return reply.render()
            else:
                # 如果所有逻辑都未能生成回复文本（理论上不应发生）
                print("--- Warning: No response text generated for the message ---")
                return "success" # 告诉微信服务器处理成功，但不回复用户

        except Exception as e:
            # 全局异常处理 (保持不变)
            print(f"--- WeChat Error processing POST request: {e} ---")
            # 打印更详细的 Traceback 方便调试
            import traceback
            traceback.print_exc()
            return "success" # 仍然返回 success 避免微信重试

# --- 你现有的启动代码 ---
if __name__ == '__main__':
    knowledge_base.load_data()
    # 注意：部署时不要用 Flask 开发服务器的 run 方法
    # 应该用 Gunicorn 或 Waitress 等 WSGI 服务器启动
    # 例如: gunicorn -w 4 -b 0.0.0.0:5000 app:app (端口可能需要是80或你配置的反向代理端口)
    # 这里为了本地测试保持原样：
    app.run(host='0.0.0.0', port=5000, debug=True) # debug=True 仅用于开发
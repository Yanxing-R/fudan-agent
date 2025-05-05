from flask import Flask, request, abort, jsonify # 确保导入 abort
# 从 wechatpy 导入所需模块
from wechatpy import parse_message, create_reply
from wechatpy.utils import check_signature
from wechatpy.exceptions import InvalidSignatureException, InvalidAppIdException

# 导入你现有的模块
import llm_interface
import knowledge_base
import json # 可能需要导入 json

app = Flask(__name__)

# --- 添加微信配置 ---
WECHAT_TOKEN = "请在这里设置你的Token" # !! 非常重要：与微信后台填写的 Token 保持一致 !!
WECHAT_APPID = "你的公众号AppID" # 可选，主要用于更高级的 API 调用
WECHAT_APPSECRET = "你的公众号AppSecret" # 可选，同上，注意保密

# --- 你现有的 / 和 /chat_text 路由可以保留用于其他测试 ---
@app.route('/')
def home():
    # ... (保持不变) ...
    pass

@app.route('/chat_text', methods=['POST'])
def chat_text():
     # ... (保持不变，但注意调试打印可以根据需要移除或保留) ...
    # --- (之前的调试打印，可以酌情保留或移除) ---
    user_input_bytes = request.data
    print(f"--- Debug App (Text): Raw bytes: {user_input_bytes!r} ---")
    try:
        user_input = user_input_bytes.decode('utf-8')
        print(f"--- Debug App (Text): Decoded input: {user_input!r} ---")
    except UnicodeDecodeError as e:
        print(f"--- Error App (Text): Decode failed: {e} ---")
        user_input = ""

    if not user_input:
        print("--- Warning App (Text): Empty input ---")
        return jsonify({"response": "请输入你想问的问题。"}), 400
    # ---

    nlu_result = llm_interface.get_llm_nlu(user_input)
    intent = nlu_result.get('intent', 'unknown')
    entities = nlu_result.get('entities', {})
    print(f"--- Debug App (Text): NLU result: intent='{intent}', entities={entities} ---") # 保留这个打印

    response_text = ""
    # ... (你现有的意图处理逻辑) ...
    if intent == 'ask_slang_explanation':
        term = entities.get('slang_term')
        if term:
            response_text = knowledge_base.get_slang_definition(term)
        else:
            response_text = "你想问哪个黑话词呢？"
    elif intent == 'ask_food_recommendation':
        location = entities.get('location')
        # ... (处理美食逻辑) ...
        if not location:
             response_text = "你想在哪附近找好吃的呀？比如邯郸校区、江湾或者五角场？"
        else:
             response_text = knowledge_base.find_food(location=location) # 假设已有此函数
    # ... (处理 greet, goodbye, error, fallback 的逻辑) ...
    else:
         response_text = "抱歉，我暂时还不太理解你的意思。你可以问我关于复旦美食推荐或者校园黑话的问题。"

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

                # -------- 复用你的核心 Agent 逻辑 --------
                nlu_result = llm_interface.get_llm_nlu(user_input)
                intent = nlu_result.get('intent', 'unknown')
                entities = nlu_result.get('entities', {})
                print(f"--- WeChat NLU result: intent='{intent}', entities={entities} ---")

                response_text = ""
                if intent == 'ask_slang_explanation':
                    term = entities.get('slang_term')
                    if term:
                        response_text = knowledge_base.get_slang_definition(term)
                    else:
                        response_text = "你想问哪个黑话词呢？"
                elif intent == 'ask_food_recommendation':
                    location = entities.get('location')
                    # ... (处理美食逻辑) ...
                    if not location:
                         response_text = "你想在哪附近找好吃的呀？比如邯郸校区、江湾或者五角场？"
                    else:
                         response_text = knowledge_base.find_food(location=location) # 假设已有此函数
                # ... (处理 greet, goodbye, error, fallback 的逻辑) ...
                else: # unknown or fallback
                     response_text = "抱歉，我暂时还不太理解你的意思。你可以问我关于复旦美食推荐或者校园黑话的问题。"

                # ----------------------------------------

                # 3. 创建回复消息 (文本类型)
                print(f"--- WeChat Replying With: {response_text!r} ---")
                reply = create_reply(response_text, message=msg) # message=msg 用于正确设置发送方和接收方

            elif msg.type == 'event' and msg.event == 'subscribe':
                # 用户关注事件
                print(f"--- WeChat Event: User {msg.source} subscribed ---")
                reply = create_reply("欢迎关注复旦校园助手！发送你想了解的复旦“黑话”或者问我附近的美食吧~", message=msg)

            # 可以根据需要处理其他事件类型 (unsubscribe) 或消息类型 (image, voice)
            # ...

            else:
                # 对于其他未处理的消息类型，回复提示信息
                print(f"--- WeChat Received unhandled message type: {msg.type} ---")
                reply = create_reply('抱歉，我现在只能听懂文字消息哦~', message=msg)

            # 4. 将回复消息序列化为 XML 格式并返回给微信服务器
            return reply.render()

        except Exception as e:
            # 处理过程中发生任何异常，打印错误日志
            # 但仍然需要给微信服务器返回一个空字符串或 'success' 表示接收成功，避免微信重试
            print(f"--- WeChat Error processing POST request: {e} ---")
            return "" # 或 'success'

# --- 你现有的启动代码 ---
if __name__ == '__main__':
    knowledge_base.load_data()
    # 注意：部署时不要用 Flask 开发服务器的 run 方法
    # 应该用 Gunicorn 或 Waitress 等 WSGI 服务器启动
    # 例如: gunicorn -w 4 -b 0.0.0.0:5000 app:app (端口可能需要是80或你配置的反向代理端口)
    # 这里为了本地测试保持原样：
    app.run(host='0.0.0.0', port=5000, debug=True) # debug=True 仅用于开发
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

# --- /chat_text 路由 (应用相同的逻辑修改) ---
@app.route('/chat_text', methods=['POST'])
def chat_text():
    response_text = ""
    try:
        user_input_bytes = request.data
        user_input = user_input_bytes.decode('utf-8')
        print(f"--- Debug App (Text): Decoded input: {user_input!r} ---")

        if not user_input:
            return jsonify({"response": "学弟/学妹你想问点什么呀？"}), 400 # 用人设语气

        # -------- 核心逻辑修改 --------
        nlu_result = llm_interface.get_llm_nlu(user_input)
        intent = nlu_result.get('intent', 'unknown')
        entities = nlu_result.get('entities', {})
        print(f"--- Debug App (Text): NLU result: intent='{intent}', entities={entities} ---")

        if intent == 'ask_slang_explanation':
            term = entities.get('slang_term')
            if term:
                definition = knowledge_base.get_slang_definition(term)
                # 检查是否是 "未找到" 的默认回复
                if "抱歉，我还不知道" in definition:
                    print(f"--- Slang '{term}' not found in KB, generating not found response ---")
                    response_text = llm_interface.generate_not_found_response(user_input)
                else:
                    print(f"--- Slang '{term}' found, generating persona response ---")
                    # 将找到的定义交给 LLM 生成回复
                    response_text = llm_interface.generate_persona_response(user_input, f"关于“{term}”：{definition}")
            else:
                # 如果没提取出实体，让通用对话处理或直接提示
                response_text = llm_interface.get_general_response("请问你想了解哪个校园黑话呢？")

        elif intent == 'ask_food_recommendation':
            location = entities.get('location')
            if not location:
                 # 反问也用通用回复生成，更自然
                 response_text = llm_interface.get_general_response("你想在哪附近找好吃的呀？比如邯郸校区、江湾或者五角场？")
            else:
                 food_info = knowledge_base.find_food(location=location)
                 if "唉呀，暂时没有找到" in food_info: # 检查是否是未找到的回复
                     print(f"--- Food near '{location}' not found in KB, generating not found response ---")
                     response_text = llm_interface.generate_not_found_response(user_input)
                 else:
                     print(f"--- Food near '{location}' found, generating persona response ---")
                     # 将找到的美食信息交给 LLM 生成回复
                     # find_food 返回的是字符串，可以直接用
                     response_text = llm_interface.generate_persona_response(user_input, food_info)

        elif intent == 'greet' or intent == 'goodbye':
             # 问候和告别也交给通用回复，语气更一致
             print(f"--- Intent '{intent}', generating general chat response ---")
             response_text = llm_interface.get_general_response(user_input)

        elif intent == 'error':
            # NLU 出错，使用通用回复告知用户
            print(f"NLU Error details: {entities.get('message')}")
            response_text = llm_interface.get_general_response("哎呀，学姐我刚刚好像走神了，没太听清，能再说一遍吗？")

        elif intent == 'unknown':
             # 未知意图，使用通用回复
             print(f"--- Intent 'unknown', generating general chat response ---")
             response_text = llm_interface.get_general_response(user_input)

        else: # 其他未处理意图
             print(f"--- Unhandled intent '{intent}', generating general chat response ---")
             response_text = llm_interface.get_general_response(user_input)
        # -------- 核心逻辑结束 --------

    except UnicodeDecodeError as e:
        # ... (异常处理) ...
        response_text = "学姐我这边好像有点乱码了，你发的是文字吗？"
        return jsonify({"response": response_text}), 400
    except Exception as e:
        # ... (异常处理) ...
        traceback.print_exc()
        response_text = "呜呜，系统好像出了点小故障，学姐我先去看看，你稍等一下下哈~"
        return jsonify({"response": response_text}), 500

    # 返回 JSON 响应
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
        response_text = ""
        try:
            msg = parse_message(request.data)
            print(f"--- WeChat Message Received --- Type: {msg.type}, From: {msg.source}")

            if msg.type == 'text':
                user_input = msg.content
                print(f"--- WeChat User Input: {user_input!r} ---")

                # -------- 核心逻辑修改 (与 chat_text 完全一致) --------
                nlu_result = llm_interface.get_llm_nlu(user_input)
                intent = nlu_result.get('intent', 'unknown')
                entities = nlu_result.get('entities', {})
                print(f"--- WeChat NLU result: intent='{intent}', entities={entities} ---")

                if intent == 'ask_slang_explanation':
                    term = entities.get('slang_term')
                    if term:
                        definition = knowledge_base.get_slang_definition(term)
                        if "抱歉，我还不知道" in definition:
                            response_text = llm_interface.generate_not_found_response(user_input)
                        else:
                            response_text = llm_interface.generate_persona_response(user_input, f"关于“{term}”：{definition}")
                    else:
                        response_text = llm_interface.get_general_response("请问你想了解哪个校园黑话呢？")
                elif intent == 'ask_food_recommendation':
                    location = entities.get('location')
                    if not location:
                         response_text = llm_interface.get_general_response("你想在哪附近找好吃的呀？比如邯郸校区、江湾或者五角场？")
                    else:
                         food_info = knowledge_base.find_food(location=location)
                         if "唉呀，暂时没有找到" in food_info:
                             response_text = llm_interface.generate_not_found_response(user_input)
                         else:
                             response_text = llm_interface.generate_persona_response(user_input, food_info)
                elif intent == 'greet' or intent == 'goodbye':
                     response_text = llm_interface.get_general_response(user_input)
                elif intent == 'error':
                    print(f"NLU Error details: {entities.get('message')}")
                    response_text = llm_interface.get_general_response("哎呀，学姐我刚刚好像走神了，没太听清，能再说一遍吗？")
                elif intent == 'unknown':
                     response_text = llm_interface.get_general_response(user_input)
                else: # 其他未处理意图
                     response_text = llm_interface.get_general_response(user_input)
                # -------- 核心逻辑结束 --------

            elif msg.type == 'event' and msg.event == 'subscribe':
                # 关注欢迎语也可以用 LLM 生成，更个性化
                response_text = llm_interface.get_general_response("一个新朋友关注了我！") # 让 LLM 基于这个输入生成欢迎语
                # 或者保留固定欢迎语：
                # response_text = "欢迎关注复旦校园助手！发送你想了解的复旦“黑话”或者问我附近的美食吧~"
            else:
                response_text = llm_interface.get_general_response("嗯？你发的好像不是文字消息哦~学姐我暂时还看不懂图片和表情呢。") # 用人设回复

            # 创建并渲染回复
            if response_text:
                print(f"--- WeChat Replying With: {response_text!r} ---")
                reply = create_reply(response_text, message=msg)
                return reply.render()
            else:
                print("--- Warning: No response text generated for the WeChat message ---")
                return "success"

        except Exception as e:
            # 全局异常处理
            print(f"--- WeChat Error processing POST request: {e} ---")
            traceback.print_exc()
            return "success" # 仍然返回 success 避免微信重试

# --- 启动代码 (保持不变) ---
if __name__ == '__main__':
    knowledge_base.load_data()
    # 部署时使用 Gunicorn/Waitress
    # 本地测试时：
    app.run(host='0.0.0.0', port=5000, debug=True)
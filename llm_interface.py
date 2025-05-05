# llm_interface.py

import os
import json
import dashscope # 确认导入了正确的库
from dashscope.api_entities.dashscope_response import GenerationResponse # 导入可能的响应类型，具体看文档
from prompts import NLU_PROMPT_TEMPLATE, GENERAL_CHAT_PROMPT_TEMPLATE, PERSONA_RESPONSE_TEMPLATE, PERSONA_NOT_FOUND_TEMPLATE # 你的 Prompt 模板保持不变

# --- 配置 API Key ---
# 从环境变量读取 API Key
api_key = os.getenv("DASHSCOPE_API_KEY")
if not api_key:
    print("错误：环境变量 DASHSCOPE_API_KEY 未设置！")
    # 可以在这里决定是抛出异常还是返回错误状态
    # raise ValueError("API Key not configured")
else:
    dashscope.api_key = api_key

# --- 选择阿里云模型 ---
# 查阅文档，选择一个包含在免费额度里的合适模型，比如通义千问的某个版本
# 例如： 'qwen-turbo', 'qwen-plus', 'qwen-max-longcontext' 等
ALI_MODEL_NAME = "qwen-turbo" # !! 请替换为实际可用的模型名称 !!

def get_llm_nlu(user_input):
    if not dashscope.api_key: # 再次检查，确保 key 已设置
         print("错误：API Key 未配置，无法调用 LLM。")
         return {"intent": "error", "entities": {"message": "API Key not configured"}}

    prompt = NLU_PROMPT_TEMPLATE.format(user_input=user_input)

    try:
        print(f"--- Debug: Sending request to DashScope API ---")
        print(f"Model: {ALI_MODEL_NAME}")
        # print(f"Prompt:\n{prompt}") # 打印 Prompt 用于调试

        # --- 调用 DashScope API ---
        # !!! 注意：以下调用方式是示例，请务必参考 DashScope 官方 Python SDK 文档 !!!
        response = dashscope.Generation.call(
            model=ALI_MODEL_NAME,
            prompt=prompt,
            # 你可能需要设置其他参数，如 temperature, max_tokens 等
            # 重要：让 LLM 返回我们需要的 JSON 字符串
            # 有些 API 支持指定返回格式，或者像之前一样依赖 Prompt 指示
            result_format='message' # 尝试使用 message 格式获取纯文本输出
        )

        print(f"--- Debug: Received response from DashScope ---")

        # --- 解析 DashScope 的响应 ---
        # !!! 响应结构取决于 DashScope SDK 版本和 API，请查阅文档 !!!
        if response.status_code == 200:
            # 假设 LLM 的输出在 response.output.choices[0].message.content 中
            generated_text = response.output.choices[0]['message']['content']
            print(f"Raw Response Text from LLM: {generated_text}")

            # 尝试解析 LLM 返回的 JSON 字符串
            try:
                # 尝试清理可能的 Markdown 代码块标记
                text_to_parse = generated_text.strip()
                if text_to_parse.startswith("```json"):
                    text_to_parse = text_to_parse[7:-3].strip()
                elif text_to_parse.startswith("`json"):
                     text_to_parse = text_to_parse[5:-1].strip()
                elif text_to_parse.startswith("{") and text_to_parse.endswith("}"):
                     pass # Looks like plain JSON already
                else:
                     print(f"Warning: LLM output doesn't look like JSON: {text_to_parse}")
                     # Maybe still try to parse, or return error directly

                nlu_dict = json.loads(text_to_parse)
                # 基本验证，确保至少有 intent 字段
                if 'intent' not in nlu_dict:
                    print("Error: LLM response JSON missing 'intent' key.")
                    return {"intent": "error", "entities": {"message": "LLM response format error"}}
                return nlu_dict

            except json.JSONDecodeError as json_err:
                print(f"Error decoding LLM JSON response: {json_err}")
                print(f"LLM Raw Text was: {generated_text}") # 打印原始文本帮助调试
                return {"intent": "error", "entities": {"message": "LLM did not return valid JSON"}}
            except Exception as parse_err:
                print(f"Error processing LLM response structure: {parse_err}")
                return {"intent": "error", "entities": {"message": "Failed to parse LLM response structure"}}

        else:
            # 处理 API 返回的错误状态
            print(f"Error: DashScope API call failed.")
            print(f"Status Code: {response.status_code}")
            # 打印错误详情，具体字段看 DashScope 文档
            error_code = getattr(response, 'code', 'N/A')
            error_message = getattr(response, 'message', 'Unknown error')
            print(f"Error Code: {error_code}")
            print(f"Error Message: {error_message}")
            return {"intent": "error", "entities": {"message": f"API Error: {error_message}"}}

    except Exception as e:
        # 处理调用过程中的其他异常 (网络问题、SDK 本身问题等)
        print(f"An unexpected error occurred calling DashScope API: {e}")
        return {"intent": "error", "entities": {"message": "Failed to call LLM API"}}

# --- 通用对话回复函数 (更新 Prompt) ---
def get_general_response(user_input):
    """调用 LLM 进行通用的、带学姐人设的对话式回复。"""
    if not dashscope.api_key:
        print("错误：General Chat - API Key 未配置。")
        return "唔…学姐我的网络好像有点小问题，稍等一下下哦~" # 用人设语气回复错误

    # 使用更新后的通用对话 Prompt
    prompt = GENERAL_CHAT_PROMPT_TEMPLATE.format(user_input=user_input)

    try:
        print(f"--- Debug General Chat: Sending request ---")
        response = dashscope.Generation.call(
            model=ALI_MODEL_NAME,
            prompt=prompt,
            result_format='message'
        )
        print(f"--- Debug General Chat: Received response ---")

        if response.status_code == 200:
            generated_text = response.output.choices[0]['message']['content']
            print(f"General Chat Raw Response Text: {generated_text}")
            return generated_text.strip()
        else:
            # 处理 API 错误
            print(f"Error General Chat: DashScope API call failed.")
            # ... (错误处理代码同前) ...
            error_code = getattr(response, 'code', 'N/A')
            return f"哎呀，和服务器通讯的时候好像卡了一下 ({error_code})，学弟/学妹你再试一次？"

    except Exception as e:
        print(f"An unexpected error occurred in get_general_response: {e}")
        return "呜，学姐我好像有点累了，脑子转不动了，稍后再来找我玩吧~"


# --- 新增: 结合知识生成回复的函数 ---
def generate_persona_response(user_input, context_info):
    """根据背景知识，用学姐人设生成回复。"""
    if not dashscope.api_key:
        print("错误：Persona Response - API Key 未配置。")
        return "唔…学姐我的网络好像有点小问题，稍等一下下哦~"

    # 格式化 context_info，如果是字典或列表，转成易读的字符串
    if isinstance(context_info, (dict, list)):
        context_str = json.dumps(context_info, ensure_ascii=False, indent=2)
        # 可以考虑进一步优化，比如只提取关键字段转成自然语言描述
        # 例如，对于美食，可以写成 "店名: XX, 简介: YY"
    else:
        context_str = str(context_info)

    # 使用结合知识的 Prompt
    prompt = PERSONA_RESPONSE_TEMPLATE.format(user_input=user_input, context_info=context_str)

    try:
        print(f"--- Debug Persona Response: Sending request ---")
        response = dashscope.Generation.call(
            model=ALI_MODEL_NAME,
            prompt=prompt,
            result_format='message'
        )
        print(f"--- Debug Persona Response: Received response ---")

        if response.status_code == 200:
            generated_text = response.output.choices[0]['message']['content']
            print(f"Persona Response Raw Text: {generated_text}")
            return generated_text.strip()
        else:
            print(f"Error Persona Response: DashScope API call failed.")
            # ... (错误处理代码同前) ...
            error_code = getattr(response, 'code', 'N/A')
            return f"哎呀，和服务器通讯的时候好像卡了一下 ({error_code})，学弟/学妹你再试一次？"

    except Exception as e:
        print(f"An unexpected error occurred in generate_persona_response: {e}")
        return "呜，学姐我好像有点累了，脑子转不动了，稍后再来找我玩吧~"


# --- 新增: 知识库未找到信息时的回复函数 ---
def generate_not_found_response(user_input):
    """当知识库未找到信息时，用学姐人设生成回复。"""
    if not dashscope.api_key:
        print("错误：Not Found Response - API Key 未配置。")
        return "唔…学姐我的网络好像有点小问题，稍等一下下哦~"

    # 使用知识库未找到的 Prompt
    prompt = PERSONA_NOT_FOUND_TEMPLATE.format(user_input=user_input)

    try:
        print(f"--- Debug Not Found Response: Sending request ---")
        response = dashscope.Generation.call(
            model=ALI_MODEL_NAME,
            prompt=prompt,
            result_format='message'
        )
        print(f"--- Debug Not Found Response: Received response ---")

        if response.status_code == 200:
            generated_text = response.output.choices[0]['message']['content']
            print(f"Not Found Response Raw Text: {generated_text}")
            return generated_text.strip()
        else:
            print(f"Error Not Found Response: DashScope API call failed.")
            # ... (错误处理代码同前) ...
            error_code = getattr(response, 'code', 'N/A')
            return f"哎呀，和服务器通讯的时候好像卡了一下 ({error_code})，学弟/学妹你再试一次？"

    except Exception as e:
        print(f"An unexpected error occurred in generate_not_found_response: {e}")
        return "呜，学姐我好像有点累了，脑子转不动了，稍后再来找我玩吧~"    
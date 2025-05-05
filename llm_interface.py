# llm_interface.py

import os
import json
import dashscope # 确认导入了正确的库
from dashscope.api_entities.dashscope_response import GenerationResponse # 导入可能的响应类型，具体看文档
from prompts import NLU_PROMPT_TEMPLATE # 你的 Prompt 模板保持不变

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
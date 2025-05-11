# llm_interface.py
# Batch 3: Adapting get_final_response to use task_outcome_status

import os
import json
import dashscope
from dashscope.api_entities.dashscope_response import GenerationResponse # 确保导入正确
import traceback

# 导入 Prompt 模板
from prompts import (
    PLANNER_PROMPT_TEMPLATE,
    GENERAL_CHAT_PROMPT_TEMPLATE,
    PERSONA_NOT_FOUND_TEMPLATE,
    MODERATION_PROMPT_TEMPLATE
)
# Import knowledge_base only if its constants are directly used here for string matching.
# If PlannerAgent determines the 'not_found' status, direct import might not be needed here.
# For now, keeping it as it was, but ideally, this dependency for 'not_found' detection
# should be removed from here.
try:
    import knowledge_base # For potential access to NOT_FOUND messages if string matching is still a fallback
except ImportError:
    print("警告: llm_interface.py 无法导入 knowledge_base。某些功能可能受影响。")
    knowledge_base = None # Define it as None to prevent AttributeError if not found

# --- API Key 配置 (No changes from Batch 1) ---
api_key = os.getenv("DASHSCOPE_API_KEY")
if not api_key:
    print("错误：环境变量 DASHSCOPE_API_KEY 未设置！程序可能无法正常调用LLM。")

# --- LLM 模型配置 (No changes from Batch 1) ---
LLM_CONFIG = {
    "planner": os.getenv("PLANNER_LLM_MODEL", "qwen-turbo"),
    "response_generator": os.getenv("RESPONSE_LLM_MODEL", "qwen-turbo"),
    "moderator": os.getenv("MODERATOR_LLM_MODEL", "qwen-turbo")
}
print(f"LLM 配置加载: Planner='{LLM_CONFIG['planner']}', ResponseGenerator='{LLM_CONFIG['response_generator']}', Moderator='{LLM_CONFIG['moderator']}'")


def _call_dashscope_llm(prompt: str, model_id: str, context_for_debug: str = "LLM Call") -> str | None:
    # (No changes to this function from Batch 1)
    if not api_key:
        print(f"错误 ({context_for_debug}): API Key 未配置。")
        return None
    dashscope.api_key = api_key

    print(f"--- Debug ({context_for_debug}): 发送 Prompt 给模型 '{model_id}' (预览前500字符) ---\n{prompt[:500]}...\n--- Prompt 预览结束 ---")
    try:
        response = dashscope.Generation.call(
            model=model_id,
            prompt=prompt,
            result_format='message'
        )

        if response.status_code == 200 and response.output and response.output.choices:
            content = response.output.choices[0].get('message', {}).get('content')
            if content is None:
                print(f"错误 ({context_for_debug}): LLM 响应中未找到有效的 'content'。模型: {model_id}, 响应: {response}")
                return None
            print(f"--- Debug ({context_for_debug}): LLM 原始响应 ---\n{content}\n--- LLM 原始响应结束 ---")
            return content.strip()
        else:
            print(f"错误 ({context_for_debug}): DashScope API 调用失败。模型: {model_id}, 状态码: {response.status_code}, 错误信息: {getattr(response, 'message', 'N/A')}, Code: {getattr(response, 'code', 'N/A')}, 请求ID: {getattr(response, 'request_id', 'N/A')}")
            return None
    except Exception as e:
        print(f"错误 ({context_for_debug}): 调用 DashScope API 时发生意外错误。模型: {model_id}")
        traceback.print_exc()
        return None

def get_llm_decision(user_input: str, chat_history: str, tools_description: str, llm_model_id: str = None) -> dict:
    # (No changes to this function from Batch 1)
    model_to_use = llm_model_id or LLM_CONFIG["planner"]
    prompt = PLANNER_PROMPT_TEMPLATE.format(
        user_input=user_input,
        chat_history=chat_history if chat_history else "无对话历史。",
        available_tools_description=tools_description
    )
    decision_json_str = _call_dashscope_llm(prompt, model_to_use, "LLM Planner Decision")

    if decision_json_str:
        try:
            text_to_parse = decision_json_str.strip()
            if text_to_parse.startswith("```json"):
                text_to_parse = text_to_parse[len("```json"):-len("```")].strip()
            elif text_to_parse.startswith("`json"):
                 text_to_parse = text_to_parse[len("`json"):-len("`")].strip()
            elif text_to_parse.startswith("```"):
                 text_to_parse = text_to_parse[len("```"):-len("```")].strip()

            decision = json.loads(text_to_parse)
            if 'action_type' not in decision:
                raise ValueError("LLM 决策 JSON 中缺少 'action_type' 字段。")
            print(f"LLM Planner 决策已解析: {decision}")
            return decision
        except (json.JSONDecodeError, ValueError) as e:
            print(f"错误: 解析 LLM Planner 的决策 JSON 失败 - {e}\nLLM Planner 原始输出为: {decision_json_str}")
            fallback_response_text = "学姐在思考下一步做什么的时候好像出了点小差错，你能换个方式问问吗？(错误参考: Planner JSON解析失败)"
            return {"action_type": "RESPOND_DIRECTLY", "response_content": fallback_response_text}
    else:
        fallback_response_text = "哎呀，学姐的思路好像卡住了，你能换个问法吗？(错误参考: Planner LLM调用失败)"
        return {"action_type": "RESPOND_DIRECTLY", "response_content": fallback_response_text}


# MODIFICATION: Added task_outcome_status parameter
def get_final_response(user_input: str, context_info: str = "", llm_model_id: str = None, task_outcome_status: str | None = None) -> str:
    """
    调用 Response Generator LLM 获取最终的、面向用户的回复。
    task_outcome_status: 由 PlannerAgent 根据工具执行结果确定的总体任务状态 (例如 "success", "not_found", "failure").
    """
    model_to_use = llm_model_id or LLM_CONFIG["response_generator"]
    use_not_found_template = False

    # MODIFICATION: Prioritize task_outcome_status for deciding the template
    if task_outcome_status == "not_found":
        use_not_found_template = True
        print("--- Debug Final Response: task_outcome_status is 'not_found', using PERSONA_NOT_FOUND_TEMPLATE ---")
    elif task_outcome_status in ["failure", "error", "partial_failure", "no_steps_executed"] and not context_info:
        # If the task failed and there's no specific context, use a generic failure persona.
        # For simplicity, we can still use the not_found template or a new one.
        # Let's use not_found for now to indicate inability to fulfill the request.
        use_not_found_template = True # Or a new template for general failure
        print(f"--- Debug Final Response: task_outcome_status is '{task_outcome_status}' with no context, using PERSONA_NOT_FOUND_TEMPLATE as fallback ---")
    # Fallback to old string matching if task_outcome_status is not definitive and knowledge_base is available
    elif knowledge_base and isinstance(context_info, str) and not use_not_found_template:
        not_found_keywords = [
            knowledge_base.NOT_FOUND_STATIC_SLANG_MSG.split("关于")[0].strip() if hasattr(knowledge_base, 'NOT_FOUND_STATIC_SLANG_MSG') else "###UNIQUE_NO_MATCH###",
            knowledge_base.NOT_FOUND_STATIC_FOOD_MSG.split("哎呀，")[1].split("哦")[0].strip() if hasattr(knowledge_base, 'NOT_FOUND_STATIC_FOOD_MSG') else "###UNIQUE_NO_MATCH###",
            knowledge_base.NOT_FOUND_ANY_INFO_FOR_QUERY_MSG.split("关于")[1].split("，")[0].strip() if hasattr(knowledge_base, 'NOT_FOUND_ANY_INFO_FOR_QUERY_MSG') else "###UNIQUE_NO_MATCH###",
            "暂时没有找到和你问题直接相关的信息呢", "学姐我好像还没学到呢",
            "小本本上还没有关于", "暂时没有找到符合你要求的美食推荐信息哦",
            "翻了翻共享的笔记，暂时没有找到", "专属小本本里，学姐暂时没有找到",
        ]
        not_found_keywords = [kw for kw in not_found_keywords if kw and kw != "###UNIQUE_NO_MATCH###"]
        if any(keyword in context_info for keyword in not_found_keywords):
            use_not_found_template = True
            print("--- Debug Final Response: Detected '未找到' keywords in context_info, using PERSONA_NOT_FOUND_TEMPLATE ---")


    if use_not_found_template:
        prompt = PERSONA_NOT_FOUND_TEMPLATE.format(user_input=user_input)
    else:
        formatted_context = ""
        if context_info:
            formatted_context = f"\n\n背景参考信息（请不要直接复述，而是自然地融入你的回答中）：\n```\n{str(context_info)[:1000]}\n```\n请你作为旦旦学姐，基于以上背景信息和我之前的问题进行回复。"
        prompt = GENERAL_CHAT_PROMPT_TEMPLATE.format(user_input=user_input, context_info=formatted_context)

    reply_text = _call_dashscope_llm(prompt, model_to_use, "LLM Final Response")

    if reply_text:
        return reply_text
    else:
        # Provide a more specific error if the persona template was used due to failure
        if use_not_found_template and task_outcome_status and task_outcome_status != "not_found":
             return "哎呀，学姐在尝试回答你的时候遇到了一点小麻烦，没能找到满意的答案，要不换个问题试试？😥 (错误参考: 回复生成LLM调用失败，任务处理中遇到问题)"
        return "哎呀，学姐在组织语言的时候好像出了点小差错，你能再说一遍吗？😅 (错误参考: 回复生成LLM调用失败)"


def check_input_appropriateness(user_input: str, llm_model_id: str = None) -> dict:
    # (No changes to this function from Batch 1)
    model_to_use = llm_model_id or LLM_CONFIG["moderator"]
    prompt = MODERATION_PROMPT_TEMPLATE.format(user_input=user_input)

    moderation_json_str = _call_dashscope_llm(prompt, model_to_use, "Content Moderation")

    if moderation_json_str:
        try:
            text_to_parse = moderation_json_str.strip()
            if text_to_parse.startswith("```json"):
                text_to_parse = text_to_parse[len("```json"):-len("```")].strip()
            elif text_to_parse.startswith("`json"):
                 text_to_parse = text_to_parse[len("`json"):-len("`")].strip()
            elif text_to_parse.startswith("```"):
                 text_to_parse = text_to_parse[len("```"):-len("```")].strip()

            moderation_result = json.loads(text_to_parse)
            is_inappropriate = moderation_result.get("is_inappropriate", False)
            warning_message = moderation_result.get("warning_message")

            if not isinstance(is_inappropriate, bool):
                print(f"警告: 审核LLM返回的 is_inappropriate 不是布尔值: {is_inappropriate}。将视为不当内容。")
                is_inappropriate = True
                warning_message = warning_message or "学姐觉得你的话好像有点不太合适哦，我们换个话题吧！"

            print(f"内容审核结果: 不当内容={is_inappropriate}, 警告消息='{warning_message}'")
            return {"is_inappropriate": is_inappropriate, "warning_message": warning_message if is_inappropriate else None}
        except (json.JSONDecodeError, ValueError) as e:
            print(f"错误: 解析内容审核LLM的JSON响应失败 - {e}")
            print(f"内容审核LLM原始输出为: {moderation_json_str}")
            return {"is_inappropriate": True, "warning_message": "系统审核暂时有点小迷糊，但还是请注意友好交流哦～ (错误参考: 审核JSON解析失败)"}
    else:
        print("错误: 内容审核LLM调用失败。为安全起见，将默认标记为不当。")
        return {"is_inappropriate": True, "warning_message": "系统审核暂时出小差了，但还是请注意友好交流哦～ (错误参考: 审核LLM调用失败)"}




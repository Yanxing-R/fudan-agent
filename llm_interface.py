# llm_interface.py
import os
import json
import dashscope
from dashscope.api_entities.dashscope_response import GenerationResponse
import traceback # 引入 traceback

# 导入 Prompt 模板 (确保 prompts.py 中有这些定义)
from prompts import (
    PLANNER_PROMPT_TEMPLATE,
    GENERAL_CHAT_PROMPT_TEMPLATE,
    PERSONA_NOT_FOUND_TEMPLATE
)

# --- API Key 配置 ---
api_key = os.getenv("DASHSCOPE_API_KEY")
if not api_key:
    print("错误：环境变量 DASHSCOPE_API_KEY 未设置！程序可能无法正常调用LLM。")
# dashscope.api_key = api_key # 建议在每个函数调用前设置

# --- LLM 模型配置 ---
LLM_CONFIG = {
    "planner": os.getenv("PLANNER_LLM_MODEL", "qwen-turbo"),
    "response_generator": os.getenv("RESPONSE_LLM_MODEL", "qwen-turbo"),
    # "knowledge_learner": os.getenv("LEARNER_LLM_MODEL", "qwen-turbo") # 如果需要单独的learner
}
print(f"LLM 配置加载: Planner='{LLM_CONFIG['planner']}', ResponseGenerator='{LLM_CONFIG['response_generator']}'")


def _call_dashscope_llm(prompt: str, model_id: str, context_for_debug: str = "LLM Call") -> str | None:
    """封装通用的 DashScope LLM 调用逻辑"""
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
        if response.status_code == 200:
            content = response.output.choices[0]['message']['content']
            print(f"--- Debug ({context_for_debug}): LLM 原始响应 ---\n{content}\n--- LLM 原始响应结束 ---")
            return content.strip()
        else:
            print(f"错误 ({context_for_debug}): DashScope API 调用失败。模型: {model_id}, 状态码: {response.status_code}, 错误信息: {getattr(response, 'message', 'N/A')}, 请求ID: {getattr(response, 'request_id', 'N/A')}")
            return None
    except Exception as e:
        print(f"错误 ({context_for_debug}): 调用 DashScope API 时发生意外错误。模型: {model_id}")
        traceback.print_exc() # 打印完整错误堆栈
        return None


def get_llm_decision(user_input: str, chat_history: str, tools_description: str, llm_model_id: str = None) -> dict:
    """调用 LLM (Planner) 进行任务规划和工具选择。返回一个包含决策的字典。"""
    model_to_use = llm_model_id or LLM_CONFIG["planner"]
    prompt = PLANNER_PROMPT_TEMPLATE.format(
        user_input=user_input,
        chat_history=chat_history if chat_history else "无对话历史。",
        available_tools_description=tools_description # 这里现在是 Specialist Agent 的能力描述
    )
    
    decision_json_str = _call_dashscope_llm(prompt, model_to_use, "LLM Planner Decision")

    if decision_json_str:
        try:
            text_to_parse = decision_json_str.strip()
            if text_to_parse.startswith("```json"):
                text_to_parse = text_to_parse[7:-3].strip()
            elif text_to_parse.startswith("`json"):
                 text_to_parse = text_to_parse[5:-1].strip()
            elif text_to_parse.startswith("```"):
                 text_to_parse = text_to_parse[3:-3].strip()

            decision = json.loads(text_to_parse)
            if 'action_type' not in decision:
                raise ValueError("LLM 决策 JSON 中缺少 'action_type' 字段。")
            print(f"LLM Planner 决策已解析: {decision}")
            return decision
        except (json.JSONDecodeError, ValueError) as e:
            print(f"错误: 解析 LLM Planner 的决策 JSON 失败 - {e}")
            print(f"LLM Planner 原始输出为: {decision_json_str}")
            return {
                "action_type": "RESPOND_DIRECTLY", 
                "response_content": get_final_response(user_input, f"学姐在思考下一步做什么的时候好像出了点小差错 ({e})，你能换个方式问问吗？", llm_model_id=LLM_CONFIG["response_generator"])
            }
    else:
        return {
            "action_type": "RESPOND_DIRECTLY",
            "response_content": "哎呀，学姐的思路好像卡住了，你能换个问法吗？🤔"
        }


def get_final_response(user_input: str, context_info: str = "", llm_model_id: str = None) -> str:
    """调用 LLM (Response Generator) 生成最终给用户的、带学姐人设的回复。"""
    model_to_use = llm_model_id or LLM_CONFIG["response_generator"]
    
    # 根据 context_info 判断是否使用 PERSONA_NOT_FOUND_TEMPLATE
    # (这个逻辑可以更精细，比如检查 context_info 是否包含特定的“未找到”关键词)
    use_not_found_template = False
    if isinstance(context_info, str):
        not_found_keywords = [
            "抱歉，我还不知道", "唉呀，暂时没有找到", 
            "暂时没有找到和你问题直接相关的信息呢", "学姐我好像还没学到呢",
            "静态知识库暂不支持查询", "知识Agent未能处理任务" # 来自 Specialist Agent 的明确失败信号
        ]
        if any(keyword in context_info for keyword in not_found_keywords):
            use_not_found_template = True
            print("--- Debug Final Response: 检测到 '未找到' 上下文，将使用 PERSONA_NOT_FOUND_TEMPLATE ---")

    if use_not_found_template:
        prompt = PERSONA_NOT_FOUND_TEMPLATE.format(user_input=user_input)
    else:
        formatted_context = ""
        if context_info:
            # 截断过长的上下文，避免超出LLM限制或影响回复重点
            formatted_context = f"\n\n背景参考信息（请不要直接复述，而是自然地融入你的回答中）：\n```\n{str(context_info)[:1000]}\n```\n请你作为旦旦学姐，基于以上背景信息和我之前的问题进行回复。"
        
        prompt = GENERAL_CHAT_PROMPT_TEMPLATE.format(
            user_input=user_input,
            context_info=formatted_context
        )
    
    reply_text = _call_dashscope_llm(prompt, model_to_use, "LLM Final Response")

    if reply_text:
        return reply_text
    else:
        return "哎呀，学姐在组织语言的时候好像出了点小差错，你能再说一遍吗？😅"

# structure_learned_knowledge 函数可以保持不变，如果 FudanKnowledgeAgent 内部需要用 LLM 辅助学习

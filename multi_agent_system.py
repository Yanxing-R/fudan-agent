# multi_agent_system.py
# Batch 3: Adapting Agents and Orchestrator to handle structured dict returns from tools.
# ADDED FIX: ReviewAgent to correctly read 'user_query'.

import datetime
import json
import uuid
import time
import traceback
import threading

import llm_interface
import knowledge_base # knowledge_base constants might be used for specific status checks if needed
import agent_tools

# --- Agent 基类 (No changes from Batch 1) ---
class BaseAgent:
    def __init__(self, agent_id: str, orchestrator, llm_model_config: dict = None):
        self.agent_id = agent_id
        self.orchestrator = orchestrator
        self.llm_model_config = llm_model_config if llm_model_config else llm_interface.LLM_CONFIG.copy()
        print(f"🚀 Agent '{self.agent_id}' 已初始化。")
    def _create_message(self, recipient_id: str, message_type: str, payload: dict, session_id: str, sender_id: str = None) -> dict:
        return {
            "message_id": f"msg_{uuid.uuid4().hex[:8]}", "session_id": session_id,
            "sender_id": sender_id or self.agent_id, "recipient_id": recipient_id,
            "message_type": message_type, "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "payload": payload
        }
    def process_message(self, message: dict):
        raise NotImplementedError(f"Agent '{self.agent_id}' 必须实现 process_message 方法。")
    def send_message(self, message: dict):
        print(f"📬 [消息发送] '{message['sender_id']}' -> '{message['recipient_id']}' (类型: {message['message_type']}, 会话: {message['session_id']})")
        self.orchestrator.add_message_to_queue(message)

# --- FudanUserProxyAgent (No changes from Batch 1) ---
class FudanUserProxyAgent(BaseAgent):
    def __init__(self, agent_id: str, orchestrator, llm_model_config: dict = None):
        super().__init__(agent_id, orchestrator, llm_model_config)
    def initiate_task(self, user_id: str, user_query: str) -> str:
        session_id = f"session_{user_id.replace('@', '_')}_{uuid.uuid4().hex[:6]}"
        self.orchestrator.register_session(session_id, user_id, user_query)
        print(f"🚀 [用户接口] '{self.agent_id}' 为用户 '{user_id}' 发起新任务 (会话: {session_id})。查询: '{user_query}'")
        initial_message_for_orchestrator = self._create_message(
            recipient_id="Orchestrator", message_type="new_user_query_received",
            payload={"user_query": user_query, "user_id": user_id}, session_id=session_id # Payload key is 'user_query'
        )
        self.send_message(initial_message_for_orchestrator); return session_id
    def process_message(self, message: dict):
        session_id = message["session_id"]; user_id = self.orchestrator.get_session_user_id(session_id)
        if message["message_type"] == "final_answer_to_user":
            final_answer = message["payload"].get("answer", "学姐好像没什么要说的了呢。")
            print(f"✅ [用户接口] '{self.agent_id}' (用户: {user_id}, 会话: {session_id}) 收到最终答案:\n   学姐回复: {final_answer}")
            self.orchestrator.mark_session_completed(session_id, final_answer)
        elif message["message_type"] == "clarification_request_to_user":
            clarification_question = message["payload"].get("question", "学姐有点没明白，能再说具体点吗？")
            print(f"❓ [用户接口] '{self.agent_id}' (用户: {user_id}, 会话: {session_id}) 收到澄清请求:\n   学姐提问: {clarification_question}")
            self.orchestrator.mark_session_pending_user_input(session_id, clarification_question)
        else: print(f"⚠️ [用户接口] '{self.agent_id}' 收到未处理的消息类型: '{message['message_type']}' (来自: '{message['sender_id']}')")

# --- FudanPlannerAgent (MODIFIED _synthesize_final_answer in Batch 3) ---
class FudanPlannerAgent(BaseAgent):
    def __init__(self, agent_id: str, orchestrator, llm_model_config: dict = None):
        super().__init__(agent_id, orchestrator, llm_model_config)
        self.specialist_agents_capabilities_description = ""
    def _plan_task_or_respond_directly(self, user_query: str, user_id: str, session_id: str, chat_history: str):
        if not self.specialist_agents_capabilities_description:
            self.specialist_agents_capabilities_description = self.orchestrator.get_specialist_agent_capabilities_description()
        llm_decision = llm_interface.get_llm_decision(
            user_input=user_query, chat_history=chat_history,
            tools_description=self.specialist_agents_capabilities_description,
            llm_model_id=self.llm_model_config.get("planner", llm_interface.LLM_CONFIG["planner"])
        )
        print(f"🧠 [规划器] LLM 决策 for '{user_query[:50]}...': {json.dumps(llm_decision, ensure_ascii=False, indent=2)}")
        action_type = llm_decision.get("action_type")
        if action_type == "RESPOND_DIRECTLY":
            response_content = llm_decision.get("response_content", "学姐想了想，但好像没什么特别要说的。🤔")
            final_msg = self._create_message("FudanUserProxyAgent", "final_answer_to_user", {"answer": response_content}, session_id)
            self.send_message(final_msg)
        elif action_type == "CLARIFY":
            clarification_question = llm_decision.get("clarification_question", "学姐有点没明白，能再说具体点吗？")
            clarify_msg = self._create_message("FudanUserProxyAgent", "clarification_request_to_user", {"question": clarification_question}, session_id)
            self.send_message(clarify_msg)
        elif action_type == "EXECUTE_PLAN":
            plan = llm_decision.get("plan")
            if isinstance(plan, list) and plan and \
               all(isinstance(step, dict) and "agent_id" in step and "task_payload" in step and \
                   isinstance(step["task_payload"], dict) for step in plan):
                print(f"📑 [规划器] 生成计划包含 {len(plan)} 个步骤。提交给 Orchestrator...")
                plan_submission_msg = self._create_message(
                    recipient_id="Orchestrator", message_type="plan_submission",
                    payload={"plan": plan, "original_query": user_query, "user_id": user_id}, session_id=session_id
                )
                self.send_message(plan_submission_msg)
            else:
                print(f"❌ [规划器] LLM 生成的计划格式无效或为空。决策: {llm_decision}")
                err_response = llm_interface.get_final_response(user_input=user_query, context_info="学姐在规划任务的时候好像出了点小问题，这个计划不太对劲哦。", llm_model_id=self.llm_model_config.get("response_generator"))
                self.send_message(self._create_message("FudanUserProxyAgent", "final_answer_to_user", {"answer": err_response}, session_id))
        else:
            print(f"❌ [规划器] LLM返回了未知的决策类型: '{action_type}' 或决策结构错误。决策: {llm_decision}")
            err_response = llm_interface.get_final_response(user_input=user_query, context_info="学姐的思路有点混乱，没法处理你的请求啦。", llm_model_id=self.llm_model_config.get("response_generator"))
            self.send_message(self._create_message("FudanUserProxyAgent", "final_answer_to_user", {"answer": err_response}, session_id))

    def _synthesize_final_answer(self, original_query: str, user_id: str, step_results: list, session_id: str):
        print(f"📝 [规划器] '{self.agent_id}' 开始为用户 '{user_id}' (会话: {session_id}) 综合最终答案...")
        context_for_synthesis = f"用户的原始问题是：“{original_query}”\n\n";
        overall_task_status = "success" 

        if step_results:
            context_for_synthesis += "为了回答这个问题，我和我的伙伴们进行了以下尝试和思考：\n"
            for i, res_info_wrapper in enumerate(step_results): 
                agent_id_executor = res_info_wrapper.get('agent_id', '未知Agent')
                tool_result_dict = res_info_wrapper.get('executed_tool_result', {})
                original_task_payload = res_info_wrapper.get('original_task_payload', {}).get('task_payload', {})
                executed_item = original_task_payload.get('tool_to_execute', original_task_payload.get('task_type', '未知任务'))

                current_step_status = tool_result_dict.get('status', 'unknown_status')
                current_step_data_summary = str(tool_result_dict.get('data', '无结果数据'))[:250] 

                context_for_synthesis += f"- 步骤 {i+1} (由 '{agent_id_executor}' 执行 '{executed_item}', 状态: {current_step_status}):\n  结果摘要: {current_step_data_summary}...\n"
                
                if current_step_status == "not_found":
                    overall_task_status = "not_found" 
                elif current_step_status in ["failure", "error"] and overall_task_status == "success":
                    overall_task_status = "partial_failure" 
        else:
            context_for_synthesis += "但似乎没有执行任何具体的步骤，或者步骤没有结果。\n"
            overall_task_status = "no_steps_executed"

        context_for_synthesis += "\n现在，请你作为“旦旦学姐”，基于以上所有信息，给用户一个友好、完整且有帮助的最终回复。"
        
        final_answer_text = llm_interface.get_final_response(
            user_input=original_query,
            context_info=context_for_synthesis,
            llm_model_id=self.llm_model_config.get("response_generator"),
            task_outcome_status=overall_task_status 
        )

        if not final_answer_text: final_answer_text = "哎呀，学姐处理完所有信息之后，发现不知道怎么回复你了...要不我们聊点别的？😅"
        self.send_message(self._create_message(recipient_id="FudanUserProxyAgent", message_type="final_answer_to_user", payload={"answer": final_answer_text}, session_id=session_id))

    def process_message(self, message: dict):
        session_id = message["session_id"]; user_id = message["payload"].get("user_id", self.orchestrator.get_session_user_id(session_id))
        if message["message_type"] == "user_query_for_planning":
            user_query = message["payload"]["user_query"]; chat_history = self.orchestrator.get_session_chat_history_str(user_id)
            print(f"📝 [规划器] '{self.agent_id}' 收到通过审核的用户查询 '{user_query}' (用户: {user_id}, 会话: {session_id})，开始规划...")
            self._plan_task_or_respond_directly(user_query, user_id, session_id, chat_history)
        elif message["message_type"] == "request_synthesis":
            original_query = message["payload"]["original_query"]; step_results = message["payload"]["step_results"]
            self._synthesize_final_answer(original_query, user_id, step_results, session_id)
        else: print(f"⚠️ [规划器] '{self.agent_id}' 收到未处理的消息类型: '{message['message_type']}' (来自: '{message['sender_id']}')")

# --- KnowledgeAgent (MODIFIED to handle tool's dict return in Batch 3) ---
class KnowledgeAgent(BaseAgent):
    def __init__(self, agent_id: str, orchestrator, llm_model_config: dict = None):
        super().__init__(agent_id, orchestrator, llm_model_config)
        self.knowledge_tools_map = {
            tool_name: tool_instance
            for tool_name, tool_instance in agent_tools.get_all_registered_tools().items()
            if tool_name in ["StaticKnowledgeBaseQueryTool", "LearnNewInfoTool", "QueryDynamicKnowledgeTool"]
        }
        print(f"📚 [知识Agent] '{self.agent_id}' 已初始化，可执行知识工具: {list(self.knowledge_tools_map.keys())}")

    def process_message(self, message: dict):
        session_id = message["session_id"]
        task_payload_from_planner = message["payload"].get("task_payload", {})
        user_id_for_tool = message["payload"].get("user_id")

        print(f"📚 [知识Agent] '{self.agent_id}' 收到任务 (会话: {session_id}, 用户: {user_id_for_tool}): {task_payload_from_planner}")

        tool_name_to_execute = task_payload_from_planner.get("tool_to_execute")
        tool_arguments = task_payload_from_planner.get("tool_args", {})
        if tool_arguments is None: tool_arguments = {}
        
        executed_tool_result_dict = {
            "status": "failure", 
            "data": f"知识Agent未能找到或执行工具 '{tool_name_to_execute}'。"
        }

        if tool_name_to_execute in self.knowledge_tools_map:
            tool_instance = self.knowledge_tools_map[tool_name_to_execute]
            try:
                if tool_name_to_execute in ["LearnNewInfoTool", "QueryDynamicKnowledgeTool"]:
                    if not user_id_for_tool:
                        raise ValueError(f"工具 '{tool_name_to_execute}' 需要 user_id，但 Orchestrator/Planner 未提供。")
                    tool_arguments["user_id"] = user_id_for_tool

                print(f"  [知识Agent] 正在执行知识工具 '{tool_name_to_execute}' 带参数: {tool_arguments}")
                executed_tool_result_dict = tool_instance.execute(**tool_arguments) 

            except TypeError as te:
                print(f"❌ [知识Agent] 调用工具 '{tool_name_to_execute}' 时参数不匹配: {te}"); traceback.print_exc()
                executed_tool_result_dict = {"status": "failure", "data": f"调用知识工具 '{tool_name_to_execute}' 时提供的参数不正确。错误: {te}", "reason": "type_error"}
            except ValueError as ve: 
                 print(f"❌ [知识Agent] 调用工具 '{tool_name_to_execute}' 时值错误: {ve}"); traceback.print_exc()
                 executed_tool_result_dict = {"status": "failure", "data": f"调用知识工具 '{tool_name_to_execute}' 时缺少必要信息。错误: {ve}", "reason": "value_error"}
            except Exception as e:
                print(f"❌ [知识Agent] 执行工具 '{tool_name_to_execute}' 时发生意外错误: {e}"); traceback.print_exc()
                executed_tool_result_dict = {"status": "error", "data": f"执行知识工具 '{tool_name_to_execute}' 时出错: {str(e)}", "reason": "execution_exception"}
        else:
            executed_tool_result_dict = {"status": "failure", "data": f"知识Agent '{self.agent_id}' 不知道名为 '{tool_name_to_execute}' 的知识工具。", "reason": "tool_not_found_in_agent"}

        print(f"  [知识Agent] 工具执行结果字典: {executed_tool_result_dict}")
        result_message_payload = {
            "executed_tool_result": executed_tool_result_dict,
            "original_task_payload": message["payload"]
        }
        self.send_message(self._create_message(recipient_id="Orchestrator", message_type="step_result", payload=result_message_payload, session_id=session_id))

# --- UtilityAgent (MODIFIED to handle tool's dict return in Batch 3) ---
class UtilityAgent(BaseAgent):
    def __init__(self, agent_id: str, orchestrator, llm_model_config: dict = None):
        super().__init__(agent_id, orchestrator, llm_model_config)
        self.utility_tools_map = {tool_name: tool_instance for tool_name, tool_instance in agent_tools.get_all_registered_tools().items() if tool_name in ["get_current_time", "calculator", "get_weather_forecast"]}
        print(f"🛠️ [通用工具Agent] '{self.agent_id}' 已初始化，可执行工具: {list(self.utility_tools_map.keys())}")

    def process_message(self, message: dict):
        session_id = message["session_id"]; task_payload_from_planner = message["payload"].get("task_payload", {})
        print(f"🛠️ [通用工具Agent] '{self.agent_id}' 收到任务 (会话: {session_id}): {task_payload_from_planner}")
        tool_name_to_execute = task_payload_from_planner.get("tool_to_execute"); tool_arguments = task_payload_from_planner.get("tool_args", {});
        if tool_arguments is None: tool_arguments = {}

        executed_tool_result_dict = {
            "status": "failure",
            "data": f"通用工具Agent未能找到或执行工具 '{tool_name_to_execute}'。"
        }

        if tool_name_to_execute in self.utility_tools_map:
            tool_instance = self.utility_tools_map[tool_name_to_execute]
            try:
                print(f"  [通用工具Agent] 正在执行工具 '{tool_name_to_execute}' 带参数: {tool_arguments}")
                executed_tool_result_dict = tool_instance.execute(**tool_arguments) 

            except TypeError as te:
                print(f"❌ [通用工具Agent] 调用工具 '{tool_name_to_execute}' 时参数不匹配: {te}"); traceback.print_exc()
                executed_tool_result_dict = {"status": "failure", "data": f"调用通用工具 '{tool_name_to_execute}' 时提供的参数不正确。错误: {te}", "reason": "type_error"}
            except Exception as e:
                print(f"❌ [通用工具Agent] 执行工具 '{tool_name_to_execute}' 时发生意外错误: {e}"); traceback.print_exc()
                executed_tool_result_dict = {"status": "error", "data": f"执行通用工具 '{tool_name_to_execute}' 时出错: {str(e)}", "reason": "execution_exception"}
        else:
            executed_tool_result_dict = {"status": "failure", "data": f"通用工具Agent '{self.agent_id}' 不知道名为 '{tool_name_to_execute}' 的工具。", "reason": "tool_not_found_in_agent"}

        print(f"  [通用工具Agent] 工具执行结果字典: {executed_tool_result_dict}")
        result_message_payload = {
            "executed_tool_result": executed_tool_result_dict,
            "original_task_payload": message["payload"]
        }
        self.send_message(self._create_message(recipient_id="Orchestrator", message_type="step_result", payload=result_message_payload, session_id=session_id))

# --- ReviewAgent (MODIFIED to correctly get user_query) ---
class ReviewAgent(BaseAgent):
    def __init__(self, agent_id: str, orchestrator, llm_model_config: dict = None):
        super().__init__(agent_id, orchestrator, llm_model_config)

    def process_message(self, message: dict):
        session_id = message["session_id"]
        # MODIFICATION: Get 'user_query' from payload, which is what UserProxyAgent sends via Orchestrator
        actual_user_query = message["payload"].get("user_query") # Correct key
        user_id = message["payload"].get("user_id")

        if not actual_user_query: # Check if the actual query is empty or None
            print(f"⚠️ [审核Agent] '{self.agent_id}' (用户: {user_id}, 会话: {session_id}) 收到空的用户查询 ('{actual_user_query}') 进行审核。将按通过处理。")
            # Pass the original (empty) query forward
            self.send_message(self._create_message(
                recipient_id="Orchestrator",
                message_type="moderation_passed_for_planning",
                payload={"user_input": actual_user_query if actual_user_query is not None else "", "user_id": user_id}, # Send original query
                session_id=session_id
            ))
            return

        print(f"🧐 [审核Agent] '{self.agent_id}' 正在审核用户 '{user_id}' 的输入: '{str(actual_user_query)[:100]}...' (会话: {session_id})")
        moderation_result = llm_interface.check_input_appropriateness(
            actual_user_query, # Use the correct query for moderation
            llm_model_id=self.llm_model_config.get("moderator", llm_interface.LLM_CONFIG["moderator"])
        )

        if moderation_result.get("is_inappropriate"):
            warning_text = moderation_result.get("warning_message", "学姐提醒您，请注意言辞，保持友好交流哦。")
            print(f"🚫 [审核Agent] 用户 '{user_id}' 输入被标记为不当。警告: '{warning_text}'")
            self.send_message(self._create_message(
                recipient_id="Orchestrator",
                message_type="moderation_failed_with_warning",
                payload={"warning_message": warning_text, "user_id": user_id, "original_query": actual_user_query},
                session_id=session_id
            ))
        else:
            print(f"👍 [审核Agent] 用户 '{user_id}' 输入通过审核。")
            self.send_message(self._create_message(
                recipient_id="Orchestrator",
                message_type="moderation_passed_for_planning",
                # IMPORTANT: Pass the original user query to the planner under the key 'user_input'
                # as this is what the PlannerAgent expects from the Orchestrator in this message type.
                payload={"user_input": actual_user_query, "user_id": user_id},
                session_id=session_id
            ))

# --- Orchestrator (MODIFIED to handle structured step_result in Batch 3) ---
class Orchestrator:
    def __init__(self):
        self.agents = {}; self.message_queue = []; self.sessions = {}
        self._initialize_agents(); self.session_completion_events = {}; self.app_context = None
        print("🌟 Orchestrator 已初始化。")

    def set_app_context(self, app_instance):
        self.app_context = app_instance; print("[Orchestrator] 应用上下文已设置。")

    def _initialize_agents(self):
        print("[Orchestrator] 系统初始化: 正在创建 Agents...")
        self.agents["FudanUserProxyAgent"] = FudanUserProxyAgent("FudanUserProxyAgent", self)
        self.agents["FudanPlannerAgent"] = FudanPlannerAgent("FudanPlannerAgent", self)
        self.agents["KnowledgeAgent"] = KnowledgeAgent("KnowledgeAgent", self)
        self.agents["UtilityAgent"] = UtilityAgent("UtilityAgent", self)
        self.agents["ReviewAgent"] = ReviewAgent("ReviewAgent", self)
        print(f"[Orchestrator] 系统初始化: {len(self.agents)} 个 Agent 已创建: {list(self.agents.keys())}")
        if "FudanPlannerAgent" in self.agents:
             planner_agent = self.agents["FudanPlannerAgent"]
             if hasattr(planner_agent, 'specialist_agents_capabilities_description'):
                 planner_agent.specialist_agents_capabilities_description = self.get_specialist_agent_capabilities_description()
                 print("[Orchestrator] FudanPlannerAgent 的专长Agent能力描述已设置。")

    def get_specialist_agent_capabilities_description(self) -> str:
        descriptions = []
        knowledge_agent_id = "KnowledgeAgent"
        if knowledge_agent_id in self.agents and hasattr(self.agents[knowledge_agent_id], 'knowledge_tools_map'):
            desc_parts = [f"- Agent ID: `{knowledge_agent_id}`", f"  能力描述: 专责处理与复旦大学相关的知识问答和学习新知识。调用此 Agent 时，你的 `task_payload` 中必须包含 `tool_to_execute` (从以下工具名中选择一个) 和该工具所需的 `tool_args` (参考各工具的参数定义)。", f"  可执行的内部工具:"]
            for tool_name, tool_instance in self.agents[knowledge_agent_id].knowledge_tools_map.items():
                tool_llm_info = tool_instance.get_info_for_llm(); desc_parts.append(f"    * 工具名 `{tool_llm_info['name']}`: {tool_llm_info['description']} 参数: {json.dumps(tool_llm_info['parameters'], ensure_ascii=False)}")
            descriptions.append("\n".join(desc_parts))
        utility_agent_id = "UtilityAgent"
        if utility_agent_id in self.agents and hasattr(self.agents[utility_agent_id], 'utility_tools_map'):
            desc_parts = [f"- Agent ID: `{utility_agent_id}`", f"  能力描述: 专责执行通用的辅助工具。调用此 Agent 时，你的 `task_payload` 中必须包含 `tool_to_execute` (从以下工具名中选择一个) 和该工具所需的 `tool_args` (参考各工具的参数定义)。", f"  可执行的内部工具:"]
            for tool_name, tool_instance in self.agents[utility_agent_id].utility_tools_map.items():
                tool_llm_info = tool_instance.get_info_for_llm(); desc_parts.append(f"    * 工具名 `{tool_llm_info['name']}`: {tool_llm_info['description']} 参数: {json.dumps(tool_llm_info['parameters'], ensure_ascii=False)}")
            descriptions.append("\n".join(desc_parts))
        if not descriptions: return "当前没有可用的专长Agent。"
        return "你可以委托以下专长Agent来完成特定类型的任务（如果一个用户请求需要多个专长Agent协作，请在计划中列出所有步骤）：\n\n" + "\n\n".join(descriptions)

    def add_message_to_queue(self, message: dict):
        self.message_queue.append(message)

    def register_session(self, session_id: str, user_id: str, user_query: str):
        self.sessions[session_id] = {"user_id": user_id, "user_query": user_query, "status": "pending_review", "plan": None, "current_step_index": 0, "step_results": [], "final_answer": None, "clarification_question": None, "start_time": time.time()};
        self.session_completion_events[session_id] = threading.Event();
        print(f"🚀 [会话管理] 会话 '{session_id}' (用户: '{user_id}') 已注册。查询: '{user_query}'。状态: pending_review")

    def get_session_user_id(self, session_id: str) -> str | None:
        return self.sessions.get(session_id, {}).get("user_id")

    def get_session_chat_history_str(self, user_id: str) -> str:
        if self.app_context and hasattr(self.app_context, 'get_user_chat_history_for_agent'):
            return self.app_context.get_user_chat_history_for_agent(user_id)
        return "无之前的对话内容（或历史获取功能未连接）。"

    def mark_session_completed(self, session_id: str, final_answer: str):
        if session_id in self.sessions:
            self.sessions[session_id]["status"] = "completed"; self.sessions[session_id]["final_answer"] = final_answer;
            print(f"✅ [会话管理] 会话 '{session_id}' 已标记为完成。");
            if session_id in self.session_completion_events: self.session_completion_events[session_id].set()
        else: print(f"⚠️ [会话管理] 尝试标记不存在的会话 '{session_id}' 为完成。")

    def mark_session_pending_user_input(self, session_id: str, clarification_question: str):
        if session_id in self.sessions:
            self.sessions[session_id]["status"] = "pending_user_input"; self.sessions[session_id]["clarification_question"] = clarification_question; self.sessions[session_id]["final_answer"] = clarification_question;
            print(f"❓ [会话管理] 会话 '{session_id}' 等待用户澄清。问题: {clarification_question}");
            if session_id in self.session_completion_events: self.session_completion_events[session_id].set()
        else: print(f"⚠️ [会话管理] 尝试标记不存在的会话 '{session_id}' 为等待用户输入。")

    def _handle_session_failure(self, session_id: str, error_reason: str, is_moderation_failure: bool = False):
        print(f"❌ [会话管理] 会话 '{session_id}' 失败: {error_reason}")
        if session_id in self.sessions:
            self.sessions[session_id]["status"] = "failed"
            if is_moderation_failure:
                user_friendly_error = error_reason # Moderation failure already provides a user-friendly message
                # Potentially log the original query if available from session_data
                original_query = self.sessions[session_id].get("user_query", "N/A")
                print(f"🚫 Moderation failed for query: '{original_query}'")
            else:
                user_friendly_error = f"哎呀，学姐在处理你的请求时好像遇到了一点小麻烦 ({str(error_reason)[:50]}...)，要不我们换个话题或者稍后再试？😥"
            self.sessions[session_id]["final_answer"] = user_friendly_error
            if session_id in self.session_completion_events: self.session_completion_events[session_id].set()
        else: print(f"⚠️ [会话管理] 尝试处理不存在的会话 '{session_id}' 的失败。")

    def _process_orchestrator_message(self, message: dict):
        session_id = message["session_id"]; session_data = self.sessions.get(session_id)
        if not session_data: print(f"⚠️ [编排器] 收到未知会话 '{session_id}' 的消息。忽略。"); return
        message_type = message["message_type"];
        print(f"⚙️ [编排器] 处理会话 '{session_id}' 的消息，类型: '{message_type}' (来自: '{message['sender_id']}')")

        if message_type == "new_user_query_received": 
            payload_for_review = message["payload"] # Contains 'user_query' and 'user_id'
            session_data["status"] = "pending_review"
            # Message type for ReviewAgent should be specific if it expects one, or generic.
            # Assuming ReviewAgent's process_message handles the payload directly.
            self.add_message_to_queue(self.agents["ReviewAgent"]._create_message(
                recipient_id="ReviewAgent",
                message_type="request_input_review", # This type is descriptive
                payload=payload_for_review, # Forward the payload containing user_query
                session_id=session_id
            ))
        elif message_type == "moderation_failed_with_warning": 
            self._handle_session_failure(session_id, message["payload"].get("warning_message", "您的输入可能不当"), is_moderation_failure=True)
        elif message_type == "moderation_passed_for_planning": 
            # Payload from ReviewAgent now contains 'user_input' (which is the original 'user_query')
            original_user_input_from_review = message["payload"].get("user_input")
            user_id = message["payload"].get("user_id");
            print(f"👍 [编排器] 会话 '{session_id}' (用户: {user_id}, 查询: '{original_user_input_from_review}') 内容审核通过。转发给规划器。");
            session_data["status"] = "pending_plan"
            self.add_message_to_queue(self.agents["FudanPlannerAgent"]._create_message(
                recipient_id="FudanPlannerAgent",
                message_type="user_query_for_planning",
                payload={"user_query": original_user_input_from_review, "user_id": user_id}, # Planner expects 'user_query'
                session_id=session_id
            ))
        elif message_type == "plan_submission": 
            plan = message["payload"].get("plan")
            if not isinstance(plan, list) or not all(isinstance(step, dict) and "agent_id" in step and "task_payload" in step for step in plan):
                self._handle_session_failure(session_id, "Planner提交的计划格式无效。"); return
            if not plan: print(f"ℹ️ [编排器] 会话 '{session_id}' 收到空计划。"); return
            session_data["plan"] = plan;
            # Ensure original_query and user_id are stored if not already (e.g., if plan comes very early)
            if "original_query" not in session_data or not session_data["original_query"]:
                 session_data["original_query"] = message["payload"].get("original_query", session_data.get("user_query")) # Fallback to initial query
            if "user_id" not in session_data or not session_data["user_id"]:
                 session_data["user_id"] = message["payload"].get("user_id", self.get_session_user_id(session_id))

            session_data["status"] = "processing_plan";
            session_data["current_step_index"] = 0;
            session_data["step_results"] = []
            self._execute_next_plan_step(session_id)
        elif message_type == "step_result": 
            step_payload = message["payload"]
            executed_tool_result_dict = step_payload.get("executed_tool_result", {"status": "error", "data": "Specialist Agent未提供工具结果字典"})
            original_task_payload_from_agent = step_payload.get("original_task_payload", {})

            session_data["step_results"].append({
                "agent_id": message["sender_id"],
                "executed_tool_result": executed_tool_result_dict, 
                "original_task_payload": original_task_payload_from_agent
            })
            
            tool_status = executed_tool_result_dict.get("status", "unknown_status")
            if tool_status in ["failure", "error"]: 
                failure_data = executed_tool_result_dict.get("data", "未知错误")
                self._handle_session_failure(session_id, f"步骤执行失败 (Agent: {message['sender_id']}, Status: {tool_status}): {failure_data}"); return

            session_data["current_step_index"] += 1
            if session_data["current_step_index"] < len(session_data["plan"]):
                self._execute_next_plan_step(session_id)
            else:
                print(f"✅ [编排器] 会话 '{session_id}' 的所有计划步骤已完成。请求最终答案综合。"); session_data["status"] = "pending_synthesis"
                synthesis_request_payload = {"original_query": session_data["user_query"], "user_id": session_data["user_id"], "step_results": session_data["step_results"]}
                self.add_message_to_queue(self.agents["FudanPlannerAgent"]._create_message(recipient_id="FudanPlannerAgent", message_type="request_synthesis", payload=synthesis_request_payload, session_id=session_id))
        elif message_type == "error_notification": 
            self._handle_session_failure(session_id, f"Agent '{message['sender_id']}' 报告错误: {message['payload'].get('error', '未知错误')}")
        else: print(f"⚠️ [编排器] 收到未处理的 Orchestrator 消息类型: '{message_type}'")

    def _execute_next_plan_step(self, session_id: str):
        session_data = self.sessions.get(session_id)
        if not (session_data and session_data["status"] == "processing_plan" and session_data.get("plan")):
            print(f"ℹ️ [编排器] 会话 '{session_id}' 状态不适合执行下一步 (当前状态: {session_data.get('status') if session_data else '不存在'})。"); return
        step_index = session_data["current_step_index"]
        if step_index < len(session_data["plan"]):
            step = session_data["plan"][step_index]; target_agent_id = step.get("agent_id"); task_payload_for_agent = step.get("task_payload")
            if not target_agent_id or not isinstance(task_payload_for_agent, dict):
                self._handle_session_failure(session_id, f"计划步骤 #{step_index + 1} 缺少 agent_id 或 task_payload 格式错误。"); return
            if target_agent_id not in self.agents:
                self._handle_session_failure(session_id, f"计划中的目标Agent '{target_agent_id}' 不存在。"); return
            action_item = task_payload_for_agent.get('tool_to_execute', task_payload_for_agent.get('task_type', '未知任务'))
            print(f"▶️ [编排器] 会话 '{session_id}', 步骤 #{step_index + 1}: 任务 '{action_item}' 分发给 Agent '{target_agent_id}'")
            self.add_message_to_queue(self.agents[target_agent_id]._create_message(recipient_id=target_agent_id, message_type="task_request", payload={"task_payload": task_payload_for_agent, "user_id": session_data["user_id"]}, session_id=session_id))
        else: print(f"ℹ️ [编排器] 会话 '{session_id}' 所有步骤已派发。等待综合。")

    def process_single_message_from_queue(self) -> bool:
        if not self.message_queue: return False
        message = self.message_queue.pop(0)
        recipient_id = message.get("recipient_id"); sender_id = message.get("sender_id"); session_id = message.get("session_id", "N/A_SESSION"); msg_type = message.get("message_type")
        if not recipient_id: print(f"⚠️ [消息队列] 错误: 消息缺少 'recipient_id'。"); return True
        if recipient_id == "Orchestrator": self._process_orchestrator_message(message)
        elif recipient_id in self.agents:
            try: self.agents[recipient_id].process_message(message)
            except NotImplementedError: print(f"❌ [消息队列] Agent '{recipient_id}' 未实现 process_message 方法！"); self._handle_session_failure(session_id, f"Agent '{recipient_id}' 内部逻辑未实现。")
            except Exception as e: print(f"❌ [消息队列] Agent '{recipient_id}' 处理消息时发生严重错误: {e}"); traceback.print_exc(); self._handle_session_failure(session_id, f"Agent '{recipient_id}' 内部处理错误: {e}")
        else: print(f"⚠️ [消息队列] 错误: 未知的消息接收者 '{recipient_id}'。消息被丢弃。")
        return True

    def run_session_until_completion(self, session_id: str, timeout_seconds: int = 60) -> str:
        start_time = time.time(); print(f"⏳ [会话执行] 开始执行会话 '{session_id}'，超时时间 {timeout_seconds} 秒。")
        if session_id not in self.session_completion_events: self.session_completion_events[session_id] = threading.Event()
        session_event = self.session_completion_events[session_id]; session_event.clear()
        self.process_single_message_from_queue()
        while not session_event.is_set():
            if time.time() - start_time > timeout_seconds: self._handle_session_failure(session_id, "会话处理超时。"); break
            if not self.process_single_message_from_queue(): time.sleep(0.05)
        if session_id in self.session_completion_events: del self.session_completion_events[session_id]
        session_data = self.sessions.get(session_id, {});
        final_output = session_data.get("final_answer", "抱歉，处理您的请求时似乎没有得到明确的结果。");
        status = session_data.get("status", "unknown")
        print(f"🏁 [会话执行] 会话 '{session_id}' 结束。状态: '{status}'。最终输出: {str(final_output)[:100]}...")
        return final_output

# --- 全局 Orchestrator 实例 ---
_orchestrator_lock = threading.Lock()
orchestrator_instance = None
def get_orchestrator():
    global orchestrator_instance
    if orchestrator_instance is None:
        with _orchestrator_lock:
            if orchestrator_instance is None:
                print("首次创建 Orchestrator 实例...")
                orchestrator_instance = Orchestrator()
    return orchestrator_instance

# --- (可选) 用于独立测试多Agent系统的 main 循环 ---
if __name__ == "__main__":
    print("--- 手动测试多Agent系统 (非Web模式) ---")
    knowledge_base.load_all_data()
    orc = get_orchestrator()
    user_proxy = orc.agents.get("FudanUserProxyAgent")
    if not user_proxy: print("严重错误: FudanUserProxyAgent 未初始化!"); exit()
    print("\n欢迎来到手动测试的多Agent系统。输入你的请求，或输入 'exit' 退出。")
    try:
        while True:
            user_input_text = input("\n🧑 你: ")
            if user_input_text.lower() == 'exit': print("正在退出..."); break
            if user_input_text.strip():
                test_session_id = user_proxy.initiate_task("manual_test_user", user_input_text)
                print(f"   (会话 '{test_session_id}' 已启动，等待系统处理...)")
                final_agent_reply = orc.run_session_until_completion(test_session_id, timeout_seconds=180)
                print(f"🤖 旦旦学姐: {final_agent_reply}")
            else: continue
    except KeyboardInterrupt: print("\n用户中断。正在退出...")
    finally: print("多Agent系统测试已关闭。")

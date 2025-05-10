# multi_agent_system.py
import datetime
import json
# import re # 暂时不用
import uuid
import time
import traceback # 用于打印详细错误

# 导入我们项目中的模块
import llm_interface    # 与 LLM API 交互
import knowledge_base   # 知识库操作 (将被 FudanKnowledgeAgent 使用)

# --- Agent 基类 (保持不变) ---
class BaseAgent:
    def __init__(self, agent_id: str, orchestrator, llm_model_config: dict = None):
        self.agent_id = agent_id
        self.orchestrator = orchestrator
        self.llm_model_config = llm_model_config if llm_model_config else llm_interface.LLM_CONFIG
        print(f"🚀 Agent '{self.agent_id}' 已初始化。")

    def _create_message(self, recipient_id: str, message_type: str, payload: dict, session_id: str, sender_id: str = None) -> dict:
        return {
            "message_id": f"msg_{uuid.uuid4().hex[:8]}",
            "session_id": session_id,
            "sender_id": sender_id or self.agent_id,
            "recipient_id": recipient_id,
            "message_type": message_type,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "payload": payload
        }

    def process_message(self, message: dict):
        raise NotImplementedError(f"Agent '{self.agent_id}' 必须实现 process_message 方法。")

    def send_message(self, message: dict):
        print(f"📬 [消息发送] '{message['sender_id']}' -> '{message['recipient_id']}' (类型: {message['message_type']}, 会话: {message['session_id']})")
        self.orchestrator.add_message_to_queue(message)

# --- FudanUserProxyAgent (保持不变) ---
class FudanUserProxyAgent(BaseAgent):
    """旦旦学姐的用户接口 Agent，处理来自外部的输入，并将最终答案传递回去。"""
    def __init__(self, agent_id: str, orchestrator, llm_model_config: dict = None):
        super().__init__(agent_id, orchestrator, llm_model_config)

    def initiate_task(self, user_id: str, user_query: str) -> str:
        session_id = f"session_{user_id.replace('@', '_')}_{uuid.uuid4().hex[:6]}"
        self.orchestrator.register_session(session_id, user_id, user_query)
        print(f"🚀 [用户接口] '{self.agent_id}' 为用户 '{user_id}' 发起新任务 (会话: {session_id})。查询: '{user_query}'")
        initial_message_to_planner = self._create_message(
            recipient_id="FudanPlannerAgent",
            message_type="user_query_for_planning",
            payload={"user_query": user_query, "user_id": user_id},
            session_id=session_id
        )
        self.send_message(initial_message_to_planner)
        return session_id

    def process_message(self, message: dict):
        session_id = message["session_id"]
        user_id = self.orchestrator.get_session_user_id(session_id)

        if message["message_type"] == "final_answer_to_user":
            final_answer = message["payload"].get("answer", "学姐好像没什么要说的了呢。")
            print(f"✅ [用户接口] '{self.agent_id}' (用户: {user_id}, 会话: {session_id}) 收到最终答案:\n   学姐回复: {final_answer}")
            self.orchestrator.mark_session_completed(session_id, final_answer)
        
        elif message["message_type"] == "clarification_request_to_user":
            clarification_question = message["payload"].get("question", "学姐有点没明白，能再说具体点吗？")
            print(f"❓ [用户接口] '{self.agent_id}' (用户: {user_id}, 会话: {session_id}) 收到澄清请求:\n   学姐提问: {clarification_question}")
            self.orchestrator.mark_session_pending_user_input(session_id, clarification_question)
        else:
            print(f"⚠️ [用户接口] '{self.agent_id}' 收到未处理的消息类型: '{message['message_type']}' (来自: '{message['sender_id']}')")

# --- FudanPlannerAgent (核心修改) ---
class FudanPlannerAgent(BaseAgent):
    """旦旦学姐的大脑 - 规划与综合 Agent。它决定任务如何执行，并综合最终回复。"""
    def __init__(self, agent_id: str, orchestrator, llm_model_config: dict = None):
        super().__init__(agent_id, orchestrator, llm_model_config)
        self.specialist_agents_capabilities_description = "" 

    def _plan_task_or_respond_directly(self, user_query: str, user_id: str, session_id: str, chat_history: str):
        """使用 LLM 决定是直接回复、请求澄清，还是生成一个包含多步骤的计划来调用 SpecialistAgent。"""
        
        if not self.specialist_agents_capabilities_description:
            self.specialist_agents_capabilities_description = self.orchestrator.get_specialist_agent_capabilities_description()

        llm_decision = llm_interface.get_llm_decision(
            user_input=user_query,
            chat_history=chat_history,
            tools_description=self.specialist_agents_capabilities_description,
            llm_model_id=self.llm_model_config["planner"]
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
        
        elif action_type == "EXECUTE_PLAN": # 修改：处理 EXECUTE_PLAN
            plan = llm_decision.get("plan") # 获取计划列表

            if isinstance(plan, list) and plan: # 确保 plan 是一个非空列表
                # 验证计划中的每个步骤是否基本完整 (至少有 agent_id 和 task_payload)
                is_valid_plan = True
                for i, step in enumerate(plan):
                    if not (isinstance(step, dict) and "agent_id" in step and "task_payload" in step):
                        print(f"❌ [规划器] 计划中的步骤 #{i} 格式无效: {step}")
                        is_valid_plan = False
                        break
                
                if is_valid_plan:
                    print(f"📑 [规划器] 生成计划包含 {len(plan)} 个步骤。提交给 Orchestrator...")
                    plan_submission_msg = self._create_message(
                        recipient_id="Orchestrator", 
                        message_type="plan_submission", 
                        payload={"plan": plan, "original_query": user_query, "user_id": user_id}, 
                        session_id=session_id
                    )
                    self.send_message(plan_submission_msg)
                else: # 计划结构无效
                    print(f"❌ [规划器] LLM 生成的计划结构无效。决策: {llm_decision}")
                    err_response = llm_interface.get_final_response(user_query, "学姐在规划任务的时候好像出了点小问题，这个计划不太对劲哦。", llm_model_id=self.llm_model_config["response_generator"])
                    err_msg = self._create_message("FudanUserProxyAgent", "final_answer_to_user", {"answer": err_response}, session_id)
                    self.send_message(err_msg)

            else: # LLM 说要执行计划，但没提供有效的计划列表
                print(f"❌ [规划器] LLM决策执行计划，但未提供有效的计划列表: {llm_decision}")
                err_response = llm_interface.get_final_response(user_query, "学姐想帮你规划一下，但是好像没想好具体的步骤呢。", llm_model_id=self.llm_model_config["response_generator"])
                err_msg = self._create_message("FudanUserProxyAgent", "final_answer_to_user", {"answer": err_response}, session_id)
                self.send_message(err_msg)
        else:
            print(f"❌ [规划器] LLM返回了未知的决策类型: '{action_type}' 或决策结构错误。决策: {llm_decision}")
            err_response = llm_interface.get_final_response(user_query, "学姐的思路有点混乱，没法处理你的请求啦。", llm_model_id=self.llm_model_config["response_generator"])
            err_msg = self._create_message("FudanUserProxyAgent", "final_answer_to_user", {"answer": err_response}, session_id)
            self.send_message(err_msg)

    def _synthesize_final_answer(self, original_query: str, user_id: str, step_results: list, session_id: str):
        # ... (此方法保持不变，它已经能处理多个步骤的结果) ...
        print(f"📝 [规划器] '{self.agent_id}' 开始为用户 '{user_id}' (会话: {session_id}) 综合最终答案...")
        context_for_synthesis = f"用户的原始问题是：“{original_query}”\n\n"
        if step_results:
            context_for_synthesis += "为了回答这个问题，我和我的伙伴们进行了以下尝试和思考：\n"
            for i, res_info in enumerate(step_results):
                context_for_synthesis += f"- 步骤 {i+1} (由 '{res_info.get('agent_id', '未知Agent')}' 处理，状态: {res_info.get('status', '未知状态')}):\n"
                context_for_synthesis += f"  结果摘要: {str(res_info.get('result', '无结果'))[:250]}...\n"
        else:
            context_for_synthesis += "但似乎没有执行任何具体的步骤，或者步骤没有结果。\n"
        context_for_synthesis += "\n现在，请你作为“旦旦学姐”，基于以上所有信息，给用户一个友好、完整且有帮助的最终回复。"
        final_answer_text = llm_interface.get_final_response(
            user_input=original_query,
            context_info=context_for_synthesis,
            llm_model_id=self.llm_model_config["response_generator"]
        )
        if not final_answer_text: final_answer_text = "哎呀，学姐处理完所有信息之后，发现不知道怎么回复你了...要不我们聊点别的？😅"
        answer_message = self._create_message(
            recipient_id="FudanUserProxyAgent", message_type="final_answer_to_user",
            payload={"answer": final_answer_text}, session_id=session_id
        )
        self.send_message(answer_message)


    def process_message(self, message: dict):
        # ... (此方法保持不变) ...
        session_id = message["session_id"]
        user_id = message["payload"].get("user_id", self.orchestrator.get_session_user_id(session_id))
        if message["message_type"] == "user_query_for_planning":
            user_query = message["payload"]["user_query"]
            chat_history = self.orchestrator.get_session_chat_history_str(user_id)
            print(f"📝 [规划器] '{self.agent_id}' 收到用户 '{user_id}' 的查询 '{user_query}' (会话: {session_id})，开始规划...")
            self._plan_task_or_respond_directly(user_query, user_id, session_id, chat_history)
        elif message["message_type"] == "request_synthesis":
            original_query = message["payload"]["original_query"]
            step_results = message["payload"]["step_results"]
            self._synthesize_final_answer(original_query, user_id, step_results, session_id)
        else:
            print(f"⚠️ [规划器] '{self.agent_id}' 收到未处理的消息类型: '{message['message_type']}' (来自: '{message['sender_id']}')")


# --- FudanKnowledgeAgent (保持不变) ---
class FudanKnowledgeAgent(BaseAgent):
    # ... (代码保持不变) ...
    def __init__(self, agent_id: str, orchestrator, llm_model_config: dict = None):
        super().__init__(agent_id, orchestrator, llm_model_config)

    def process_message(self, message: dict):
        session_id = message["session_id"]
        task_payload = message["payload"].get("task_payload", {}) 
        print(f"🛠️ [知识Agent] '{self.agent_id}' 收到任务 (会话: {session_id}): {task_payload}")
        result_data = f"知识Agent未能处理任务: {task_payload.get('task_type', '未知任务类型')}"
        status = "failure"
        task_type = task_payload.get("task_type")
        category = task_payload.get("knowledge_category")
        try:
            if task_type == "query_static":
                filters = task_payload.get("query_filters", {})
                if not category: result_data = "查询静态知识需要指定 'knowledge_category'。"
                elif category == "slang":
                    term = filters.get("term")
                    if not term: result_data = "查询黑话需要提供 'term'。"
                    else: result_data = knowledge_base.get_slang_definition(term)
                    status = "success" if "抱歉，我还不知道" not in result_data else "partial_success_not_found"
                elif category == "food":
                    location = filters.get("location")
                    if not location: result_data = "查询美食需要提供 'location'。"
                    else: result_data = knowledge_base.find_food(location)
                    status = "success" if "唉呀，暂时没有找到" not in result_data else "partial_success_not_found"
                else: result_data = f"静态知识库暂不支持查询 '{category}' 类别。"
            elif task_type == "query_dynamic":
                query = task_payload.get("user_query_for_learned_info")
                if not category: result_data = "查询动态知识需要指定 'knowledge_category'。"
                elif not query: result_data = "查询动态知识需要提供 'user_query_for_learned_info'。"
                else:
                    result_data = knowledge_base.search_learned_info(category, query)
                    status = "success" if "暂时没有找到和你问题直接相关的信息呢" not in result_data else "partial_success_not_found"
            elif task_type == "learn_info":
                topic = task_payload.get("topic")
                info = task_payload.get("information")
                q_taught = task_payload.get("question_taught")
                a_taught = task_payload.get("answer_taught")
                success_learn = False
                if not category: result_data = "学习新知识需要指定 'knowledge_category'。"
                elif q_taught and a_taught:
                    success_learn = knowledge_base.add_learned_qa_pair(category, q_taught, a_taught)
                    result_data = f"问答对已学习到 '{category}' 类别。" if success_learn else "问答对学习失败。"
                elif topic and info:
                    success_learn = knowledge_base.add_learned_info(category, topic, info)
                    result_data = f"主题信息已学习到 '{category}' 类别。" if success_learn else "主题信息学习失败。"
                else: result_data = "学习新知识需要提供 topic/information 或 question_taught/answer_taught。"
                status = "success" if success_learn else "failure"
            else: result_data = f"知识Agent不理解的任务类型: '{task_type}'"
        except Exception as e:
            print(f"❌ [知识Agent] '{self.agent_id}' 执行任务时出错: {e}")
            traceback.print_exc()
            result_data = f"知识Agent在处理您的请求时发生内部错误: {str(e)}"; status = "failure"
        print(f"  [知识Agent] 结果 ({status}): {str(result_data)[:100]}...")
        result_message_payload = {"status": status, "data": result_data, "original_task_payload": task_payload}
        result_message = self._create_message(
            recipient_id="Orchestrator", message_type="step_result",
            payload=result_message_payload, session_id=session_id
        )
        self.send_message(result_message)

# --- Orchestrator (核心逻辑不变，它已经能处理多步计划) ---
class Orchestrator:
    # ... (大部分代码保持不变，特别是 _process_orchestrator_message 和 _execute_next_plan_step) ...
    def __init__(self):
        self.agents = {} 
        self.message_queue = [] 
        self.sessions = {} 
        self._initialize_agents()
        self.session_completion_events = {} 
        self.app_context = None 

    def set_app_context(self, app_instance):
        self.app_context = app_instance

    def _initialize_agents(self):
        print("系统初始化: 正在创建 Agents...")
        self.agents["FudanUserProxyAgent"] = FudanUserProxyAgent("FudanUserProxyAgent", self)
        self.agents["FudanPlannerAgent"] = FudanPlannerAgent("FudanPlannerAgent", self)
        self.agents["FudanKnowledgeAgent"] = FudanKnowledgeAgent("FudanKnowledgeAgent", self)
        print(f"系统初始化: {len(self.agents)} 个 Agent 已创建: {list(self.agents.keys())}")

    def get_specialist_agent_capabilities_description(self) -> str:
        # 这个描述现在对 Planner LLM 生成多步计划至关重要
        descriptions = [
            f"- Agent ID: `FudanKnowledgeAgent`\n  能力描述: 负责处理与复旦大学相关的知识问答和学习新知识。它接收一个 `task_payload` 对象，其中必须包含 `task_type` (可选值: 'query_static', 'query_dynamic', 'learn_info') 和 `knowledge_category` (可选值: {knowledge_base.SUPPORTED_DYNAMIC_CATEGORIES})。根据 `task_type`，还需要提供其他参数：\n    - 对于 'query_static': 需要 `query_filters` 对象 (例如 `{{\"term\": \"黑话\"}}` 或 `{{\"location\": \"地点\"}}`)。\n    - 对于 'query_dynamic': 需要 `user_query_for_learned_info` (字符串)。\n    - 对于 'learn_info': 需要 `topic` 和 `information`，或者 `question_taught` 和 `answer_taught`。",
            # (未来可以添加更多 Specialist Agent 的描述)
            # f"- Agent ID: `CampusEventAgent`\n  能力描述: 专门负责查询校园活动。任务负载中应包含 `date_range` (可选) 和 `event_type` (可选)。"
        ]
        return "你可以委托以下专长Agent来完成特定类型的任务（如果一个用户请求需要多个专长Agent协作，请在计划中列出所有步骤）：\n\n" + "\n".join(descriptions)

    def add_message_to_queue(self, message: dict):
        self.message_queue.append(message)
        print(f"📬 [消息队列] 消息已入队 (发往: {message['recipient_id']}, 类型: {message['message_type']}, 会话: {message['session_id']})。当前队列长度: {len(self.message_queue)}")

    def register_session(self, session_id: str, user_id: str, user_query: str):
        self.sessions[session_id] = {
            "user_id": user_id, "user_query": user_query, "status": "pending_plan",
            "plan": None, "current_step_index": 0, "step_results": [], 
            "final_answer": None, "clarification_question": None, 
            "start_time": time.time()
        }
        self.session_completion_events[session_id] = threading.Event()
        print(f"🚀 [会话管理] 会话 '{session_id}' (用户: '{user_id}') 已注册。查询: '{user_query}'")

    def get_session_user_id(self, session_id: str) -> str | None:
        return self.sessions.get(session_id, {}).get("user_id")

    def get_session_chat_history_str(self, user_id: str) -> str:
        if self.app_context and hasattr(self.app_context, 'get_user_chat_history_for_agent'):
            return self.app_context.get_user_chat_history_for_agent(user_id)
        return "无之前的对话内容（或历史获取功能未连接）。"

    def mark_session_completed(self, session_id: str, final_answer: str):
        if session_id in self.sessions:
            self.sessions[session_id]["status"] = "completed"
            self.sessions[session_id]["final_answer"] = final_answer
            print(f"✅ [会话管理] 会话 '{session_id}' 已标记为完成。")
            if session_id in self.session_completion_events: self.session_completion_events[session_id].set()
        else: print(f"⚠️ [会话管理] 尝试标记不存在的会话 '{session_id}' 为完成。")
    
    def mark_session_pending_user_input(self, session_id: str, clarification_question: str):
        if session_id in self.sessions:
            self.sessions[session_id]["status"] = "pending_user_input"
            self.sessions[session_id]["clarification_question"] = clarification_question
            self.sessions[session_id]["final_answer"] = clarification_question
            print(f"❓ [会话管理] 会话 '{session_id}' 等待用户澄清。问题: {clarification_question}")
            if session_id in self.session_completion_events: self.session_completion_events[session_id].set()
        else: print(f"⚠️ [会话管理] 尝试标记不存在的会话 '{session_id}' 为等待用户输入。")

    def _handle_session_failure(self, session_id: str, error_reason: str):
        print(f"❌ [会话管理] 会话 '{session_id}' 失败: {error_reason}")
        if session_id in self.sessions:
            self.sessions[session_id]["status"] = "failed"
            user_friendly_error = f"哎呀，学姐在处理你的请求时好像遇到了一点小麻烦 ({error_reason[:50]}...)，要不我们换个话题或者稍后再试？😥"
            self.sessions[session_id]["final_answer"] = user_friendly_error
            if session_id in self.session_completion_events: self.session_completion_events[session_id].set()
        else: print(f"⚠️ [会话管理] 尝试处理不存在的会话 '{session_id}' 的失败。")

    def _process_orchestrator_message(self, message: dict):
        session_id = message["session_id"]
        session_data = self.sessions.get(session_id)
        if not session_data: print(f"⚠️ [编排器] 收到未知会话 '{session_id}' 的消息。忽略。"); return
        message_type = message["message_type"]
        print(f"⚙️ [编排器] 处理会话 '{session_id}' 的消息，类型: '{message_type}' (来自: '{message['sender_id']}')")

        if message_type == "plan_submission":
            plan = message["payload"].get("plan")
            if not isinstance(plan, list) or not all(isinstance(step, dict) and "agent_id" in step and "task_payload" in step for step in plan):
                self._handle_session_failure(session_id, "Planner提交的计划格式无效。"); return
            if not plan: print(f"ℹ️ [编排器] 会话 '{session_id}' 收到空计划，可能 Planner 已直接处理。"); return
            session_data["plan"] = plan
            session_data["original_query"] = message["payload"].get("original_query")
            session_data["user_id"] = message["payload"].get("user_id")
            session_data["status"] = "processing_plan"
            session_data["current_step_index"] = 0
            session_data["step_results"] = []
            self._execute_next_plan_step(session_id)
        
        elif message_type == "step_result":
            step_payload = message["payload"]
            session_data["step_results"].append({
                "agent_id": message["sender_id"], "result": step_payload.get("data", "无结果数据"),
                "status": step_payload.get("status", "unknown_status"),
                "original_task_payload": step_payload.get("original_task_payload", {})
            })
            if step_payload.get("status") == "failure":
                self._handle_session_failure(session_id, f"步骤执行失败 (Agent: {message['sender_id']}): {step_payload.get('data', '未知错误')}"); return
            session_data["current_step_index"] += 1
            if session_data["current_step_index"] < len(session_data["plan"]):
                self._execute_next_plan_step(session_id)
            else:
                print(f"✅ [编排器] 会话 '{session_id}' 的所有计划步骤已完成。请求最终答案综合。")
                session_data["status"] = "pending_synthesis"
                synthesis_request_payload = {
                    "original_query": session_data["user_query"], "user_id": session_data["user_id"],
                    "step_results": session_data["step_results"]
                }
                synthesis_request = self.agents["FudanPlannerAgent"]._create_message(
                    recipient_id="FudanPlannerAgent", message_type="request_synthesis",
                    payload=synthesis_request_payload, session_id=session_id
                )
                self.add_message_to_queue(synthesis_request)
        elif message["message_type"] == "error_notification":
            self._handle_session_failure(session_id, f"Agent '{message['sender_id']}' 报告错误: {message['payload'].get('error', '未知错误')}")
        else: print(f"⚠️ [编排器] 收到未处理的 Orchestrator 消息类型: '{message_type}'")

    def _execute_next_plan_step(self, session_id: str):
        session_data = self.sessions.get(session_id)
        if not (session_data and session_data["status"] == "processing_plan" and session_data.get("plan")):
            print(f"ℹ️ [编排器] 会话 '{session_id}' 状态不适合执行下一步 (当前状态: {session_data.get('status') if session_data else '不存在'})。"); return
        step_index = session_data["current_step_index"]
        if step_index < len(session_data["plan"]):
            step = session_data["plan"][step_index]
            target_agent_id = step.get("agent_id")
            task_payload_for_specialist = step.get("task_payload")
            if not target_agent_id or not isinstance(task_payload_for_specialist, dict):
                self._handle_session_failure(session_id, f"计划步骤 #{step_index + 1} 缺少 agent_id 或 task_payload 格式错误。"); return
            if target_agent_id not in self.agents:
                self._handle_session_failure(session_id, f"计划中的目标Agent '{target_agent_id}' 不存在。"); return
            print(f"▶️ [编排器] 会话 '{session_id}', 步骤 #{step_index + 1}: 任务分发给 Agent '{target_agent_id}'")
            task_message = self.agents[target_agent_id]._create_message(
                recipient_id=target_agent_id, message_type="task_request",
                payload={"task_payload": task_payload_for_specialist, "user_id": session_data["user_id"]},
                session_id=session_id
            )
            self.add_message_to_queue(task_message)
        else: print(f"ℹ️ [编排器] 会话 '{session_id}' 所有步骤已派发。等待综合。")

    def process_single_message_from_queue(self) -> bool:
        if not self.message_queue: return False
        message = self.message_queue.pop(0)
        recipient_id = message.get("recipient_id"); sender_id = message.get("sender_id")
        session_id = message.get("session_id", "N/A_SESSION"); msg_type = message.get("message_type")
        print(f"🚚 [消息队列] 处理消息: '{sender_id}' -> '{recipient_id}' (会话: {session_id}, 类型: {msg_type})")
        if not recipient_id: print(f"⚠️ [消息队列] 错误: 消息缺少 'recipient_id'。"); return True
        if recipient_id == "Orchestrator": self._process_orchestrator_message(message)
        elif recipient_id in self.agents:
            try: self.agents[recipient_id].process_message(message)
            except NotImplementedError: print(f"❌ [消息队列] Agent '{recipient_id}' 未实现 process_message 方法！"); self._handle_session_failure(session_id, f"Agent '{recipient_id}' 内部逻辑未实现。")
            except Exception as e: print(f"❌ [消息队列] Agent '{recipient_id}' 处理消息时发生严重错误: {e}"); traceback.print_exc(); self._handle_session_failure(session_id, f"Agent '{recipient_id}' 内部处理错误: {e}")
        else: print(f"⚠️ [消息队列] 错误: 未知的消息接收者 '{recipient_id}'。消息被丢弃。")
        return True

    def run_session_until_completion(self, session_id: str, timeout_seconds: int = 60) -> str:
        start_time = time.time()
        print(f"⏳ [会话执行] 开始执行会话 '{session_id}'，超时时间 {timeout_seconds} 秒。")
        if session_id not in self.session_completion_events: self.session_completion_events[session_id] = threading.Event()
        session_event = self.session_completion_events[session_id]; session_event.clear()
        self.process_single_message_from_queue() # 主动处理一次
        while not session_event.is_set():
            if time.time() - start_time > timeout_seconds: self._handle_session_failure(session_id, "会话处理超时。"); break 
            if not self.process_single_message_from_queue(): time.sleep(0.05)
        if session_id in self.session_completion_events: del self.session_completion_events[session_id]
        session_data = self.sessions.get(session_id, {})
        final_output = session_data.get("final_answer", "抱歉，处理您的请求时似乎没有得到明确的结果。")
        status = session_data.get("status", "unknown")
        print(f"🏁 [会话执行] 会话 '{session_id}' 结束。状态: '{status}'。最终输出: {str(final_output)[:100]}...")
        return final_output

# --- 全局 Orchestrator 实例 (保持不变) ---
import threading
_orchestrator_lock = threading.Lock()
orchestrator_instance = None
def get_orchestrator():
    global orchestrator_instance
    if orchestrator_instance is None:
        with _orchestrator_lock:
            if orchestrator_instance is None:
                orchestrator_instance = Orchestrator()
    return orchestrator_instance

# --- (可选) 用于独立测试多Agent系统的 main 循环 (保持不变) ---
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
                final_agent_reply = orc.run_session_until_completion(test_session_id, timeout_seconds=120)
                print(f"🤖 旦旦学姐: {final_agent_reply}")
            else: continue
    except KeyboardInterrupt: print("\n用户中断。正在退出...")
    finally: print("多Agent系统测试已关闭。")



# tools.py
import knowledge_base
import json

TOOL_REGISTRY = []

def register_tool(name: str, description: str, parameters_schema: dict = None):
    # ... (装饰器代码不变) ...
    if parameters_schema is None:
        parameters_schema = {"type": "object", "properties": {}}

    def decorator(execute_function):
        tool_info = {
            "name": name,
            "description": description,
            "parameters": parameters_schema,
            "execute": execute_function
        }
        TOOL_REGISTRY.append(tool_info)
        print(f"[工具注册] 工具 '{name}' 已成功注册。")
        return execute_function
    return decorator

# --- 静态知识库查询工具 (基本不变) ---
@register_tool(
    name="StaticKnowledgeBaseQueryTool",
    description="当用户想查询复旦大学校园内的固定信息时使用此工具，例如查询黑话含义、美食推荐、宿舍规定、校车信息等预定义的静态知识。",
    parameters_schema={
        "type": "object",
        "properties": {
            "knowledge_category": {
                "type": "string",
                "description": "要查询的知识类别。例如：'slang' (黑话), 'food' (美食)。未来可支持 'housing_rules', 'transport_info' 等。"
            },
            "query_filters": {
                "type": "object",
                "description": "根据知识类别提供的具体查询条件。例如，查黑话时是 {'term': '黑话词'}；查美食时是 {'location': '地点'}。",
                "properties": {
                    "term": {"type": "string", "description": "当 knowledge_category 为 'slang' 时，用户想要查询的具体黑话词语。"},
                    "location": {"type": "string", "description": "当 knowledge_category 为 'food' 时，用户指定查询美食的地点。"}
                }
            }
        },
        "required": ["knowledge_category"]
    }
)
def execute_static_knowledge_query(knowledge_category: str, query_filters: dict = None) -> str:
    # ... (此函数逻辑不变，它只操作静态数据) ...
    if query_filters is None: query_filters = {}
    print(f"[工具执行] StaticKnowledgeBaseQueryTool: category='{knowledge_category}', filters='{query_filters}'")
    if knowledge_category == "slang":
        term = query_filters.get("term")
        if not term: return "你需要告诉我你想查哪个黑话词哦，学姐才能帮你查呀 🤔。"
        return knowledge_base.get_slang_definition(term)
    elif knowledge_category == "food":
        location = query_filters.get("location")
        if not location: return "你想查哪个校区或者地点附近的美食呀？比如“邯郸食堂”或者“五角场”？"
        return knowledge_base.find_food(location=location)
    return f"学姐暂时还不支持查询“{knowledge_category}”这类静态信息哦。😊"


# --- 动态知识学习工具 (增加 knowledge_category 参数) ---
@register_tool(
    name="LearnNewInfoTool",
    description="当用户明确表示要“教”你新信息、新知识点、某个问题的答案，或者让你“记住”某些事情时使用此工具。你需要判断这个新知识属于哪个类别，并将信息和类别一起存储起来供以后查询。",
    parameters_schema={
        "type": "object",
        "properties": {
            "knowledge_category": {
                "type": "string",
                "description": f"用户教授的新知识最适合归入哪个类别。可选类别：{knowledge_base.SUPPORTED_DYNAMIC_CATEGORIES}。如果无法明确分类，可以使用 'general_notes' (你需要将 general_notes 加入 SUPPORTED_DYNAMIC_CATEGORIES)。",
            },
            "topic": {"type": "string", "description": "用户教授信息的主题或类别 (可选，当信息是陈述性时)。"},
            "information": {"type": "string", "description": "用户教授的具体信息内容 (当 topic 存在时使用)。"},
            "question_taught": {"type": "string", "description": "用户教的一个具体问题 (当教授问答对时使用)。"},
            "answer_taught": {"type": "string", "description": "针对用户教的问题，对应的答案 (当教授问答对时使用)。"}
        },
        "required": ["knowledge_category"] # 类别是必须的，内容是 topic/info 或 question/answer
    }
)
def execute_learn_new_info(knowledge_category: str, topic: str = None, information: str = None, question_taught: str = None, answer_taught: str = None) -> str:
    """执行学习新知识的逻辑，并将信息存入指定类别的动态知识库。"""
    print(f"[工具执行] LearnNewInfoTool: category='{knowledge_category}', topic='{topic}', info='{information}', q='{question_taught}', a='{answer_taught}'")
    
    if not knowledge_category: # LLM 必须提供类别
        return "学姐需要知道这个知识点属于哪个类别才能更好地记住哦，比如是关于“美食”的还是“校园生活”的？"
    if knowledge_category not in knowledge_base.SUPPORTED_DYNAMIC_CATEGORIES:
        # 如果 LLM 给了一个不支持的类别，可以尝试放入一个默认类别或提示错误
        # 为了简单，这里我们先假设 LLM 会给出支持的类别，或者我们在 prompt 里引导它
        # 也可以在调用前由 app.py 校验，或在这里将其归入一个“杂项”类别
        print(f"警告：LearnNewInfoTool 收到不支持的类别 '{knowledge_category}'，尝试存入 'general_fudan_info'")
        knowledge_category = "general_fudan_info" # Fallback category
        if "general_fudan_info" not in knowledge_base.SUPPORTED_DYNAMIC_CATEGORIES: # 确保 fallback 存在
             knowledge_base.SUPPORTED_DYNAMIC_CATEGORIES.append("general_fudan_info")


    success = False
    if question_taught and answer_taught:
        success = knowledge_base.add_learned_qa_pair(knowledge_category, question_taught, answer_taught)
        if success:
            return f"好嘞，关于“{knowledge_category}”类别的问题“{question_taught}”，学姐记住答案是“{answer_taught}”啦！😉 谢谢你！"
    elif topic and information:
        success = knowledge_base.add_learned_info(knowledge_category, topic, information)
        if success:
            return f"嗯嗯，关于“{knowledge_category}”类别的主题“{topic}”，信息：“{information}”，学姐记下了！👍"
    
    if success:
        return "学姐已经把新知识点记在小本本上啦！" # 通用成功回复
    else:
        return "你想教给学姐什么新知识呢？需要告诉我知识的类别、主题/信息，或者具体的问题和答案哦。😊"


# --- 动态知识查询工具 (增加 knowledge_category 参数) ---
@register_tool(
    name="QueryDynamicKnowledgeTool",
    description="当用户的问题可能涉及到之前TA明确教给你的、非预设的个人化信息或特定类别的知识时使用此工具。你需要判断用户想查询哪个类别的已学知识。",
    parameters_schema={
        "type": "object",
        "properties": {
            "knowledge_category": {
                "type": "string",
                "description": f"用户想查询的已学知识属于哪个类别。可选类别：{knowledge_base.SUPPORTED_DYNAMIC_CATEGORIES}。",
            },
            "user_query_for_learned_info": {
                "type": "string",
                "description": "用户提出的、希望从该类别的已学习动态知识中查找答案的具体问题或关键词。"
            }
        },
        "required": ["knowledge_category", "user_query_for_learned_info"]
    }
)
def execute_query_dynamic_knowledge(knowledge_category: str, user_query_for_learned_info: str) -> str:
    """执行查询指定类别的用户教授的动态知识。"""
    print(f"[工具执行] QueryDynamicKnowledgeTool: category='{knowledge_category}', query='{user_query_for_learned_info}'")

    if not knowledge_category:
        return "你想查哪个类别的学习笔记呀？"
    if knowledge_category not in knowledge_base.SUPPORTED_DYNAMIC_CATEGORIES:
        return f"学姐我还不知道怎么查找“{knowledge_category}”类别的学习笔记呢。😅"
        
    if not user_query_for_learned_info:
        return f"你想问学姐在“{knowledge_category}”类别里学到的什么事情呀？"
    
    learned_answer = knowledge_base.search_learned_info(knowledge_category, user_query_for_learned_info)
    
    # search_learned_info 现在会返回一个包含类别的提示，所以这里可以直接返回
    return learned_answer


# --- 工具管理函数 (不变) ---
def get_tool_by_name(name: str):
    # ... (代码不变) ...
    for tool in TOOL_REGISTRY:
        if tool["name"] == name:
            return tool
    return None

def get_tools_description_for_llm():
    # ... (代码不变) ...
    descriptions = []
    if not TOOL_REGISTRY: return "当前没有可用的外部工具。"
    for tool in TOOL_REGISTRY:
        desc = f"工具名称: `{tool['name']}`\n"
        desc += f"  描述: {tool['description']}\n"
        if tool.get("parameters") and tool["parameters"].get("properties"):
            params_desc_list = []
            for param_name, param_info in tool["parameters"]["properties"].items():
                param_type = param_info.get('type', '未知类型')
                param_description = param_info.get('description', '无描述')
                is_required = " (必须)" if param_name in tool["parameters"].get("required", []) else ""
                params_desc_list.append(f"{param_name}{is_required}: {param_description} (类型: {param_type})")
            if params_desc_list: desc += f"  参数: \n    - " + "\n    - ".join(params_desc_list) + "\n"
            else: desc += "  参数: 无\n"
        else: desc += "  参数: 无\n"
        descriptions.append(desc)
    return "你可以使用以下工具来帮助回答用户的问题：\n\n" + "\n".join(descriptions)

print(f"工具模块加载完毕，已注册 {len(TOOL_REGISTRY)} 个工具。")

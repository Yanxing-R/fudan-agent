# agent_tools.py
import datetime
import random
import json
import knowledge_base # 导入更新后的知识库模块

# --- 工具注册表 ---
TOOL_REGISTRY = {}

# --- Tool 基类 (保持不变) ---
class Tool:
    def __init__(self, name: str, description: str):
        if not name or not description:
            raise ValueError("工具必须提供名称和描述。")
        self.name = name
        self.description = description

    def execute(self, **kwargs) -> dict: # MODIFICATION: Return type changed to dict
        raise NotImplementedError(f"工具 '{self.name}' 未实现 execute 方法。")

    def get_parameters_schema(self) -> dict:
        return {"type": "object", "properties": {}, "required": []}

    def get_info_for_llm(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.get_parameters_schema()
        }

# --- 工具注册装饰器 (保持不变) ---
def tool(cls):
    if not issubclass(cls, Tool):
        raise TypeError("被 @tool 装饰的类必须是 Tool 的子类。")
    try:
        tool_instance = cls()
        if tool_instance.name in TOOL_REGISTRY:
            print(f"警告：工具名称 '{tool_instance.name}' 已存在，将被覆盖。")
        TOOL_REGISTRY[tool_instance.name] = tool_instance
        print(f"[工具注册] 工具 '{tool_instance.name}' (类: {cls.__name__}) 已成功注册。")
    except Exception as e:
        print(f"错误：注册工具类 {cls.__name__} 失败：{e}。")
    return cls

# --- 通用工具 (Return type changed to dict) ---

@tool
class GetCurrentTimeTool(Tool):
    def __init__(self):
        super().__init__(name="get_current_time", description="获取当前的完整日期、时间和星期几。")
    def execute(self, **kwargs) -> dict:
        print(f">>> [工具执行] {self.name}")
        now = datetime.datetime.now()
        days_map = {"Monday": "星期一", "Tuesday": "星期二", "Wednesday": "星期三", "Thursday": "星期四", "Friday": "星期五", "Saturday": "星期六", "Sunday": "星期日"}
        day_of_week_zh = days_map.get(now.strftime("%A"), now.strftime("%A"))
        time_str = f"现在是北京时间 {now.strftime('%Y年%m月%d日 %H:%M:%S')}，{day_of_week_zh}。"
        return {"status": "success", "data": time_str}

@tool
class CalculatorTool(Tool):
    def __init__(self):
        super().__init__(name="calculator", description="执行简单的算术运算，包括加法、减法、乘法和除法。")
    def get_parameters_schema(self) -> dict:
        return {"type": "object", "properties": {"operation": {"type": "string", "description": "运算类型 ('add', '+', 'subtract', '-', 'multiply', '*', 'divide', '/')。"}, "operand1": {"type": "number", "description": "第一个操作数。"}, "operand2": {"type": "number", "description": "第二个操作数。"}}, "required": ["operation", "operand1", "operand2"]}
    def execute(self, operation: str, operand1: float, operand2: float, **kwargs) -> dict:
        print(f">>> [工具执行] {self.name}: op='{operation}', op1='{operand1}', op2='{operand2}'")
        try:
            op1_f = float(operand1); op2_f = float(operand2); result = None; op_symbol = ""
            op_lower = operation.lower()
            if op_lower == "add" or op_lower == "+": result, op_symbol = op1_f + op2_f, "+"
            elif op_lower == "subtract" or op_lower == "-": result, op_symbol = op1_f - op2_f, "-"
            elif op_lower == "multiply" or op_lower == "*": result, op_symbol = op1_f * op2_f, "*"
            elif op_lower == "divide" or op_lower == "/":
                if op2_f == 0: return {"status": "failure", "data": "哎呀，除数不能是零哦！那样宇宙会爆炸的！💥"}
                result, op_symbol = op1_f / op2_f, "/"
            else: return {"status": "failure", "data": f"学姐暂时只支持加减乘除哦，这个 '{operation}' 运算我还在学呢。😅"}
            return {"status": "success", "data": f"计算结果：{op1_f} {op_symbol} {op2_f} = {result} ✨"}
        except ValueError: return {"status": "failure", "data": "操作数必须是数字才行哦，学姐我可算不了文字呀。🤔"}
        except Exception as e: return {"status": "error", "data": f"计算过程中好像出了点小问题：{str(e)} 😵"}

@tool
class GetWeatherForecastTool(Tool):
    def __init__(self):
        super().__init__(name="get_weather_forecast", description="(模拟) 获取指定地点和日期的天气预报。")
    def get_parameters_schema(self) -> dict:
        return {"type": "object", "properties": {"location": {"type": "string", "description": "用户想查询天气的城市或地点名称。"}, "date": {"type": "string", "description": "日期 (例如 '今天', '明天')。默认'今天'。"}}, "required": ["location"]}
    def execute(self, location: str, date: str = "今天", **kwargs) -> dict:
        print(f">>> [工具执行] {self.name}: location='{location}', date='{date}'")
        simulated_weather = {"上海": {"今天": "晴朗，25°C☀️", "明天": "多云转小雨，22°C☂️"}, "复旦大学邯郸校区": {"今天": "校园阳光明媚，26°C！"}}
        location_weather = simulated_weather.get(location)
        if not location_weather:
            if "复旦" in location or "上海" in location: location_weather = simulated_weather.get("上海")
            else: return {"status": "not_found", "data": f"学姐暂时查不到“{location}”的天气呢 🌍"}
        normalized_date = date.lower(); date_key_map = {"今天": "今天", "明日": "明天"}; date_key = date_key_map.get(normalized_date, date)
        forecast = location_weather.get(date_key)
        if not forecast:
            # forecast = location_weather.get("今天", f"学姐只知道“{location}”今天的天气。😅") # Original logic
            # if date_key != "今天": return f"关于“{location}”在“{date}”的天气，学姐还没记呢。🗓️"
            return {"status": "not_found", "data": f"关于“{location}”在“{date}”的天气，学姐还没记呢。🗓️ 我只知道今天的：{location_weather.get('今天', '未知')}"}
        return {"status": "success", "data": f"关于“{location}”在“{date}”的天气预报：{forecast}"}

# --- 知识库相关工具 (MODIFIED to handle structured return from knowledge_base) ---

@tool
class StaticKnowledgeQueryTool(Tool):
    def __init__(self):
        super().__init__(
            name="StaticKnowledgeBaseQueryTool",
            description="当用户想查询复旦大学校园内的固定、权威信息时使用此工具，例如查询官方黑话含义、官方食堂/美食地点、校园官方信息（如图书馆开放时间）等预定义的静态知识。"
        )
    def get_parameters_schema(self) -> dict:
        try:
            static_categories = list(knowledge_base.STATIC_KB_CONFIG.keys())
            category_desc = f"要查询的静态知识类别。例如：{static_categories}。"
        except AttributeError:
            category_desc = "要查询的静态知识类别 (例如 'slang', 'food', 'campus_info')。"
            print("警告: agent_tools.py 无法在定义时访问 knowledge_base.STATIC_KB_CONFIG。请确保 knowledge_base.py 已正确加载。")

        return {
            "type": "object",
            "properties": {
                "knowledge_category": {"type": "string", "description": category_desc},
                "query_filters": {
                    "type": "object",
                    "description": "根据知识类别提供的具体查询条件。例如，查黑话时是 {'term': '黑话词'}；查美食时是 {'location': '地点'}；查校园信息时是 {'topic': '具体主题'}。",
                    "properties": {
                        "term": {"type": "string", "description": "当 knowledge_category 为 'slang' 时，用户想要查询的具体黑话词语。"},
                        "location": {"type": "string", "description": "当 knowledge_category 为 'food' 时，用户指定查询美食的地点。"},
                        "topic": {"type": "string", "description": "当 knowledge_category 为 'campus_info' 时，用户关心的具体主题。"}
                    }
                }
            },
            "required": ["knowledge_category"]
        }

    def execute(self, knowledge_category: str, query_filters: dict = None, **kwargs) -> dict:
        if query_filters is None: query_filters = {}
        print(f">>> [工具执行] {self.name}: category='{knowledge_category}', filters='{query_filters}'")

        if knowledge_category == "slang":
            term = query_filters.get("term")
            if not term: return {"status": "failure", "data": "你需要告诉我你想查哪个黑话词哦 🤔。", "reason": "missing_term"}
            return knowledge_base.get_slang_definition(term) # Returns dict
        elif knowledge_category == "food":
            location = query_filters.get("location")
            # Location can be optional for random recommendations, knowledge_base.find_food handles this.
            return knowledge_base.find_food(location=location if location else "") # Returns dict
        elif knowledge_category == "campus_info":
            topic = query_filters.get("topic")
            if not topic: return {"status": "failure", "data": "你想查询哪个校园官方信息主题呢？", "reason": "missing_topic"}
            return knowledge_base.get_static_campus_info(topic) # Returns dict

        return {"status": "error", "data": f"学姐的官方资料库里暂时还不支持查询“{knowledge_category}”这类信息哦 😊", "reason": "unsupported_category"}

@tool
class LearnNewInfoTool(Tool):
    def __init__(self):
        super().__init__(
            name="LearnNewInfoTool",
            description="当用户明确表示要“教”你新信息、新知识点、某个问题的答案，或者让你“记住”某些事情时使用此工具。信息将存储在用户的个人笔记中，并按类别整理。"
        )

    def get_parameters_schema(self) -> dict:
        try:
            personal_categories = knowledge_base.SUPPORTED_PERSONAL_CATEGORIES
            category_desc = f"用户教授的新知识最适合归入哪个个人笔记类别。可选类别：{personal_categories}。如果无法明确分类，可以使用 'my_notes'。"
        except AttributeError:
            category_desc = "用户教授的新知识最适合归入哪个个人笔记类别 (例如 'my_notes', 'my_food_discoveries', 'learned_slang_personal')。"
            print("警告: agent_tools.py 无法在定义时访问 knowledge_base.SUPPORTED_PERSONAL_CATEGORIES。")

        return {
            "type": "object",
            "properties": {
                "knowledge_category": {"type": "string", "description": category_desc},
                "topic": {"type": "string", "description": "信息主题 (可选，当信息是陈述性时)。"},
                "information": {"type": "string", "description": "具体信息内容 (当 topic 存在时使用)。"},
                "question_taught": {"type": "string", "description": "用户教的具体问题 (当教授问答对时使用)。"},
                "answer_taught": {"type": "string", "description": "对应答案 (当教授问答对时使用)。"}
            },
            "required": ["knowledge_category"]
        }

    def execute(self, knowledge_category: str, user_id: str,
                topic: str = None, information: str = None,
                question_taught: str = None, answer_taught: str = None, **kwargs) -> dict:
        print(f">>> [工具执行] {self.name}: user='{user_id}', category='{knowledge_category}', topic='{topic}', info='{information}', q='{question_taught}', a='{answer_taught}'")
        if not user_id: return {"status": "failure", "data": "学姐需要知道这是为谁记笔记哦！(缺少用户信息)", "reason": "missing_user_id"}
        if not knowledge_category: return {"status": "failure", "data": "学姐需要知道这个知识点属于哪个类别才能更好地记住哦。", "reason": "missing_category"}

        result_dict = {"status": "failure", "data": "你想教给学姐什么新知识呢？需要告诉我知识的类别、主题/信息，或者具体的问题和答案哦。😊"}
        if question_taught and answer_taught:
            try:
                result_dict = knowledge_base.add_learned_qa_pair_to_personal_kb(user_id, knowledge_category, question_taught, answer_taught)
            except Exception as e:
                print(f"Error adding QA pair to personal KB: {e}")
                result_dict = {"status": "error", "data": f"添加问答对时发生错误: {str(e)}"}
        elif information:
            result_dict = knowledge_base.add_learned_info_to_personal_kb(user_id, knowledge_category, topic, information)
        
        return result_dict # Returns dict from knowledge_base

@tool
class DynamicKnowledgeQueryTool(Tool):
    def __init__(self):
        super().__init__(
            name="QueryDynamicKnowledgeTool",
            description="当用户的问题可能涉及到之前TA明确教给你的个人化信息，或社群共享的、经常更新的动态知识时使用此工具。Agent会智能地先查阅个人笔记，再查阅共享动态知识。"
        )

    def get_parameters_schema(self) -> dict:
        try:
            all_learnable_categories = sorted(list(set(knowledge_base.SUPPORTED_PERSONAL_CATEGORIES + knowledge_base.SUPPORTED_SHARED_DYNAMIC_CATEGORIES)))
            category_desc = f"用户想查询的已学知识或动态信息属于哪个类别。Agent会优先查找个人笔记，然后查找共享动态知识。可选类别：{all_learnable_categories}。"
        except AttributeError:
            category_desc = "用户想查询的已学知识或动态信息属于哪个类别 (例如 'my_notes', 'learned_slang_personal', 'campus_life_hacks')。"
            print("警告: agent_tools.py 无法在定义时访问 knowledge_base 类别列表。")

        return {
            "type": "object",
            "properties": {
                "knowledge_category": {"type": "string", "description": category_desc},
                "user_query_for_learned_info": {
                    "type": "string",
                    "description": "用户提出的、希望从已学习的动态知识（个人或通用）中查找答案的具体问题或关键词。"
                }
            },
            "required": ["knowledge_category", "user_query_for_learned_info"]
        }

    def execute(self, knowledge_category: str, user_query_for_learned_info: str, user_id: str, **kwargs) -> dict:
        print(f">>> [工具执行] {self.name}: user='{user_id}', category='{knowledge_category}', query='{user_query_for_learned_info}'")
        if not user_id: return {"status": "failure", "data": "学姐需要知道是谁在问，才能查阅相关的学习笔记哦！(缺少用户信息)", "reason": "missing_user_id"}
        if not knowledge_category: return {"status": "failure", "data": "你想查哪个类别的学习笔记呀？", "reason": "missing_category"}
        if not user_query_for_learned_info: return {"status": "failure", "data": f"你想问学姐在“{knowledge_category}”类别里学到的什么事情呀？", "reason": "missing_query"}

        return knowledge_base.search_learned_info(user_id, knowledge_category, user_query_for_learned_info) # Returns dict


# --- 辅助函数 (保持不变) ---
def get_all_registered_tools() -> dict:
    return TOOL_REGISTRY

def get_tools_description_for_llm_from_registry() -> str:
    descriptions = []
    if not TOOL_REGISTRY: return "当前没有可用的外部工具。"
    for tool_name, tool_instance in TOOL_REGISTRY.items():
        tool_info = tool_instance.get_info_for_llm()
        desc = f"工具名称: `{tool_info['name']}`\n"
        desc += f"  描述: {tool_info['description']}\n"
        params_schema = tool_info.get("parameters", {})
        if params_schema and params_schema.get("properties"):
            params_desc_list = []
            for param_name, param_detail in params_schema["properties"].items():
                param_type = param_detail.get('type', '未知类型'); param_description = param_detail.get('description', '无描述')
                is_required_str = " (必须)" if param_name in params_schema.get("required", []) else ""
                params_desc_list.append(f"{param_name}{is_required_str}: {param_description} (类型: {param_type})")
            if params_desc_list: desc += f"  参数: \n    - " + "\n    - ".join(params_desc_list) + "\n"
            else: desc += "  参数: 无\n"
        else: desc += "  参数: 无 (或由工具描述指明)\n"
        descriptions.append(desc)
    return "你可以使用以下工具来帮助回答用户的问题：\n\n" + "\n".join(descriptions)

print(f"agent_tools.py 模块加载完毕，已注册 {len(TOOL_REGISTRY)} 个工具。")




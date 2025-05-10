# knowledge_base.py
import json
import os
import shutil # 用于复制文件等操作

# --- 文件路径定义 ---
DATA_DIR = "data"
STATIC_SLANG_FILE = os.path.join(DATA_DIR, "slang.json")
STATIC_FOOD_FILE = os.path.join(DATA_DIR, "food.json")
# 可以为其他静态知识添加文件定义
# STATIC_HOUSING_RULES_FILE = os.path.join(DATA_DIR, "housing_rules.json")

# 动态知识库文件将按类别存储，例如 data/dynamic_slang.json, data/dynamic_food.json
# 定义一个模板文件名，以及支持的动态知识类别
DYNAMIC_KB_FILE_TEMPLATE = os.path.join(DATA_DIR, "dynamic_{category}.json")
SUPPORTED_DYNAMIC_CATEGORIES = ["slang", "food", "campus_life", "personal_notes", "general_fudan_info"] # 可扩展

# --- 数据存储 ---
static_slang_data = {}
static_food_data = []
# 其他静态数据...

# dynamic_kbs_data 将是一个字典，键是类别，值是该类别加载的数据
# 例如: {"slang": {"qa_pairs": [], "general_info": {}}, "food": ...}
dynamic_kbs_data = {}

def _ensure_data_dir_exists():
    """确保 data 目录存在"""
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
        print(f"目录 '{DATA_DIR}' 已创建。")

def load_all_data():
    """加载所有静态和动态知识库数据"""
    global static_slang_data, static_food_data, dynamic_kbs_data
    _ensure_data_dir_exists()

    # 加载静态知识 - 黑话
    try:
        with open(STATIC_SLANG_FILE, 'r', encoding='utf-8') as f:
            static_slang_data = json.load(f)
        print(f"静态黑话知识库 '{STATIC_SLANG_FILE}' 加载成功。")
    except FileNotFoundError:
        print(f"警告: 静态黑话文件 '{STATIC_SLANG_FILE}' 未找到。")
        static_slang_data = {} # 使用空数据
    except json.JSONDecodeError:
        print(f"错误: 静态黑话文件 '{STATIC_SLANG_FILE}' 格式错误。")
        static_slang_data = {}

    # 加载静态知识 - 美食
    try:
        with open(STATIC_FOOD_FILE, 'r', encoding='utf-8') as f:
            static_food_data = json.load(f)
        print(f"静态美食知识库 '{STATIC_FOOD_FILE}' 加载成功。")
    except FileNotFoundError:
        print(f"警告: 静态美食文件 '{STATIC_FOOD_FILE}' 未找到。")
        static_food_data = []
    except json.JSONDecodeError:
        print(f"错误: 静态美食文件 '{STATIC_FOOD_FILE}' 格式错误。")
        static_food_data = []
    
    # 加载所有类别的动态知识库
    dynamic_kbs_data = {} # 重置
    for category in SUPPORTED_DYNAMIC_CATEGORIES:
        file_path = DYNAMIC_KB_FILE_TEMPLATE.format(category=category)
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                dynamic_kbs_data[category] = json.load(f)
            print(f"动态知识库 '{file_path}' (类别: {category}) 加载成功。")
        except FileNotFoundError:
            print(f"警告: 动态知识库文件 '{file_path}' (类别: {category}) 未找到。将为此类别创建新知识库。")
            dynamic_kbs_data[category] = {"qa_pairs": [], "general_info": {}}
            _save_dynamic_kb(category) # 保存一次空结构
        except json.JSONDecodeError:
            print(f"错误: 动态知识库文件 '{file_path}' (类别: {category}) 格式错误。")
            dynamic_kbs_data[category] = {"qa_pairs": [], "general_info": {}}

def _save_dynamic_kb(category: str) -> bool:
    """保存指定类别的动态知识库到文件"""
    if category not in SUPPORTED_DYNAMIC_CATEGORIES:
        print(f"错误: 不支持的动态知识类别 '{category}'，无法保存。")
        return False
    if category not in dynamic_kbs_data:
        print(f"错误: 类别 '{category}' 的动态知识数据未加载，无法保存。")
        return False

    file_path = DYNAMIC_KB_FILE_TEMPLATE.format(category=category)
    try:
        _ensure_data_dir_exists()
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(dynamic_kbs_data[category], f, ensure_ascii=False, indent=4)
        print(f"动态知识库 (类别: {category}) 已保存到 '{file_path}'。")
        return True
    except Exception as e:
        print(f"错误: 保存动态知识库 (类别: {category}) 失败 - {e}")
        return False

# --- 静态知识查询函数 (基本不变) ---
def get_slang_definition(term: str) -> str:
    return static_slang_data.get(term, f"抱歉，我还不知道“{term}”是什么意思呢。")

def find_food(location: str, limit: int = 3) -> str:
    # ... (此函数逻辑保持不变，它查询 static_food_data) ...
    results = []
    if location:
        possible_matches = [
            item for item in static_food_data 
            if location.lower() in item.get('校区/区域', '').lower() or \
               location.lower() in item.get('名称', '').lower()
        ]
    else:
        possible_matches = static_food_data

    if not possible_matches:
        return "唉呀，暂时没有找到符合你要求的美食推荐信息呢。"
    import random
    selected_count = min(len(possible_matches), limit)
    selected_items = random.sample(possible_matches, selected_count)
    if not selected_items:
         return "唉呀，暂时没有找到符合你要求的美食推荐信息呢。"
    response_parts = [f"学姐为你找到了“{location}”附近的这些美食哦："]
    for item in selected_items:
        response_parts.append(f"- {item.get('名称', '未知店铺')}: {item.get('简介', '暂无简介')} (人均约: {item.get('人均消费', '未知')})")
    return "\n".join(response_parts)

# --- 动态知识库操作函数 (增加 category 参数) ---
def add_learned_qa_pair(category: str, question: str, answer: str) -> bool:
    """用户教授一个问答对到指定类别"""
    if category not in SUPPORTED_DYNAMIC_CATEGORIES:
        print(f"错误: 尝试向不支持的动态知识类别 '{category}' 添加QA对。")
        return False
    
    #确保该类别的数据已加载/初始化
    if category not in dynamic_kbs_data:
        dynamic_kbs_data[category] = {"qa_pairs": [], "general_info": {}}

    category_data = dynamic_kbs_data[category]
    for pair in category_data.get("qa_pairs", []):
        if pair.get("question") == question:
            pair["answer"] = answer
            print(f"动态知识更新 (类别: {category}): 问题 '{question}' 的答案已更新。")
            return _save_dynamic_kb(category)
            
    category_data.setdefault("qa_pairs", []).append({"question": question, "answer": answer})
    print(f"动态知识新增 (类别: {category}): 问题 '{question}' 已学习。")
    return _save_dynamic_kb(category)

def add_learned_info(category: str, topic: str, information: str) -> bool:
    """用户教授一个关于某主题的信息到指定类别"""
    if category not in SUPPORTED_DYNAMIC_CATEGORIES:
        print(f"错误: 尝试向不支持的动态知识类别 '{category}' 添加主题信息。")
        return False

    if category not in dynamic_kbs_data:
        dynamic_kbs_data[category] = {"qa_pairs": [], "general_info": {}}
        
    category_data = dynamic_kbs_data[category]
    category_data.setdefault("general_info", {})[topic] = information
    print(f"动态知识新增/更新 (类别: {category}): 主题 '{topic}' 的信息已学习。")
    return _save_dynamic_kb(category)

def search_learned_info(category: str, query_text: str) -> str | None:
    """在指定类别的动态知识库中搜索信息。"""
    if category not in SUPPORTED_DYNAMIC_CATEGORIES:
        return f"学姐我还不知道怎么查找“{category}”类别的学习笔记呢。😅"
    if category not in dynamic_kbs_data:
        return f"关于“{category}”类别，学姐的小本本还是空的哦。🤔"

    category_data = dynamic_kbs_data[category]
    query_lower = query_text.lower()

    # 1. 搜索 QA 对
    for pair in category_data.get("qa_pairs", []):
        if query_lower in pair.get("question", "").lower():
            return pair.get("answer")

    # 2. 搜索通用信息
    for topic, info in category_data.get("general_info", {}).items():
        if query_lower in topic.lower() or query_lower in info.lower():
            return f"关于“{topic}”（属于{category}类别），我学到的是：“{info}”"
            
    return f"在学姐的“{category}”类别小本本里，暂时没有找到和你问题“{query_text}”直接相关的信息呢。🤔"

# load_all_data() # 应用启动时由 app.py 调用

# knowledge_base.py
import json
import os
import random
import glob
from collections import Counter # For review agent logic
from thefuzz import fuzz, process

# Import database syncer for MongoDB integration (optional - graceful fallback if not available)
try:
    import database_syncer
    _DB_SYNC_ENABLED = True
except ImportError:
    print("警告: database_syncer 模块未找到，MongoDB同步功能将被禁用。")
    database_syncer = None
    _DB_SYNC_ENABLED = False

# --- Configuration: File Paths and Categories ---
DATA_DIR = "data"
PERSONAL_KBS_DIR = os.path.join(DATA_DIR, "personal_kbs") # Base dir for all personal KBs

# Static Knowledge Base Files - Authoritative, pre-defined
STATIC_KB_CONFIG = {
    "slang": {"file": "static_slang.json", "default_data": {}},
    "food": {"file": "static_food.json", "default_data": []},
    "campus_info": {"file": "static_campus_info.json", "default_data": { # e.g., building locations, office hours
        "光华楼": "位于邯郸校区中心区域，是复旦的标志性建筑之一，很多重要讲座和活动会在这里举办哦。东辅楼和西辅楼有很多教室。",
        "图书馆开放时间": "本部图书馆一般是周一到周日 8:00 - 22:00，但节假日可能会调整，最好查看图书馆官网通知呢。"
    }},
}

# Shared Dynamic Knowledge Base Files - Learned from multiple users, reviewed/promoted
SHARED_DYNAMIC_KB_FILE_TEMPLATE = "dynamic_shared_{category}.json"
# Categories for knowledge that can be learned and shared after review
SUPPORTED_SHARED_DYNAMIC_CATEGORIES = ["slang", "food_tips", "campus_life_hacks", "event_info"]
DEFAULT_SHARED_DYNAMIC_KB_STRUCTURE = {"qa_pairs": [], "general_info": {}} # Structure for shared dynamic KBs

# Personal Dynamic Knowledge Base Files - User-specific, private
PERSONAL_KB_FILE_TEMPLATE = "{category}.json" # Stored under data/personal_kbs/{user_id}/
# Categories for personal notes, preferences, or unverified learned items
SUPPORTED_PERSONAL_CATEGORIES = [
    "my_notes", "my_preferences", "reminders",
    "learned_slang_personal", "my_food_discoveries", "learned_campus_life_personal"
]
DEFAULT_PERSONAL_KB_STRUCTURE = {"qa_pairs": [], "general_info": {}}

# --- In-Memory Data Stores ---
static_data_stores = {}
shared_dynamic_kbs_data = {} # For general dynamic knowledge

# --- Constants for "Not Found" / Informative Messages ---
# 这些常量仍然有用，但函数会返回结构化数据
NOT_FOUND_STATIC_SLANG_MSG = "抱歉，学姐的权威小本本上还没有关于\"{term}\"这个黑话的记录呢。🤔"
NOT_FOUND_STATIC_FOOD_MSG = "哎呀，学姐的官方美食指南里暂时没有找到符合你要求的美食推荐哦。🍜"
NOT_FOUND_STATIC_CAMPUS_INFO_MSG = "关于\"{topic}\"的官方信息，学姐这里暂时还没有录入哦。"

NOT_FOUND_SHARED_DYNAMIC_INFO_MSG = "学姐翻了翻大家的共享笔记，暂时没有找到和你问题\"{query}\"直接相关的信息呢。也许还没人教过我这个？😅"
NOT_FOUND_PERSONAL_DYNAMIC_INFO_MSG = "在你的专属小本本里，学姐暂时没有找到关于\"{query}\"的信息哦。是不是还没教过我呀？✍️"
NOT_FOUND_ANY_INFO_FOR_QUERY_MSG = "关于\"{query}\"，学姐的个人笔记、共享笔记和官方资料里都没有找到相关信息呢。" # 更通用的未找到
NOT_FOUND_CATEGORY_INFO_MSG = "关于\"{category}\"类别，学姐的知识库还是空的哦。要不你先教我一点？"
LEARNED_TO_PERSONAL_KB_CONFIRMATION_MSG = "好嘞，学姐已经在你的个人小本本上记下关于\"{category}\"的这个信息啦！如果很多人都教我类似的内容，我说不定能把它变成通用知识哦。😉"

# --- Utility Functions (largely unchanged) ---
def _ensure_dir_exists(dir_path: str):
    if not os.path.exists(dir_path):
        try: os.makedirs(dir_path); print(f"[知识库] 目录 '{dir_path}' 已创建。")
        except OSError as e: print(f"错误: 创建目录 '{dir_path}' 失败: {e}"); return False
    return True

def _load_json_file(file_path: str, default_data_structure_generator=None):
    try:
        with open(file_path, 'r', encoding='utf-8') as f: return json.load(f)
    except FileNotFoundError:
        if callable(default_data_structure_generator):
            default_data = default_data_structure_generator()
            if _save_json_file(file_path, default_data):
                 print(f"信息: 文件 '{file_path}' 未找到，已创建并保存默认结构。")
            else:
                 print(f"警告: 文件 '{file_path}' 未找到，创建默认结构后保存失败。")
            return default_data
        return None
    except json.JSONDecodeError: print(f"错误: 文件 '{file_path}' JSON 格式无效。"); return default_data_structure_generator() if callable(default_data_structure_generator) else None
    except Exception as e: print(f"错误: 加载文件 '{file_path}' 时发生意外错误: {e}"); return default_data_structure_generator() if callable(default_data_structure_generator) else None

def _save_json_file(file_path: str, data) -> bool:
    try:
        # Use enhanced save function if database syncer is available
        if _DB_SYNC_ENABLED and database_syncer:
            return database_syncer.enhanced_save_json_file(file_path, data, sync_to_db=True)
        else:
            # Fallback to original implementation
            parent_dir = os.path.dirname(file_path)
            if not _ensure_dir_exists(parent_dir): return False
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            return True
    except Exception as e: print(f"错误: 保存数据到 '{file_path}' 失败: {e}"); return False

# --- Fuzzy Search Utility Functions ---
def _format_nested_content(data, max_depth=2, current_depth=0):
    """格式化嵌套内容的显示，避免过深的嵌套"""
    if current_depth >= max_depth:
        return "[内容过深，已省略]"
    
    if isinstance(data, str):
        return data
    elif isinstance(data, dict):
        content_parts = []
        for key, value in data.items():
            if isinstance(value, str):
                content_parts.append(f"{'  ' * current_depth}- {key}: {value}")
            elif isinstance(value, dict):
                content_parts.append(f"{'  ' * current_depth}- {key}:")
                nested_content = _format_nested_content(value, max_depth, current_depth + 1)
                content_parts.append(nested_content)
        return "\n".join(content_parts)
    else:
        return str(data)

def _fuzzy_match_slang(term: str, slang_dict: dict, threshold: int = 70) -> list:
    """使用模糊匹配查找俚语，返回匹配度高于阈值的结果列表"""
    if not slang_dict:
        return []
    
    # 使用thefuzz进行模糊匹配
    matches = process.extract(term, slang_dict.keys(), limit=3, scorer=fuzz.ratio)
    
    # 过滤低于阈值的匹配
    good_matches = [(key, score) for key, score in matches if score >= threshold]
    
    # 返回匹配的结果
    results = []
    for key, score in good_matches:
        results.append({
            "term": key,
            "definition": slang_dict[key],
            "match_score": score
        })
    
    return results

def _fuzzy_match_food(location: str, food_items: list, threshold: int = 70) -> list:
    """使用模糊匹配查找美食，支持对名称和区域的模糊搜索"""
    if not food_items or not location:
        return []
    
    location_lower = location.lower()
    potential_matches = []
    
    for item in food_items:
        # 检查区域匹配
        area_text = item.get('校区/区域', '')
        area_score = fuzz.partial_ratio(location_lower, area_text.lower())
        
        # 检查名称匹配
        name_text = item.get('名称', '')
        name_score = fuzz.partial_ratio(location_lower, name_text.lower())
        
        # 取最高分数
        max_score = max(area_score, name_score)
        
        if max_score >= threshold:
            potential_matches.append((item, max_score))
    
    # 按分数排序，分数高的在前
    potential_matches.sort(key=lambda x: x[1], reverse=True)
    
    return [item for item, score in potential_matches]

def _fuzzy_match_campus_info(topic: str, campus_dict: dict, threshold: int = 70) -> list:
    """使用模糊匹配查找校园信息，支持递归搜索嵌套结构"""
    # 调试打印语句
    print(f"[调试] _fuzzy_match_campus_info 被调用")
    print(f"[调试] 传入的 topic: '{topic}'")
    print(f"[调试] campus_dict 的键: {list(campus_dict.keys())}")
    
    if not campus_dict:
        print(f"[调试] campus_dict 为空，返回空列表")
        return []
    
    results = []
    
    # 递归搜索函数
    def recursive_search(current_dict, path=""):
        """递归搜索嵌套字典结构"""
        search_results = []
        
        for key, value in current_dict.items():
            current_path = f"{path} > {key}" if path else key
            
            if isinstance(value, dict):
                # 如果值是字典，递归搜索
                nested_results = recursive_search(value, current_path)
                search_results.extend(nested_results)
                
                # 同时也检查当前层级的key是否匹配
                key_score = fuzz.token_set_ratio(topic.lower(), key.lower())
                if key_score >= threshold:
                    # 如果匹配的是一个分类，展示该分类下的所有内容
                    category_info = f"分类\"{key}\"包含以下内容：\n{_format_nested_content(value, max_depth=3, current_depth=1)}"
                    search_results.append({
                        "topic": key,
                        "info": category_info,
                        "match_score": key_score,
                        "path": current_path,
                        "match_type": "category"
                    })
            
            elif isinstance(value, str):
                # 如果值是字符串，检查key和value的匹配
                key_score = fuzz.token_set_ratio(topic.lower(), key.lower())
                value_score = fuzz.token_set_ratio(topic.lower(), value.lower())
                max_score = max(key_score, value_score)
                
                if max_score >= threshold:
                    search_results.append({
                        "topic": key,
                        "info": value,
                        "match_score": max_score,
                        "path": current_path,
                        "match_type": "content"
                    })
        
        return search_results
    
    # 执行递归搜索
    all_matches = recursive_search(campus_dict)
    
    print(f"[调试] 递归搜索找到的所有匹配: {len(all_matches)}")
    for match in all_matches:
        print(f"[调试] 匹配项: {match['topic']} (路径: {match['path']}, 分数: {match['match_score']}, 类型: {match['match_type']})")
    
    # 按分数排序，分数高的在前
    all_matches.sort(key=lambda x: x["match_score"], reverse=True)
    
    # 过滤重复和低质量匹配
    seen_paths = set()
    for match in all_matches:
        if match["path"] not in seen_paths and match["match_score"] >= threshold:
            results.append(match)
            seen_paths.add(match["path"])
    
    print(f"[调试] 经过阈值({threshold})过滤和去重后的结果数量: {len(results)}")
    return results

def _fuzzy_search_in_qa_pairs(query: str, qa_pairs: list, threshold: int = 70) -> list:
    """在QA对中进行模糊搜索"""
    if not qa_pairs:
        return []
    
    results = []
    for pair in qa_pairs:
        question = pair.get("question", "")
        answer = pair.get("answer", "")
        
        # 对问题进行模糊匹配
        question_score = fuzz.partial_ratio(query.lower(), question.lower())
        
        if question_score >= threshold:
            results.append({
                "question": question,
                "answer": answer,
                "match_score": question_score,
                "match_type": "question"
            })
    
    # 按分数排序
    results.sort(key=lambda x: x["match_score"], reverse=True)
    return results

def _fuzzy_search_in_general_info(query: str, general_info: dict, threshold: int = 70) -> list:
    """在通用信息中进行模糊搜索"""
    if not general_info:
        return []
    
    results = []
    for topic, info in general_info.items():
        # 对主题和信息内容都进行模糊匹配
        topic_score = fuzz.partial_ratio(query.lower(), topic.lower())
        info_score = fuzz.partial_ratio(query.lower(), info.lower())
        max_score = max(topic_score, info_score)
        
        if max_score >= threshold:
            results.append({
                "topic": topic,
                "info": info,
                "match_score": max_score,
                "match_type": "topic" if topic_score > info_score else "content"
            })
    
    # 按分数排序
    results.sort(key=lambda x: x["match_score"], reverse=True)
    return results

# --- Initialization ---
def load_all_data():
    """Loads all static and SHARED dynamic knowledge base data from files."""
    global static_data_stores, shared_dynamic_kbs_data
    _ensure_dir_exists(DATA_DIR)
    print("[知识库] 开始加载所有静态和共享动态数据...")

    static_data_stores = {}
    for category, config in STATIC_KB_CONFIG.items():
        file_path = os.path.join(DATA_DIR, config["file"])
        static_data_stores[category] = _load_json_file(file_path, lambda: config["default_data"])
        print(f"  静态知识库 '{category}' (来自 '{config['file']}') 加载完毕。")

    shared_dynamic_kbs_data = {}
    for category in SUPPORTED_SHARED_DYNAMIC_CATEGORIES:
        file_path = os.path.join(DATA_DIR, SHARED_DYNAMIC_KB_FILE_TEMPLATE.format(category=category))
        shared_dynamic_kbs_data[category] = _load_json_file(file_path, lambda: DEFAULT_SHARED_DYNAMIC_KB_STRUCTURE.copy())
        print(f"  共享动态知识库 '{category}' (来自 '{os.path.basename(file_path)}') 加载完毕。")
    print("[知识库] 所有静态和共享动态数据加载完成。")

# --- Static Knowledge Query Functions (Return structured data) ---
def get_slang_definition(term: str) -> dict:
    slang_dict = static_data_stores.get("slang", {})
    
    # 首先尝试精确匹配
    definition = slang_dict.get(term)
    if definition:
        return {"status": "success", "data": definition, "match_type": "exact"}
    
    # 如果精确匹配失败，尝试模糊匹配
    fuzzy_matches = _fuzzy_match_slang(term, slang_dict)
    if fuzzy_matches:
        if len(fuzzy_matches) == 1:
            # 只有一个匹配结果，直接返回
            match = fuzzy_matches[0]
            response = f"学姐没有找到\"{term}\"的精确定义，不过找到了相似的：\"{match['term']}\" - {match['definition']}（匹配度：{match['match_score']}%）"
            return {"status": "success", "data": response, "match_type": "fuzzy", "fuzzy_matches": fuzzy_matches}
        else:
            # 多个匹配结果，列出所有可能的选项
            response_parts = [f"学姐没有找到\"{term}\"的精确定义，不过找到了几个相似的选项："]
            for i, match in enumerate(fuzzy_matches, 1):
                response_parts.append(f"{i}. \"{match['term']}\" - {match['definition']}（匹配度：{match['match_score']}%）")
            return {"status": "success", "data": "\n".join(response_parts), "match_type": "fuzzy", "fuzzy_matches": fuzzy_matches}
    
    # 完全没有找到匹配的结果
    return {"status": "not_found", "data": NOT_FOUND_STATIC_SLANG_MSG.format(term=term)}

def find_food(location: str, limit: int = 3) -> dict:
    all_food_items = static_data_stores.get("food", [])
    possible_matches = []
    
    if location:
        # 首先尝试精确匹配（原有逻辑）
        location_lower = location.lower()
        for item in all_food_items:
            if location_lower in item.get('校区/区域', '').lower() or \
               location_lower in item.get('名称', '').lower():
                possible_matches.append(item)
        
        # 如果精确匹配没有结果，尝试模糊匹配
        if not possible_matches:
            possible_matches = _fuzzy_match_food(location, all_food_items, threshold=60)
            if possible_matches:
                # 添加模糊匹配的提示信息
                fuzzy_note = f"（学姐使用模糊搜索为你找到了与\"{location}\"相关的美食）"
            else:
                return {"status": "not_found", "data": NOT_FOUND_STATIC_FOOD_MSG}
        else:
            fuzzy_note = ""
    else:
        # 如果没有指定位置，随机选择一些
        possible_matches = random.sample(all_food_items, min(len(all_food_items), limit)) if all_food_items else []
        fuzzy_note = ""

    if not possible_matches:
        return {"status": "not_found", "data": NOT_FOUND_STATIC_FOOD_MSG}

    selected_items = random.sample(possible_matches, min(len(possible_matches), limit))
    if not selected_items:
        return {"status": "not_found", "data": NOT_FOUND_STATIC_FOOD_MSG}

    response_parts = [f"学姐为你找到了\"{location if location else '一些'}\"美食哦：{fuzzy_note}"]
    for item in selected_items:
        response_parts.append(
            f"- {item.get('名称', '未知店铺')}: {item.get('简介', '暂无简介')} "
            f"(人均约: {item.get('人均消费', '未知')}, 标签: {', '.join(item.get('标签', ['暂无']))})"
        )
    
    match_type = "fuzzy" if fuzzy_note else "exact"
    return {"status": "success", "data": "\n".join(response_parts), "match_type": match_type}

def get_static_campus_info(topic: str) -> dict:
    campus_dict = static_data_stores.get("campus_info", {})
    
    # 递归查找函数
    def recursive_exact_search(current_dict, path=""):
        """递归进行精确匹配搜索"""
        for key, value in current_dict.items():
            current_path = f"{path} > {key}" if path else key
            
            # 检查当前key是否精确匹配
            if key == topic:
                if isinstance(value, str):
                    return {"found": True, "data": value, "path": current_path, "type": "content"}
                elif isinstance(value, dict):
                    # 如果匹配的是分类，展示分类内容
                    category_info = f"分类\"{key}\"包含以下内容：\n{_format_nested_content(value, max_depth=3, current_depth=1)}"
                    return {"found": True, "data": category_info, "path": current_path, "type": "category"}
            
            # 如果值是字典，递归搜索
            if isinstance(value, dict):
                result = recursive_exact_search(value, current_path)
                if result["found"]:
                    return result
        
        return {"found": False}
    
    # 首先尝试精确匹配（递归）
    exact_result = recursive_exact_search(campus_dict)
    if exact_result["found"]:
        return {
            "status": "success", 
            "data": exact_result["data"], 
            "match_type": "exact",
            "path": exact_result["path"],
            "content_type": exact_result["type"]
        }
    
    # 如果精确匹配失败，尝试模糊匹配
    fuzzy_matches = _fuzzy_match_campus_info(topic, campus_dict)
    if fuzzy_matches:
        if len(fuzzy_matches) == 1:
            # 只有一个匹配结果，直接返回
            match = fuzzy_matches[0]
            if match["path"] != match["topic"]:
                # 有路径信息，说明是嵌套结构
                response = f"学姐没有找到\"{topic}\"的精确信息，不过在路径「{match['path']}」下找到了相似的内容：\n\n{match['info']}（匹配度：{match['match_score']}%）"
            else:
                # 顶层匹配
                response = f"学姐没有找到\"{topic}\"的精确信息，不过找到了相似的：\n\n关于\"{match['topic']}\"：{match['info']}（匹配度：{match['match_score']}%）"
            
            return {
                "status": "success", 
                "data": response, 
                "match_type": "fuzzy", 
                "fuzzy_matches": fuzzy_matches,
                "path": match["path"],
                "content_type": match["match_type"]
            }
        else:
            # 多个匹配结果，列出所有可能的选项
            response_parts = [f"学姐没有找到\"{topic}\"的精确信息，不过找到了几个相似的选项：\n"]
            for i, match in enumerate(fuzzy_matches, 1):
                if match["path"] != match["topic"]:
                    # 有路径信息
                    response_parts.append(f"{i}. 在路径「{match['path']}」：{match['info']}（匹配度：{match['match_score']}%）")
                else:
                    # 顶层匹配
                    response_parts.append(f"{i}. 关于\"{match['topic']}\"：{match['info']}（匹配度：{match['match_score']}%）")
            
            return {
                "status": "success", 
                "data": "\n".join(response_parts), 
                "match_type": "fuzzy", 
                "fuzzy_matches": fuzzy_matches
            }
    
    # 完全没有找到匹配的结果
    return {"status": "not_found", "data": NOT_FOUND_STATIC_CAMPUS_INFO_MSG.format(topic=topic)}


# --- Personal Knowledge Base Helper Functions ---
def _get_personal_kb_category_path(user_id: str, category: str) -> str | None:
    if not user_id: print("错误: 操作个人知识库需要 user_id。"); return None
    user_dir = os.path.join(PERSONAL_KBS_DIR, str(user_id))
    return os.path.join(user_dir, PERSONAL_KB_FILE_TEMPLATE.format(category=category))

def _load_or_initialize_personal_kb_category(user_id: str, category: str) -> dict | None:
    file_path = _get_personal_kb_category_path(user_id, category)
    if not file_path: return None
    data = _load_json_file(file_path, lambda: DEFAULT_PERSONAL_KB_STRUCTURE.copy())
    return data if data is not None else DEFAULT_PERSONAL_KB_STRUCTURE.copy()


def _save_personal_kb_category(user_id: str, category: str, data: dict) -> bool:
    file_path = _get_personal_kb_category_path(user_id, category)
    if not file_path: return False
    user_specific_dir = os.path.join(PERSONAL_KBS_DIR, str(user_id))
    if not _ensure_dir_exists(user_specific_dir): return False
    return _save_json_file(file_path, data)

# --- Functions for Storing User-Taught Knowledge (Return structured data) ---
def add_learned_qa_pair_to_personal_kb(user_id: str, category: str, question: str, answer: str) -> dict:
    if not user_id:
        return {"status": "failure", "data": "错误: user_id 不能为空以添加个人QA对。"}
    if category not in SUPPORTED_PERSONAL_CATEGORIES:
        print(f"警告: 尝试向个人知识库添加不支持的类别 '{category}'。将使用 'my_notes'。")
        category = "my_notes"
        if category not in SUPPORTED_PERSONAL_CATEGORIES: SUPPORTED_PERSONAL_CATEGORIES.append(category)

    personal_kb_category_data = _load_or_initialize_personal_kb_category(user_id, category)
    if personal_kb_category_data is None:
        return {"status": "failure", "data": f"错误: 无法加载或初始化用户 '{user_id}' 的个人知识库类别 '{category}'。"}

    qa_pairs = personal_kb_category_data.setdefault("qa_pairs", [])
    updated = False
    for pair in qa_pairs:
        if pair.get("question", "").lower() == question.lower():
            pair["answer"] = answer
            updated = True
            print(f"[个人知识] 更新 (用户: {user_id}, 类别: {category}): 问题 '{question}'。")
            break
    if not updated:
        qa_pairs.append({"question": question, "answer": answer})
        print(f"[个人知识] 新增 (用户: {user_id}, 类别: {category}): 问题 '{question}'。")

    if _save_personal_kb_category(user_id, category, personal_kb_category_data):
        return {"status": "success", "data": LEARNED_TO_PERSONAL_KB_CONFIRMATION_MSG.format(category=category)}
    else:
        return {"status": "failure", "data": f"错误: 保存用户 '{user_id}' 的个人知识库类别 '{category}' 失败。"}

def add_learned_info_to_personal_kb(user_id: str, category: str, topic: str, information: str) -> dict:
    if not user_id:
        return {"status": "failure", "data": "错误: user_id 不能为空以添加个人信息。"}
    if category not in SUPPORTED_PERSONAL_CATEGORIES:
        print(f"警告: 尝试向个人知识库添加不支持的类别 '{category}'。将使用 'my_notes'。")
        category = "my_notes"
        if category not in SUPPORTED_PERSONAL_CATEGORIES: SUPPORTED_PERSONAL_CATEGORIES.append(category)

    personal_kb_category_data = _load_or_initialize_personal_kb_category(user_id, category)
    if personal_kb_category_data is None:
        return {"status": "failure", "data": f"错误: 无法加载或初始化用户 '{user_id}' 的个人知识库类别 '{category}'。"}

    general_info_store = personal_kb_category_data.setdefault("general_info", {})
    general_info_store[topic] = information
    print(f"[个人知识] 新增/更新 (用户: {user_id}, 类别: {category}): 主题 '{topic}'。")

    if _save_personal_kb_category(user_id, category, personal_kb_category_data):
        return {"status": "success", "data": LEARNED_TO_PERSONAL_KB_CONFIRMATION_MSG.format(category=category)}
    else:
        return {"status": "failure", "data": f"错误: 保存用户 '{user_id}' 的个人知识库类别 '{category}' 失败。"}

# --- Functions for ReviewAgent to Promote Knowledge to Shared Dynamic KB ---
# These can remain returning boolean for now, or also be updated to return dicts if needed by ReviewAgent logic
def add_promoted_qa_pair_to_shared_dynamic_kb(category: str, question: str, answer: str) -> bool:
    if category not in SUPPORTED_SHARED_DYNAMIC_CATEGORIES:
        print(f"错误: 尝试向共享动态库添加不支持的类别 '{category}'。")
        return False
    category_kb = shared_dynamic_kbs_data.get(category)
    if category_kb is None:
        shared_dynamic_kbs_data[category] = DEFAULT_SHARED_DYNAMIC_KB_STRUCTURE.copy()
        category_kb = shared_dynamic_kbs_data[category]
    qa_pairs = category_kb.setdefault("qa_pairs", [])
    for pair in qa_pairs:
        if pair.get("question", "").lower() == question.lower():
            pair["answer"] = answer
            print(f"[共享动态知识] 更新 (类别: {category}): 问题 '{question}' (由审核Agent晋升)。")
            return _save_json_file(os.path.join(DATA_DIR, SHARED_DYNAMIC_KB_FILE_TEMPLATE.format(category=category)), category_kb)
    qa_pairs.append({"question": question, "answer": answer})
    print(f"[共享动态知识] 新增 (类别: {category}): 问题 '{question}' (由审核Agent晋升)。")
    return _save_json_file(os.path.join(DATA_DIR, SHARED_DYNAMIC_KB_FILE_TEMPLATE.format(category=category)), category_kb)

def add_promoted_info_to_shared_dynamic_kb(category: str, topic: str, information: str) -> bool:
    if category not in SUPPORTED_SHARED_DYNAMIC_CATEGORIES:
        print(f"错误: 尝试向共享动态库添加不支持的类别 '{category}'。")
        return False
    category_kb = shared_dynamic_kbs_data.get(category)
    if category_kb is None:
        shared_dynamic_kbs_data[category] = DEFAULT_SHARED_DYNAMIC_KB_STRUCTURE.copy()
        category_kb = shared_dynamic_kbs_data[category]
    general_info_store = category_kb.setdefault("general_info", {})
    general_info_store[topic] = information
    print(f"[共享动态知识] 新增/更新 (类别: {category}): 主题 '{topic}' (由审核Agent晋升)。")
    return _save_json_file(os.path.join(DATA_DIR, SHARED_DYNAMIC_KB_FILE_TEMPLATE.format(category=category)), category_kb)

# --- Function for ReviewAgent to Read ALL Personal KBs for a specific personal category ---
def get_all_entries_from_personal_kbs_by_category(target_personal_category: str) -> list:
    if not _ensure_dir_exists(PERSONAL_KBS_DIR): return []
    if target_personal_category not in SUPPORTED_PERSONAL_CATEGORIES:
        print(f"警告: 尝试为审核读取不支持的个人类别 '{target_personal_category}'。")
        return []
    all_learned_items = []
    for user_id_dir in os.listdir(PERSONAL_KBS_DIR):
        user_dir_path = os.path.join(PERSONAL_KBS_DIR, user_id_dir)
        if os.path.isdir(user_dir_path):
            personal_category_file_path = os.path.join(user_dir_path, PERSONAL_KB_FILE_TEMPLATE.format(category=target_personal_category))
            if os.path.exists(personal_category_file_path):
                user_category_data = _load_json_file(personal_category_file_path, lambda: DEFAULT_PERSONAL_KB_STRUCTURE.copy())
                if user_category_data:
                    for qa in user_category_data.get("qa_pairs", []):
                        all_learned_items.append({
                            "user_id": user_id_dir, "category": target_personal_category, "type": "qa",
                            "question": qa.get("question"), "answer": qa.get("answer"),
                            "raw_entry": qa
                        })
                    for topic, info in user_category_data.get("general_info", {}).items():
                        all_learned_items.append({
                            "user_id": user_id_dir, "category": target_personal_category, "type": "info",
                            "topic": topic, "information": info,
                            "raw_entry": {topic: info}
                        })
    print(f"[审核支持] 为个人类别 '{target_personal_category}' 从所有用户处收集到 {len(all_learned_items)} 条目。")
    return all_learned_items

# --- Unified Dynamic Knowledge Search Function (Return structured data) ---
def search_learned_info(user_id: str, category_to_search: str, query_text: str) -> dict:
    personal_found_answer_data = None
    personal_fuzzy_matches = []
    
    if user_id and category_to_search in SUPPORTED_PERSONAL_CATEGORIES:
        personal_kb_category_data = _load_or_initialize_personal_kb_category(user_id, category_to_search)
        if personal_kb_category_data:
            query_lower = query_text.lower()
            
            # 首先尝试精确匹配
            for pair in personal_kb_category_data.get("qa_pairs", []):
                if query_lower in pair.get("question", "").lower():
                    personal_found_answer_data = pair.get("answer")
                    break
            
            if not personal_found_answer_data:
                for topic, info in personal_kb_category_data.get("general_info", {}).items():
                    if query_lower in topic.lower() or query_lower in info.lower():
                        personal_found_answer_data = f"关于\"{topic}\"（在你的\"{category_to_search}\"个人笔记里），我学到的是：\"{info}\""
                        break
            
            # 如果精确匹配失败，尝试模糊匹配
            if not personal_found_answer_data:
                # 在QA对中进行模糊搜索
                qa_fuzzy_results = _fuzzy_search_in_qa_pairs(query_text, personal_kb_category_data.get("qa_pairs", []), threshold=60)
                if qa_fuzzy_results:
                    best_match = qa_fuzzy_results[0]
                    personal_found_answer_data = f"学姐在你的个人笔记里没找到精确匹配，不过找到了相似的问题：\n\n问：{best_match['question']}（匹配度：{best_match['match_score']}%）\n答：{best_match['answer']}"
                    personal_fuzzy_matches = qa_fuzzy_results
                
                # 如果QA对中没有找到，在通用信息中搜索
                if not personal_found_answer_data:
                    info_fuzzy_results = _fuzzy_search_in_general_info(query_text, personal_kb_category_data.get("general_info", {}), threshold=60)
                    if info_fuzzy_results:
                        best_match = info_fuzzy_results[0]
                        personal_found_answer_data = f"学姐在你的个人笔记里找到了相似的信息：\n\n关于\"{best_match['topic']}\"（匹配度：{best_match['match_score']}%）：{best_match['info']}"
                        personal_fuzzy_matches = info_fuzzy_results
        
        if personal_found_answer_data:
            print(f"[动态查询] 在用户 '{user_id}' 的个人 '{category_to_search}' 知识中找到。")
            result = {"status": "success", "data": personal_found_answer_data, "source": "personal_kb"}
            if personal_fuzzy_matches:
                result["match_type"] = "fuzzy"
                result["fuzzy_matches"] = personal_fuzzy_matches
            else:
                result["match_type"] = "exact"
            return result

    shared_found_answer_data = None
    shared_fuzzy_matches = []
    
    if category_to_search in SUPPORTED_SHARED_DYNAMIC_CATEGORIES:
        shared_category_kb = shared_dynamic_kbs_data.get(category_to_search)
        if shared_category_kb:
            query_lower = query_text.lower()
            
            # 首先尝试精确匹配
            for pair in shared_category_kb.get("qa_pairs", []):
                if query_lower in pair.get("question", "").lower():
                    shared_found_answer_data = pair.get("answer")
                    break
            
            if not shared_found_answer_data:
                for topic, info in shared_category_kb.get("general_info", {}).items():
                    if query_lower in topic.lower() or query_lower in info.lower():
                        shared_found_answer_data = f"关于\"{topic}\"（在共享的\"{category_to_search}\"知识里），学姐了解到的是：\"{info}\""
                        break
            
            # 如果精确匹配失败，尝试模糊匹配
            if not shared_found_answer_data:
                # 在QA对中进行模糊搜索
                qa_fuzzy_results = _fuzzy_search_in_qa_pairs(query_text, shared_category_kb.get("qa_pairs", []), threshold=60)
                if qa_fuzzy_results:
                    best_match = qa_fuzzy_results[0]
                    shared_found_answer_data = f"学姐在共享知识里没找到精确匹配，不过找到了相似的问题：\n\n问：{best_match['question']}（匹配度：{best_match['match_score']}%）\n答：{best_match['answer']}"
                    shared_fuzzy_matches = qa_fuzzy_results
                
                # 如果QA对中没有找到，在通用信息中搜索
                if not shared_found_answer_data:
                    info_fuzzy_results = _fuzzy_search_in_general_info(query_text, shared_category_kb.get("general_info", {}), threshold=60)
                    if info_fuzzy_results:
                        best_match = info_fuzzy_results[0]
                        shared_found_answer_data = f"学姐在共享知识里找到了相似的信息：\n\n关于\"{best_match['topic']}\"（匹配度：{best_match['match_score']}%）：{best_match['info']}"
                        shared_fuzzy_matches = info_fuzzy_results
        
        if shared_found_answer_data:
            print(f"[动态查询] 在共享 '{category_to_search}' 知识中找到。")
            result = {"status": "success", "data": shared_found_answer_data, "source": "shared_kb"}
            if shared_fuzzy_matches:
                result["match_type"] = "fuzzy"
                result["fuzzy_matches"] = shared_fuzzy_matches
            else:
                result["match_type"] = "exact"
            return result

    # Not found in either, or category was invalid for one of them
    is_valid_personal_cat = category_to_search in SUPPORTED_PERSONAL_CATEGORIES
    is_valid_shared_cat = category_to_search in SUPPORTED_SHARED_DYNAMIC_CATEGORIES

    if is_valid_personal_cat and is_valid_shared_cat:
        # Tried both, found nothing
        return {"status": "not_found", "data": NOT_FOUND_ANY_INFO_FOR_QUERY_MSG.format(query=query_text) + f" (在 '{category_to_search}' 类别里哦)", "source": "none"}
    elif is_valid_personal_cat:
        # Only personal was relevant/searched and not found
        return {"status": "not_found", "data": NOT_FOUND_PERSONAL_DYNAMIC_INFO_MSG.format(query=query_text) + f" (在你的 '{category_to_search}' 个人笔记里)", "source": "none"}
    elif is_valid_shared_cat:
        # Only shared was relevant/searched and not found
        return {"status": "not_found", "data": NOT_FOUND_SHARED_DYNAMIC_INFO_MSG.format(query=query_text) + f" (在共享的 '{category_to_search}' 笔记里)", "source": "none"}
    else:
        # Category was not valid for any dynamic search
        msg = f"学姐不太确定\"{category_to_search}\"类别里有没有可以学习或查询的笔记呢。你可以试试这些类别：个人笔记({SUPPORTED_PERSONAL_CATEGORIES})，共享知识({SUPPORTED_SHARED_DYNAMIC_CATEGORIES})。或者直接教我一些新东西吧！"
        return {"status": "error", "data": msg, "reason": "invalid_category_for_dynamic_search"}


# --- Functions for the Review Process (to be called by a ReviewAgent or batch script) ---
def review_and_promote_knowledge(personal_category_to_review: str,
                                 target_shared_category: str,
                                 min_mentions_to_promote: int = 3,
                                 similarity_threshold: float = 0.8): # Placeholder for future
    if personal_category_to_review not in SUPPORTED_PERSONAL_CATEGORIES:
        print(f"审核错误: 个人知识类别 '{personal_category_to_review}' 不支持审核。")
        return {"promoted_count": 0, "errors": 1, "message": f"个人知识类别 '{personal_category_to_review}' 不支持审核。"}
    if target_shared_category not in SUPPORTED_SHARED_DYNAMIC_CATEGORIES:
        print(f"审核错误: 目标共享类别 '{target_shared_category}' 不支持。")
        return {"promoted_count": 0, "errors": 1, "message": f"目标共享类别 '{target_shared_category}' 不支持。"}

    print(f"\n--- 开始审核个人知识类别 '{personal_category_to_review}' 以晋升到共享类别 '{target_shared_category}' ---")
    # MODIFICATION: Corrected function name
    all_items = get_all_entries_from_personal_kbs_by_category(personal_category_to_review)
    if not all_items:
        print("没有找到可供审核的个人知识条目。")
        return {"promoted_count": 0, "errors": 0, "message": "没有找到可供审核的个人知识条目。"}

    promoted_count = 0
    qa_candidates = {}
    original_qa_entries = {}

    for item in all_items:
        if item["type"] == "qa" and item.get("question") and item.get("answer"):
            q_lower = item["question"].lower().strip()
            a_lower = item["answer"].lower().strip()
            key = (q_lower, a_lower)
            qa_candidates[key] = qa_candidates.get(key, 0) + 1
            if key not in original_qa_entries:
                original_qa_entries[key] = (item["question"], item["answer"])

    for (q_l, a_l), count in qa_candidates.items():
        if count >= min_mentions_to_promote:
            original_q, original_a = original_qa_entries[(q_l, a_l)]
            print(f"  晋升QA对: '{original_q}' -> '{original_a}' (被提及 {count} 次)")
            if add_promoted_qa_pair_to_shared_dynamic_kb(target_shared_category, original_q, original_a):
                promoted_count += 1

    info_candidates = {}
    original_info_entries = {}
    for item in all_items:
        if item["type"] == "info" and item.get("topic") and item.get("information"):
            t_lower = item["topic"].lower().strip()
            i_lower = item["information"].lower().strip()
            key = (t_lower, i_lower)
            info_candidates[key] = info_candidates.get(key, 0) + 1
            if key not in original_info_entries:
                 original_info_entries[key] = (item["topic"], item["information"])

    for (t_l, i_l), count in info_candidates.items():
        if count >= min_mentions_to_promote:
            original_t, original_i = original_info_entries[(t_l, i_l)]
            print(f"  晋升主题信息: '{original_t}' -> '{original_i}' (被提及 {count} 次)")
            if add_promoted_info_to_shared_dynamic_kb(target_shared_category, original_t, original_i):
                promoted_count += 1

    final_message = f"审核完成。共晋升 {promoted_count} 条知识到共享类别 '{target_shared_category}'"
    print(f"--- {final_message} ---")
    return {"promoted_count": promoted_count, "candidates_evaluated": len(qa_candidates) + len(info_candidates), "message": final_message}

# load_all_data() # Called by app.py at startup


import json
import random # 用于随机推荐

slang_data = {}
food_data = []

def load_data():
    global slang_data, food_data
    try:
        with open('data/slang.json', 'r', encoding='utf-8') as f:
            slang_data = json.load(f) # 假设格式是 {"旦旦": "解释...", ...}
        # 假设 food.csv 有 '名称', '校区/区域', '简介' 列
        # 使用 pandas 会更方便:
        # import pandas as pd
        # food_data = pd.read_csv('data/food.csv').to_dict('records')
        # 这里用简单列表示例
        with open('data/food.json', 'r', encoding='utf-8') as f: # 假设是 JSON 列表
            food_data = json.load(f)

    except FileNotFoundError:
        print("Warning: Data files not found.")

def get_slang_definition(term):
    return slang_data.get(term, "抱歉，我还不知道“" + term + "”是什么意思呢。")

def find_food(location=None, limit=3):
    results = []
    if location:
        # 简单匹配 location
        possible_matches = [item for item in food_data if location in item.get('校区/区域', '')]
    else:
        # 如果没有指定地点，可以随机推荐或推荐默认区域
        possible_matches = food_data

    if not possible_matches:
        return "唉呀，暂时没有找到合适的美食推荐信息呢。"

    # 随机选择几个推荐
    selected = random.sample(possible_matches, min(len(possible_matches), limit))
    response_text = f"为你找到一些美食推荐：\n"
    for item in selected:
        response_text += f"- {item.get('名称', '未知名称')}: {item.get('简介', '暂无简介')}\n"
    return response_text

# 在应用启动时加载数据
load_data()
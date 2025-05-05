NLU_PROMPT_TEMPLATE = """
You are a helpful assistant for Fudan University students. Analyze the user's request and identify the intent and key entities. Output the result ONLY in JSON format.

Available intents: 'ask_food_recommendation', 'ask_slang_explanation', 'greet', 'goodbye', 'unknown'.
Available entities for food: 'location', 'cuisine_type', 'price_range'.
Available entities for slang: 'slang_term'.

User request: "{user_input}"

JSON output:
"""
import ast
import re

args_str = 'question_text="Cho ham so y=x^2, tim dao ham", options=["A. 2x", "B. x"], correct_answer="A", explanation="", difficulty="Easy", topic="Dao ham", grade=12, subject="Toan"'

pattern = r'(\w+)\s*=\s*(?:(["\'])(.*?)\2|([\[\{].*?[\]\}])|([^,\s]+))'
matches = re.findall(pattern, args_str)
args_dict = {}
for match in matches:
    key = match[0]
    val = match[2] or match[3] or match[4]
    val = val.strip()
    try:
        args_dict[key] = ast.literal_eval(val)
    except Exception:
        args_dict[key] = val
print(args_dict)

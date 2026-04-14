from extract_quotes import _remove_substring_quotes
import json

quotes = [
    {
        "text": "推进任何一项工作，只要我们党旗帜鲜明了，全党都行动起来了，全社会就会跟着走",
        "type": "direct"
    },
    {
        "text": "推进任何一项工作，只要我们党旗帜鲜明了，全党都行动起来了，全社会就会跟着走。一个政党执政，最怕的是在重大问题上态度不坚定，结果社会上对有关问题沸沸扬扬、莫衷一是，别有用心的人趁机煽风点火、蛊惑搅和，最终没有不出事的！道路问题不能含糊，必须向全社会释放正确而又明确的信号。",
        "type": "direct"
    },
    {
        "text": "我们既要立足当前，运用法治思维和法治方式解决经济社会发展面临的深层次问题",
        "type": "direct"
    },
    {
        "text": "我们既要立足当前，运用法治思维和法治方式解决经济社会发展面临的深层次问题；又要着眼长远，筑法治之基、行法治之力、积法治之势，促进各方面制度更加成熟更加定型，为党和国家事业发展提供长期性的制度保障。",
        "type": "direct"
    }
]

res = _remove_substring_quotes(quotes)
print(json.dumps(res, ensure_ascii=False, indent=2))
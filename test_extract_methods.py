import re
import json
import requests

# ==========================================================
# 方案1：基于规则（正则表达式）提取“习近平”讲过的语句
# ==========================================================
def extract_quotes_by_rule(text):
    """
    使用正则表达式提取文本中“习近平”讲过的语句。
    匹配逻辑：寻找包含“习近平”的句子，并提取其中双引号内的内容。
    """
    results = []
    # 匹配引导语的正则：寻找“习近平”以及常见的发言动词
    # 寻找诸如“习近平指出”、“习近平强调”等后面的双引号内容
    
    # 简单切分句子，按句号切分
    sentences = re.split(r'([。！？])', text)
    sentences = ["".join(i) for i in zip(sentences[0::2], sentences[1::2] + [""])]
    
    quote_pattern = re.compile(r'["“]([^"”]+)["”]')
    
    for sentence in sentences:
        if "习近平" in sentence:
            # 截取“习近平”出现位置到段落末尾的子串
            xi_context = sentence[sentence.find("习近平"):]
            
            # 检查是否有引导动词
            verbs = ["指出", "强调", "要求", "提出", "明确", "认为", "深刻指出", "强调指出", "指出："]
            if any(verb in xi_context[:50] for verb in verbs):
                # 提取双引号内的内容
                quotes = quote_pattern.findall(xi_context)
                if quotes:
                    # 过滤掉极短的可能不是整句的引用
                    valid_quotes = [q for q in quotes if len(q) > 2]
                    if valid_quotes:
                        results.append({
                            "original_text": sentence.strip(),
                            "extracted_quotes": valid_quotes
                        })
    return results


# ==========================================================
# 方案2：基于大语言模型（Ollama API）提取“习近平”讲过的语句
# ==========================================================
def extract_quotes_by_llm(text, ollama_url="http://192.168.0.19:11435/api/chat", model="qwen2.5:7b"):
    """
    调用 Ollama 接口，让大语言模型进行信息提取，并以 JSON 格式返回。
    """
    system_prompt = '''
    # 角色定位
    你是一个专业的文本分析和信息抽取专家，擅长从复杂的中文文献中精准提取特定人物的言论。

    # 任务目标
    请阅读下方提供的【文本内容】，提取出其中所有由“习近平”直接讲过的语句，并以严格的 JSON 格式返回。

    # 提取规则
    1. 目标人物：仅提取“习近平”本人的讲话或论述内容。
    2. 内容范围：通常紧跟在“指出”、“强调”、“明确”等引导词之后，且被双引号“ ”包裹的内容。
    3. 数据清洗：提取时，请去掉内容结尾处可能附带的引用序号（如 ①, ②, ③ 等），仅保留讲话的纯文本内容。
    4. 间接引用：如果是作者的间接叙述而非习近平本人的原话引用，请不要提取。
    5. 完整性：如果一句话中有多个由逗号分隔的独立引号引用（如：“句话A”，“句话B”），请将它们作为独立的元素提取或合并为一个连贯的句子。

    # 输出格式（严格的 JSON 格式，不要输出其他多余的解释文字）
    {
      "status": "success",
      "data": {
        "person": "习近平",
        "quotes": [
          {
            "content": "提取出的第一句讲话内容原文",
            "context": "该讲话所在的简短背景或前缀（如：在谈到中央全面依法治国委员会的职责定位时强调）"
          }
        ]
      }
    }
    如果未发现符合条件的讲话，请返回：
    {
      "status": "empty",
      "message": "未提取到相关言论"
    }
    '''

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"【文本内容】\n{text}"}
        ],
        "temperature": 0.1,  # 降低温度以保证输出格式的稳定性
        "stream": False
    }

    try:
        print(f"正在调用 LLM ({model}) 进行分析...")
        response = requests.post(ollama_url, json=payload, timeout=120)
        response.raise_for_status()
        
        result_json = response.json()
        content = result_json.get("message", {}).get("content", "")
        
        # 尝试解析返回的 JSON 内容
        # 有时 LLM 会用 ```json 包裹返回内容
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
            
        parsed_data = json.loads(content.strip())
        return parsed_data
        
    except requests.exceptions.RequestException as e:
        print(f"API 请求失败: {e}")
        return {"status": "error", "message": str(e)}
    except json.JSONDecodeError as e:
        print(f"解析 LLM 返回的 JSON 失败: {e}")
        print(f"LLM 原始返回内容:\n{content}")
        return {"status": "error", "message": "解析 JSON 失败"}


# ==========================================================
# 测试与调用示例
# ==========================================================
if __name__ == "__main__":
    # 示例文本（包含习近平的讲话，带有引用角标）
    sample_text = """
    党的领导发挥着战略规划、顶层设计的作用。习近平总书记在谈到中央全面依法治国委员会的职责定位时强调，要“把主要精力放在顶层设计上”“做好全面依法治国重大问题的运筹谋划、科学决策”③。
    党的十八大以来，党中央加强对全面依法治国的战略谋划。另外，张三指出：“这是一句无关的话。”
    """

    print("=" * 60)
    print("测试文本内容:")
    print(sample_text.strip())
    print("=" * 60)

    # 1. 测试方案1（规则提取）
    print("\n【方案1：基于规则（正则表达式）的提取结果】")
    rule_results = extract_quotes_by_rule(sample_text)
    print(json.dumps(rule_results, ensure_ascii=False, indent=4))

    # 2. 测试方案2（LLM提取）
    # 注意：运行此部分需要您的 Ollama 服务正在运行且可以访问
    print("\n【方案2：基于 LLM (Ollama API) 的提取结果】")
    # 使用代码中配置的 pub_ollama_url_list 中的一个地址
    ollama_api_url = "http://192.168.0.19:11435/api/chat"
    llm_model_name = "qwen2.5:7b" 
    
    llm_results = extract_quotes_by_llm(sample_text, ollama_url=ollama_api_url, model=llm_model_name)
    print(json.dumps(llm_results, ensure_ascii=False, indent=4))

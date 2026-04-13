import os
import json
import requests
import time
from datetime import datetime

# ==================== 配置 ====================
BASE_DIR = r"c:\gzb_file_to_github\P2_Pdf_To_Markdown\lingdaoren\eval_results"
INPUT_FILE = r"c:\gzb_file_to_github\P2_Pdf_To_Markdown\lingdaoren\extracted_quotes.md"
REPORT_FILE = os.path.join(BASE_DIR, "report.html")

# Ollama 配置
OLLAMA_URL = "http://192.168.0.19:11435/api/chat"
# OLLAMA_MODELS = ["qwen2.5:7b", "deepseek-r1:32b", "deepseek-r1:7b"] # 替换为您本地有的模型
OLLAMA_MODELS = ["qwen2.5:7b"] # 为了测试快速运行，可以先配置一个

SYSTEM_PROMPT = '''
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

# 输出格式规范（严格遵守以下 JSON 格式，不要输出其他多余的解释文字）

1. 当内容中包含领导人言论时：
```json
{
  "message": "发现人物言论信息",
  "status": "success",
  "data": {
    "people": [
      {
        "name": "识别到的人名",
        "position": "自动推断的职位/身份（如可推断）",
        "quotes": [
          {
            "text": "直接引用的原文",
            "type": "direct/indirect",
            "context": "前后文摘要（50字内）"
          }
        ]
      }
    ],
    "summary": {
      "total_people": 总数,
      "total_quotes": 总引用数
    }
  }
}
```

2. 当内容中不包含领导人言论时：
```json
{
  "message": "没有发现人物言论信息",
  "status": "empty"
}
```
'''

def parse_llm_json(content):
    content = content.strip()
    if content.startswith("```json"):
        content = content[7:]
    if content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    try:
        return json.loads(content.strip())
    except json.JSONDecodeError:
        return None

def call_ollama(model, text):
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"【文本内容】\n{text}"}
        ],
        "temperature": 0.1,
        "stream": False
    }
    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=120)
        response.raise_for_status()
        result_json = response.json()
        content = result_json.get("message", {}).get("content", "")
        return parse_llm_json(content), content
    except Exception as e:
        print(f"Error calling {model}: {e}")
        return None, str(e)

def extract_quotes_by_rule(text):
    """
    作为基准的规则提取方法，提取准确性很高
    """
    import re
    quotes_list = []
    sentences = re.split(r'([。！？])', text)
    sentences = ["".join(i) for i in zip(sentences[0::2], sentences[1::2] + [""])]
    quote_pattern = re.compile(r'["“]([^"”]+)["”]')
    
    for sentence in sentences:
        if "习近平" in sentence:
            xi_context = sentence[sentence.find("习近平"):]
            verbs = ["指出", "强调", "要求", "提出", "明确", "认为", "深刻指出", "强调指出", "指出："]
            if any(verb in xi_context[:50] for verb in verbs):
                quotes = quote_pattern.findall(xi_context)
                if quotes:
                    valid_quotes = [q for q in quotes if len(q) > 2]
                    for q in valid_quotes:
                        context = sentence[:50] + "..." if len(sentence) > 50 else sentence
                        quotes_list.append({
                            "text": q,
                            "type": "direct",
                            "context": context
                        })
                        
    if not quotes_list:
        return {"message": "没有发现人物言论信息", "status": "empty"}
        
    return {
        "message": "发现人物言论信息",
        "status": "success",
        "data": {
            "people": [{"name": "习近平", "position": "中共中央总书记、国家主席、中央军委主席", "quotes": quotes_list}],
            "summary": {"total_people": 1, "total_quotes": len(quotes_list)}
        }
    }

def process_models():
    if not os.path.exists(INPUT_FILE):
        print(f"Input file not found: {INPUT_FILE}")
        return

    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        lines = [line.strip() for line in f if line.strip()]
        
    # 为了测试速度，可以只取前 5 条测试，实际运行可去掉 [:5]
    lines = lines[:5] 
    
    # 1. 先用基准规则生成标准答案
    baseline_dir = os.path.join(BASE_DIR, "baseline_rule")
    os.makedirs(baseline_dir, exist_ok=True)
    print("\n--- 正在生成 Baseline 基准数据 ---")
    for idx, line in enumerate(lines, start=1):
        out_file = os.path.join(baseline_dir, f"{idx:03d}.json")
        if os.path.exists(out_file):
            continue
        baseline_result = extract_quotes_by_rule(line)
        with open(out_file, 'w', encoding='utf-8') as out_f:
            json.dump({
                "id": idx,
                "model": "baseline_rule",
                "parsed_json": baseline_result
            }, out_f, ensure_ascii=False, indent=4)

    # 2. 遍历大模型进行处理
    for model in OLLAMA_MODELS:
        model_dir = os.path.join(BASE_DIR, model.replace(":", "_"))
        os.makedirs(model_dir, exist_ok=True)
        print(f"\n--- 开始处理模型: {model} ---")
        
        for idx, line in enumerate(lines, start=1):
            out_file = os.path.join(model_dir, f"{idx:03d}.json")
            if os.path.exists(out_file):
                print(f"[{model}] 跳过第 {idx} 行 (已存在)")
                continue
                
            print(f"[{model}] 处理第 {idx} 行...")
            parsed_json, raw_content = call_ollama(model, line)
            
            result_data = {
                "id": idx,
                "text_content": line,
                "model": model,
                "timestamp": datetime.now().isoformat(),
                "parsed_json": parsed_json,
                "raw_response": raw_content
            }
            
            with open(out_file, 'w', encoding='utf-8') as out_f:
                json.dump(result_data, out_f, ensure_ascii=False, indent=4)
                
    # 3. 对比分析并生成报告
    generate_report(lines)

def generate_report(lines):
    print("\n--- 正在生成对比报告 ---")
    baseline_dir = os.path.join(BASE_DIR, "baseline_rule")
    
    # 提取出的核心对比逻辑：抽取纯文本比较
    def get_quotes_from_json(parsed_json):
        if not parsed_json or parsed_json.get("status") != "success":
            return []
        quotes = []
        for person in parsed_json.get("data", {}).get("people", []):
            if "习近平" in person.get("name", ""):
                for q in person.get("quotes", []):
                    # 去除可能包含的标点，统一做比较
                    text = q.get("text", "").strip('。！？，、”“"\'')
                    if text:
                        quotes.append(text)
        return quotes

    model_stats = {}
    for model in OLLAMA_MODELS:
        model_stats[model] = {"total": len(lines), "match": 0, "mismatch": 0, "details": []}
        model_dir = os.path.join(BASE_DIR, model.replace(":", "_"))
        
        for idx, line in enumerate(lines, start=1):
            baseline_file = os.path.join(baseline_dir, f"{idx:03d}.json")
            model_file = os.path.join(model_dir, f"{idx:03d}.json")
            
            if not os.path.exists(baseline_file) or not os.path.exists(model_file):
                continue
                
            with open(baseline_file, 'r', encoding='utf-8') as f:
                base_data = json.load(f)
            with open(model_file, 'r', encoding='utf-8') as f:
                model_data = json.load(f)
                
            base_quotes = get_quotes_from_json(base_data.get("parsed_json"))
            model_quotes = get_quotes_from_json(model_data.get("parsed_json"))
            
            # 判断是否匹配 (简单判断提取的条数和内容是否大致一致)
            # 为了容错，只要大模型提取出的某句话被包含在基准中，就认为该句正确
            matched = True
            if len(base_quotes) != len(model_quotes):
                matched = False
            else:
                for b_q, m_q in zip(base_quotes, model_quotes):
                    # 允许有微小的文字差异
                    if m_q not in b_q and b_q not in m_q:
                        matched = False
                        break
            
            if matched:
                model_stats[model]["match"] += 1
            else:
                model_stats[model]["mismatch"] += 1
                
            model_stats[model]["details"].append({
                "id": idx,
                "matched": matched,
                "base_quotes": base_quotes,
                "model_quotes": model_quotes
            })

    # 生成 HTML
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>LLM 模型提取能力对比报告</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; line-height: 1.6; }}
            h1, h2 {{ color: #333; }}
            table {{ border-collapse: collapse; width: 100%; margin-bottom: 30px; }}
            th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
            th {{ background-color: #f2f2f2; }}
            .match {{ color: green; font-weight: bold; }}
            .mismatch {{ color: red; font-weight: bold; }}
            .detail-box {{ background: #f9f9f9; padding: 15px; margin-bottom: 15px; border-radius: 5px; border-left: 5px solid #ccc; }}
        </style>
    </head>
    <body>
        <h1>LLM 模型提取能力对比报告</h1>
        <p>生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        <p>测试样本总数: {len(lines)}</p>
        
        <h2>统计摘要</h2>
        <table>
            <tr>
                <th>模型名称</th>
                <th>一致匹配数</th>
                <th>不一致数</th>
                <th>一致率 (%)</th>
            </tr>
    """
    
    for model, stats in model_stats.items():
        total = stats["total"]
        match = stats["match"]
        mismatch = stats["mismatch"]
        rate = (match / total * 100) if total > 0 else 0
        html_content += f"""
            <tr>
                <td>{model}</td>
                <td>{match}</td>
                <td>{mismatch}</td>
                <td>{rate:.2f}%</td>
            </tr>
        """
        
    html_content += """
        </table>
        <h2>不一致详情对比</h2>
    """
    
    for model, stats in model_stats.items():
        html_content += f"<h3>模型: {model}</h3>"
        has_mismatch = False
        for detail in stats["details"]:
            if not detail["matched"]:
                has_mismatch = True
                html_content += f"""
                <div class="detail-box" style="border-left-color: red;">
                    <p><strong>样本 ID: {detail['id']}</strong></p>
                    <p><strong>基准提取 (Baseline):</strong> {detail['base_quotes']}</p>
                    <p><strong>模型提取 ({model}):</strong> {detail['model_quotes']}</p>
                </div>
                """
        if not has_mismatch:
            html_content += "<p>完全一致，无差异项。</p>"

    html_content += """
    </body>
    </html>
    """
    
    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        f.write(html_content)
        
    print(f"对比报告已生成: {REPORT_FILE}")

if __name__ == "__main__":
    process_models()

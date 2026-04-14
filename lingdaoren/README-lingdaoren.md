# 领导人讲话信息提取工具 (Quote Extractor)

本工具采用 **“规则召回 + LLM判别/补全”** 的混合架构，旨在从复杂的中文文献中精准提取特定人物（如“习近平”）的讲话原话。

## 方案优势
- **高召回率（规则层）**：不仅提取带有双引号的明确引语，还能提取冒号后面的大段无引号引语，甚至能识别紧跟在引导词（强调、指出、提出等）后的无引号原话。利用逆向查找机制，确保准确绑定离句子最近的说话人与提示词。
- **高准确率（LLM判别层）**：支持本地部署的大模型（如 Ollama 的 Qwen 系列）或云端商业模型（如阿里百炼 API），对规则召回的候选集进行“是否确为人物原话”的二分类判定。模型会提供证据支持，剔除作者转述、政策解读等非原话内容。
- **灵活的接口支持**：支持通过参数轻松切换底层大模型服务提供商（Ollama 或 阿里百炼 Bailian）。
- **严格结构化**：输出严格符合预定规范的 JSON 格式，包含讲话内容、上下文、数量统计等。

## 环境要求
1. **Python**: 3.7+ (仅使用标准库 `re`, `json`, `urllib` 等，无需第三方依赖)
2. **大模型服务**: 
   - **本地服务**: 需运行 Ollama 服务及相关模型（如 `qwen2.5:32b`）
   - **云端服务**: 需提供阿里百炼 (Bailian) API Key 及对应模型名（如 `qwen-plus`）

## 核心工作逻辑
1. **规则召回 (`extract_candidates`)**：
   - 扫描文本中带有双引号的引语。
   - 扫描冒号后面无引号的长句子。
   - 扫描紧跟在提示词（如“强调”、“提出”）后面的无引号句子。
   - 提取候选片段及上下文，利用正则精确定位离句子最近的“说话人”和“提示词”。
2. **LLM 判别清洗 (`filter_with_llm`)**：
   - 构造结构化 Prompt，将提取的候选 JSON 列表交给大模型。
   - 大模型依据严格的判定标准（必须是指向目标人物的原话，并清洗引用标记如①、[1]），对候选集打标 `keep=true/false`。
   - 如果大模型输出不合规，支持自动进行一次重试修复（Retry）。
3. **结构化输出 (`extract_xjp_quotes`)**：
   - 组装提取成功的原话，构建包含人物信息、言论列表、数量统计的标准 JSON。

## 快速使用

### 1. 使用阿里百炼 API (推荐)
通过 `api_provider="bailian"` 调用云端接口，速度和准确度更佳：

```python
import json
from extract_quotes import extract_xjp_quotes

text = """习近平总书记强调：要坚持人民至上、生命至上。文章作者认为这很重要。习近平总书记提出坚持党的领导是社会主义法治的根本要求，是全面依法治国题中应有之义。习近平总书记指出："中国共产党为什么能，中国特色社会主义为什么好，归根到底是马克思主义行，是中国化时代化的马克思主义行。"①"""

# 使用阿里百炼大模型接口进行提取
result = extract_xjp_quotes(
    text=text,
    use_llm=True,
    model="qwen-plus",
    api_provider="bailian",
    api_key="your_bailian_api_key_here"  # 替换为您的百炼 API Key
)

print(json.dumps(result, ensure_ascii=False, indent=2))
```

### 2. 使用本地 Ollama
确保本地 Ollama 服务已启动，且已下载所需模型（例如 `ollama run qwen2.5:32b`）：

```python
import json
from extract_quotes import extract_xjp_quotes

text = "习近平总书记强调：要坚持人民至上、生命至上。"

result = extract_xjp_quotes(
    text=text, 
    use_llm=True, 
    model="qwen2.5:32b", 
    base_url="http://localhost:11434",
    api_provider="ollama"
)

print(json.dumps(result, ensure_ascii=False, indent=2))
```

### 3. 输出格式示例
```json
{
  "message": "发现人物言论信息",
  "status": "success",
  "data": {
    "people": [
      {
        "name": "习近平",
        "position": "",
        "quotes": [
          {
            "text": "要坚持人民至上、生命至上",
            "type": "direct",
            "context": "习近平总书记强调：要坚持人民至上、生命至上。文章作者认为这很重要。"
          }
        ]
      }
    ],
    "summary": {
      "total_people": 1,
      "total_quotes": 1
    }
  }
}
```

## 自定义修改建议
1. **修改引导词**：如果发现有遗漏的提示动词，可以在 `extract_quotes.py` 的 `CUE_VERBS` 列表中添加（如“指出”、“强调”、“明确”等）。
2. **更换目标人物**：通过修改 `SPEAKER_PAT` 的正则表达式，可以切换或扩展要提取的人物范围。
3. **Prompt 微调**：在 `filter_with_llm` 函数中，可以针对具体的误判情况，对传递给大模型的判定标准（`user` 变量）进行微调。

# 领导人讲话信息提取工具 (Quote Extractor)

本工具采用 **“规则召回 + LLM判别/补全”** 的混合架构，旨在从复杂的中文文献中精准提取特定人物（如“习近平”）的讲话原话。

## 方案优势
- **高召回率（规则层）**：不仅提取带有双引号的明确引语，还能提取冒号后面的大段无引号引语，甚至能识别紧跟在引导词后的无引号原话。
- **高准确率（LLM判别层）**：利用本地部署的大模型（如 Qwen2.5），对规则召回的候选集进行“是否确为人物原话”的二分类判定。模型会提供证据支持，剔除作者转述、政策解读等非原话内容。
- **严格结构化**：输出严格符合预定规范的 JSON 格式，包含讲话内容、上下文、数量统计等。

## 环境要求
1. **Python**: 3.7+ 
2. **Ollama**: 本地需运行 Ollama 服务。
3. **模型支持**: 建议拉取并运行如 `qwen2.5:32b`, `qwen3.5:35b` 等模型（需要能够较好理解中文并严格输出 JSON 的模型）。

## 核心文件
- `extract_quotes.py`: 提取工具的源码。内置了规则正则匹配模块和 Ollama HTTP 接口请求模块。无需安装额外的第三方依赖包（仅使用标准库 `re`, `json`, `urllib` 等）。

## 快速使用

### 1. 确保 Ollama 正在运行
请确保本地 Ollama 服务已启动，且已下载所需模型：
```bash
ollama run qwen2.5:32b
```
默认情况下，Ollama 服务在 `http://localhost:11434` 运行。

### 2. 在代码中调用
您可以直接引入并调用 `extract_xjp_quotes` 函数：

```python
import json
from extract_quotes import extract_xjp_quotes

text = """
近日，会议在北京召开。习近平总书记强调：要坚持人民至上、生命至上。
与会代表表示，我们要把这些重要指示落实到实际工作中。
"""

# 使用 LLM 进行精确判别提取
result = extract_xjp_quotes(
    text=text, 
    use_llm=True, 
    model="qwen2.5:32b", 
    ollama_base_url="http://localhost:11434"
)

# 打印结果
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
            "text": "要坚持人民至上、生命至上。",
            "type": "direct",
            "context": "近日，会议在北京召开。习近平总书记强调：要坚持人民至上、生命至上。\n与会代表表示，我们要把这些重要"
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

## 模块说明
- **`extract_candidates(text: str)`**: 规则召回函数。使用多组正则表达式（带引号、冒号后、逗号/无标点后）尽最大可能抓取可能包含讲话的文本片段。
- **`filter_with_ollama(text, candidates, model, ollama_base_url)`**: LLM 过滤函数。构造包含原文和候选列表的 Prompt，请求 Ollama 进行判定和清洗。
- **`extract_xjp_quotes(text, use_llm, model, ollama_base_url)`**: 对外暴露的主入口。将上述两步结合，整理并返回最终所需的规范 JSON 结构。

## 自定义修改建议
1. **修改引导词**：如果发现有遗漏的提示动词，可以在 `extract_quotes.py` 的 `CUE_VERBS` 列表中添加（如“指出”、“强调”、“明确”等）。
2. **更换目标人物**：通过修改 `SPEAKER_PAT` 的正则表达式，可以切换或扩展要提取的人物范围。
3. **更换模型**：如果 `qwen2.5:32b` 效果不佳或资源受限，可切换至 `gpt-oss:120b` 或其他可用模型，只需要修改 `model` 参数即可。

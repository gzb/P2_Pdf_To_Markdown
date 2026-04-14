from extract_quotes import extract_candidates, filter_with_llm

text = """习近平总书记强调：要坚持人民至上、生命至上。文章作者认为这很重要。习近平总书记提出坚持党的领导是社会主义法治的根本要求，是全面依法治国题中应有之义。习近平总书记指出："中国共产党为什么能，中国特色社会主义为什么好，归根到底是马克思主义行，是中国化时代化的马克思主义行。"①"""

cands = extract_candidates(text)
print("--- Candidates ---")
for c in cands:
    print(c)

print("\n--- LLM Filtered ---")
kept = filter_with_llm(
    text, cands,
    model="qwen-plus", 
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
    api_provider="bailian", 
    api_key="sk-d547b1e274774d33a530c124b0f49f92"
)
for k in kept:
    print(k)

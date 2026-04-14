import re
import json
import urllib.request
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Tuple


CUE_VERBS = [
    "指出", "强调", "明确", "表示", "提出", "认为", "说", "称", "谈到", "写道",
    "要求", "号召", "重申", "阐明", "部署", "提出要求", "作出指示", "作出重要指示",
    "作出重要论述", "作出重要讲话", "发表重要讲话", "在.*?讲话", "在.*?强调"
]

SPEAKER_PAT = r"(习近平(?:总书记|主席|同志)?)"

QUOTE_MARKS = [
    ("“", "”"),
    ("\"", "\""),
    ("「", "」"),
    ("『", "』"),
]


def _strip_trailing_refs(s: str) -> str:
    s = s.strip()
    s = re.sub(r"[\u2460-\u2473①②③④⑤⑥⑦⑧⑨⑩]+$", "", s).strip()
    s = re.sub(r"(\[\d+\]|（\d+）|\(\d+\))+$", "", s).strip()
    s = re.sub(r"[，,;；:：]+$", "", s).strip()
    return s


def _window(text: str, start: int, end: int, w: int = 80) -> str:
    a = max(0, start - w)
    b = min(len(text), end + w)
    return text[a:b]


@dataclass
class Candidate:
    id: str
    text: str
    start: int
    end: int
    cue: str
    speaker: str
    context: str
    source: str


def _find_quoted_spans(text: str) -> List[Tuple[int, int]]:
    spans = []
    for lq, rq in QUOTE_MARKS:
        pattern = re.escape(lq) + r"([^" + re.escape(rq) + r"]{2,2000})" + re.escape(rq)
        for m in re.finditer(pattern, text):
            spans.append((m.start(1), m.end(1)))
    spans.sort()
    return spans


def extract_candidates(text: str) -> List[Candidate]:
    candidates: List[Candidate] = []
    quoted_spans = _find_quoted_spans(text)
    cue_pat = "|".join(map(re.escape, sorted(CUE_VERBS, key=len, reverse=True)))

    # 1. 带引号的明确引语
    for i, (qs, qe) in enumerate(quoted_spans):
        left_ctx = text[max(0, qs - 120):qs]
        m_speaker = re.search(SPEAKER_PAT, left_ctx)
        m_cue = re.search(r"(" + cue_pat + r")", left_ctx)
        if not (m_speaker and m_cue):
            continue

        quote_text = _strip_trailing_refs(text[qs:qe])
        if not quote_text:
            continue

        start = qs
        end = qs + len(quote_text)
        candidates.append(Candidate(
            id=f"Q{i}",
            text=quote_text,
            start=start,
            end=end,
            cue=m_cue.group(1),
            speaker=m_speaker.group(1),
            context=_window(text, start, end, 80),
            source="quoted"
        ))

    # 2. 冒号后面的大段引语（无引号）
    pat_colon = re.compile(
        SPEAKER_PAT
        + r".{0,40}?"
        + r"(" + cue_pat + r")"
        + r".{0,20}?[：:]"
        + r"([^。！？；\n]{6,500})"
    )

    idx = 0
    for m in pat_colon.finditer(text):
        speaker = m.group(1)
        cue = m.group(2)
        seg = _strip_trailing_refs(m.group(3))
        if not seg:
            continue
        s = m.start(3)
        e = s + len(seg)
        candidates.append(Candidate(
            id=f"C{idx}",
            text=seg,
            start=s,
            end=e,
            cue=cue,
            speaker=speaker,
            context=_window(text, s, e, 80),
            source="colon"
        ))
        idx += 1

    # 3. 逗号后或直接连着的无引号引语（明显原话）
    pat_noquote = re.compile(
        SPEAKER_PAT
        + r".{0,40}?"
        + r"(" + cue_pat + r")"
        + r"[，, ]*"
        + r"([^。！？；\n]{6,260})"
    )

    jdx = 0
    for m in pat_noquote.finditer(text):
        speaker = m.group(1)
        cue = m.group(2)
        seg = _strip_trailing_refs(m.group(3))
        if not seg:
            continue
        s = m.start(3)
        e = s + len(seg)
        candidates.append(Candidate(
            id=f"N{jdx}",
            text=seg,
            start=s,
            end=e,
            cue=cue,
            speaker=speaker,
            context=_window(text, s, e, 80),
            source="noquote"
        ))
        jdx += 1

    # 去重
    uniq: Dict[Tuple[int, int, str], Candidate] = {}
    for c in candidates:
        key = (c.start, c.end, c.text)
        uniq[key] = c
    merged = list(uniq.values())
    merged.sort(key=lambda x: (x.start, x.end))
    return merged


def _extract_json_object(s: str) -> Dict[str, Any]:
    i = s.find("{")
    j = s.rfind("}")
    if i == -1 or j == -1 or j <= i:
        raise ValueError("no_json_object")
    return json.loads(s[i:j + 1])


def _ollama_chat(url: str, model: str, messages: List[Dict[str, str]], temperature: float = 0.0) -> str:
    payload = {
        "model": model,
        "stream": False,
        "messages": messages,
        "options": {"temperature": temperature}
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url.rstrip("/") + "/api/chat", data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        raw = resp.read().decode("utf-8")
    obj = json.loads(raw)
    return (obj.get("message") or {}).get("content") or ""


def filter_with_ollama(text: str, candidates: List[Candidate], model: str = "qwen2.5:32b", ollama_base_url: str = "http://localhost:11434") -> List[Dict[str, Any]]:
    cand_json = [
        {
            "id": c.id,
            "quote_text": c.text,
            "cue": c.cue,
            "speaker": c.speaker,
            "context": c.context,
            "source": c.source
        }
        for c in candidates
    ]

    system = (
        "你是中文文本证据驱动的信息抽取器。你只能基于输入原文与候选上下文判断。"
        "输出必须是严格JSON且只输出JSON。"
    )

    user = (
        "任务：判断候选片段是否为“习近平”的直接讲话原文或明显原话（可无引号），并返回严格JSON。\n"
        "判定标准（必须同时满足才keep=true）：\n"
        "1) 说话人能由原文证据指向“习近平”（含同指：习近平总书记/习近平主席）。\n"
        "2) 片段是其原话/直接引语，或无引号但明显是他说的原话句子；若只是作者概述、政策解读、他人转述且无法证明为原话，则keep=false。\n"
        "3) 若是别人的话、会议文件条款、记者提问、网民评论等，keep=false。\n"
        "4) 清洗：去掉末尾①②③、[1]、（1）等引用标记；保留语义完整。\n\n"
        f"【原文】\n{text}\n\n"
        f"【候选列表(JSON)】\n{json.dumps(cand_json, ensure_ascii=False)}\n\n"
        "输出JSON格式如下（只允许这些字段）：\n"
        "{\n"
        '  "items": [\n'
        "    {\n"
        '      "id": "候选id",\n'
        '      "keep": true,\n'
        '      "type": "direct",\n'
        '      "text": "清洗后的引语",\n'
        '      "evidence": "用于判定的原文证据(<=60字)"\n'
        "    }\n"
        "  ]\n"
        "}\n"
    )

    content = _ollama_chat(ollama_base_url, model, [{"role": "system", "content": system}, {"role": "user", "content": user}], temperature=0.0)

    try:
        out = _extract_json_object(content)
    except Exception:
        # Retry once if the output wasn't strict JSON
        fix_user = (
            "你上一次输出不是严格JSON。请只输出严格JSON对象，字段仅允许 items[id,keep,type,text,evidence]。不要输出任何解释。"
        )
        content2 = _ollama_chat(ollama_base_url, model, [{"role": "system", "content": system}, {"role": "user", "content": user}, {"role": "assistant", "content": content}, {"role": "user", "content": fix_user}], temperature=0.0)
        out = _extract_json_object(content2)

    items = out.get("items") or []
    keep_map = {it.get("id"): it for it in items if isinstance(it, dict) and it.get("id")}
    results = []
    for c in candidates:
        it = keep_map.get(c.id)
        if not it:
            continue
        keep = bool(it.get("keep"))
        if not keep:
            continue
        qtext = _strip_trailing_refs(str(it.get("text") or ""))
        if not qtext:
            continue
        results.append({
            "id": c.id,
            "text": qtext,
            "type": it.get("type") or "direct",
            "context": c.context
        })
    return results


def extract_xjp_quotes(text: str, use_llm: bool = True, model: str = "qwen2.5:32b", ollama_base_url: str = "http://localhost:11434") -> Dict[str, Any]:
    candidates = extract_candidates(text)

    if not use_llm:
        quotes = [{"text": c.text, "type": "direct", "context": c.context} for c in candidates]
    else:
        kept = filter_with_ollama(text, candidates, model=model, ollama_base_url=ollama_base_url)
        quotes = [{"text": k["text"], "type": k["type"], "context": k["context"]} for k in kept]

    if quotes:
        return {
            "message": "发现人物言论信息",
            "status": "success",
            "data": {
                "people": [
                    {
                        "name": "习近平",
                        "position": "",
                        "quotes": quotes
                    }
                ],
                "summary": {
                    "total_people": 1,
                    "total_quotes": len(quotes)
                }
            }
        }

    return {"message": "没有发现人物言论信息", "status": "empty"}


if __name__ == "__main__":
    # 测试样例
    sample = "习近平总书记强调：要坚持人民至上、生命至上。文章作者认为这很重要。"
    print(json.dumps(extract_xjp_quotes(sample, use_llm=True, model="qwen2.5:32b"), ensure_ascii=False, indent=2))

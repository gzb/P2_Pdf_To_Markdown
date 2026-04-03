import json
import re

def merge_text(deepseek_ocr_text: str, box_text: str) -> str:
    """这里放你的 merge_text 函数，为了独立运行暂时用简单实现或原实现"""
    # 模拟保留 OCR 格式和 box_text 正确字的逻辑
    return box_text if box_text else deepseek_ocr_text

def load_ocr_file_ds_to_py(json_data, filename):
    """
    修改版本：
    1. 解析 raw_text 中的标签和文本
    2. 进行坐标转换
    3. 找到 boxes 中对应的块，修改其 text_content
    4. 返回原始的 json_data 结构，而不是重新组装 nodes
    """
    raw_text = json_data.get("raw_text", "")
    if not raw_text:
        return json_data

    # 使用 "<|ref|>" 作为分割符号拆分 raw_text
    parts = raw_text.split('<|ref|>')

    boxes = json_data.get("boxes", [])

    image_dims = json_data.get("image_dims", {"w": 1191, "h": 1684})
    scale_ratio_w = image_dims.get("w", 1191)
    scale_ratio_h = image_dims.get("h", 1684)

    # 解析各个部分
    for part in parts[1:]:
        ref_part = re.match(r"(.*?)(<\|det\|>\[\[(.*?)\]\]<\|/det\|>)(.*)", part, re.DOTALL)
        
        if ref_part:
            # ref_text = ref_part.group(1).strip() if ref_part.group(1) else ""
            # ref_text = ref_text.replace("<|/ref|>", "")
            det_data = ref_part.group(3).strip() if ref_part.group(3) else ""
            deepseek_ocr_text = ref_part.group(4).strip() if ref_part.group(4) else ""

            if not det_data:
                continue
            
            try:
                box = list(map(int, det_data.split(',')))
                # 将 999 比例的坐标缩放到实际宽高
                box[0] = int(float(box[0]) / 999 * scale_ratio_w)
                box[1] = int(float(box[1]) / 999 * scale_ratio_h)
                box[2] = int(float(box[2]) / 999 * scale_ratio_w)
                box[3] = int(float(box[3]) / 999 * scale_ratio_h)
            except ValueError:
                continue

            # 查找并修改对应的 text_content
            for box_entry in boxes:
                # 坐标比对：需要有一定的容错，或者严格等于（旧代码是严格等于）
                # 注意：经过 int 和 float 转换后，有可能会有一两个像素的误差
                # 这里先按原代码逻辑严格匹配，如果匹配不上可能需要引入容差
                if box_entry.get('box') == box:
                    box_text = box_entry.get('text_content', '')
                    box_label = box_entry.get('label', 'text')
                    
                    if box_text == '':
                        box_text = deepseek_ocr_text
                    else:
                        if box_label == 'title':
                            box_text = "\r\n#" + box_text
                        elif box_label == 'sub_title':
                            box_text = "\r\n##" + box_text
                        elif box_label == 'image':
                            box_text = "\r\n"
                            
                    # 特殊空格替换
                    box_text = box_text.replace(' ', ' ').replace('', ' ').replace('', ' ')
                    
                    # 融合文本（调用你原本的 merge_text，这里独立文件用了 mock）
                    box_text = merge_text(deepseek_ocr_text, box_text)

                    # 保留 table 原始格式
                    if deepseek_ocr_text and "<table><tr><td>" in deepseek_ocr_text:
                        box_text = deepseek_ocr_text

                    # 仅优化 text_content 节点
                    box_entry['text_content'] = box_text
                    # 找到一个匹配的就结束内层循环
                    break

    # 直接返回修改后的原 json_data 结构
    return json_data

# 测试代码
if __name__ == "__main__":
    # 使用你给出的示例数据进行测试
    sample_json = {
        "success": True,
        "text": "队伍政治素质、业务素质...", # 省略长文本
        "raw_text": "<|ref|>text<|/ref|><|det|>[[152, 149, 825, 510]]<|/det|>\n队伍政治素质...",
        "boxes": [
            {
                "label": "text",
                "box": [169, 225, 918, 770],
                "text_content": "队伍政治素质..."
            }
        ],
        "image_dims": {"w": 1112, "h": 1509},
        "prompt_type": "document",
        "metadata": {
            "mode": "document",
            "grounding": True,
            "has_boxes": True,
            "engine": "transformers"
        }
    }
    
    # 因为示例数据的 box 和 raw_text 缩放后坐标可能有微小差异，这里只是演示函数结构
    result = load_ocr_file_ds_to_py(sample_json, "test.json")
    print(json.dumps(result, indent=4, ensure_ascii=False))

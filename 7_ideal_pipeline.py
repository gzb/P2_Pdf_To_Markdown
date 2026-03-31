import os
import json
import difflib

# ==========================================
# 核心工具函数
# ==========================================

def merge_text(deepseek_ocr_text: str, box_text: str) -> str:
    """结合 OCR 的完美排版与 PyMuPDF 的正确文字"""
    ds_seq = []
    ds_pos_map = []
    for i, char in enumerate(deepseek_ocr_text):
        if not char.isspace():
            ds_seq.append(char)
            ds_pos_map.append(i)
            
    box_seq = [char for char in box_text if not char.isspace()]
    sm = difflib.SequenceMatcher(None, ds_seq, box_seq)
    
    result = []
    last_ds_idx = 0
    
    def catch_up_spaces(target_idx):
        nonlocal last_ds_idx
        while last_ds_idx < target_idx:
            if deepseek_ocr_text[last_ds_idx].isspace():
                result.append(deepseek_ocr_text[last_ds_idx])
            last_ds_idx += 1

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            for k in range(i2 - i1):
                ds_idx = ds_pos_map[i1 + k]
                catch_up_spaces(ds_idx)
                result.append(box_seq[j1 + k])
                last_ds_idx = ds_idx + 1
        elif tag == 'replace':
            if i1 < i2: catch_up_spaces(ds_pos_map[i1])
            box_idx = j1
            if i1 < i2:
                ds_idx_start = ds_pos_map[i1]
                ds_idx_end = ds_pos_map[i2 - 1] + 1
                for idx in range(ds_idx_start, ds_idx_end):
                    if deepseek_ocr_text[idx].isspace():
                        result.append(deepseek_ocr_text[idx])
                    else:
                        if box_idx < j2:
                            result.append(box_seq[box_idx])
                            box_idx += 1
                last_ds_idx = ds_idx_end
            while box_idx < j2:
                result.append(box_seq[box_idx])
                box_idx += 1
        elif tag == 'delete':
            if i1 < i2:
                ds_idx_start = ds_pos_map[i1]
                ds_idx_end = ds_pos_map[i2 - 1] + 1
                catch_up_spaces(ds_idx_start)
                for idx in range(ds_idx_start, ds_idx_end):
                    if deepseek_ocr_text[idx].isspace():
                        result.append(deepseek_ocr_text[idx])
                last_ds_idx = ds_idx_end
        elif tag == 'insert':
            if i1 < len(ds_pos_map): catch_up_spaces(ds_pos_map[i1])
            else: catch_up_spaces(len(deepseek_ocr_text))
            for k in range(j2 - j1):
                result.append(box_seq[j1 + k])

    catch_up_spaces(len(deepseek_ocr_text))
    return "".join(result)

def is_contained_or_overlap(py_box, target_box):
    """判断 PyMuPDF 的块是否在目标框内（中心点算法）"""
    center_x = (py_box[0] + py_box[2]) / 2
    center_y = (py_box[1] + py_box[3]) / 2
    return (target_box[0] <= center_x <= target_box[2]) and (target_box[1] <= center_y <= target_box[3])

def is_terminal_punctuation(char):
    return char in set('。！？!?…:：；;')

def get_effective_last_char(text):
    text = text.strip()
    if not text: return ''
    last_char = text[-1]
    if len(text) > 1 and last_char in '”’"\'》>】]':
        last_char = text[-2]
    return last_char

# ==========================================
# 步骤 4：合并 OCR 布局与 PyMuPDF 文本
# ==========================================
def step4_merge_ocr_and_py_json(ocr_data, py_data):
    """
    将 py_data 中的准确文字填入 ocr_data 的完美排版中。
    """
    ds_w = ocr_data.get("image_dims", {}).get("w", 1024)
    ds_h = ocr_data.get("image_dims", {}).get("h", 1024)
    py_w = py_data.get("width", 1)
    py_h = py_data.get("height", 1)
    scale_x, scale_y = ds_w / py_w, ds_h / py_h
    
    py_blocks = py_data.get("blocks", [])
    for p in py_blocks:
        b = p["bbox"]
        p["ds_bbox"] = [b[0]*scale_x, b[1]*scale_y, b[2]*scale_x, b[3]*scale_y]
        
    for block in ocr_data.get("boxes", []):
        if block.get("label") not in ["text", "sub_title"]:
            continue
        bbox = block.get("box")
        if not bbox: continue
        
        target_box = [bbox[0]-5, bbox[1]-5, bbox[2]+5, bbox[3]+5]
        matches = [p for p in py_blocks if is_contained_or_overlap(p["ds_bbox"], target_box)]
        combined_py_text = "".join([m.get("text", "") for m in matches])
        
        ocr_text = block.get("text_content", "")
        # 融合两者优点
        merged_text = merge_text(ocr_text, combined_py_text)
        block["text_content"] = merged_text
        
    return ocr_data

# ==========================================
# 步骤 5：页内段落合并（彻底避免过度嵌套）
# ==========================================
def step5_inpage_paragraph_merge(page_data, page_num):
    """
    将同页内属于同一个段落的区块合并。
    采用扁平化数组结构设计，彻底避免 [[[x,y]]] 的多层嵌套。
    """
    page_width = page_data.get("image_dims", {}).get("w", 1024)
    page_height = page_data.get("image_dims", {}).get("h", 1024)
    
    merged_nodes = []
    pending_node = None
    separated_by_non_text = False
    
    for block in page_data.get("boxes", []):
        label = block.get("label", "")
        text_content = block.get("text_content", "").strip()
        original_box = block.get("box", [])
        
        if label not in ["text", "sub_title"]:
            # 非文本块直接作为独立节点，初始化扁平结构
            merged_nodes.append({
                "label": label,
                "text_content": text_content,
                "boxs": [original_box] if original_box else [],
                "pages": [str(page_num)],
                "nodes_text_len": [0],
                "image_dims": [page_data.get("image_dims", {})]
            })
            separated_by_non_text = True
            continue
            
        if not text_content: continue
        
        # 将每个文本块初始化为标准扁平结构
        current_node = {
            "label": label,
            "text_content": text_content,
            "boxs": [original_box],
            "pages": [str(page_num)],
            "nodes_text_len": [len(text_content)],
            "image_dims": [page_data.get("image_dims", {})]
        }
            
        if pending_node is None:
            pending_node = current_node
            merged_nodes.append(pending_node)
            separated_by_non_text = False
        else:
            last_char = get_effective_last_char(pending_node["text_content"])
            is_cut_off = last_char and not is_terminal_punctuation(last_char)
            
            cb = pending_node["boxs"][-1]
            nb = current_node["boxs"][0]
            
            is_cross_column = abs(cb[0] - nb[0]) > page_width * 0.05
            is_bottom_of_page = cb[3] > page_height * 0.85
            
            if is_cut_off and (is_cross_column or is_bottom_of_page or separated_by_non_text):
                # 扁平化合并：直接 extend 数组，不产生嵌套
                pending_node["text_content"] += "\n" + current_node["text_content"]
                pending_node["boxs"].extend(current_node["boxs"])
                pending_node["pages"].extend(current_node["pages"])
                pending_node["nodes_text_len"].extend(current_node["nodes_text_len"])
                pending_node["image_dims"].extend(current_node["image_dims"])
                separated_by_non_text = False
            else:
                pending_node = current_node
                merged_nodes.append(pending_node)
                separated_by_non_text = False
                
    return merged_nodes

# ==========================================
# 步骤 6 & 7：跨页合并与坐标格式化（1024基准）
# ==========================================
def step6_crosspage_merge_and_format(all_pages_nodes):
    """
    跨页合并段落，并将最终结果的所有坐标等比例缩放至 1024 基准宽度。
    """
    final_nodes = []
    pending_node = None
    
    for node in all_pages_nodes:
        if node["label"] not in ["text", "sub_title"]:
            final_nodes.append(node)
            continue
            
        if pending_node is None:
            pending_node = node
            final_nodes.append(pending_node)
        else:
            last_char = get_effective_last_char(pending_node["text_content"])
            is_cut_off = last_char and not is_terminal_punctuation(last_char)
            
            if is_cut_off:
                # 跨页合并，依然使用 extend 保持扁平化
                pending_node["text_content"] += "\n" + node["text_content"]
                pending_node["boxs"].extend(node["boxs"])
                pending_node["pages"].extend(node["pages"])
                pending_node["nodes_text_len"].extend(node["nodes_text_len"])
                pending_node["image_dims"].extend(node["image_dims"])
            else:
                pending_node = node
                final_nodes.append(pending_node)
                
    # 格式化阶段：坐标转换与最终结构生成
    formatted_output = []
    for idx, node in enumerate(final_nodes):
        scaled_boxs = []
        for i, box in enumerate(node["boxs"]):
            if len(box) == 4:
                # 读取对应的原始宽高
                dim = node["image_dims"][i]
                scale_x = 1024.0 / dim.get("w", 1024)
                scale_y = 1024.0 / dim.get("h", 1024)
                
                scaled_box = [
                    int(round(box[0] * scale_x)),
                    int(round(box[1] * scale_y)),
                    int(round(box[2] * scale_x)),
                    int(round(box[3] * scale_y))
                ]
                scaled_boxs.append(scaled_box)
            else:
                scaled_boxs.append(box)
                
        formatted_output.append({
            "id": idx + 1,
            "type": node["label"],
            "content": node["text_content"],
            "page": node["pages"][0] if node["pages"] else "1",
            "pages": [node["pages"]],              # 配合原有结构套一层
            "nodes_text_len": [node["nodes_text_len"]], 
            "boxs": [scaled_boxs],                 # 此时 scaled_boxs 已经是干净的 [[x,y,x,y], [x,y,x,y]]
            "image_dims": [[{"w": 1024, "h": 1024} for _ in node["boxs"]]]
        })
        
    return formatted_output

# ==========================================
# 主控制流 (理想代码架构示例)
# ==========================================
def ideal_pdf_to_markdown_pipeline(pdf_file_path, target_dir):
    """
    理想状态下的 PDF 转 Markdown 全流程调度。
    """
    # 1. & 2. & 3. 假设这些基础步骤已经生成了初始 JSON 文件
    # pdf_to_images(...)
    # process_images_to_json(...) -> ocr_json_dir
    # extract_pdf_to_json(...) -> py_json_dir
    
    ocr_json_dir = os.path.join(target_dir, "pdf-2-json")
    py_json_dir = os.path.join(target_dir, "pdf-2-json-python")
    
    all_pages_nodes = []
    
    # 遍历所有页，执行融合与页内合并
    for filename in sorted(os.listdir(ocr_json_dir)): # 假设按页码排序
        if not filename.endswith(".json"): continue
        page_num = filename.replace(".json", "")
        
        # 读取两套 JSON
        with open(os.path.join(ocr_json_dir, filename), 'r', encoding='utf-8') as f:
            ocr_data = json.load(f)
        with open(os.path.join(py_json_dir, filename), 'r', encoding='utf-8') as f:
            py_data = json.load(f)
            
        # 步骤 4：融合 OCR 与 PyMuPDF
        merged_data = step4_merge_ocr_and_py_json(ocr_data, py_data)
        
        # 步骤 5：页内段落合并 (生成无嵌套的扁平节点)
        page_nodes = step5_inpage_paragraph_merge(merged_data, page_num)
        all_pages_nodes.extend(page_nodes)
        
    # 步骤 6 & 7：跨页合并与坐标转换
    final_json_data = step6_crosspage_merge_and_format(all_pages_nodes)
    
    # 保存最终结果
    output_path = os.path.join(target_dir, "processed_merged_nodes_three-py-to-ds-curpage-merged_format-v2.json")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(final_json_data, f, ensure_ascii=False, indent=4)
        
    print(f"完美流水线执行完毕！最终文件: {output_path}")


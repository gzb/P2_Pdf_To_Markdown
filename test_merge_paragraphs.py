import json
import os
import re

def is_title_format(text):
    """
    判断文本是否属于典型的标题格式。
    如果是标题，通常不需要与下一段合并。
    """
    text = text.strip()
    if not text:
        return False
        
    # 特征 1：以典型的章节序号开头
    # 例如：一、 （一） 1. 1.1 第一章 第1节
    title_patterns = [
        r"^第[一二三四五六七八九十百千万\d]+[章节篇部分条款]",
        r"^[一二三四五六七八九十]+[、，\.]",
        r"^\([一二三四五六七八九十]+\)",
        r"^（[一二三四五六七八九十]+）",
        r"^\d+\.",
        r"^\(\d+\)",
        r"^（\d+）"
    ]
    for pattern in title_patterns:
        if re.match(pattern, text):
            return True
            
    # 特征 2：以 Markdown 标题开头
    if text.startswith("#"):
        return True
        
    # 特征 3：短文本且没有标点符号结尾（很多短标题的特征）
    # 但这个容易误判换行导致的短文字，需要谨慎，这里暂时不加入，以正则为主
    return False

def is_terminal_punctuation(char):
    """
    判断字符是否为段落结束标点
    """
    terminals = set('。！？!?…:：；;')
    return char in terminals

def get_effective_last_char(text):
    """
    获取文本的有效最后一个字符（忽略末尾的引号等）
    """
    text = text.strip()
    if not text:
        return ''
    
    last_char = text[-1]
    if len(text) > 1 and last_char in '”’"\'》>】]':
        last_char = text[-2]
    return last_char

def merge_paragraph_blocks(json_data, input_filename):
    """
    根据页面布局，将属于同一个段落的相邻区块文字链接到一起。
    """
    if "boxes" not in json_data:
        return json_data

    # 从 input_filename 中提取纯数字文件名作为 page 的值
    base_name = os.path.basename(input_filename)
    page_num = base_name.replace(".json", "")
        
    page_width = json_data.get("image_dims", {}).get("w", 1024)
    page_height = json_data.get("image_dims", {}).get("h", 1024)
    
    original_boxes = json_data["boxes"]
    merged_boxes = []

    pending_text_block = None
    separated_by_non_text = False
    
    for block in original_boxes:
        label = block.get("label", "")
        
        if label in ["text", "sub_title"]:
            text_content = block.get("text_content", "").strip()
            if not text_content:
                # 忽略空文本块
                continue
                
            if pending_text_block is None:
                # 初始化新的待合并文本块
                pending_text_block = block.copy()
                merged_boxes.append(pending_text_block)
                separated_by_non_text = False
            else:
                # 判断是否需要与 pending_text_block 合并
                last_char = get_effective_last_char(pending_text_block.get("text_content", ""))
                
                cb = pending_text_block.get("box", [0, 0, 0, 0])
                nb = block.get("box", [0, 0, 0, 0])
                
                # 触发合并的条件：
                # 1. 前一个区块不是以句号等结束符结尾
                is_cut_off = last_char and not is_terminal_punctuation(last_char)
                
                # 2. 前一个区块不能是典型的章节标题（否则它可能会错误地跟下一段合并）
                is_not_title = not is_title_format(pending_text_block.get("text_content", ""))
                
                # 3. 并且满足以下布局特征之一：
                #   a. 跨栏：两者的 X 坐标差异较大
                is_cross_column = abs(cb[0] - nb[0]) > page_width * 0.05
                #   b. 跨页底：前一个区块已经接近页面底部
                is_bottom_of_page = cb[3] > page_height * 0.85
                #   c. 被非文本区块（如图片、表格）物理截断
                is_separated = separated_by_non_text
                
                if is_cut_off and is_not_title and (is_cross_column or is_bottom_of_page or is_separated):
                    # 执行合并
                    # 记录被合并区块的原始文本长度 (修正了这里原本用 pending_text_block["text_content"] 而非原始文字长度的问题)
                    original_len = len(pending_text_block.get("text_content", ""))
                    added_len = len(text_content)
                    
                    pending_text_block["text_content"] += text_content
                    
                    # 更新边界框为包含两者的最小包围盒
                    pending_text_block["box"] = [
                        min(cb[0], nb[0]),
                        min(cb[1], nb[1]),
                        max(cb[2], nb[2]),
                        max(cb[3], nb[3])
                    ]
                    
                    # 记录合并前的所有原始坐标框和对应文本长度
                    if "merged_boxes" not in pending_text_block:
                        pending_text_block["merged_boxes"] = [cb]
                        pending_text_block["merged_text_lens"] = [original_len]
                        
                    pending_text_block["merged_boxes"].append(nb)
                    pending_text_block["merged_text_lens"].append(added_len)
                    
                    # 合并后重置分隔标志，因为我们刚刚接上了一个文本块
                    separated_by_non_text = False
                else:
                    # 无法合并，作为新的独立段落
                    pending_text_block = block.copy()
                    merged_boxes.append(pending_text_block)
                    separated_by_non_text = False
                    
        else:
            # 非文本区块（如 image, table, equation 等）
            merged_boxes.append(block.copy())
            separated_by_non_text = True
            
    # 构建新的 JSON 数据
    new_json_data = json_data.copy()
    new_json_data["boxes"] = merged_boxes
    
    return new_json_data

def merge_py_json_to_ds_json_curpage_process_file(input_filename, output_filename):
    input_path = input_filename
    output_path = output_filename
    
    print(f"Reading from {input_path}")
    if not os.path.exists(input_path):
        print(f"Error: The input file does not exist: {input_path}")
        return

    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    new_data = merge_paragraph_blocks(data, input_filename)
    
    # 确保输出目录存在
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    print(f"Writing to {output_path}")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(new_data, f, ensure_ascii=False, indent=4)
    print("Done!")

if __name__ == "__main__":
    # 指定的测试输入和输出路径
    input_file = r"C:\1_web_book_check_v2\1_Server\fastapi-auth-app\check_book\87c0c8816de13122fc58fcc878b9e22f\pdf-2-json-py-to-ds-b\9.json"
    output_file = r"C:\1_web_book_check_v2\1_Server\fastapi-auth-app\check_book\87c0c8816de13122fc58fcc878b9e22f\pdf-2-json-py-to-ds-b\9_n.json"
    
    merge_py_json_to_ds_json_curpage_process_file(input_file, output_file)
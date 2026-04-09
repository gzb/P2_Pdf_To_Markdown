import json
import os

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

def merge_paragraph_blocks(json_data):
    """
    根据页面布局，将属于同一个段落的相邻区块文字链接到一起。
    """
    if "boxes" not in json_data:
        return json_data
        
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
                
                # 2.5 当前区块也不能是典型的章节标题（否则它就是新起的一段，不应追加到前一段）
                current_is_not_title = not is_title_format(text_content)
                
                # 3. 并且满足以下布局特征之一：
                #   a. 跨栏：两者的 X 坐标差异较大
                is_cross_column = abs(cb[0] - nb[0]) > page_width * 0.05
                #   b. 跨页底：前一个区块已经接近页面底部
                is_bottom_of_page = cb[3] > page_height * 0.85
                #   c. 被非文本区块（如图片、表格）物理截断
                is_separated = separated_by_non_text
                
                if is_cut_off and is_not_title and current_is_not_title and (is_cross_column or is_bottom_of_page or is_separated):
                    # 执行合并
                    # 记录被合并区块的原始文本长度
                    original_len = len(pending_text_block["text_content"])
                    added_len = len(text_content)
                    
                    pending_text_block["text_content"] += text_content
                    
                    # 更新边界框为包含两者的最小包围盒（或者保留各自的盒子记录）
                    pending_text_block["box"] = [
                        min(cb[0], nb[0]),
                        min(cb[1], nb[1]),
                        max(cb[2], nb[2]),
                        max(cb[3], nb[3])
                    ]
                    
                    # 可选：记录合并前的所有原始坐标框和对应文本长度
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

def process_file(input_path, output_path):
    print(f"Reading from {input_path}")
    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    new_data = merge_paragraph_blocks(data)
    
    print(f"Writing to {output_path}")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(new_data, f, ensure_ascii=False, indent=4)
    print("Done!")

if __name__ == "__main__":
    input_file = r"C:\gzb_file_to_github\P2_Pdf_To_Markdown\test_json\12.json"
    output_file = r"C:\gzb_file_to_github\P2_Pdf_To_Markdown\test_json\12_merged.json"
    
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    process_file(input_file, output_file)

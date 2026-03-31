import json
import os

def load_ocr_file_ds_to_py_curpage(json_data, filename):
    """
    解析新的 DS-OCR 合并格式 JSON 数据。
    将 boxes 节点的数据转换为指定的字典格式，并处理 merged_boxes 和 merged_text_lens。
    """
    nodes = []
    ref_idx = 0
    box_text_all = ''
    page_text_len = 0
    
    # 遍历 boxes 节点
    for block in json_data.get("boxes", []):
        ref_text = block.get("label", "")
        box_text = block.get("text_content", "")
        
        # 判断是否有合并信息
        if "merged_boxes" in block:
            box = block["merged_boxes"]
        else:
            box = block.get("box", [])
            
        if "merged_text_lens" in block:
            text_len = block["merged_text_lens"]
        else:
            text_len = len(box_text) if box_text else 0
            
        # 生成节点
        # 注意：如果 merged_boxes 中有多组值，题目要求"对应的在 node_index 写入多个 ref_idx 的值"
        # 我们需要判断 box 是不是一个列表的列表 (即多个 box)
        
        is_merged = "merged_boxes" in block
        
        if is_merged:
            # 如果是合并的，box 是一个列表的列表，例如 [[x,y,x,y], [x,y,x,y]]
            num_merged = len(box)
            node_index = [ref_idx + i for i in range(num_merged)]
            # 更新全局的 ref_idx
            current_ref_idx = node_index  # 记录到节点中
            ref_idx += num_merged
        else:
            node_index = ref_idx
            ref_idx += 1
            
        nodes.append({
            "filename": filename,
            "page": filename.replace('.json', ''),
            "node_index": node_index,
            "text_len": text_len, # 存放纯文本长度，可能是单个 int，也可能是 int 数组
            "ref": ref_text,      # 存储 <|ref|> 标签内容，这里对应 label
            "box": box,           # 存储坐标数据，可能是单个 box，也可能是多个 box
            "text": box_text      # 剩余的纯文本
        })
        
        if box_text_all == '':
            box_text_all = box_text
        else:
            if box_text: # 如果 box_text 不为空才加换行
                box_text_all += '\n' + box_text

    page_text_len += len(box_text_all)
    
    return {
        "filename": filename,
        "page": filename.replace('.json', ''),
        "page_text_len": page_text_len, # 当前页的纯文本长度
        "image_dims": json_data.get("image_dims", {"w": 1191, "h": 1684}),        
        "box_text_all": box_text_all,
        "nodes": nodes        
    }

if __name__ == "__main__":
    file_path = r"C:\gzb_file_to_github\P2_Pdf_To_Markdown\test_json\8_merged.json"
    output_path = r"C:\gzb_file_to_github\P2_Pdf_To_Markdown\test_json\8_merged_v2.json"
    filename = os.path.basename(file_path)
    
    print(f"Reading from {file_path}")
    with open(file_path, 'r', encoding='utf-8') as f:
        page_json_data = json.load(f)
        
    result = load_ocr_file_ds_to_py_curpage(page_json_data, filename)
    
    # 打印结果看看
    print("\n--- 解析结果 ---")
    print(f"filename: {result['filename']}")
    print(f"page: {result['page']}")
    print(f"page_text_len: {result['page_text_len']}")
    print(f"image_dims: {result['image_dims']}")
    print(f"nodes count: {len(result['nodes'])}")
    
    print("\n--- 节点详情预览 ---")
    for i, node in enumerate(result['nodes']):
        print(f"Node {i}:")
        print(f"  node_index: {node['node_index']}")
        print(f"  ref: {node['ref']}")
        print(f"  text_len: {node['text_len']}")
        print(f"  box: {node['box']}")
        print(f"  text: {node['text'][:20]}..." if node['text'] else "  text: ")
        print("-" * 20)
        
    print(f"\nWriting result to {output_path}")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=4)
    print("Done!")

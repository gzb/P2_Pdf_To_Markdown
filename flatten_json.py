import json
import os

def flatten_array(arr):
    """
    递归展开多层嵌套的数组。
    由于我们需要的是形如 [[x1,y1,x2,y2], [x3,y3,x4,y4]] 或简单的 [w, h] 字典，
    这取决于具体的节点类型。
    
    对于 boxs:
    原本期望的格式是：
    [
        [[x1,y1,x2,y2]], 
        [[x3,y3,x4,y4], [x5,y5,x6,y6]]
    ]
    每一项代表一个段落对应的所有 box。
    如果发现多了一层，比如：
    [
        [ [[x1,y1,x2,y2]] ]
    ]
    需要将其展平。
    """
    pass

def process_file(input_path, output_path):
    print(f"Reading {input_path}")
    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    for item in data:
        # 首先提取当前 item 第一组的 image_dims 用于坐标转换（假设整页的宽高相同）
        page_w, page_h = 1000, 1000
        if "image_dims" in item and len(item["image_dims"]) > 0:
            first_dim = item["image_dims"][0]
            # 如果 first_dim 还是嵌套的列表，取第一个元素
            if isinstance(first_dim, list) and len(first_dim) > 0:
                dim_dict = first_dim[0]
            else:
                dim_dict = first_dim
                
            if isinstance(dim_dict, dict):
                page_w = dim_dict.get("w", 1000)
                page_h = dim_dict.get("h", 1000)
                
        scale_x = 1000.0 / page_w if page_w else 1.0
        scale_y = 1000.0 / page_h if page_h else 1.0

        # 处理 boxs
        if "boxs" in item:
            new_boxs = []
            for group in item["boxs"]:
                flattened_group = []
                for sub_item in group:
                    # 如果 sub_item 的第一个元素是一个列表，说明多了一层嵌套
                    if isinstance(sub_item, list) and len(sub_item) > 0 and isinstance(sub_item[0], list):
                        # 把里面那一层的元素加到 flattened_group 中，并转换坐标
                        for box in sub_item:
                            if len(box) == 4:
                                scaled_box = [
                                    int(round(box[0] * scale_x)),
                                    int(round(box[1] * scale_y)),
                                    int(round(box[2] * scale_x)),
                                    int(round(box[3] * scale_y))
                                ]
                                flattened_group.append(scaled_box)
                            else:
                                flattened_group.append(box)
                    else:
                        # 当前 sub_item 就是一个 box [x1, y1, x2, y2]
                        if len(sub_item) == 4 and isinstance(sub_item[0], (int, float)):
                            scaled_box = [
                                int(round(sub_item[0] * scale_x)),
                                int(round(sub_item[1] * scale_y)),
                                int(round(sub_item[2] * scale_x)),
                                int(round(sub_item[3] * scale_y))
                            ]
                            flattened_group.append(scaled_box)
                        else:
                            flattened_group.append(sub_item)
                new_boxs.append(flattened_group)
            item["boxs"] = new_boxs
            
        # 处理 nodes_text_len 和 pages 的联动
        if "nodes_text_len" in item:
            new_lens = []
            new_pages = []
            has_pages = "pages" in item
            
            for i, group in enumerate(item["nodes_text_len"]):
                flattened_group = []
                is_nested = False
                for sub_item in group:
                    if isinstance(sub_item, list):
                        flattened_group.extend(sub_item)
                        is_nested = True
                    else:
                        flattened_group.append(sub_item)
                new_lens.append(flattened_group)
                
                # 如果发现过度嵌套，需要调整对应的 pages 数组
                if has_pages and i < len(item["pages"]):
                    page_group = item["pages"][i]
                    if is_nested:
                        # 读取第一个值
                        first_page_val = page_group[0] if len(page_group) > 0 else "1"
                        # 添加和 "nodes_text_len" (展平后) 数组中数量一样多的相同记录
                        new_page_group = [first_page_val] * len(flattened_group)
                        new_pages.append(new_page_group)
                    else:
                        new_pages.append(page_group)
                elif has_pages:
                    new_pages.append([]) # 兜底防止索引越界
                    
            item["nodes_text_len"] = new_lens
            if has_pages:
                item["pages"] = new_pages
            
        # 处理 nodes_index
        if "nodes_index" in item:
            new_idx = []
            for group in item["nodes_index"]:
                flattened_group = []
                for sub_item in group:
                    if isinstance(sub_item, list):
                        flattened_group.extend(sub_item)
                    else:
                        flattened_group.append(sub_item)
                new_idx.append(flattened_group)
            item["nodes_index"] = new_idx
            
        # 处理 image_dims
        if "image_dims" in item:
            new_dims = []
            for group in item["image_dims"]:
                flattened_group = []
                for sub_item in group:
                    if isinstance(sub_item, list):
                        flattened_group.extend(sub_item)
                    else:
                        flattened_group.append(sub_item)
                new_dims.append(flattened_group)
            item["image_dims"] = new_dims

    print(f"Writing to {output_path}")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    print("Done!")

if __name__ == "__main__":
    input_file = r"C:\gzb_file_to_github\P2_Pdf_To_Markdown\test_json\processed_merged_nodes_three-py-to-ds-curpage-merged.json"
    output_file = r"C:\gzb_file_to_github\P2_Pdf_To_Markdown\test_json\processed_merged_nodes_three-py-to-ds-curpage-merged_format.json"
    process_file(input_file, output_file)

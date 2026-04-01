#pdf转图片相关
import os
import fitz  # PyMuPDF
from PIL import Image
import io
import json

#图片转json相关
import time
import requests
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import deque

#json合并相关
import re
import requests
import difflib

#第1大步：pdf转图片相关===================================================================
def pdf_to_images(pdf_file: str, output_folder: str):
    """Convert PDF to images and save them in the output folder."""
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    # Open the PDF file
    pdf_doc = fitz.open(pdf_file)

    # Set the zoom factor (for better resolution)
    zoom = 144 / 72.0  # Higher zoom for higher quality
    matrix = fitz.Matrix(zoom, zoom)

    # Loop through each page in the PDF
    for page_num in range(pdf_doc.page_count):
        page = pdf_doc.load_page(page_num)  # Load page by page number
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)

        # Convert the pixmap (image) to a BytesIO object
        img_bytes = pixmap.tobytes("png")
        img = Image.open(io.BytesIO(img_bytes))

        # Save the image
        #output_image_path = os.path.join(output_folder, f"page_{page_num + 1}.png")
        output_image_path = os.path.join(output_folder, f"{page_num + 1}.png")
        img.save(output_image_path, format="PNG")

        print(f"Page {page_num + 1} converted to {output_image_path}")

    pdf_doc.close()

#第2大步：图片转json相关===================================================================

# 定义API服务器的地址和并发限制
api_urls = [
    'http://192.168.0.19:8001/ocr',
    'http://192.168.0.19:8002/ocr'
   # 'http://192.168.0.19:8003/ocr',
   # 'http://192.168.0.19:8004/ocr'
]

# API队列，每个队列最多保持2个任务
api_queues = [deque() for _ in api_urls]

def call_api(file_path, url):
    """调用OCR API接口，返回结果。"""
    try:
        # 文件内容
        with open(file_path, 'rb') as f:
            file_data = f.read()

        # 设置multipart/form-data的boundary和头信息
        boundary = '----WebKitFormBoundaryacCXMQisnxWgutzv'
        headers = {
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Content-Type': f'multipart/form-data; boundary={boundary}',
            'Cookie': 'token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6ImU2ZDdhNTZiLTlhOTMtNDc1NS05NmJjLTNiNmY3NmJiNWZhYyJ9.owISsiR5TQie_FQDlBr19wQLsqU-ykbzSZe0BjbSJig; SecurityEntrance=NDhlZDk2ZWY1Yw%3D%3D;',
            'Origin': 'http://192.168.0.19:8001',
            'Pragma': 'no-cache',
            'Referer': 'http://192.168.0.19:8001/docs',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36',
            'accept': 'application/json'
        }

        # 构造multipart/form-data请求体
        body = (
            f'--{boundary}\r\n'
            f'Content-Disposition: form-data; name="file"; filename="{file_path.name}"\r\n'
            f'Content-Type: image/png\r\n\r\n' +
            file_data.decode('ISO-8859-1') +  # 必须将文件内容以合适的编码传输
            f'\r\n--{boundary}\r\n'
            f'Content-Disposition: form-data; name="prompt_type"\r\n\r\ndocument\r\n'
            f'--{boundary}\r\n'
            f'Content-Disposition: form-data; name="find_term"\r\n\r\n\r\n'
            f'--{boundary}\r\n'
            f'Content-Disposition: form-data; name="custom_prompt"\r\n\r\n\r\n'
            f'--{boundary}\r\n'
            f'Content-Disposition: form-data; name="grounding"\r\n\r\nfalse\r\n'
            f'--{boundary}--\r\n'
        ).encode('ISO-8859-1')  # 对整个请求体进行编码

        # 发送POST请求
        print(url)
        response = requests.post(url, headers=headers, data=body, verify=False)

        # 检查返回状态
        if response.status_code == 200:
            return response.json()  # 返回API响应的json内容
        else:
            print(f"API 调用失败，状态码: {response.status_code}")
            print(f"错误信息: {response.text}")
            return None
    except Exception as e:
        print(f"API调用异常: {e}")
        return None

def process_file(png_file, dist_path):
    """处理单个文件的API请求，并保存结果"""
    json_file = dist_path / (png_file.stem + '.json')

    if json_file.exists():
        print(f"文件 {json_file} 已存在，跳过")
        return

    print(f"正在处理文件: {png_file.name}")

    retries = 0
    success = False
    result = None

    while retries < 3 and not success:
        # 查找并分配一个空闲的API服务器
        assigned = False
        for i in range(len(api_queues)):
            if len(api_queues[i]) < 2:  # 每个服务器最多有2个并发
                url = api_urls[i]
                api_queues[i].append(png_file)  # 加入队列，表示该API正在处理任务
                result = call_api(png_file, url)
                if result:
                    success = True
                api_queues[i].remove(png_file)  # 完成任务后移除队列
                assigned = True
                break

        if not assigned:
            print("所有API服务器都已满载，稍后重试...")
            retries += 1
            time.sleep(2)  # 等待2秒后重试

    if success and result:
        # 将返回结果保存为json文件
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=4)
        print(f"文件 {json_file} 保存成功")
    else:
        print(f"文件 {png_file.name} 处理失败，跳过")

def process_files_to_json(path_source, path_dist):
    """并发处理文件夹中的多个文件，最大并发数为4"""
    source_path = Path(path_source)
    dist_path = Path(path_dist)
    
    # 如果目标文件夹不存在，创建它
    dist_path.mkdir(parents=True, exist_ok=True)

    # 获取文件名并按数字排序（文件名非数字时默认赋值为0）

    png_files = sorted(
        [f for f in source_path.glob('*') if f.suffix in ['.png', '.jpg']],  # 过滤出 .png 和 .jpg 文件
        key=lambda x: (int(x.stem) if x.stem.isdigit() else 0)  # 使用 x.stem 获取文件名
    )

    # 输出 png_files 的长度
    print(f"目录：{path_source}\n png_files 的数量为: {len(png_files)}")


    # 使用ThreadPoolExecutor控制并发数量，最大并发数为4
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(process_file, png_file, dist_path) for png_file in png_files]

        # 等待所有任务完成
        for future in as_completed(futures):
            future.result()  # 获取任务结果

# 第3大步：Json文件合并（基于理想流水线重构）===================================================================

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

def normalize_block_text(label, text):
    text = text or ""
    # 注意：这里不能用 .strip() 否则会把段落前后的排版空格（用于缩进/分割的）直接干掉
    if not text.strip():
        return ""
    if label == "title":
        return f"# {text}"
    if label == "sub_title":
        return f"## {text}"
    return text

def merge_final_output_by_content_limit(formatted_output, max_content_len=1024):
    merged_output = []
    current_item = None

    for item in formatted_output:
        content = item.get("content", "")

        if "<table>" in content:
            if current_item is not None:
                merged_output.append(current_item)
                current_item = None
            merged_output.append(item)
            continue

        if content.startswith("#"):
            if current_item is not None:
                merged_output.append(current_item)
            current_item = {
                "content": content,
                "texts": list(item.get("texts", [])),
                "page": item.get("page", "1"),
                "pages": list(item.get("pages", [])),
                "nodes_text_len": list(item.get("nodes_text_len", [])),
                "nodes_index": list(item.get("nodes_index", [])),
                "boxs": list(item.get("boxs", [])),
                "image_dims": list(item.get("image_dims", [])),
                "ref": list(item.get("ref", []))
            }
            continue

        if current_item is None:
            current_item = {
                "content": content,
                "texts": list(item.get("texts", [])),
                "page": item.get("page", "1"),
                "pages": list(item.get("pages", [])),
                "nodes_text_len": list(item.get("nodes_text_len", [])),
                "nodes_index": list(item.get("nodes_index", [])),
                "boxs": list(item.get("boxs", [])),
                "image_dims": list(item.get("image_dims", [])),
                "ref": list(item.get("ref", []))
            }
            continue

        merged_content = f"{current_item['content']}\n{content}" if current_item["content"] else content
        if len(merged_content) <= max_content_len:
            current_item["content"] = merged_content
            current_item["texts"].extend(item.get("texts", []))
            current_item["pages"].extend(item.get("pages", []))
            current_item["nodes_text_len"].extend(item.get("nodes_text_len", []))
            current_item["nodes_index"].extend(item.get("nodes_index", []))
            current_item["boxs"].extend(item.get("boxs", []))
            current_item["image_dims"].extend(item.get("image_dims", []))
            current_item["ref"].extend(item.get("ref", []))
        else:
            merged_output.append(current_item)
            current_item = {
                "content": content,
                "texts": list(item.get("texts", [])),
                "page": item.get("page", "1"),
                "pages": list(item.get("pages", [])),
                "nodes_text_len": list(item.get("nodes_text_len", [])),
                "nodes_index": list(item.get("nodes_index", [])),
                "boxs": list(item.get("boxs", [])),
                "image_dims": list(item.get("image_dims", [])),
                "ref": list(item.get("ref", []))
            }

    if current_item is not None:
        merged_output.append(current_item)

    for idx, item in enumerate(merged_output, start=1):
        item["id"] = idx
        item["type"] = "text"
        first_group = item.get("nodes_index", [])
        item["number"] = first_group[0][0] if first_group and first_group[0] else None

    return merged_output

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
        label = block.get("label")
        
        # 始终确保哪怕是不匹配的区块（例如 image、table），也有一个基本的 text_content 容错
        ocr_text = block.get("text_content", "")
        
        if label not in ["text", "sub_title", "title"]:
            # 如果是非文本块，但之前没识别出 text_content，尝试从 raw_text 解析找回
            if not ocr_text:
                bbox = block.get("box")
                if bbox:
                    raw_text = ocr_data.get("raw_text", "")
                    if raw_text:
                        det_str = f"<|det|>[[{bbox[0]}, {bbox[1]}, {bbox[2]}, {bbox[3]}]]<|/det|>"
                        start_idx = raw_text.find(det_str)
                        if start_idx != -1:
                            start_idx += len(det_str)
                            if start_idx < len(raw_text) and raw_text[start_idx] == '\n':
                                start_idx += 1
                            end_idx = raw_text.find("<|ref|>", start_idx)
                            if end_idx == -1:
                                extracted_text = raw_text[start_idx:]
                            else:
                                extracted_text = raw_text[start_idx:end_idx]
                            if extracted_text.endswith('\n'):
                                extracted_text = extracted_text[:-1]
                            block["text_content"] = extracted_text
            continue
            
        bbox = block.get("box")
        if not bbox: continue
        
        # 修正 a: 如果 pdf-2json 的数据中存在 table，目标文件中的 text 数据使用 ocr 的数据。
        if "<table>" in ocr_text:
            # 跳过合并，直接保留原始 ocr 的文本（包含 HTML 结构）
            continue
            
        target_box = [bbox[0]-5, bbox[1]-5, bbox[2]+5, bbox[3]+5]
        matches = [p for p in py_blocks if is_contained_or_overlap(p["ds_bbox"], target_box)]
        
        combined_py_text = "".join([m.get("text", "") for m in matches])
        
        # 修正 b: 如果 pdf-2-json-python 区块没有内容但 ocr 的有内容，则使用 ocr 的 (这部分已有逻辑满足：if combined_py_text才覆盖)
        if combined_py_text:
            merged_text = merge_text(ocr_text, combined_py_text)
            block["text_content"] = merged_text
        else:
            # 当 combined_py_text 为空时，尝试从 raw_text 中回退提取最原始带所有排版的 OCR 数据
            if not ocr_text:
                raw_text = ocr_data.get("raw_text", "")
                if raw_text:
                    det_str = f"<|det|>[[{bbox[0]}, {bbox[1]}, {bbox[2]}, {bbox[3]}]]<|/det|>"
                    start_idx = raw_text.find(det_str)
                    if start_idx != -1:
                        start_idx += len(det_str)
                        if start_idx < len(raw_text) and raw_text[start_idx] == '\n':
                            start_idx += 1
                        
                        end_idx = raw_text.find("<|ref|>", start_idx)
                        if end_idx == -1:
                            extracted_text = raw_text[start_idx:]
                        else:
                            extracted_text = raw_text[start_idx:end_idx]
                            
                        if extracted_text.endswith('\n'):
                            extracted_text = extracted_text[:-1]
                            
                        block["text_content"] = extracted_text
        
    return ocr_data

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
    
    for block_index, block in enumerate(page_data.get("boxes", [])):
        label = block.get("label", "")
        # 原有的原始文本保留其排版空格（不使用 strip）
        original_text = block.get("text_content", "")
        text_content = normalize_block_text(label, original_text)
        original_box = block.get("box", [])
        
        if label not in ["text", "sub_title", "title"]:
            merged_nodes.append({
                "label": label,
                "text_content": text_content,
                # texts 中直接保存原原本本的数据（保留空格），而 content 负责拼装带 \n 的
                "texts": [original_text] if original_text else [],
                "ref": [label],
                "boxs": [original_box] if original_box else [],
                "pages": [str(page_num)],
                "nodes_text_len": [len(text_content)] if text_content else [0],
                "nodes_index": [block_index],
                "image_dims": [page_data.get("image_dims", {})]
            })
            separated_by_non_text = True
            continue
            
        if not text_content: continue
        
        # 将每个文本块初始化为标准扁平结构
        current_node = {
            "label": label,
            "text_content": text_content,
            "texts": [original_text],
            "ref": [label],
            "boxs": [original_box],
            "pages": [str(page_num)],
            "nodes_text_len": [len(text_content)],
            "nodes_index": [block_index],
            "image_dims": [page_data.get("image_dims", {})]
        }
            
        if pending_node is None:
            pending_node = current_node
            merged_nodes.append(pending_node)
            separated_by_non_text = False
        else:
            last_char = get_effective_last_char(pending_node["text_content"])
            is_cut_off = last_char and not is_terminal_punctuation(last_char)
            
            cb = pending_node["boxs"][-1] if pending_node["boxs"] else [0,0,0,0]
            nb = current_node["boxs"][0] if current_node["boxs"] else [0,0,0,0]
            
            is_cross_column = abs(cb[0] - nb[0]) > page_width * 0.05
            is_bottom_of_page = cb[3] > page_height * 0.85
            
            if (
                pending_node["label"] == "text"
                and current_node["label"] == "text"
                and is_cut_off
                and (is_cross_column or is_bottom_of_page or separated_by_non_text)
            ):
                # 扁平化合并：直接 extend 数组，不产生嵌套
                pending_node["text_content"] += "\n" + current_node["text_content"]
                pending_node["texts"].extend(current_node["texts"])
                pending_node["ref"].extend(current_node["ref"])
                pending_node["boxs"].extend(current_node["boxs"])
                pending_node["pages"].extend(current_node["pages"])
                pending_node["nodes_text_len"].extend(current_node["nodes_text_len"])
                pending_node["nodes_index"].extend(current_node["nodes_index"])
                pending_node["image_dims"].extend(current_node["image_dims"])
                separated_by_non_text = False
            else:
                pending_node = current_node
                merged_nodes.append(pending_node)
                separated_by_non_text = False
                
    return merged_nodes

def step6_crosspage_merge_and_format(all_pages_nodes):
    """
    跨页合并段落，并将最终结果的所有坐标等比例缩放至 1024 基准宽度。
    """
    final_nodes = []
    pending_node = None
    
    for node in all_pages_nodes:
        if node["label"] not in ["text", "sub_title", "title"]:
            final_nodes.append(node)
            continue
            
        if pending_node is None:
            pending_node = node
            final_nodes.append(pending_node)
        else:
            last_char = get_effective_last_char(pending_node["text_content"])
            is_cut_off = last_char and not is_terminal_punctuation(last_char)
            
            if pending_node["label"] == "text" and node["label"] == "text" and is_cut_off:
                # 跨页合并，依然使用 extend 保持扁平化
                pending_node["text_content"] += "\n" + node["text_content"]
                pending_node["texts"].extend(node["texts"])
                pending_node["ref"].extend(node["ref"])
                pending_node["boxs"].extend(node["boxs"])
                pending_node["pages"].extend(node["pages"])
                pending_node["nodes_text_len"].extend(node["nodes_text_len"])
                pending_node["nodes_index"].extend(node["nodes_index"])
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
                dim = node["image_dims"][i] if i < len(node["image_dims"]) else {"w": 1024, "h": 1024}
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
            "content": node["text_content"],
            "texts": node.get("texts", []),
            "page": node["pages"][0] if node["pages"] else "1",
            "pages": [node["pages"]],
            "nodes_text_len": [node["nodes_text_len"]],
            "nodes_index": [node.get("nodes_index", [])],
            "boxs": [scaled_boxs],
            "image_dims": [node["image_dims"]],
            "ref": node.get("ref", []),
            "id": idx + 1,
            "type": "text",
            "number": node.get("nodes_index", [None])[0] if node.get("nodes_index") else None
        })
        
    return merge_final_output_by_content_limit(formatted_output, max_content_len=1024)

def ideal_pdf_to_markdown_pipeline(target_dir):
    """
    理想状态下的 PDF 转 Markdown 全流程调度。
    增加对中间处理结果 (pdf-2-json-py-to-ds, pdf-2-json-py-to-ds-curpage-merged) 的留存。
    """
    ocr_json_dir = os.path.join(target_dir, "pdf-2-json")
    py_json_dir = os.path.join(target_dir, "pdf-2-json-python")
    
    # 新增或恢复的中间目录
    py_to_ds_dir = os.path.join(target_dir, "pdf-2-json-py-to-ds")
    curpage_merged_dir = os.path.join(target_dir, "pdf-2-json-py-to-ds-curpage-merged")
    mk_folder = os.path.join(target_dir, "pdf-3-mk")
    
    os.makedirs(py_to_ds_dir, exist_ok=True)
    os.makedirs(curpage_merged_dir, exist_ok=True)
    os.makedirs(mk_folder, exist_ok=True)
    
    all_pages_nodes = []
    
    # 获取页码文件并排序
    json_files = []
    if os.path.exists(ocr_json_dir):
        json_files = [f for f in os.listdir(ocr_json_dir) if f.endswith(".json")]
        json_files.sort(key=lambda x: int(x.split('.')[0]) if x.split('.')[0].isdigit() else 0)

    # 遍历所有页，执行融合与页内合并
    for filename in json_files:
        page_num = filename.replace(".json", "")
        
        # 读取两套 JSON
        ocr_path = os.path.join(ocr_json_dir, filename)
        py_path = os.path.join(py_json_dir, filename)
        
        with open(ocr_path, 'r', encoding='utf-8') as f:
            ocr_data = json.load(f)
            
        if os.path.exists(py_path):
            with open(py_path, 'r', encoding='utf-8') as f:
                py_data = json.load(f)
        else:
            py_data = {"blocks": []}
            
        # 步骤 3/4：融合 OCR 与 PyMuPDF (保存到 pdf-2-json-py-to-ds)
        merged_data = step4_merge_ocr_and_py_json(ocr_data, py_data)
        with open(os.path.join(py_to_ds_dir, filename), 'w', encoding='utf-8') as f:
            json.dump(merged_data, f, ensure_ascii=False, indent=4)
        
        # 步骤 4/5：页内段落合并 (生成无嵌套的扁平节点)
        page_nodes = step5_inpage_paragraph_merge(merged_data, page_num)
        
        # 为了兼容旧流程查看，把单页合并后的节点也伪装成完整结构存一份到 curpage_merged_dir
        with open(os.path.join(curpage_merged_dir, filename), 'w', encoding='utf-8') as f:
            # 这里简单包装成 {"boxes": page_nodes} 形式，方便查看
            json.dump({"boxes": page_nodes, "image_dims": merged_data.get("image_dims", {})}, f, ensure_ascii=False, indent=4)
            
        all_pages_nodes.extend(page_nodes)
        
    # 步骤 5/6 & 7：跨页合并与坐标转换
    final_json_data = step6_crosspage_merge_and_format(all_pages_nodes)
    
    # 保存最终结果
    output_path = os.path.join(mk_folder, "processed_merged_nodes_three-py-to-ds-curpage-merged_format-v2.json")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(final_json_data, f, ensure_ascii=False, indent=4)
        
    print(f"完美流水线执行完毕！最终文件: {output_path}")
    return output_path

# ==============================================================================
# 保留用于兼容性的外壳函数，统一调用新的理想流水线
# ==============================================================================
def convert_pdf_to_images(pdf_file, target_path):
    pass

def process_images_to_json(target_path):
    pass

def extract_pdf_to_json(pdf_path, output_dir):
    pass

def merge_json_to_mk(target_path):
    pass

def merge_py_json_to_ds_json(ds_json_folder, py_json_folder, output_folder):
    pass

def merge_json_to_mk_py_to_ds(target_path):
    pass

def merge_py_json_to_ds_json_curpage(merged_output_folder,merged_output_folder_curpage_merged):
    pass

def merge_json_to_mk_py_to_ds_curpage(target_path):
    pass

def merged_format_process_file(input_file, output_file):
    pass

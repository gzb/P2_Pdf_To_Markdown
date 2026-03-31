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

#第3大步：Json文件合并===================================================================
            
# --------------------------------------
# 工具函数（段落合并）
# --------------------------------------
def is_title(line):
    if line.strip().startswith("#"):
        return True
    if re.match(r"^第[\d一二三四五六七八九十百]+[章节篇]", line):
        return True
    return False

def ends_with_sentence_punc(line):
    return bool(re.search(r"[。！？!?]$", line.strip()))

def should_merge(prev_text, next_text):
    prev_lines = [l for l in prev_text.split("\n") if l.strip()]
    next_lines = [l for l in next_text.split("\n") if l.strip()]
    if not prev_lines or not next_lines:
        return False

    last = prev_lines[-1].strip()
    first = next_lines[0].strip()

    if is_title(first):
        return False
    if ends_with_sentence_punc(last):
        return False
    if len(last) <= 6:
        return False

    return True


# --------------------------------------
# 默认错误分析 API（或使用用户 API）
# --------------------------------------
def error_analysis(text):
    """支持 external API，否则 fallback demo。"""
    API = ""  # ("api_url", "")
    if API:
        try:
            r = requests.post(API, json={"text": text})
            return r.json().get("keywords", [])
        except:
            print("外部 API 调用失败，退回本地分析")

    # fallback：简单关键字
    demo_words = ["编制真实", "交叉混同", "承担连带责任"]
    found = [w for w in demo_words if w in text]
    return found


# --------------------------------------
# 加载 OCR JSON
# --------------------------------------
def load_ocr_file(json_data, filename):
    raw_text = json_data["raw_text"]  # 从 raw_text 中提取

    # 使用 "<|ref|>" 作为分割符号拆分 raw_text
    parts = raw_text.split('<|ref|>')

    nodes = []
    ref_idx = 0
    det_idx = 0
    box_text_all=''
    page_text_len=0
    # 解析各个部分
    for part in parts[1:]:  # 跳过第一个空部分（split 后的第一个部分为空）
        ref_part = re.match(r"(.*?)(<\|det\|>\[\[(.*?)\]\]<\|/det\|>)(.*)", part, re.DOTALL)
        
        if ref_part:
            ref_text = ref_part.group(1).strip() if ref_part.group(1) else ""  # 提取 ref 内容
            ref_text = ref_text.replace("<|/ref|>", "")  # 去除 ref_text 中的 "<|/ref|>"
            det_data = ref_part.group(3).strip() if ref_part.group(3) else ""  # 提取 det 内容
            box_text = ref_part.group(4).strip() if ref_part.group(4) else ""  # 剩余文本（去除 <|det|> 部分）

            # 如果没有找到 det 数据，则跳过当前部分
            if not det_data:
                continue
            
            # 解析坐标数据
            try:
                box = list(map(int, det_data.split(',')))  # 将坐标字符串转化为整数列表
            except ValueError:
                continue  # 如果解析失败，则跳过

            # 生成节点
            nodes.append({
                "filename": filename,
                "page":filename.replace('.json', ''),
                "node_index": ref_idx,  
                "text_len":len(box_text), #存放纯文本长度
                "ref": ref_text,  # 存储 <|ref|> 标签内容
                "box": box,  # 存储坐标数据
                "text": box_text # 剩余的纯文本   
            })
            if box_text_all=='':
                box_text_all=box_text            
            else:
                box_text_all+='\n'+box_text

            ref_idx += 1

    page_text_len+=len(box_text_all)
    return {
        "filename": filename,
        "page":filename.replace('.json', ''),
        "page_text_len":page_text_len, #当前页的纯文本长度
        "image_dims": json_data.get("image_dims", {"w": 1191, "h": 1684}),        
        "box_text_all": box_text_all,  # full_text 使用 text
        "nodes": nodes        
    }

# --------------------------------------
# 实现跨页段落合并
# --------------------------------------
def merge_pages(pages):
    paragraphs = []
    cur = None

    for page in pages:
        if cur is None:
            cur = {
                "filename":page["filename"],
                "page":page["page"],
                "pages": [page["page"]],  # 初始化为包含当前页面的页码
                "page_text_len":[page["page_text_len"]],
                "image_dims": page["image_dims"],
                "box_text_all": page["box_text_all"],   
                "nodes": page["nodes"].copy()                
            }
            continue

        if should_merge(cur["box_text_all"], page["box_text_all"]):
            cur["box_text_all"] += page["box_text_all"] #跨页合并，不加换行符
            cur["nodes"].extend(page["nodes"])
            cur["pages"].append(page["page"])  # 向"pages"列表添加当前页码
            cur["page_text_len"].append(page["page_text_len"])  
        else:
            paragraphs.append(cur)
            cur = {
                "filename":page["filename"],
                "page":page["page"],
                "pages": [page["page"]],  # 初始化为包含当前页面的页码
                "page_text_len":[page["page_text_len"]],
                "image_dims": page["image_dims"],
                "box_text_all": page["box_text_all"],   
                "nodes": page["nodes"].copy()                
            }

    paragraphs.append(cur)
    return paragraphs


# --------------------------------------
# 保存合并后的文本到文件
# --------------------------------------
def save_to_md(paragraphs, output_file):
    # 检查 paragraphs 是否为列表
    if not isinstance(paragraphs, list):
        print("Error: paragraphs 参数应该是一个列表。")
        return

    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            for i, p in enumerate(paragraphs):
                # 确保每个段落都包含 'box_text_all' 键
                if isinstance(p, dict) and 'box_text_all' in p:
                    f.write(f"{p['box_text_all']}\n\n")
                else:
                    print(f"Warning: 第 {i+1} 段数据格式错误，缺少 'box_text_all' 键，已跳过该段。")
    except IOError as e:
        print(f"Error: 无法写入文件 {output_file}，错误信息：{e}")

# --------------------------------------
# 保存问题词语到 JSON 文件
# --------------------------------------
def save_issues_to_json(issues, output_file):
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(issues, f, ensure_ascii=False, indent=4)


def process_json_files(folder):
    pages = []
    
    # 获取目录下所有.json文件，并按文件名排序
    json_files = sorted(
        [f for f in os.listdir(folder) if f.endswith(".json")],
        key=lambda x: int(x.split('.')[0]) if x.split('.')[0].isdigit() else 0  # 按文件名数字排序
    )

    # 遍历排序后的文件，执行load_ocr_file
    for filename in json_files:
        path = os.path.join(folder, filename)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        p = load_ocr_file(data, filename)
        pages.append(p)
    
    return pages


def write_paragraphs_to_json(paragraphs, output_file):
    """将 paragraphs 数据写入 JSON 文件"""
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            # 使用 json.dump 将 Python 对象写入 JSON 文件
            json.dump(paragraphs, f, ensure_ascii=False, indent=4)
        print(f"数据成功写入 {output_file}")
    except Exception as e:
        print(f"写入文件时发生错误: {e}")


def merge_nodes(pages):
    merged_nodes = []

    for page in pages:
        # 提取当前页面的 "page" 和 "image_dims"
        page_value = page["page"]
        image_dims_value = page["image_dims"]

        for node in page["nodes"]:
            # 将每个节点的信息提取并添加到 merged_nodes 列表中
            merged_nodes.append({               
                "page": page_value,  # 添加 page 信息
                "image_dims": image_dims_value ,  # 添加 image_dims 信息
                "node_index": node["node_index"],
                "text_len": node["text_len"],
                "ref": node["ref"],
                "box": node["box"],
                "text": node["text"]
            })

    return merged_nodes


def save_nodes_to_json(merged_nodes, output_file):
    """将合并后的节点数据写入 JSON 文件"""
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(merged_nodes, f, ensure_ascii=False, indent=4)
        print(f"合并后的节点数据已成功保存到 {output_file}")
    except Exception as e:
        print(f"写入文件时发生错误: {e}")

def save_merged_nodes_to_json(merged_result, output_file):
    """将合并后的节点数据保存到 JSON 文件"""
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(merged_result, f, ensure_ascii=False, indent=4)
        print(f"合并后的节点数据已成功保存到 {output_file}")
    except Exception as e:
        print(f"写入文件时发生错误: {e}")

def save_merged_nodes_to_json_three(merged_result, output_file):
    """将合并后的节点数据保存到 JSON 文件"""
    try:
        # 添加 id、type 和 number 节点
        for idx, node in enumerate(merged_result, 1):
            node["id"] = idx  # 添加 id，值从 1 到 n
            node["type"] = "text"  # 添加 type，值为 "text"
            node["number"] = node["nodes_index"][0][0] if node["nodes_index"] else None  # 添加 number，取 nodes_index 的第一个值

        # 保存修改后的 merged_result 到 JSON 文件
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(merged_result, f, ensure_ascii=False, indent=4)
        
        print(f"合并后的节点数据已成功保存到 {output_file}")
    except Exception as e:
        print(f"写入文件时发生错误: {e}")

def merge_nodes_two(merged_nodes):
    merged_result = []
    cur = None
    i = 0

    # 用于标记哪些节点已经合并
    merged_indexes = set()

    while i < len(merged_nodes):
        node = merged_nodes[i]
        #print(i)

        # 跳过特定文本内容
        if node["text"] == '# 1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.2.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1':
            i += 1  # 跳过当前节点
            cur = None
            print("跳过特殊文本")
            continue

        # 如果 cur 是 None，则初始化为当前节点
        cur = {
            "page": [node["page"]],
            "pages": [node["page"]],
            "nodes_text_len": [node["text_len"]],
            "nodes_index": [node["node_index"]],
            "boxs": [node["box"]],
            "text": node["text"],                
            "image_dims": [node["image_dims"]],
            "ref": node["ref"]                
        }
        
        # 获取当前节点是否是当前页面的最后一个节点
        if i + 1 < len(merged_nodes):
            is_last_node_in_page = (i + 1 == len(merged_nodes)) or (merged_nodes[i + 1]["page"] != node["page"])
        else:
            is_last_node_in_page = (i + 1 == len(merged_nodes))

        # 如果是以 "#" 开头的文本，并且不是当前页面的最后一个节点，则直接追加到 merged_result
        if cur["text"].startswith('#') and not is_last_node_in_page:
            merged_result.append(cur)  # 添加当前节点到结果
            cur = None  # 重置 cur 为 None，准备处理下一个节点
            i += 1  # 跳到下一个节点
            continue

        # 合并同页面不同节点
        if i + 1 < len(merged_nodes):
            next_node = merged_nodes[i + 1]
            
            # 如果当前页面和下一个页面不相同，则判断是否合并
            if node["page"] != next_node["page"] and f"{node['page']}_{node['node_index']}" not in merged_indexes:
                if should_merge(cur["text"], next_node["text"]):
                    # 如果可以合并，累加 pages、nodes_text_len 和 nodes_index 信息
                    cur["pages"].append(next_node["page"])
                    cur["nodes_text_len"].append(next_node["text_len"])
                    cur["nodes_index"].append(next_node["node_index"])
                    cur["boxs"].append(next_node["box"])
                    cur["text"] += next_node["text"]  # 合并文本内容
                    
                    # 使用 page 和 node_index 的组合来唯一标识节点
                    merged_indexes.add(f"{node['page']}_{node['node_index']}")  
                    # 将合并进来的节点标记为已合并
                    merged_indexes.add(f"{next_node['page']}_{next_node['node_index']}")
                    i += 2  # 跳过已合并的节点
                    merged_result.append(cur)
                    continue
                else:
                    i += 1  # 跳过当前节点
                    merged_indexes.add(f"{node['page']}_{node['node_index']}")
                    merged_result.append(cur)
            else:
                if f"{node['page']}_{node['node_index']}" not in merged_indexes:
                    i += 1  # 跳到下一个节点
                    merged_result.append(cur)
                    merged_indexes.add(f"{node['page']}_{node['node_index']}")
                else:
                    i += 1  # 跳到下一个节点
                    print(f"{i}已经合并节点，跳过")
        else:
            i+=1
            # 最后将 cur 添加到结果中
            if cur and f"{node['page']}_{node['node_index']}" not in merged_indexes:
                merged_result.append(cur)

    return merged_result

def merge_nodes_three(merged_result):
    merged_output = []
    content = ""  # 存储累加的内容
    texts = []  # 存储所有被合并的节点文本
    cur = None  # 当前合并的节点
    is_content_started = False  # 标记是否已经开始累加内容
    content_length = 0  # 当前内容的长度
    i=-1
    for node in merged_result:
        text = node["text"]        
        i+=1
        # 如果 text 包含 <table> 字样，则不与之前的内容合并，单独处理
        if "<table>" in node["text"]:
            # 如果有正在合并的内容，先将其保存
            if cur:
                merged_output.append(cur)

            # 直接将当前节点单独保存
            cur = {
                "content": text,  # 当前节点的文本内容
                "texts": [text],  # 以列表形式存放被合并的节点文本
                "page": node["page"][0],  # 当前页面
                "pages": [node["pages"]],
                "nodes_text_len": [node["nodes_text_len"]],
                "nodes_index": [node["nodes_index"]],  # 当前节点索引
                "boxs": [node["boxs"]],
                "image_dims": [node["image_dims"]],
                "ref": [node["ref"]]
            }
            merged_output.append(cur)  # 将单独处理的节点加入结果
            cur = None  # 清空当前合并节点，准备处理下一个节点
            is_content_started = False  # 标记是否已经开始累加内容
            continue  # 跳过后续合并，直接处理下一个节点

        # 如果是以 "#" 开头的文本
        if text.startswith('#'):
            if cur:
                merged_output.append(cur)
                content=''
                content_length = 0
                texts=[]

            # 直接赋值当前节点
            content = text
            content_length = len(text)
            cur = {
                "content": text,  # 当前节点的文本内容
                "texts": [text],  # 以列表形式存放被合并的节点文本
                "page": node["page"][0],  # 当前页面
                "pages": [node["pages"]],
                "nodes_text_len": [node["nodes_text_len"]],
                "nodes_index": [node["nodes_index"]],  # 当前节点索引
                "boxs": [node["boxs"]],
                "image_dims": [node["image_dims"]],
                "ref": [node["ref"]]
            }
        else:
            if cur:
                content += "\n" + text
                content_length += len(text)

                if content_length <= 1024:
                    # 累加                    
                    cur["content"]=content
                    cur["texts"].append(text)
                    # 累加当前节点的其他数据
                    cur["pages"].append(node["pages"])
                    cur["nodes_text_len"].append(node["nodes_text_len"])
                    cur["nodes_index"].append(node["nodes_index"])
                    cur["boxs"].append(node["boxs"])
                    cur["image_dims"].append(node["image_dims"])
                    cur["ref"].append(node["ref"])
                else:
                    merged_output.append(cur)
                    content=''
                    content_length = 0
                    texts=[]
                    # 直接赋值当前节点
                    content = text
                    content_length = len(text)
                    cur = {
                        "content": text,  # 当前节点的文本内容
                        "texts": [text],  # 以列表形式存放被合并的节点文本
                        "page": node["page"][0],  # 当前页面
                        "pages": [node["pages"]],
                        "nodes_text_len": [node["nodes_text_len"]],
                        "nodes_index": [node["nodes_index"]],  # 当前节点索引
                        "boxs": [node["boxs"]],
                        "image_dims": [node["image_dims"]],
                        "ref": [node["ref"]]
                    }

            else:
                # 直接赋值当前节点
                content = text
                content_length = len(text)
                cur = {
                    "content": text,  # 当前节点的文本内容
                    "texts": [text],  # 以列表形式存放被合并的节点文本
                    "page": node["page"][0],  # 当前页面
                    "pages": [node["pages"]],
                    "nodes_text_len": [node["nodes_text_len"]],
                    "nodes_index": [node["nodes_index"]],  # 当前节点索引
                    "boxs": [node["boxs"]],
                    "image_dims": [node["image_dims"]],
                    "ref": [node["ref"]]
                }

    # 将最后剩余的合并节点添加到结果中
    if cur:
        cur["content"]=content
        merged_output.append(cur)

    return merged_output  


def save_to_json(data, output_file):
    """Save the merged data to JSON"""
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    print(f"Data saved to {output_file}")


# ------------------------------------------------
# Main workflow functions
# ------------------------------------------------

def convert_pdf_to_images(pdf_file, target_path):
    images_folder = os.path.join(target_path, "pdf-1-images")
    pdf_to_images(pdf_file, images_folder)


def process_images_to_json(target_path):
    images_folder = os.path.join(target_path, "pdf-1-images")
    json_folder = os.path.join(target_path, "pdf-2-json")
    process_files_to_json(images_folder, json_folder)


def merge_json_to_mk(target_path):
    json_folder = os.path.join(target_path, "pdf-2-json")
    mk_folder = os.path.join(target_path, "pdf-3-mk")
    

    path_mk_dist = mk_folder  # 目标文件夹路径
    folder = json_folder  # "./ocr_jsons"
    pages = []

    pages=process_json_files(folder)

    # 2. 合并段落
    paragraphs = merge_pages(pages)    

    # 4. 将合并后的文本写入 .md 文件
    save_to_md(paragraphs, os.path.join(path_mk_dist, "output.md"))
    print(f"保存合并后的文本成功{os.path.join(path_mk_dist, 'output.md')}")

    #5.保存合并结果到 JSON 文件
    write_paragraphs_to_json(paragraphs, os.path.join(path_mk_dist, "processed_data_ocr.json"))
    print(f"保存合并后的段落成功{os.path.join(path_mk_dist, 'processed_data_ocr.json')}")

    # 合并节点
    merged_nodes = merge_nodes(pages)

    # 将合并后的节点写入 JSON 文件
    save_nodes_to_json(merged_nodes, os.path.join(path_mk_dist, 'processed_data_nodes.json'))
 
    # 合并后的节点记录（通过 should_merge 判断）
    merged_result = merge_nodes_two(merged_nodes)

    # 将合并后的节点写入 JSON 文件
    save_merged_nodes_to_json(merged_result, os.path.join(path_mk_dist,'processed_merged_nodes.json'))

    #合并节点
    merged_output=merge_nodes_three(merged_result)
    save_merged_nodes_to_json_three(merged_output, os.path.join(path_mk_dist,'processed_merged_nodes_three.json'))


#2026.03.23 添加pyMuPdf文件读取Json数据Begin
def extract_pdf_to_json(pdf_path, output_dir):
    # 如果输出目录不存在，则创建
    os.makedirs(output_dir, exist_ok=True)    

    print(f"正在打开 PDF 文件: {pdf_path}")
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        print(f"无法打开 PDF 文件，错误信息: {e}")
        return

    total_pages = len(doc)
    print(f"共发现 {total_pages} 页。开始提取...")

    for page_num in range(total_pages):
        page = doc[page_num]
        
        # 使用 "dict" 模式提取，可以获取字体大小、上标等更丰富的排版信息
        dict_data = page.get_text("dict")
        blocks = dict_data.get("blocks", [])

        page_data = {
            "page": page_num + 1,
            "width": page.rect.width,
            "height": page.rect.height,
            "blocks": []
        }
        
        # 建立 a-t 到 ①-⑳ 的映射字典
        CIRCLE_MAP = {
            'a': '①', 'b': '②', 'c': '③', 'd': '④', 'e': '⑤', 
            'f': '⑥', 'g': '⑦', 'h': '⑧', 'i': '⑨', 'j': '⑩',
            'k': '⑪', 'l': '⑫', 'm': '⑬', 'n': '⑭', 'o': '⑮',
            'p': '⑯', 'q': '⑰', 'r': '⑱', 's': '⑲', 't': '⑳'
        }

        for b in blocks:
            # type == 0 代表文本块
            if b.get("type") == 0:
                block_text = ""
                lines = b.get("lines", [])
                
                # 判断整个block是否包含中文，作为上下文辅助判断
                block_has_chinese = any('\u4e00' <= c <= '\u9fff' for l in lines for s in l.get("spans", []) for c in s.get("text", ""))
                
                for line in lines:
                    line_text = ""
                    spans = line.get("spans", [])
                    if not spans:
                        continue
                    
                    max_size = max((s.get("size", 10) for s in spans), default=10)
                    line_bbox = line.get("bbox", [0,0,0,0])
                    
                    for i, span in enumerate(spans):
                        text = span.get("text", "")
                        clean_text = text.strip()
                        
                        # 启发式：处理脚注图标被错误识别为 a, b, c 的问题
                        # 检查是否全部由字母组成（可能有空格）
                        if clean_text and all(c.isspace() or ('a' <= c.lower() <= 'z') for c in clean_text):
                            is_superscript = (span.get("flags", 0) & 1) != 0
                            span_bbox = span.get("bbox", [0,0,0,0])
                            
                            # 判断是否字体更小且位置偏上（典型上标特征）
                            is_smaller_and_higher = (span.get("size", 10) < max_size * 0.95) and (span_bbox[3] < line_bbox[3] - max_size * 0.1)
                            
                            # 判断是否位于页面底部的行首（典型脚注说明特征）
                            is_footnote_bottom = (i == 0 and block_has_chinese and line_bbox[1] > page.rect.height * 0.7)
                            
                            # 判断是否为特殊符号字体
                            font_lower = span.get("font", "").lower()
                            font_is_symbol = any(x in font_lower for x in ['symbol', 'wingding', 'dingbat', 'ropesequencenumber'])

                            
                            if is_superscript or is_smaller_and_higher or is_footnote_bottom or font_is_symbol:
                                new_text = ""
                                for c in text:
                                    if 'a' <= c.lower() <= 'z':
                                        new_text += CIRCLE_MAP.get(c.lower(), c)
                                    else:
                                        new_text += c
                                text = new_text
                        
                        # 补充空格逻辑：恢复英文单词之间的自然间距
                        if i > 0:
                            prev_span = spans[i-1]
                            gap = span.get("bbox", [0,0,0,0])[0] - prev_span.get("bbox", [0,0,0,0])[2]
                            if gap > max_size * 0.2:
                                prev_char = prev_span.get("text", "")[-1:]
                                curr_char = text[:1]
                                # 如果前后都不是中文，则补充空格
                                if prev_char and curr_char:
                                    if not ('\u4e00' <= prev_char <= '\u9fff' or '\u4e00' <= curr_char <= '\u9fff'):
                                        line_text += " "

                        line_text += text
                        
                    block_text += line_text + "\n"
                    
                block_text = block_text.strip()
                if block_text:
                    page_data["blocks"].append({
                        "bbox": b.get("bbox"),
                        "text": block_text
                    })

        # 按页码生成 json 文件名 (例如: 1.json)
        json_filename = os.path.join(output_dir, f"{page_num + 1}.json")
        
        with open(json_filename, 'w', encoding='utf-8') as f:
            json.dump(page_data, f, ensure_ascii=False, indent=4)

    doc.close()
    print(f"提取完成！所有 JSON 文件已保存至: {output_dir}")

'''
2026.03.23
函数：merge_py_json_to_ds_json
ds_json_folder -deepseek-ocr识别出来的json文件
py_json_folder -python识别出来的json文件
output_folder -合并后的json文件保存路径 （路径为：pdf-2-json-py-to-ds）
'''
def merge_py_json_to_ds_json(ds_json_folder, py_json_folder, output_folder):
    os.makedirs(output_folder, exist_ok=True)
    
    import copy
    
    for filename in os.listdir(ds_json_folder):
        if not filename.endswith('.json'):
            continue
            
        ds_path = os.path.join(ds_json_folder, filename)
        py_path = os.path.join(py_json_folder, filename)
        out_path = os.path.join(output_folder, filename)
        
        if not os.path.exists(py_path):
            print(f"警告: 找不到对应的 py_json 文件 {py_path}")
            continue
            
        try:
            with open(ds_path, 'r', encoding='utf-8') as f:
                ds_data = json.load(f)
            with open(py_path, 'r', encoding='utf-8') as f:
                py_data = json.load(f)
                
            # 读取尺寸
            image_dims = ds_data.get("image_dims", {})
            if isinstance(image_dims, list) and len(image_dims) > 0:
                image_dims = image_dims[0]
            
            ds_w = image_dims.get("w", 1024)
            ds_h = image_dims.get("h", 1024)
            
            py_w = py_data.get("width", 1)
            py_h = py_data.get("height", 1)
            
            # 计算缩放比例 (将 py 坐标转为 ds 坐标)
            scale_x = ds_w / py_w
            scale_y = ds_h / py_h
            
            # 转换 py_json 中的 bbox
            py_blocks = py_data.get("blocks", [])
            for block in py_blocks:
                bbox = block.get("bbox")
                if bbox and len(bbox) == 4:
                    block["ds_bbox"] = [
                        bbox[0] * scale_x,
                        bbox[1] * scale_y,
                        bbox[2] * scale_x,
                        bbox[3] * scale_y
                    ]
            
            # 遍历 ds_json 中的 boxes
            ds_boxes = ds_data.get("boxes", [])
            for box_obj in ds_boxes:
                # 兼容字典格式或直接数组格式
                is_dict = isinstance(box_obj, dict)
                bbox = box_obj.get("box") if is_dict else box_obj
                
                if bbox and len(bbox) == 4:
                    # 将 box 中的左上角的x,y的值减小5，右下角的x,y的值加大5
                    target_box = [
                        bbox[0] - 5,
                        bbox[1] - 5,
                        bbox[2] + 5,
                        bbox[3] + 5
                    ]
                    
                    matches = []
                    # 从 py_json 中寻找落在 target_box 内的文本块
                    for p_block in py_blocks:
                        p_bbox = p_block.get("ds_bbox")
                        if p_bbox:
                            if is_contained_or_overlap(p_bbox, target_box):
                                matches.append(p_block)
                                
                    # 排序：首先按 ds_bbox[1] 升序，其次按 ds_bbox[0] 升序
                    #matches.sort(key=lambda x: (x["ds_bbox"][1], x["ds_bbox"][0]))
                    
                    # 链接 text
                    combined_text = "".join([m.get("text", "") for m in matches])
                    
                    # 写入到与 box 属性平级的节点中
                    if is_dict:
                        box_obj["text_content"] = combined_text
                    else:
                        # 如果原来直接是数组，无法添加平级属性，这里为了保持结构可能需要修改原数据结构
                        # 但根据提示，通常是字典 {"label": "...", "box": [...]}
                        pass 
                        
            # 保存新文件
            with open(out_path, 'w', encoding='utf-8') as f:
                json.dump(ds_data, f, ensure_ascii=False, indent=4)
                
            print(f"合并完成并保存: {out_path}")
            
        except Exception as e:
            print(f"处理文件 {filename} 时发生错误: {e}")

def is_contained_or_overlap(cand_box, target_box):
    # cand_box: [x0, y0, x1, y1]
    # target_box: [X0, Y0, X1, Y1]
    
    # Relaxed containment: Center of cand is inside target
    cx = (cand_box[0] + cand_box[2]) / 2
    cy = (cand_box[1] + cand_box[3]) / 2
    
    if (target_box[0] <= cx <= target_box[2] and 
        target_box[1] <= cy <= target_box[3]):
        return True
        
    return False

def merge_json_to_mk_py_to_ds(target_path):
    json_folder = os.path.join(target_path, "pdf-2-json-py-to-ds")
    mk_folder = os.path.join(target_path, "pdf-3-mk")
    

    path_mk_dist = mk_folder  # 目标文件夹路径
    folder = json_folder  # "./ocr_jsons"
    pages = []

    pages=process_json_files_ds_to_py(folder)

    # 2. 合并段落
    paragraphs = merge_pages(pages)    

    # 4. 将合并后的文本写入 .md 文件
    save_to_md(paragraphs, os.path.join(path_mk_dist, "output-py-to-ds.md"))
    print(f"保存合并后的文本成功{os.path.join(path_mk_dist, 'output-py-to-ds.md')}")

    #5.保存合并结果到 JSON 文件
    write_paragraphs_to_json(paragraphs, os.path.join(path_mk_dist, "processed_data_ocr-py-to-ds.json"))
    print(f"保存合并后的段落成功{os.path.join(path_mk_dist, 'processed_data_ocr-py-to-ds.json')}")

    # 合并节点
    merged_nodes = merge_nodes(pages)

    # 将合并后的节点写入 JSON 文件
    save_nodes_to_json(merged_nodes, os.path.join(path_mk_dist, 'processed_data_nodes-py-to-ds.json'))
 
    # 合并后的节点记录（通过 should_merge 判断）
    merged_result = merge_nodes_two(merged_nodes)

    # 将合并后的节点写入 JSON 文件
    save_merged_nodes_to_json(merged_result, os.path.join(path_mk_dist,'processed_merged_nodes-py-to-ds.json'))

    #合并节点
    merged_output=merge_nodes_three(merged_result)
    save_merged_nodes_to_json_three(merged_output, os.path.join(path_mk_dist,'processed_merged_nodes_three-py-to-ds.json'))    

'''
2026.03.23
'''

def process_json_files_ds_to_py(folder):
    pages = []
    
    # 获取目录下所有.json文件，并按文件名排序
    json_files = sorted(
        [f for f in os.listdir(folder) if f.endswith(".json")],
        key=lambda x: int(x.split('.')[0]) if x.split('.')[0].isdigit() else 0  # 按文件名数字排序
    )

    # 遍历排序后的文件，执行load_ocr_file
    for filename in json_files:
        path = os.path.join(folder, filename)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        p = load_ocr_file_ds_to_py(data, filename)
        pages.append(p)
    
    return pages

def load_ocr_file_ds_to_py(json_data, filename):
    raw_text = json_data["raw_text"]  # 从 raw_text 中提取

    # 使用 "<|ref|>" 作为分割符号拆分 raw_text
    parts = raw_text.split('<|ref|>')

    nodes = []
    ref_idx = 0
    det_idx = 0
    box_text_all = ''
    page_text_len = 0
    boxes = json_data.get("boxes", [])  # 获取 OCR 识别的框数据

    image_dims = json_data.get("image_dims", {"w": 1191, "h": 1684})  # 获取图片的宽高
    scale_ratio_w = image_dims["w"]   # 计算缩放比例
    scale_ratio_h = image_dims["h"]   # 计算缩放比例

    # 解析各个部分
    for part in parts[1:]:  # 跳过第一个空部分（split 后的第一个部分为空）
        ref_part = re.match(r"(.*?)(<\|det\|>\[\[(.*?)\]\]<\|/det\|>)(.*)", part, re.DOTALL)
        
        if ref_part:
            ref_text = ref_part.group(1).strip() if ref_part.group(1) else ""  # 提取 ref 内容
            ref_text = ref_text.replace("<|/ref|>", "")  # 去除 ref_text 中的 "<|/ref|>"
            det_data = ref_part.group(3).strip() if ref_part.group(3) else ""  # 提取 det 内容
            deepseek_ocr_text = ref_part.group(4).strip() if ref_part.group(4) else ""  # 剩余文本（去除 <|det|> 部分）

            # 如果没有找到 det 数据，则跳过当前部分
            if not det_data:
                continue
            
            # 解析坐标数据
            try:
                box = list(map(int, det_data.split(',')))  # 将坐标字符串转化为整数列表
                # 等比例缩放每个坐标
                #box = [int(coord * scale_ratio) for coord in box]
                box[0] = int(float(box[0]) / 999 * scale_ratio_w)
                box[1] = int(float(box[1]) / 999 * scale_ratio_h)
                box[2] = int(float(box[2]) / 999 * scale_ratio_w)
                box[3] = int(float(box[3]) / 999 * scale_ratio_h)
            except ValueError:
                continue  # 如果解析失败，则跳过

            # 查找对应的 text_content
            box_label='text' #默认文本时类型是：text 其他还有"title" "sub_title"
            for box_entry in boxes:
                if box_entry['box'] == box:
                    box_text = box_entry.get('text_content', '')  # 获取对应的 text_content                    
                    
                    box_label=box_entry.get('label', 'text') #获取box中文本的类型 2026.03.24 添加markdown的标志
                    #2026.03.24 发现pymupdf在读取pdf文件的文字的时候，如果是图片，无法读取到对应得文字信息 导致 box_text为空,此时还是用deepseek_ocr的识别结果
                    if box_text == '':
                        box_text = deepseek_ocr_text
                    else:
                        if box_label=='title':
                            box_text="\r\n#"+box_text
                        elif box_label=='sub_title':
                            box_text="\r\n##"+box_text
                        elif box_label=='image': #2026.03.24 如果此区域被deepseek_ocr识别为图片，则忽略此区域（暂无文字）
                            box_text="\r\n"
                    #2026.03.24 将box_text中的”特殊空格“替换为”普通空格“”
                    box_text = box_text.replace(' ', ' ')
                    box_text = box_text.replace('', ' ')
                    box_text = box_text.replace('', ' ')
                    
                    #2026.03.24 保留ds的排版格式，吸取pymupdf的正确数据
                    box_text=merge_text(deepseek_ocr_text,box_text)

                    #2026.03.24 deepseek_ocr_text 内容里面包含""<table><tr><td>""，则保留ds的数据格式
                    if deepseek_ocr_text and "<table><tr><td>" in deepseek_ocr_text:
                        box_text = deepseek_ocr_text

            # 生成节点
            nodes.append({
                "filename": filename,
                "page": filename.replace('.json', ''),
                "node_index": ref_idx,
                "text_len": len(box_text),  # 存放纯文本长度
                "ref": ref_text,  # 存储 <|ref|> 标签内容
                "box": box,  # 存储坐标数据
                "text": box_text  # 剩余的纯文本   
            })
            
            if box_text_all == '':
                box_text_all = box_text
            else:
                box_text_all += '\n' + box_text

            ref_idx += 1

    page_text_len += len(box_text_all)
    
    return {
        "filename": filename,
        "page": filename.replace('.json', ''),
        "page_text_len": page_text_len,  # 当前页的纯文本长度
        "image_dims": json_data.get("image_dims", {"w": 1191, "h": 1684}),
        "box_text_all": box_text_all,  # full_text 使用 text
        "nodes": nodes        
    }    

def merge_text_v1(deepseek_ocr_text: str, box_text: str) -> str:
    """
    合并 DeepSeek OCR 识别的文本与 PyMuPDF 提取的文本（box_text）。
    
    规则：
    1. deepseek_ocr_text 提供了正确的控制符号（如空格、回车、换行等），但可能有错别字。
    2. box_text 提供了正确的文本内容，但控制符号（排版）可能混乱或不正确。
    3. 将 box_text 中的真实字符按顺序“填入” deepseek_ocr_text 的排版骨架中。
    
    :param deepseek_ocr_text: 包含正确排版但可能有错别字的字符串
    :param box_text: 包含正确文字但排版可能有误的字符串
    :return: 合并后的字符串
    """
    
    # 提取 box_text 中所有非空白字符，作为“正确字符”的来源队列
    # 使用 \s 匹配所有空白字符（包括空格、\n、\r、\t 等），并将其过滤掉
    box_chars = [char for char in box_text if not char.isspace()]
    box_len = len(box_chars)
    box_idx = 0
    
    result = []
    
    # 遍历带有正确控制符号的 deepseek_ocr_text
    for char in deepseek_ocr_text:
        if char.isspace():
            # 如果是空白/控制符号（空格、换行等），直接保留 DeepSeek 的格式
            result.append(char)
        else:
            # 如果是实际可见字符，则从 box_text 提取正确的字符进行替换
            if box_idx < box_len:
                result.append(box_chars[box_idx])
                box_idx += 1
            else:
                # 如果 box_text 的字符已经用完，但 deepseek 还有多余字符，则保留 deepseek 原字符（兜底容错）
                result.append(char)
                
    # 如果 deepseek_ocr_text 遍历完后，box_text 还有剩余未填入的字符，则将其追加到末尾
    if box_idx < box_len:
        result.append("".join(box_chars[box_idx:]))
        
    return "".join(result)

#保留ds的排版格式，吸取pymupdf的正确数据 2026.03.24
def merge_text(deepseek_ocr_text: str, box_text: str) -> str:
    """
    合并 DeepSeek OCR 识别的文本与 PyMuPDF 提取的文本（box_text）。
    
    规则：
    1. deepseek_ocr_text 提供了正确的控制符号（如空格、回车、换行等），但可能有错别字（或多字、少字）。
    2. box_text 提供了正确的文本内容，但控制符号（排版）可能混乱或不正确。
    3. 使用 difflib 进行序列对齐，将 box_text 中的真实字符“智能填入” deepseek_ocr_text 的排版骨架中，避免因字数不一致导致的错位。
    
    :param deepseek_ocr_text: 包含正确排版但可能有错别字的字符串
    :param box_text: 包含正确文字但排版可能有误的字符串
    :return: 合并后的字符串
    """
    
    # 提取非空字符并记录其在 deepseek_ocr_text 中的原始索引
    ds_seq = []
    ds_pos_map = []
    for i, char in enumerate(deepseek_ocr_text):
        if not char.isspace():
            ds_seq.append(char)
            ds_pos_map.append(i)
            
    # 提取 box_text 中的非空字符序列
    box_seq = [char for char in box_text if not char.isspace()]
    
    # 使用 difflib 寻找最长公共子序列（对齐两个纯字符序列）
    sm = difflib.SequenceMatcher(None, ds_seq, box_seq)
    
    result = []
    last_ds_idx = 0
    
    # 辅助函数：将 deepseek_ocr_text 中被跳过的控制符号（空格、换行）补齐
    def catch_up_spaces(target_idx):
        nonlocal last_ds_idx
        while last_ds_idx < target_idx:
            if deepseek_ocr_text[last_ds_idx].isspace():
                result.append(deepseek_ocr_text[last_ds_idx])
            last_ds_idx += 1

    # 根据对齐结果进行合并
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            # 完全匹配，填入 box 的字符，并保留对应位置的空格
            for k in range(i2 - i1):
                ds_idx = ds_pos_map[i1 + k]
                catch_up_spaces(ds_idx)
                result.append(box_seq[j1 + k])
                last_ds_idx = ds_idx + 1
                
        elif tag == 'replace':
            # 替换：可能字符数不同。先补齐第一个字符前的空格
            if i1 < i2:
                catch_up_spaces(ds_pos_map[i1])
            
            box_idx = j1
            if i1 < i2:
                ds_idx_start = ds_pos_map[i1]
                ds_idx_end = ds_pos_map[i2 - 1] + 1
                
                # 遍历 ds 这段区间，遇到可见字符就尝试用 box 字符替换，遇到空格则保留
                for idx in range(ds_idx_start, ds_idx_end):
                    if deepseek_ocr_text[idx].isspace():
                        result.append(deepseek_ocr_text[idx])
                    else:
                        if box_idx < j2:
                            result.append(box_seq[box_idx])
                            box_idx += 1
                last_ds_idx = ds_idx_end
                
            # 如果 ds 的槽位用完了，box 还有多余的替换字符，直接追加
            while box_idx < j2:
                result.append(box_seq[box_idx])
                box_idx += 1
                
        elif tag == 'delete':
            # 删除：ds 中多余的字符（例如 OCR 幻觉产生的多余字符）。
            # 不输出字符，但要保留这段区间内的空格
            if i1 < i2:
                ds_idx_start = ds_pos_map[i1]
                ds_idx_end = ds_pos_map[i2 - 1] + 1
                catch_up_spaces(ds_idx_start)
                for idx in range(ds_idx_start, ds_idx_end):
                    if deepseek_ocr_text[idx].isspace():
                        result.append(deepseek_ocr_text[idx])
                last_ds_idx = ds_idx_end
                
        elif tag == 'insert':
            # 插入：box 中多出来的字符。
            # 直接在当前位置插入，先补齐到当前位置的空格
            if i1 < len(ds_pos_map):
                catch_up_spaces(ds_pos_map[i1])
            else:
                catch_up_spaces(len(deepseek_ocr_text))
            
            for k in range(j2 - j1):
                result.append(box_seq[j1 + k])

    # 补齐末尾可能剩余的控制符号
    catch_up_spaces(len(deepseek_ocr_text))
    
    return "".join(result)
#2026.03.23 添加pyMuPdf文件读取Json数据End

#2026.03.25 页内内容合并--begin
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

def merge_paragraph_blocks(json_data,input_filename):
    """
    根据页面布局，将属于同一个段落的相邻区块文字链接到一起。
    """
    if "boxes" not in json_data:
        return json_data

    #从input_filename中得到的对应的page的值
    page_num=input_filename.replace(".json","")
        
    page_width = json_data.get("image_dims", {}).get("w", 1024)
    page_height = json_data.get("image_dims", {}).get("h", 1024)
    
    original_boxes = json_data["boxes"]
    merged_boxes = []
    #merged_pages=[]

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
                
                # 2. 并且满足以下布局特征之一：
                #   a. 跨栏：两者的 X 坐标差异较大
                is_cross_column = abs(cb[0] - nb[0]) > page_width * 0.05
                #   b. 跨页底：前一个区块已经接近页面底部
                is_bottom_of_page = cb[3] > page_height * 0.85
                #   c. 被非文本区块（如图片、表格）物理截断
                is_separated = separated_by_non_text
                
                if is_cut_off and (is_cross_column or is_bottom_of_page or is_separated):
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
                    #pending_text_block["merged_pages"].append(page_num) #添加合并块对应的页码
                    
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

#添加遍历文件夹文件的主函数
'''
for filename in os.listdir(ds_json_folder):
        if not filename.endswith('.json'):
            continue
'''

def merge_py_json_to_ds_json_curpage_process_file(input_filename, output_filename):
    input_path=input_filename
    output_path=output_filename
    print(f"Reading from {input_path}")
    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    new_data = merge_paragraph_blocks(data,input_filename)
    
    print(f"Writing to {output_path}")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(new_data, f, ensure_ascii=False, indent=4)
    print("Done!")

def merge_py_json_to_ds_json_curpage(merged_output_folder,merged_output_folder_curpage_merged):
    
    os.makedirs(merged_output_folder_curpage_merged, exist_ok=True)

    for filename in os.listdir(merged_output_folder):
        if not filename.endswith('.json'):
            continue
        source_path = os.path.join(merged_output_folder, filename)
        dist_path = os.path.join(merged_output_folder_curpage_merged, filename)
        merge_py_json_to_ds_json_curpage_process_file(source_path, dist_path)

'''
#2026.03.25 将当前页面中内容并的数据，进行合并
'''
def merge_json_to_mk_py_to_ds_curpage(target_path):
    json_folder = os.path.join(target_path, "pdf-2-json-py-to-ds-curpage-merged") #读取数据的目录
    mk_folder = os.path.join(target_path, "pdf-3-mk")#合并后结果存放的目录
    

    path_mk_dist = mk_folder  # 目标文件夹路径
    folder = json_folder  # "./ocr_jsons"
    pages = []

    #pdf-2-json-py-to-ds-curpage-merged 中的json格式有所调整，添加了当前页面内的内容合并功能，需要通过-2026.03.31
    pages = process_json_files_ds_to_py_curpage(folder)

    # 2.跨页合并
    paragraphs = merge_pages(pages)    

    # 4. 将合并后的文本写入 .md 文件
    save_to_md(paragraphs, os.path.join(path_mk_dist, "output-py-to-ds-curpage-merged.md"))
    print(f"保存合并后的文本成功{os.path.join(path_mk_dist, 'output-py-to-ds-curpage-merged.md')}")

    # 5.保存合并结果到 JSON 文件
    write_paragraphs_to_json(paragraphs, os.path.join(path_mk_dist, "processed_data_ocr-py-to-ds-curpage-merged.json"))
    print(f"保存合并后的段落成功{os.path.join(path_mk_dist, 'processed_data_ocr-py-to-ds-curpage-merged.json')}")

    # 将 pages 中的 nodes 的内容读取出来到 merged_nodes
    merged_nodes = merge_nodes(pages)

    # 将合并后的节点写入 JSON 文件
    save_nodes_to_json(merged_nodes, os.path.join(path_mk_dist, 'processed_data_nodes-py-to-ds-curpage-merged.json'))
 
    # 合并后的节点记录（通过 should_merge 判断跨页合并）
    merged_result = merge_nodes_two(merged_nodes)

    # 将合并后的节点写入 JSON 文件
    save_merged_nodes_to_json(merged_result, os.path.join(path_mk_dist, 'processed_merged_nodes-py-to-ds-curpage-merged.json'))

    # 合并节点（主要是合并节点，让 content 的值尽量长约 1024 个长度）
    merged_output = merge_nodes_three(merged_result)
    save_merged_nodes_to_json_three(merged_output, os.path.join(path_mk_dist, 'processed_merged_nodes_three-py-to-ds-curpage-merged.json'))   


'''
2026.03.25
'''

def process_json_files_ds_to_py_curpage(folder):
    pages = []
    
    # 获取目录下所有.json文件，并按文件名排序
    json_files = sorted(
        [f for f in os.listdir(folder) if f.endswith(".json")],
        key=lambda x: int(x.split('.')[0]) if x.split('.')[0].isdigit() else 0  # 按文件名数字排序
    )

    # 遍历排序后的文件，执行load_ocr_file
    for filename in json_files:
        path = os.path.join(folder, filename)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        p = load_ocr_file_ds_to_py_curpage(data, filename)
        pages.append(p)
    
    return pages

'''
2026.03.30 读取文件夹：pdf-2-json-py-to-ds-curpage-merged （单页不同栏之间合并过的数据)
'''
def load_ocr_file_ds_to_py_curpage_v1(json_data, filename):
    nodes = []
    ref_idx = 0
    box_text_all = ''
    page_text_len = 0

    # 遍历 json_data 中的 "boxes" 节点
    for box_data in json_data.get("boxes", []):
        text_content = box_data.get("text_content", "")  # 获取文本内容
        box = box_data.get("box", [])  # 获取当前节点的坐标信息
        merged_boxes = box_data.get("merged_boxes", None)  # 获取 merged_boxes
        merged_text_lens = box_data.get("merged_text_lens", None)  # 获取 merged_text_lens

        # 如果有 merged_boxes 和 merged_text_lens，使用它们代替原始 box 和 text_len
        if merged_boxes and merged_text_lens:
            for idx, merged_box in enumerate(merged_boxes):
                # 确保 merged_box 中的坐标是整数类型
                merged_box = [int(coord) for coord in merged_box]
                nodes.append({
                    "filename": filename,
                    "page": filename.replace('.json', ''),
                    "node_index": ref_idx + idx,  # 对应每一个合并的 box，ref_idx 增加
                    "text_len": merged_text_lens[idx],  # 对应合并后的文本长度
                    "ref": text_content.strip(),  # 存储文本内容
                    "box": merged_box,  # 使用 merged_box 作为坐标数据，确保是数字格式
                    "text": text_content.strip()  # 存储文本内容
                })
                # 更新文本长度
                page_text_len += merged_text_lens[idx]
            ref_idx += len(merged_boxes)
        else:
            # 处理单个 box 的情况，确保 box 中的坐标是整数类型
            box = [int(coord) for coord in box]
            nodes.append({
                "filename": filename,
                "page": filename.replace('.json', ''),
                "node_index": ref_idx,  # 对应当前的 ref_idx
                "text_len": len(text_content),  # 使用原文本内容的长度
                "ref": text_content.strip(),  # 存储文本内容
                "box": box,  # 使用原始的 box 坐标数据，确保是数字格式
                "text": text_content.strip()  # 存储文本内容
            })
            page_text_len += len(text_content)
            ref_idx += 1
        
        # 拼接所有文本内容
        if box_text_all == '':
            box_text_all = text_content.strip()
        else:
            box_text_all += '\n' + text_content.strip()

    return {
        "filename": filename,
        "page": filename.replace('.json', ''),
        "page_text_len": page_text_len,  # 当前页的纯文本长度
        "image_dims": json_data.get("image_dims", {"w": 1191, "h": 1684}),
        "box_text_all": box_text_all,  # 所有文本内容的合并
        "nodes": nodes
    }

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
#2026.03.25 页内内容合并--end

#2026.03.31-对结果数据中的“节点过度嵌套”进行结构优化 -begin
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

def merged_format_process_file(input_path, output_path):
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

'''
if __name__ == "__main__":
    input_file = r"C:\gzb_file_to_github\P2_Pdf_To_Markdown\test_json\processed_merged_nodes_three-py-to-ds-curpage-merged.json"
    output_file = r"C:\gzb_file_to_github\P2_Pdf_To_Markdown\test_json\processed_merged_nodes_three-py-to-ds-curpage-merged_format.json"
    merged_format_process_file(input_file, output_file)
'''    
#2026.03.31-对结果数据中的“节点过度嵌套”进行结构优化 -end
'''
2025.11.17 遍历Pdf文件，将pdf转换为图片，调用deepseek-ocr进行识别，按页转换为markdown格式，之后进行页面内容合并

ai审稿--

pdf-to-image 
image-to-markdown
markdown-to-process-data （带pagenum的json数据。做段落或者跨页合并的处理；--如果跨页合并--pages[1,2,3]  len）

'''

import os
import json
import re
#import datetime
import hashlib
from pydantic import BaseModel, Field, field_validator
from datetime import datetime, timedelta
from typing import List
from docx import Document
import requests
from dataclasses import dataclass
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import base64

import shutil
import time
from Fun.Fun_OCR_Pdf_To_MarkDown_v3 import convert_pdf_to_images, process_images_to_json, merge_json_to_mk,extract_pdf_to_json,merge_py_json_to_ds_json,merge_json_to_mk_py_to_ds,merge_py_json_to_ds_json_curpage,merge_json_to_mk_py_to_ds_curpage,merged_format_process_file,process_pdf_2_json_py_to_ds_to_b
import logging

import fitz  # PyMuPDF 2026.03.23

path_word_spit=f"E:\\faxin_ai_2023\\branches\\faxin_ai_uie_2023\\39_book_check_v2\\1_web_book_check_v2\\1_Server\\fastapi-auth-app\\"
#path_word_spit=f"/faxin/core/book_check/1_Server/fastapi-auth-app/"

path_check_log=f"E:\\faxin_ai_2023\\branches\\faxin_ai_uie_2023\\39_book_check_v2\\1_web_book_check_v2\\2_Server_Check\\"
#path_check_log=f"/faxin/core/book_check/2_Server_Check/"

path_book_check_dist="check_book" #存用户的文件，被大模型分析后的json文件保存的目录（每个文件夹以文件的md5值为文件夹名称，之后创建多个不同的文件夹，存放不同的模型分析的数据结果）
path_book_source="uploads" #存放用户上传的文件保存的目录，每个用户以用户名称创建对应的文件夹

pub_url_pdfjs_service="http://192.168.5.109:3008/pdfAnalysis/content?url=" #2025.08.05添加
#开发的测试地址
pub_url_get_pdf_file="http://192.168.0.159/api/get_pdf_file_by_md5/" #2025.08.01 此url 为 获取pdf文件的接口地址（为让pdfjs服务从这个地址获取要进行分析的pdf的文件）
#正式发布的线上地址
#pub_url_get_pdf_file="http://192.168.5.96:3002/api/get_pdf_file_by_md5/" #2025.08.01 此url 为 获取pdf文件的接口地址（为让pdfjs服务从这个地址获取要进行分析的pdf的文件）

# 全局密钥（16字节）
pub_fileid_info_key = b"ai_cbs_2025__key"  # 补足16位

#2025.10.28 文件字数统计-Begin

def count_text_length_from_json(json_file_name):
    """
    读取指定的 JSON 文件，统计所有 type 不是 'image' 的 content 字数。
    
    返回：
        (0, "文件不存在")       —— 文件不存在
        (字数总和, "统计成功")  —— 统计成功
        (0, "文件格式错误")     —— JSON 格式不正确
    """
    if not os.path.exists(json_file_name):
        return 0, "文件不存在"

    try:
        with open(json_file_name, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return 0, "文件格式错误"

    if not isinstance(data, list):
        return 0, "文件格式错误"

    total_chars = 0
    for item in data:
        if isinstance(item, dict) and item.get("type") != "image":
            content = item.get("content", "")
            if isinstance(content, str):
                total_chars += len(content)

    return total_chars, "统计成功"

def write_total_chars_json(file_path, total_chars):
    """
    在指定路径下创建 file_chars.json 文件，内容为 {"total_chars": total_chars}

    参数：
        file_path (str): 保存文件的目录路径
        total_chars (int): 总字数

    返回：
        True  —— 创建成功
        False —— 创建失败
    """
    try:
        # 确保目录存在
        os.makedirs(file_path, exist_ok=True)

        # 目标文件路径
        target_file = os.path.join(file_path, "file_chars.json")

        # 写入内容
        with open(target_file, "w", encoding="utf-8") as f:
            json.dump({"total_chars": total_chars}, f, ensure_ascii=False, indent=4)

        return True
    except Exception as e:
        print(f"写入 file_chars.json 失败: {e}")
        return False   


def rec_file_total_chars(file_path):
    """
    统计指定路径下 processed_data.json 的总字数，
    并将结果写入 file_chars.json 文件。

    参数：
        file_path (str): 目录路径

    流程：
        1. 调用 count_text_length_from_json 统计字数
        2. 调用 write_total_chars_json 写入结果

    返回：
        (True, "统计并写入成功") —— 成功
        (False, "文件不存在或格式错误") —— 文件不存在或格式错误
        (False, "写入失败") —— 写入 file_chars.json 失败
    """

    # 构造 processed_data.json 文件路径
    processed_data_file = os.path.join(file_path, "processed_data.json")

    # 调用统计函数
    total_chars, msg = count_text_length_from_json(processed_data_file)
    if total_chars == 0 and msg != "统计成功":
        return False, msg  # 文件不存在或格式错误

    # 调用写入函数
    ok = write_total_chars_json(file_path, total_chars)
    if ok:
        return True, "统计并写入成功"
    else:
        return False, "写入失败"

#2025.10.28 文件字数统计-End
    
def process_all_processed_data_to_file_chars(base_path):
    """
    遍历 base_path 下所有子目录，
    找到包含 '1_Json' 子目录的路径，
    调用 rec_file_total_chars()，
    并输出执行结果。

    参数：
        base_path (str): 要遍历的根目录路径
    """
    # 遍历所有子目录
    for root, dirs, files in os.walk(base_path):
        if "1_Json" in dirs:
            json_dir_path = os.path.join(root, "1_Json")
            print(f"\n正在处理目录: {json_dir_path}")

            # 调用统计函数
            result = rec_file_total_chars(json_dir_path)

            # 输出结果
            print(f"处理结果: {result}")


def process_tongji_file_chars_file_path(base_path):
    """
    遍历 base_path 下所有包含 '1_Json' 的目录。

    功能：
    1. 检查是否存在 file_chars.json 文件；
       - 不存在则调用 rec_file_total_chars(json_dir_path) 创建；
       - 存在则读取 total_chars。
    2. 读取 file_path.json，提取 uploads 之后的路径部分；
       - 判断该文件是否真实存在（存在 -> file_exist=1，否则 0）。
    3. 从路径中提取 "check_book" 与 "1_Json" 之间的内容作为 file_md5。
    4. 将 file_md5、total_chars、file_path、file_exist 记录到 results。
    5. 汇总输出到 base_path/total_file_chars.json。

    输出格式：
    {
        "files": [
            {
                "file_md5": "abcd1234",
                "total_chars": 123,
                "file_path": "admin2/xxx.pdf",
                "file_exist": 1
            },
            ...
        ],
        "total_file_counts": 2,
        "total_file_chars": 456
    }
    """
    results = []
    total_chars_sum = 0
    total_file_count = 0

    total_file_count_del = 0
    total_chars_sum_del = 0

    for root, dirs, files in os.walk(base_path):
        if "1_Json" in dirs:
            json_dir_path = os.path.join(root, "1_Json")
            print(f"\n正在处理目录: {json_dir_path}")

            # --- 提取 file_md5 （位于 check_book 与 1_Json 之间的部分） ---
            file_md5 = ""
            match = re.search(r"check_book[\\/](.*?)[\\/]1_Json", json_dir_path)
            if match:
                file_md5 = match.group(1)
            else:
                file_md5 = "unknown"

            file_chars_path = os.path.join(json_dir_path, "file_chars.json")
            file_path_json = os.path.join(json_dir_path, "file_path.json")

            # Step 1: 检查 file_chars.json 是否存在
            if not os.path.exists(file_chars_path):
                result, msg = rec_file_total_chars(json_dir_path)
                print(f"创建 file_chars.json 结果: {msg}")

            # Step 2: 读取 file_chars.json
            total_chars = 0
            if os.path.exists(file_chars_path):
                try:
                    with open(file_chars_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        total_chars = data.get("total_chars", 0)
                except Exception as e:
                    print(f"读取 {file_chars_path} 出错: {e}")

            # Step 3: 读取 file_path.json 并提取 uploads 后的路径
            short_file_path = ""
            file_exist = 0
            if os.path.exists(file_path_json):
                try:
                    with open(file_path_json, "r", encoding="utf-8") as f:
                        file_info = json.load(f)
                        full_path = file_info.get("file_path", "")
                        if "uploads" in full_path:
                            short_file_path = full_path.split("uploads", 1)[-1].lstrip("\\/")  # 去除前导符
                        
                        # 检查 full_path 对应的文件是否存在
                        if os.path.exists(full_path):
                            file_exist = 1
                            # 获取文件创建时间
                            ctime = os.path.getctime(full_path)
                            file_upload_time = datetime.datetime.fromtimestamp(ctime).strftime("%Y-%m-%d %H:%M:%S")
                        else:
                            file_exist = 0
                            file_upload_time = None
                except Exception as e:
                    print(f"读取 {file_path_json} 出错: {e}")

            # Step 4: 累加统计
            results.append({
                "file_md5": file_md5,
                "total_chars": total_chars,
                "file_path": short_file_path,
                "file_exist": file_exist,
                "file_upload_time": file_upload_time
            })

            if file_exist == 0:
                total_file_count_del += 1
                total_chars_sum_del += total_chars
            else:
                total_file_count += 1
                total_chars_sum += total_chars

    # Step 5: 汇总输出到 total_file_chars.json
    # 按 file_upload_time 降序排序（None 置后）
    results.sort(
        key=lambda x: x["file_upload_time"] if x["file_upload_time"] else "1970-01-01 00:00:00",
        reverse=True
    )
    
    summary = {
        "files": results,
        "total_file_counts": total_file_count,
        "total_file_chars": total_chars_sum,
        "total_file_counts_del": total_file_count_del,
        "total_file_chars_del": total_chars_sum_del
    }

    output_file = os.path.join(base_path, "total_file_chars.json")
    try:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=4)
        print(f"\n统计结果已写入: {output_file}")
    except Exception as e:
        print(f"写入 total_file_chars.json 失败: {e}")


#2025.10.30 遍历uploads目录下的所有文件
class FileInfo(BaseModel):
    filename: str
    create_time: str
    total_chunks: int = 0
    processed_chunks: int = 0
    md5: str
    directory_name:str
    file_id: str
    file_path:str

def get_file_queue_list_by_token():
    """
    获取用户文件列表（包括子目录中的.docx文件）
    """
    user_dir = os.path.join(path_word_spit, "uploads")
    if not os.path.exists(user_dir):
        return {"total": 0, "data": []}

    file_list = []

    for root, dirs, files in os.walk(user_dir):
        for filename in files:
            #if (filename.endswith(".docx") or filename.endswith(".pdf")): #2025.08.12添加对pdf格式的支持:
            if  filename.endswith(".pdf"): #2025.11.17 仅判断pdf格式的文件
                file_path = os.path.join(root, filename)
                create_time_dt = datetime.fromtimestamp(os.path.getctime(file_path))
                create_time_str = create_time_dt.strftime("%Y-%m-%d %H:%M:%S")
                file_size = os.path.getsize(file_path)

                filename_md5 = hashlib.md5(filename.encode()).hexdigest()

                filename_display = (
                    filename[:6] + '*' * (len(filename) - 26) + filename[-24:]
                    if len(filename) > 26 else filename
                )
                directory_name = os.path.basename(root) if root != user_dir else "根目录"

                file_info = FileInfo(
                    filename=directory_name + "===" + filename_display,
                    create_time=create_time_str,
                    total_chunks=0,
                    processed_chunks=0,
                    md5=filename_md5,
                    directory_name=directory_name,
                    file_id=filename_md5,
                    file_path=file_path
                )

                # 附加原始属性方便后续统计
                file_info._original_time = create_time_dt
                file_info._file_size = file_size

                file_list.append(file_info)

    # 排序
    file_list.sort(key=lambda x: x.create_time, reverse=True)
   
    return file_list    


def check_file_processed_data_info(file_path: str, username: str = "default_user"):
    """
    检查并处理文件的分析信息，根据文件类型(.docx / .pdf)分别调用不同的处理函数。
    """
    # 确认文件路径存在
    if not os.path.exists(file_path):
        return {
            "status": "fail",
            "message": f"文件不存在: {file_path}"
        }

    # 提取文件名
    filename = os.path.basename(file_path)

    #filename_with_extension_md5_name = os.path.splitext(filename)[0]  # 用作文件夹名（或MD5名）
    filename_with_extension_md5_name = create_processing_folders(file_path)
    # Step 1️⃣: 检查 file_path.json 是否存在/有效
    file_path_json_info = ensure_file_path_json(
        path_word_spit,
        path_book_check_dist,
        filename_with_extension_md5_name,
        file_path
    )

    # 记录上传的文件的类型
    upload_file_type = None
    if filename.endswith(".docx"):
        upload_file_type = ".docx"
    elif filename.endswith(".pdf"):
        upload_file_type = ".pdf"
    else:
        upload_file_type = None  # 其他文件类型暂不支持

    # 根据类型分别调用处理函数
    if upload_file_type == ".docx":
        try:
            # 调用 Word 拆分处理逻辑
            Create_Folder_And_Split_Word(file_path)
        except Exception as e:
            return {
                "status": "fail",
                "message": f"上传失败：分析处理失败 - {str(e)}"
            }

        return {
            "status": "success",
            "filename": filename,
            "file_type": upload_file_type
        }

    elif upload_file_type == ".pdf":
        try:
            # 调用 PDF 拆分处理逻辑（Node.js 服务）
            Create_Folder_And_Split_PDF(file_path, username)
        except Exception as e:
            return {
                "status": "fail",
                "message": f"上传失败：分析处理失败 - {str(e)}"
            }

        return {
            "status": "success",
            "filename": filename,
            "file_type": upload_file_type,
            "file_path_json_status": file_path_json_info["status"],
            "file_path_json": file_path_json_info["path"]
        }

    else:
        # 其他文件类型不支持
        return {
            "status": "fail",
            "message": f"上传失败：不支持的文件格式 ({filename})"
        }

def process_file_list(file_list: List[FileInfo]):
    """
    遍历 file_list，取出每个 FileInfo 的 file_path，调用 check_file_processed_data_info
    """
    results = []
    for file_info in file_list:
        file_path = file_info.file_path
        filename_with_extension_md5_name = create_processing_folders(file_path)
        print(f"'正在处理文件','{filename_with_extension_md5_name}','{file_path}'")
        result = check_file_processed_data_info(file_path,'')
        results.append(result)
    return results

def create_processing_folders(filename):
    """Create processing folders for a Word document."""
    # Extract filename with extension but without path
    filename_with_extension = os.path.basename(filename)
    # Generate MD5 hash of filename
    filename_with_extension_md5_name = hashlib.md5(filename_with_extension.encode()).hexdigest()
    
    # Define subfolder names
    subfolders = ['1_Json', '2_Check_A', '2_Check_B', '2_Check_C', '2_Check_D', '2_Check_E', '2_Check_F', '2_Check_G']
    
    # Create main folder with MD5 name
    main_folder = os.path.join(path_word_spit, path_book_check_dist,filename_with_extension_md5_name)
    if not os.path.exists(main_folder):
        os.makedirs(main_folder)
    
    # Create subfolders
    for subfolder in subfolders:
        folder_path = os.path.join(main_folder, subfolder)
        if not os.path.exists(folder_path):
            print(f"Created sub folders in: {folder_path}")
            os.makedirs(folder_path)
            
    return filename_with_extension_md5_name

def extract_page_number(paragraph):
    """
    检测是否为分页段落（粗略方法）。
    """
    try:
        xml_str = paragraph._element.xml
        return '<w:br w:type="page"/>' in xml_str
    except Exception as e:
        print(f"[Error] 检测分页符失败: {e}")
        return False

def extract_footnotes(doc):
    """
    提取所有脚注，返回 {编号: 内容} 映射。
    修复 target_mode 错误判断，改为使用 rel.reltype。
    2025.04.23
    """
    footnotes = {}

    for rel in doc.part.rels.values():
        if rel.reltype.endswith("/footnotes"):  # 更通用的判断方式
            try:
                footnote_part = rel.target_part
                footnote_xml = footnote_part._blob.decode(errors="ignore")
                footnote_tree = ET.ElementTree(ET.fromstring(footnote_xml))
                ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

                for footnote in footnote_tree.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}footnote"):
                    footnote_id = footnote.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}id")
                    footnote_text = "".join(footnote.itertext()).strip()
                    if footnote_id and footnote_text:
                        footnotes[footnote_id] = footnote_text

            except Exception as e:
                print(f"[Error] 解析脚注失败: {e}")

            break  # 找到一个 footnotes.xml 即可

    return footnotes

def extract_paragraph_with_footnotes(paragraph, footnotes):
    """
    提取段落内容，并匹配其中的脚注。
    如果在text中发现脚注引用（footnote_refs），则尝试从footnotes中提取对应内容。
    返回段落文本和匹配到的脚注内容列表。
    出现异常时返回错误信息。
    2025.04.23
    """
    try:
        text = paragraph.text.strip() if paragraph.text else ""
        
        # 尝试获取段落的 XML 结构
        try:
            xml_str = paragraph._element.xml
        except Exception as e:
            print(f"[Error] 获取段落 XML 失败: {e}")
            return text, []

        # 查找脚注引用 ID
        footnote_refs = re.findall(r'w:footnoteReference w:id="(\d+)"', xml_str)

        if footnote_refs:
            print(f"Footnote references found: {footnote_refs}")

        matched_footnotes = []
        for ref_id in footnote_refs:
            if ref_id in footnotes:
                matched_footnotes.append(f"{ref_id}: {footnotes[ref_id]}")
            else:
                print(f"[Warning] 脚注ID {ref_id} 未在footnotes中找到")

        return text, matched_footnotes

    except Exception as e:
        print(f"[Error] 处理段落时发生异常: {e}")
        return "", []    
def read_word_document(doc_path):
    """
    读取 Word 文档，提取正文、脚注、图片，并标注页码
    """
    doc = Document(doc_path)
    footnotes = extract_footnotes(doc)  # 先提取脚注
    content = []
    images = []
    page_number = 1  

    # 处理正文内容
    for para in doc.paragraphs:
        if extract_page_number(para):
            page_number += 1  # 遇到分页符，页码+1

        text, matched_footnotes = extract_paragraph_with_footnotes(para, footnotes)
        #2025.03.07 有时候存在text为空，但是matched_footnotes不为空的情况，这种情况下，只保留matched_footnotes
        if text or matched_footnotes:
            entry = {"type": "text", "content": text, "page": page_number}
            if matched_footnotes:
                entry["footnote"] = matched_footnotes  # 添加脚注字段
            content.append(entry)
    
    # 处理图片
    '''
    修复 target_mode 错误判断，改用 rel.reltype + try-except 判断是否为有效内部图片。
    '''
    for rel in doc.part.rels.values():
        if rel.reltype == "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image":
            try:
                image_data = rel.target_part.blob  # 若为 External 链接或损坏会抛异常
                img_b64 = base64.b64encode(image_data).decode('utf-8')
                images.append({
                    "type": "image",
                    "content": img_b64,
                    "page": page_number
                })
            except Exception as e:
                print(f"[Warning] 跳过图片: rel.target_ref = {getattr(rel, 'target_ref', '')}, 错误: {e}")

    return content, images

def save_to_json(chunks, output_path):
    """
    保存数据为 JSON，并为每条记录添加一个 id 属性
    """
    for i, chunk in enumerate(chunks, start=1):
        chunk['id'] = i

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=4)

def write_book_file_path(book_file_path, write_to_file_name):
    """
    写入图书文件存放的路径信息
    2025.07.30
    """
    data = {
        "file_path": book_file_path
    }

    # 使用 utf-8 编码写入文件
    with open(write_to_file_name, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
def word_split_main(doc_path, output_json_path):
    content, images = read_word_document(doc_path)
    all_data = content + images
    save_to_json(all_data, output_json_path)
    print(f"Processed document saved to {output_json_path}")


import os

def ensure_processed_data_json_word(path_word_spit: str, 
                               path_book_check_dist: str, 
                               filename_with_extension_md5_name: str, 
                               input_doc: str):
    """
    检查 processed_data.json 文件是否存在及是否为空。
    若不存在或为空，则执行 word_split_main(input_doc, output_json)。
    """
    output_json = os.path.join(
        path_word_spit,
        path_book_check_dist,
        filename_with_extension_md5_name,
        "1_Json",
        "processed_data.json"
    )

    os.makedirs(os.path.dirname(output_json), exist_ok=True)

    need_to_run = False

    # 1️⃣ 文件不存在 → 需要执行
    if not os.path.exists(output_json):
        need_to_run = True
    else:
        # 2️⃣ 文件存在但为空 → 需要执行
        try:
            if os.path.getsize(output_json) == 0:
                need_to_run = True
            else:
                # 3️⃣ 文件存在但内容为空JSON {}
                with open(output_json, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if not content or content in ["{}", "[]"]:
                        need_to_run = True
        except Exception as e:
            # 如果读取出错，也重新执行
            need_to_run = True

    # 4️⃣ 执行逻辑
    if need_to_run:
        try:
            word_split_main(input_doc, output_json)
            return {
                "status": "executed",
                "message": "重新生成 processed_data.json",
                "output_json": output_json
            }
        except Exception as e:
            return {
                "status": "fail",
                "message": f"执行 word_split_main 失败 - {str(e)}",
                "output_json": output_json
            }

    # 5️⃣ 文件已存在且内容有效
    return {
        "status": "ok",
        "message": "processed_data.json 已存在且内容有效",
        "output_json": output_json
    }

def ensure_processed_data_json_pdf(path_word_spit: str, 
                               path_book_check_dist: str, 
                               filename_with_extension_md5_name: str, 
                               input_doc: str,
                               pub_url_pdfjs_service, url_pdf_file,json_file_save_path):
    """
    检查 processed_data.json 文件是否存在及是否为空。
    若不存在或为空，则执行 word_split_main(input_doc, output_json)。
    """
    output_json = os.path.join(
        path_word_spit,
        path_book_check_dist,
        filename_with_extension_md5_name,
        "1_Json",
        "processed_data.json"
    )

    os.makedirs(os.path.dirname(output_json), exist_ok=True)

    need_to_run = False

    # 1️⃣ 文件不存在 → 需要执行
    if not os.path.exists(output_json):
        need_to_run = True
    else:
        # 2️⃣ 文件存在但为空 → 需要执行
        try:
            if os.path.getsize(output_json) == 0:
                need_to_run = True
            else:
                # 3️⃣ 文件存在但内容为空JSON {}
                with open(output_json, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if not content or content in ["{}", "[]"]:
                        need_to_run = True
        except Exception as e:
            # 如果读取出错，也重新执行
            need_to_run = True

    # 4️⃣ 执行逻辑
    if need_to_run:
        try:
            #word_split_main(input_doc, output_json)
            process_pdf_data(pub_url_pdfjs_service, url_pdf_file, json_file_save_path)
            return {
                "status": "executed",
                "message": "重新生成 processed_data.json",
                "output_json": output_json
            }
        except Exception as e:
            return {
                "status": "fail",
                "message": f"执行 word_split_main 失败 - {str(e)}",
                "output_json": output_json
            }

    # 5️⃣ 文件已存在且内容有效
    return {
        "status": "ok",
        "message": "processed_data.json 已存在且内容有效",
        "output_json": output_json
    }

def Create_Folder_And_Split_Word(input_doc):
    '''
    接收文件名称，创建对应的文件夹，并把文件拆分成多个json文件    '''
    filename_with_extension_md5_name = create_processing_folders(input_doc)
    output_json = os.path.join(path_word_spit,path_book_check_dist,filename_with_extension_md5_name, "1_Json","processed_data.json")
    #word_split_main(input_doc, output_json)
    ensure_processed_data_json_word(path_word_spit, path_book_check_dist, filename_with_extension_md5_name, input_doc)

    #将文件的路径信息写入：file_path.json文件中
    file_path_file_name_json = os.path.join(path_word_spit,path_book_check_dist,filename_with_extension_md5_name, "1_Json","file_path.json")
    write_book_file_path(input_doc,file_path_file_name_json)
    #2025.03.25 接收output_json，分析maxid的值，写入：maxid.json文件

    #2025.10.28添加统计文件字数的功能
    file_path = os.path.join(path_word_spit,path_book_check_dist,filename_with_extension_md5_name, "1_Json")
    rec_file_total_chars(file_path)

    return filename_with_extension_md5_name

@dataclass
class Fileid_Info:
    fileid: str
    file_ownername: str
    isshare: int  # 0 or 1
    to_username: str = ""  # 备用字段
    express_time: str = ""  # 格式："YYYY-MM-DD HH:MM:SS"

    def to_dict(self):
        return {
            "fileid": self.fileid,
            "file_ownername": self.file_ownername,
            "isshare": self.isshare,
            "to_username": self.to_username,
            "express_time": self.express_time
        }

    @staticmethod
    def from_dict(data: dict):
        return Fileid_Info(
            fileid=data.get("fileid", ""),
            file_ownername=data.get("file_ownername", ""),
            isshare=int(data.get("isshare", 0)),
            to_username=data.get("to_username", ""),
            express_time=data.get("express_time", "")
        )

def encrypt_fileid_info(fileid_info: Fileid_Info) -> str:
    try:
        aesgcm = AESGCM(pub_fileid_info_key)
        nonce = os.urandom(12)  # GCM标准推荐12字节 nonce
        json_data = json.dumps(fileid_info.to_dict()).encode("utf-8")
        encrypted_data = aesgcm.encrypt(nonce, json_data, None)
        combined = base64.urlsafe_b64encode(nonce + encrypted_data).decode("utf-8")
        return combined
    except Exception as e:
        print(f"[加密失败] {e}")
        return ""

def decrypt_fileid_info(encrypted_str: str) -> Fileid_Info:
    try:
        aesgcm = AESGCM(pub_fileid_info_key)
        data = base64.urlsafe_b64decode(encrypted_str.encode("utf-8"))
        nonce = data[:12]
        encrypted_data = data[12:]
        json_data = aesgcm.decrypt(nonce, encrypted_data, None)
        info_dict = json.loads(json_data.decode("utf-8"))
        return Fileid_Info.from_dict(info_dict)
    except Exception as e:
        print(f"[解密失败] {e}")
        return Fileid_Info(fileid="", file_ownername="", isshare=0)


def get_encrypted_fileid(fileid: str, current_username: str) -> str:
    try:
        # 默认设置：isshare=0, to_username为空, express_time默认3天后
        default_expire = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")
        info = Fileid_Info(
            fileid=fileid,
            file_ownername=current_username,
            isshare=0,
            to_username="",
            express_time=default_expire
        )
        return encrypt_fileid_info(info)
    except Exception as e:
        print(f"[生成加密fileid失败] {e}")
        return ""  
def get_encrypted_fileid(fileid: str, current_username: str) -> str:
    try:
        # 默认设置：isshare=0, to_username为空, express_time默认3天后
        default_expire = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")
        info = Fileid_Info(
            fileid=fileid,
            file_ownername=current_username,
            isshare=0,
            to_username="",
            express_time=default_expire
        )
        return encrypt_fileid_info(info)
    except Exception as e:
        print(f"[生成加密fileid失败] {e}")
        return ""  

def process_pdf_data(url_pdfjs_service, url_pdf_file, json_file_save_path):
    try:
        # 1. 发出HTTP请求获取JSON数据
        print(f"正在获取JSON数据="+url_pdfjs_service + url_pdf_file)
        response = requests.get(url_pdfjs_service + url_pdf_file)
        
        # 检查请求是否成功
        if response.status_code != 200:
            print(f"请求失败，状态码：{response.status_code}")
            return
        
        # 解析响应的JSON内容
        try:
            data = response.json()
        except json.JSONDecodeError:
            print("响应内容不是有效的JSON格式")
            return
        
        # 2. 将获取到的JSON数据保存到文件
        pdfjs_return_data_path = os.path.join(json_file_save_path, "pdfjs_0_return_data.json")
        try:
            with open(pdfjs_return_data_path, 'w', encoding='utf-8') as json_file:
                json.dump(data, json_file, ensure_ascii=False, indent=4)
            print(f"JSON数据已保存到：{pdfjs_return_data_path}")
        except Exception as e:
            print(f"保存JSON数据时发生错误：{e}")
            return
        
        #2.1 保存各个字段到独立的文件
        with open(os.path.join(json_file_save_path,'pdfjs_1_words.json'), 'w', encoding='utf-8') as f:
            json.dump(data.get('words', []), f, ensure_ascii=False, indent=2)

        with open(os.path.join(json_file_save_path,'pdfjs_2_lines.json'), 'w', encoding='utf-8') as f:
            json.dump(data.get('lines', []), f, ensure_ascii=False, indent=2)

        with open(os.path.join(json_file_save_path,'pdfjs_3_sections.json'), 'w', encoding='utf-8') as f:
            json.dump(data.get('sections', []), f, ensure_ascii=False, indent=2)

        with open(os.path.join(json_file_save_path,'pdfjs_4_processed_data.json'), 'w', encoding='utf-8') as f:
            json.dump(data.get('pdfContent', []), f, ensure_ascii=False, indent=2)
        
        #2025.10.24 保存docinfo到单独的文件
        with open(os.path.join(json_file_save_path,'pdfjs_5_docinfo.json'), 'w', encoding='utf-8') as f:
            json.dump(data.get('docInfo', []), f, ensure_ascii=False, indent=2)

        # 3. 读取并处理文件内容，更新id字段
        pdfjs_processed_data_path = os.path.join(json_file_save_path, "pdfjs_4_processed_data.json")
        try:
            with open(pdfjs_processed_data_path, 'r', encoding='utf-8') as json_file:
                content = json.load(json_file)
        except Exception as e:
            print(f"读取JSON文件时发生错误：{e}")
            return
        
        # 遍历内容，更新id字段(让item['id']的值从1开始)
        # 2025.11.14 安全处理：在遍历时判断 item 是否为字典；不是字典（None、其他类型）就跳过
        for idx, item in enumerate(content, start=1):
            if isinstance(item, dict):      # 只有 item 是 dict 才更新
                item['id'] = idx
            else:
                continue  # item 为 None 或其他类型则跳过

        # 4. 保存处理后的数据到新的文件
        processed_data_path = os.path.join(json_file_save_path, "processed_data.json")
        try:
            with open(processed_data_path, 'w', encoding='utf-8') as json_file:
                json.dump(content, json_file, ensure_ascii=False, indent=4)
            print(f"处理后的数据已保存到：{processed_data_path}")

            #2025.10.28添加统计文件字数的功能
            rec_file_total_chars(json_file_save_path)

        except Exception as e:
            print(f"保存处理后数据时发生错误：{e}")
            return

    except Exception as e:
        print(f"发生错误：{e}")

def Create_Folder_And_Split_PDF(input_doc,current_username):
    '''
    2025.07.29 调用nodejs启动的服务，将pdf转换为json格式的文件。
    '''
    filename_with_extension_md5_name = create_processing_folders(input_doc)
    #output_json = os.path.join(path_word_spit,path_book_check_dist,filename_with_extension_md5_name, "1_Json","processed_data.json")

    #将文件的路径信息写入：file_path.json文件中
    file_path_file_name_json = os.path.join(path_word_spit,path_book_check_dist,filename_with_extension_md5_name, "1_Json","file_path.json")
    write_book_file_path(input_doc,file_path_file_name_json)

    #2025.08.01 分析pdf的内容（使用pdfjs--获取pdf的json数据）    
    # pub_url_get_pdf_file
    jiami_md5=get_encrypted_fileid(filename_with_extension_md5_name,current_username)
    #url_pdf_file="http://192.168.0.159/api/get_pdf_file_by_md5/Q1-HIKbs1_VDWOY550DHmHyGfja93D1H_FtWqnGCjoZTvVWfTJTusU2dBTkktbXOy0bp5BDMuRsynxXMGenx0J9R9Pxpt6VXmGmQsx_xUoIzl0GYLJE7uYGUXERvcrzvYn1CpBWrzyqf7f5kLoOeUVEJNrGiSU1kmpRoPUNFagkRXsaQUpq9EHwd4dA-wkn6c1mfJhDAbej2KXmxR_2jDLinEIIRNuYQT9gwcs7s"
    url_pdf_file=pub_url_get_pdf_file+jiami_md5

    json_file_save_path=file_path_file_name_json = os.path.join(path_word_spit,path_book_check_dist,filename_with_extension_md5_name, "1_Json")
    
    #process_pdf_data(pub_url_pdfjs_service, url_pdf_file, json_file_save_path)
    ensure_processed_data_json_pdf(path_word_spit, path_book_check_dist, filename_with_extension_md5_name, input_doc,pub_url_pdfjs_service, url_pdf_file,json_file_save_path)
    #2025.09.22 采用流式下载文件
    #process_pdf_data_stream(pub_url_pdfjs_service, url_pdf_file, json_file_save_path)


    #word_split_main(input_doc, output_json)
    return filename_with_extension_md5_name

def ensure_file_path_json(path_word_spit: str, 
                          path_book_check_dist: str, 
                          filename_with_extension_md5_name: str, 
                          input_doc: str):
    """
    检查并维护 file_path.json 文件：
    1. 构建 file_path_file_name_json 路径；
    2. 如果文件不存在 -> 调用 write_book_file_path；
    3. 如果存在 -> 读取并校验 file_path 字段；
       若读取失败或 file_path 不匹配 -> 重新调用 write_book_file_path。
    """

    # 1. 组装 file_path.json 的完整路径
    file_path_file_name_json = os.path.join(
        path_word_spit,
        path_book_check_dist,
        filename_with_extension_md5_name,
        "1_Json",
        "file_path.json"
    )

    # 确保目录存在
    os.makedirs(os.path.dirname(file_path_file_name_json), exist_ok=True)

    # 2. 判断文件是否存在
    if not os.path.exists(file_path_file_name_json):
        # 文件不存在，直接写入
        write_book_file_path(input_doc, file_path_file_name_json)
        return {
            "status": "created",
            "message": f"file_path.json 不存在，已创建",
            "path": file_path_file_name_json
        }

    # 3. 文件存在，尝试读取
    try:
        with open(file_path_file_name_json, "r", encoding="utf-8") as f:
            file_info = json.load(f)
            full_path = file_info.get("file_path", "")
    except Exception as e:
        # 如果读取失败，也重新生成
        write_book_file_path(input_doc, file_path_file_name_json)
        return {
            "status": "recreated",
            "message": f"读取 file_path.json 失败，已重新生成 ({e})",
            "path": file_path_file_name_json
        }

    # 4. 校验 file_path 字段是否一致
    if not full_path or full_path != file_path_file_name_json:
        write_book_file_path(input_doc, file_path_file_name_json)
        return {
            "status": "updated",
            "message": "file_path 与实际路径不符，已重新写入",
            "path": file_path_file_name_json
        }

    # 5. 正常情况
    return {
        "status": "ok",
        "message": "file_path.json 文件存在且内容正确",
        "path": file_path_file_name_json
    }

def filter_files_by_directory(return_file_list):
    # 创建一个空列表来存储匹配的数据
    filtered_files = []
    
    # 遍历字典中的每个项
    for file_info in return_file_list:
        # 检查 'directory_name' 是否等于 'admin2'
        if file_info.directory_name == 'admin2':
            # 如果匹配，则添加到过滤后的列表中
            filtered_files.append(file_info)
    
    return filtered_files

def process_file_list_to_deepseek_ocr(file_list: List[FileInfo]):
    """
    遍历 file_list，取出每个 FileInfo 的 file_path，调用 check_file_processed_data_info
    """
    results = []
    for file_info in file_list:
        file_path = file_info.file_path
        filename_with_extension_md5_name = create_processing_folders(file_path)
        print(f"'开始进行pdf转markdown--正在处理文件-','{filename_with_extension_md5_name}','{file_path}'")
        #result = check_file_processed_data_info(file_path,'')
        #开始进行pdf转markdown
        #pdf_to_mk_main(file_path,os.path.join(path_word_spit,path_book_check_dist),filename_with_extension_md5_name)
        #2026.04.01使用V3版本
        pdf_to_mk_main_v3(file_path,os.path.join(path_word_spit,path_book_check_dist),filename_with_extension_md5_name)

        #将文件的路径信息写入：file_path.json文件中
        file_path_file_name_json = os.path.join(path_word_spit,path_book_check_dist,filename_with_extension_md5_name, "1_Json","file_path.json")
        if not os.path.exists(file_path_file_name_json):
            write_book_file_path(file_path,file_path_file_name_json)
            print(f"'file_path.json 不存在，已创建'")
        else:
            print(f"'file_path.json 文件已存在，正在检查文件路径是否正确-','{filename_with_extension_md5_name}','{file_path}'")

        #2026.04.10 添加统计文件字数的程序
        #file_path = os.path.join(path_word_spit,path_book_check_dist,filename_with_extension_md5_name, "1_Json")
        #rec_file_total_chars(file_path)

        #2026.04.10 添加maxid的数据、统计
        #Create_Maxid_Json(path_word_spit,path_book_check_dist,filename_with_extension_md5_name)

        #results.append(result)
    return results


def Create_Maxid_Json(sub_path_word_spit, sub_path_book_check_dist, sub_str_md5):

    main_folder = os.path.join(sub_path_word_spit, sub_path_book_check_dist, sub_str_md5)
    maxid_json = os.path.join(main_folder, "1_Json", "maxid.json")
    output_json = os.path.join(main_folder, "1_Json", "processed_data.json")
    
    try:
        with open(output_json, "r", encoding="utf-8") as file:
            data = json.load(file)
        
        # 提取所有 id 值，过滤出 type 为 "text" 的条目
        ids = [entry.get("id", 0) for entry in data if isinstance(entry, dict) and entry.get("type") == "text"]
        max_id = max(ids, default=0)
        
        # 更新 maxid.json 文件
        with open(maxid_json, "w", encoding="utf-8") as file:
            json.dump({"maxid": max_id}, file, ensure_ascii=False, indent=4)
        
        return max_id
    except Exception as e:
        print(f"读取 JSON 文件出错: {e}")
        return 0
    
#2025.12.12 pdf ocr 识别开始

def pdf_to_mk_main(pdf_file_path, target_path, md5_value):
    # Create the necessary directories
    images_folder = os.path.join(target_path,md5_value, "pdf-1-images")
    json_folder = os.path.join(target_path,md5_value, "pdf-2-json")
    mk_folder = os.path.join(target_path, md5_value,"pdf-3-mk")
    json_backup_folder = os.path.join(target_path,md5_value, "1_Json")

    json_python_folder = os.path.join(target_path,md5_value, "pdf-2-json-python") #2026.03.23
    merged_output_folder=os.path.join(target_path,md5_value, "pdf-2-json-py-to-ds") #2026.03.23
    merged_output_folder_curpage_merged=os.path.join(target_path,md5_value, "pdf-2-json-py-to-ds-curpage-merged") #2026.03.25

    os.makedirs(images_folder, exist_ok=True)
    os.makedirs(json_folder, exist_ok=True)
    os.makedirs(mk_folder, exist_ok=True)
    os.makedirs(json_backup_folder, exist_ok=True)
    os.makedirs(json_python_folder, exist_ok=True) #2026.03.23
    os.makedirs(merged_output_folder, exist_ok=True) #2026.03.23

    # Convert PDF to images
    # 判断 pdf-1-images.json 文件是否存在
    json_file_path = os.path.join(json_backup_folder, "pdf-1-images.json")
    if not os.path.exists(json_file_path):
        # 文件不存在，调用 convert_pdf_to_images 函数进行转换
        convert_pdf_to_images(pdf_file_path, os.path.join(target_path, md5_value))
        # 创建 pdf-1-images.json 文件并写入当前时间
        with open(json_file_path, 'w', encoding='utf-8') as json_file:
            json.dump({"timestamp": datetime.now().isoformat()}, json_file)
    else:
        print("文件 pdf-1-images.json 已存在，跳过操作。")

    # Process images to json
    json_file_path = os.path.join(json_backup_folder, "pdf-2-json.json")
    if not os.path.exists(json_file_path):
        process_images_to_json(os.path.join(target_path,md5_value))
        # 创建 pdf-2-json.json 文件并写入当前时间
        with open(json_file_path, 'w', encoding='utf-8') as json_file:
            json.dump({"timestamp": datetime.now().isoformat()}, json_file)
    else:
        print("文件 pdf-2-json.json 已存在，跳过操作。")

    #判断标记文件--2026.03.23   
    json_file_path = os.path.join(json_backup_folder, "pdf-2-json-python.json")
    if not os.path.exists(json_file_path):
        extract_pdf_to_json(pdf_file_path, json_python_folder)
        # 创建 pdf-2-json-python.json 文件并写入当前时间
        with open(json_file_path, 'w', encoding='utf-8') as json_file:
            json.dump({"timestamp": datetime.now().isoformat()}, json_file)
    else:
        print("文件 pdf-2-json-python.json 已存在，跳过操作。")

    #判断标记文件--2026.03.23   
    json_file_path = os.path.join(json_backup_folder, "pdf-2-json-py-to-ds.json")
    if not os.path.exists(json_file_path):
        merge_py_json_to_ds_json(json_folder, json_python_folder, merged_output_folder)
        # 创建 pdf-2-json-py-to-ds.json 文件并写入当前时间
        with open(json_file_path, 'w', encoding='utf-8') as json_file:
            json.dump({"timestamp": datetime.now().isoformat()}, json_file)
    else:
        print("文件 pdf-2-json-py-to-ds.json 已存在，跳过操作。")

    #2026.03.25 在此环节添加：单页内不同区块的数据的连续合并，数据源：pdf-2-json-py-to-ds 目标文件夹：pdf-2-json-py-to-ds-curpage-merged
    #merged_output_folder_curpage_merged
    json_file_path = os.path.join(json_backup_folder, "pdf-2-json-py-to-ds-curpage-merged.json")
    if not os.path.exists(json_file_path):
        merge_py_json_to_ds_json_curpage(merged_output_folder,merged_output_folder_curpage_merged)
        # 创建 pdf-2-json-py-to-ds-curpage-merged.json 文件并写入当前时间
        with open(json_file_path, 'w', encoding='utf-8') as json_file:
            json.dump({"timestamp": datetime.now().isoformat()}, json_file)
    else:
        print("文件 pdf-2-json-py-to-ds-curpage-merged.json 已存在，跳过操作。")
    
        
    # Merge json files and create final processed file
    json_file_path = os.path.join(json_backup_folder, "pdf-3-mk.json")
    if not os.path.exists(json_file_path):
        merge_json_to_mk(os.path.join(target_path,md5_value))
        # 创建 pdf-3-mk.json 文件并写入当前时间
        with open(json_file_path, 'w', encoding='utf-8') as json_file:
            json.dump({"timestamp": datetime.now().isoformat()}, json_file)
    else:
        print("文件 pdf-3-mk.json 已存在，跳过操作。")

    #2026.03.23新版本的json文件合并到markdown文件
    json_file_path = os.path.join(json_backup_folder, "pdf-3-mk-py-to-ds.json")
    if not os.path.exists(json_file_path):
        merge_json_to_mk_py_to_ds(os.path.join(target_path,md5_value))
        # 创建 pdf-3-mk-py-to-ds.json 文件并写入当前时间
        with open(json_file_path, 'w', encoding='utf-8') as json_file:
            json.dump({"timestamp": datetime.now().isoformat()}, json_file)
    else:
        print("文件 pdf-3-mk-py-to-ds.json 已存在，跳过操作。")

    #2026.03.25 将pdf2-json-py-to-ds-courrent-merged目录下的文件遍历读取，写入：processed_merged_nodes_three_py_to_ds_curpage-merged.json
    #任务是否完成的标志文件名称是：pdf-3-mk-py-to-ds.json
    
    json_file_path = os.path.join(json_backup_folder, "pdf-3-mk-py-to-ds_curpage.json")
    if not os.path.exists(json_file_path):
        merge_json_to_mk_py_to_ds_curpage(os.path.join(target_path,md5_value))
        # 创建 pdf-3-mk-py-to-ds.json 文件并写入当前时间
        with open(json_file_path, 'w', encoding='utf-8') as json_file:
            json.dump({"timestamp": datetime.now().isoformat()}, json_file)
    else:
        print("文件 pdf-3-mk-py-to-ds.json 已存在，跳过操作。")

    json_file_path = os.path.join(json_backup_folder, "pdf-3-mk-py-to-ds_curpage-merged-format.json")
    if not os.path.exists(json_file_path):
        #2026.03.31-对结果数据中的“节点过度嵌套”进行结构优化 -begin
        input_file=os.path.join(target_path,md5_value,"pdf-3-mk","processed_merged_nodes_three-py-to-ds-curpage-merged.json")
        output_file=os.path.join(target_path,md5_value,"pdf-3-mk","processed_merged_nodes_three-py-to-ds-curpage-merged_format.json")
        merged_format_process_file(input_file,output_file)
        # Backup existing process_data.json if it exists
        backup_json_file(json_backup_folder)
        # Copy the processed file to 1_Json folder
        copy_processed_file(mk_folder, json_backup_folder)

        # 创建 pdf-3-mk-py-to-ds_curpage-merged-format.json 文件并写入当前时间
        with open(json_file_path, 'w', encoding='utf-8') as json_file:
            json.dump({"timestamp": datetime.now().isoformat()}, json_file)
    else:
        print("文件 pdf-3-mk-py-to-ds_curpage-merged-format.json 已存在，跳过操作。")


def backup_json_file(json_backup_folder):
    # Check if the process_data.json file exists and rename it with timestamp if found
    process_data_path = os.path.join(json_backup_folder, "process_data.json")
    if os.path.exists(process_data_path):
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(json_backup_folder, f"process_data_{timestamp}.json")
        os.rename(process_data_path, backup_path)
        print(f"Backup of process_data.json created at {backup_path}")


def copy_processed_file(mk_folder, json_backup_folder):
    #processed_file = os.path.join(mk_folder, "processed_merged_nodes_three.json")
    processed_file = os.path.join(mk_folder, "processed_merged_nodes_three-py-to-ds-curpage-merged_format.json")
    target_path = os.path.join(json_backup_folder, "processed_data.json")
    shutil.copy(processed_file, target_path)
    print(f"Processed file copied to {target_path}")


def Loop_Check_Pdf_toMarkdown():
    # 创建日志目录
    log_dir = os.path.join(path_check_log, "log_file")
    os.makedirs(log_dir, exist_ok=True)
    
    # 获取当前日期作为日志文件名
    log_filename = os.path.join(log_dir, datetime.now().strftime('%Y-%m-%d') + "_pdf_to_markdown.log")

    # 配置日志
    logging.basicConfig(
        filename=log_filename,
        level=logging.INFO,
        format='%(asctime)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    while True:
        start_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        logging.info(f'开始执行 {start_time}')
        print(f'开始执行 {start_time}')
        
        #主处理函数
        main_pdf_to_markdown() 
        
        end_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        logging.info(f'执行完毕 {end_time}')
        print(f'执行完毕 {end_time}')
        
        print(f'休眠 1 分钟...{end_time}')
        print(f'log file={log_filename}')
        time.sleep(60)  # 休眠 1 分钟

def main_pdf_to_markdown():
    base_path = os.path.join(path_word_spit, path_book_check_dist)   # 可替换为你自己的路径
    return_file_list=get_file_queue_list_by_token()

    #过滤只保留admin2的目录的文件
    filtered_files=filter_files_by_directory(return_file_list)
    #process_file_list(return_file_list)
    process_file_list_to_deepseek_ocr(return_file_list)
    print(filtered_files)

#2026.04.01 V3-梳理代码-Begin
def pdf_to_mk_main_v3(pdf_file_path, target_path, md5_value):
    print(f'\r\n pdf_to_mk_main_v3 pdf_file_path={pdf_file_path}-\r\n ')
    # Create the necessary directories
    images_folder = os.path.join(target_path,md5_value, "pdf-1-images")

    #目录pdf-2-json存放的是通过deepseek-ocr模型识别出来的数据，坐标布局分析的区块比较好，但有识别出来的错字。
    json_folder = os.path.join(target_path,md5_value, "pdf-2-json")
    
    #目录pdf-3-mk存放跨页合并出最终结果
    mk_folder = os.path.join(target_path, md5_value,"pdf-3-mk")
    json_backup_folder = os.path.join(target_path,md5_value, "1_Json")
    
    #目录pdf-2-json-python存放的是pymupdf识别出来的数据局，文字数据准确。
    json_python_folder = os.path.join(target_path,md5_value, "pdf-2-json-python") #2026.03.23

    #目录pdf-2-json-py-to-ds存放的是 结合pdf-2-json和pdf-2-json-python数据的优势的结果。
    merged_output_folder=os.path.join(target_path,md5_value, "pdf-2-json-py-to-ds") #2026.03.23

    #目录pdf-2-json-py-to-ds-curpage-merged将当前页面的数据进行合并
    merged_output_folder_curpage_merged=os.path.join(target_path,md5_value, "pdf-2-json-py-to-ds-curpage-merged") #2026.03.25

    os.makedirs(images_folder, exist_ok=True)
    os.makedirs(json_folder, exist_ok=True)
    os.makedirs(mk_folder, exist_ok=True)
    os.makedirs(json_backup_folder, exist_ok=True)
    os.makedirs(json_python_folder, exist_ok=True) #2026.03.23
    os.makedirs(merged_output_folder, exist_ok=True) #2026.03.23

    # Convert PDF to images
    # 判断 pdf-1-images.json 文件是否存在
    json_file_path = os.path.join(json_backup_folder, "pdf-1-images.json")
    if not os.path.exists(json_file_path):
        # 文件不存在，调用 convert_pdf_to_images 函数进行转换
        convert_pdf_to_images(pdf_file_path, os.path.join(target_path, md5_value))
        # 创建 pdf-1-images.json 文件并写入当前时间
        with open(json_file_path, 'w', encoding='utf-8') as json_file:
            json.dump({"timestamp": datetime.now().isoformat()}, json_file)
    else:
        print("文件 pdf-1-images.json 已存在，跳过操作。")

    # Process images to json
    json_file_path = os.path.join(json_backup_folder, "pdf-2-json.json")
    if not os.path.exists(json_file_path):
        process_images_to_json(os.path.join(target_path,md5_value))
        # 创建 pdf-2-json.json 文件并写入当前时间
        with open(json_file_path, 'w', encoding='utf-8') as json_file:
            json.dump({"timestamp": datetime.now().isoformat()}, json_file)
    else:
        print("文件 pdf-2-json.json 已存在，跳过操作。")

    #判断标记文件--2026.03.23   
    json_file_path = os.path.join(json_backup_folder, "pdf-2-json-python.json")
    if not os.path.exists(json_file_path):
        extract_pdf_to_json(pdf_file_path, json_python_folder)
        # 创建 pdf-2-json-python.json 文件并写入当前时间
        with open(json_file_path, 'w', encoding='utf-8') as json_file:
            json.dump({"timestamp": datetime.now().isoformat()}, json_file)
    else:
        print("文件 pdf-2-json-python.json 已存在，跳过操作。")

    #判断标记文件--2026.03.23   
    json_file_path = os.path.join(json_backup_folder, "pdf-2-json-py-to-ds.json")
    if not os.path.exists(json_file_path):
        #此程序将合并后的结果存入：pdf-2-json-py-to-ds 目录
        merge_py_json_to_ds_json(json_folder, json_python_folder, merged_output_folder)
        # 创建 pdf-2-json-py-to-ds.json 文件并写入当前时间
        with open(json_file_path, 'w', encoding='utf-8') as json_file:
            json.dump({"timestamp": datetime.now().isoformat()}, json_file)
    else:
        print("文件 pdf-2-json-py-to-ds.json 已存在，跳过操作。")

    #2026.04.01 添加一个中间环节pdf-2-json-py-to-ds-b 源：pdf-2-json-py-to-ds，经过ds+py的格式优化后，存入此目录
    json_file_path = os.path.join(json_backup_folder, "pdf-2-json-py-to-ds-b.json")
    if not os.path.exists(json_file_path):
        #此程序将合并后的结果存入：pdf-2-json-py-to-ds-b 目录
        #merge_py_json_to_ds_json_b(json_folder, json_python_folder, merged_output_folder)
        source_json_folder=os.path.join(target_path,md5_value, "pdf-2-json-py-to-ds")
        dist_json_folder=os.path.join(target_path,md5_value, "pdf-2-json-py-to-ds-b")
        os.makedirs(source_json_folder, exist_ok=True)
        os.makedirs(dist_json_folder, exist_ok=True)

        process_pdf_2_json_py_to_ds_to_b(source_json_folder, dist_json_folder)
        # 创建 pdf-2-json-py-to-ds.json 文件并写入当前时间
        with open(json_file_path, 'w', encoding='utf-8') as json_file:
            json.dump({"timestamp": datetime.now().isoformat()}, json_file)
    else:
        print("文件 pdf-2-json-py-to-ds-b.json 已存在，跳过操作。")   

    #2026.04.02 在此环节添加：单页内不同区块的数据的连续合并，数据源：pdf-2-json-py-to-ds-b 目标文件夹：pdf-2-json-py-to-ds-curpage-merged
    #目录pdf-2-json-py-to-ds-b
    merged_output_folder_b=os.path.join(target_path,md5_value, "pdf-2-json-py-to-ds-b") 
    #目录pdf-2-json-py-to-ds-curpage-merged将当前页面的数据进行合并
    merged_output_folder_curpage_merged=os.path.join(target_path,md5_value, "pdf-2-json-py-to-ds-curpage-merged") #2026.03.25

    json_file_path = os.path.join(json_backup_folder, "pdf-2-json-py-to-ds-curpage-merged.json")
    if not os.path.exists(json_file_path):
        merge_py_json_to_ds_json_curpage(merged_output_folder_b,merged_output_folder_curpage_merged)
        # 创建 pdf-2-json-py-to-ds-curpage-merged.json 文件并写入当前时间
        with open(json_file_path, 'w', encoding='utf-8') as json_file:
            json.dump({"timestamp": datetime.now().isoformat()}, json_file)
    else:
        print("文件 pdf-2-json-py-to-ds-curpage-merged.json 已存在，跳过操作。")
    
        
    # Merge json files and create final processed file
    json_file_path = os.path.join(json_backup_folder, "pdf-3-mk.json")
    if not os.path.exists(json_file_path):
        #中间过程-可以不看 2026.04.03
        merge_json_to_mk(os.path.join(target_path,md5_value))
        # 创建 pdf-3-mk.json 文件并写入当前时间
        with open(json_file_path, 'w', encoding='utf-8') as json_file:
            json.dump({"timestamp": datetime.now().isoformat()}, json_file)
    else:
        print("文件 pdf-3-mk.json 已存在，跳过操作。")

    #2026.03.23新版本的json文件合并到markdown文件
    json_file_path = os.path.join(json_backup_folder, "pdf-3-mk-py-to-ds.json")
    if not os.path.exists(json_file_path):
        #中间过程-可以不看 2026.04.03
        merge_json_to_mk_py_to_ds(os.path.join(target_path,md5_value))
        # 创建 pdf-3-mk-py-to-ds.json 文件并写入当前时间
        with open(json_file_path, 'w', encoding='utf-8') as json_file:
            json.dump({"timestamp": datetime.now().isoformat()}, json_file)
    else:
        print("文件 pdf-3-mk-py-to-ds.json 已存在，跳过操作。")

    #2026.03.25 将pdf2-json-py-to-ds-courrent-merged目录下的文件遍历读取，写入：processed_merged_nodes_three_py_to_ds_curpage-merged.json
    #任务是否完成的标志文件名称是：pdf-3-mk-py-to-ds.json
    
    json_file_path = os.path.join(json_backup_folder, "pdf-3-mk-py-to-ds_curpage.json")
    if not os.path.exists(json_file_path):
        #输入文件夹：pdf-2-json-py-to-ds-curpage-merged
        #输出：markdown文件，以及最后的 processed_merged_nodes_three-py-to-ds-curpage-merged.json 文件
        merge_json_to_mk_py_to_ds_curpage(os.path.join(target_path,md5_value))
        # 创建 pdf-3-mk-py-to-ds.json 文件并写入当前时间
        with open(json_file_path, 'w', encoding='utf-8') as json_file:
            json.dump({"timestamp": datetime.now().isoformat()}, json_file)
    else:
        print("文件 pdf-3-mk-py-to-ds.json 已存在，跳过操作。")

    json_file_path = os.path.join(json_backup_folder, "pdf-3-mk-py-to-ds_curpage-merged-format.json")
    if not os.path.exists(json_file_path):
        #2026.03.31-对结果数据中的“节点过度嵌套”进行结构优化 -begin
        input_file=os.path.join(target_path,md5_value,"pdf-3-mk","processed_merged_nodes_three-py-to-ds-curpage-merged.json")
        output_file=os.path.join(target_path,md5_value,"pdf-3-mk","processed_merged_nodes_three-py-to-ds-curpage-merged_format.json")
        merged_format_process_file(input_file,output_file)
        # Backup existing process_data.json if it exists
        backup_json_file(json_backup_folder)
        # Copy the processed file to 1_Json folder
        copy_processed_file(mk_folder, json_backup_folder)

        #process_data.json文件内容变化后，重新计算字数、和maxid
        #2026.04.10 添加统计文件字数的程序
        file_path = os.path.join(path_word_spit,path_book_check_dist,md5_value, "1_Json")
        rec_file_total_chars(file_path)
        #2026.04.10 添加maxid的数据、统计
        Create_Maxid_Json(path_word_spit,path_book_check_dist,md5_value)


        # 创建 pdf-3-mk-py-to-ds_curpage-merged-format.json 文件并写入当前时间
        with open(json_file_path, 'w', encoding='utf-8') as json_file:
            json.dump({"timestamp": datetime.now().isoformat()}, json_file)
    else:
        print("文件 pdf-3-mk-py-to-ds_curpage-merged-format.json 已存在，跳过操作。")    
#2026.04.01 V3-梳理代码-End    

# 示例调用
if __name__ == "__main__":
    #main_pdf_to_markdown()
    Loop_Check_Pdf_toMarkdown()
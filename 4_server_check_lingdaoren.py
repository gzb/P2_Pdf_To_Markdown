from docx import Document
import json
import base64
from io import BytesIO
import os
import hashlib
import xml.etree.ElementTree as ET
import re
import requests
import glob
from typing import List, Tuple
import datetime as dt

import concurrent.futures
import itertools
from typing import List, Tuple

import time
import logging
from datetime import datetime
from bs4 import BeautifulSoup
import shutil
import random

'''
优化点：
使用 ThreadPoolExecutor 进行并行处理（最大 4 个线程）。
itertools.cycle 轮换模型，确保每个线程调用不同的模型。
避免重复处理：如果 JSON 结果已存在，跳过处理。
这样，每个线程会轮流调用不同的 deepseek-r1:32b-* 模型，同时保证线程数量不超过 4。你可以试试看！
'''

'''
返回值例子： 2025.04.09
{
  "people": [
    {
      "name": "习近平",
      "position": "国家领导人",
      "quotes": [
        {
          "text": "推进全面依法治国，根本目的是依法保障人民权益。",
          "type": "direct",
          "context": "在讨论司法改革时提到的法治目标"
        }
      ]
    },
    {
      "name": "张军",
      "position": "最高人民法院院长",
      "quotes": [
        {
          "text": "‘一张网’要建好，加好就是半年大业。",
          "type": "direct",
          "context": "在讨论数字化改革重要性时提到的法院信息化建设"
        }
      ]
    }
  ],
  "summary": {
    "total_people": 2,
    "total_quotes": 2
  }
}

'''

# Base path where all folders will be created
#path_word_spit = os.path.dirname(os.path.abspath(__file__))
path_word_spit=f"E:\\faxin_ai_2023\\branches\\faxin_ai_uie_2023\\39_book_check_v2\\1_web_book_check_v2\\1_Server\\fastapi-auth-app\\"
#path_word_spit=f"/faxin/core/book_check/1_Server/fastapi-auth-app/"

path_check_log=f"E:\\faxin_ai_2023\\branches\\faxin_ai_uie_2023\\39_book_check_v2\\1_web_book_check_v2\\2_Server_Check\\"
#path_check_log=f"/faxin/core/book_check/2_Server_Check/"

path_book_source="uploads" #存放用户上传的文件保存的目录，每个用户以用户名称创建对应的文件夹
path_book_check_dist="check_book" #存用户的文件，被大模型分析后的json文件保存的目录（每个文件夹以文件的md5值为文件夹名称，之后创建多个不同的文件夹，存放不同的模型分析的数据结果）
path_book_html_mode="html_model" #存放大模型分析后的html 模板文件的文件夹
pub_ollama_url="http://192.168.0.19:11434/api/chat" #ollama的url

# 轮询模型列表
#model_list = ["deepseek-r1:32b-1", "deepseek-r1:32b-2", "deepseek-r1:32b-3", "deepseek-r1:32b-4"]
#model_cycle = itertools.cycle(model_list)  # 轮流获取模型名称

#pub_ollama_url_list = ["http://192.168.0.19:11435/api/chat", "http://192.168.0.19:11436/api/chat", "http://192.168.0.19:11437/api/chat", "http://192.168.0.19:11438/api/chat", "http://192.168.0.19:11439/api/chat", "http://192.168.0.19:11440/api/chat", "http://192.168.0.19:11441/api/chat", "http://192.168.0.19:11442/api/chat"]
pub_ollama_url_list = ["http://192.168.0.19:11435/api/chat", "http://192.168.0.19:11436/api/chat", "http://192.168.0.19:11437/api/chat", "http://192.168.0.19:11438/api/chat"]
pub_ollama_url_cycle = itertools.cycle(pub_ollama_url_list)  # 轮流获取模型名称

pub_default_llm_mode_name='qwen2.5:7b'
pub_default_prompt='''
                # 领导人言论分析助手提示词
                ## 角色定位与处理要求
                你是一个专业的内容分析引擎，专门从文本中提取领导人言论信息并以严格的JSON格式输出。
                ## 输出规范
                1. 当内容中包含领导人言论时：
                ```json
                {
                "message": "发现人物言论信息",
                "status": "success",
                "data": {
                    "people": [
                    {
                        "name": "识别到的人名",
                        "position": "自动推断的职位/身份（如可推断）",
                        "quotes": [
                        {
                            "text": "直接引用的原文",
                            "type": "direct/indirect",
                            "context": "前后文摘要（50字内）"
                        }
                        ]
                    }
                    ],
                    "summary": {
                    "total_people": 总数,
                    "total_quotes": 总引用数
                    }
                }
                }
                ```

                2.当内容中不包含领导人言论时：
                ```json
                {
                "message": "没有发现人物言论信息",
                "status": "empty"
                }
                ```
                ## 处理规则
                1. 人名识别支持：中文姓名、英文名+姓、常见称谓+姓氏（如"王教授"）
                2. 模糊指代（如"某专家"）标记为"anonymous"
                3. 同一人物的不同称谓合并处理
                4. 间接引用需标注原意概括
                5. 至少满足以下条件之一才视为有效人物言论：
                - 包含明确的姓名+言论
                - 有直接引语（引号内内容）
                - 有明确的间接引用（如"XX表示/认为..."）
                6. 如果内容中一个人物的言论出现在多处，请分别单独列出来。

                ## 特别说明
                - 政治敏感人物自动添加"public_figure"标记
                - 存在争议的言论保留原文不做解释
                - 无法确定准确性的引用添加"uncertain"标签
                - "张军"目前的职务是"最高人民法院院长"

                [系统指令] 先进行全文扫描，确认存在人物言论信息后再执行详细分析，否则立即返回空结果提示。只输出JSON格式结果，不包含任何解释性文字。

                '''
pub_default_prompt_v2='''
                # 人物言论分析助手提示词
                ## 角色定位与处理要求
                你是一个专业的内容分析引擎，专门从文本中提取人物言论信息并以严格的JSON格式输出。
                ## 输出规范
                1. 当内容中包含人物言论时：
                ```json
                {
                "message": "发现人物言论信息",
                "status": "success",
                "data": {
                    "people": [
                    {
                        "name": "识别到的人名",
                        "position": "自动推断的职位/身份（如可推断）",
                        "quotes": [
                        {
                            "text": "直接引用的原文",
                            "type": "direct/indirect",
                            "context": "前后文摘要（50字内）"
                        }
                        ]
                    }
                    ],
                    "summary": {
                    "total_people": 总数,
                    "total_quotes": 总引用数
                    }
                }
                }
                ```

                2.当内容中不包含人物言论时：
                ```json
                {
                "message": "没有发现人物言论信息",
                "status": "empty"
                }
                ```
                ## 处理规则
                1. 人名识别支持：中文姓名、英文名+姓、常见称谓+姓氏（如"王教授"）
                2. 模糊指代（如"某专家"）标记为"anonymous"
                3. 同一人物的不同称谓合并处理
                4. 间接引用需标注原意概括
                5. 至少满足以下条件之一才视为有效人物言论：
                - 包含明确的姓名+言论
                - 有直接引语（引号内内容）
                - 有明确的间接引用（如"XX表示/认为..."）

                ## 特别说明
                - 政治敏感人物自动添加"public_figure"标记
                - 存在争议的言论保留原文不做解释
                - 无法确定准确性的引用添加"uncertain"标签

                [系统指令] 先进行全文扫描，确认存在人物言论信息后再执行详细分析，否则立即返回空结果提示。只输出JSON格式结果，不包含任何解释性文字。

                '''
pub_default_prompt_v1='''            
            # 人物言论分析助手提示词

            ## 角色定位
            你是一个专业的内容分析引擎，专门从文本中提取人物言论信息并结构化输出。

            ## 处理要求
            1. **输入分析**
            - 接收任意长度的文本内容
            - 自动识别所有提及的人名（中英文）
            - 检测直接引用和间接引用的言论

            2. **输出规范**
            - 严格使用JSON格式
            - 包含以下字段：
                ```json
                {
                "people": [
                    {
                    "name": "识别到的人名",
                    "position": "自动推断的职位/身份（如可推断）",
                    "quotes": [
                        {
                        "text": "直接引用的原文",
                        "type": "direct/indirect",
                        "context": "前后文摘要（50字内）"
                        }
                    ]
                    }
                ],
                "summary": {
                    "total_people": 总数,
                    "total_quotes": 总引用数
                }
                }
                ```

            ## 处理规则
            1. 人名识别支持中文姓名、英文名+姓
            2. 模糊指代（如"某专家"）标记为"anonymous"
            3. 同一人物的不同称谓合并处理
            4. 间接引用需标注原意概括

            ## 特别说明
            - 政治敏感人物自动添加"public_figure"标记
            - 存在争议的言论保留原文不做解释
            - 无法确定准确性的引用添加"uncertain"标签

            [系统指令] 始终优先保持原文准确性，不做任何内容润色或总结性评论。
            '''
#定义全局变量--从llm_prompt_file.json文件中读取的prompt和llm_mode_name
#如果文件为空则去默认值
pub_llm_mode_name=pub_default_llm_mode_name
pub_prompt=pub_default_prompt

def chat_with_ollama(ollama_url:str,model: str, system_prompt: str, user_input: str, output_file: str, temperature: float = 0.8, top_k: int = 50, top_p: float = 0.9):
    url = ollama_url  # Ollama 本地服务地址
    print(f"正在与 Ollama 服务器 {ollama_url} 进行对话...")
    headers = {"Content-Type": "application/json"}
    
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"请分析这段内容：\r\n {user_input}"}
        ],
        "temperature": temperature,  # 控制生成的随机性
        "top_k": top_k,  # 选择前 k 个最高概率的词
        "top_p": top_p,  # 采样前 P 概率质量的词
        "stream": False  # 关闭流式输出
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=180)  # 设置超时时间为180秒（3分钟）
        
        if response.status_code == 200:
            result = response.json()
            with open(output_file, "w", encoding="utf-8") as file:
                json.dump(result, file, ensure_ascii=False, indent=4)
            print(f"结果已保存至 {output_file}")

            print(json.dumps(result, indent=4, ensure_ascii=False))
        else:
            print(f"请求失败: {response.status_code}, {response.text}")
    except requests.Timeout:
        with open(output_file, "w", encoding="utf-8") as file:
            error_data = {
                "model": model,
                "created_at": "",
                "message": {
                    "role": "error",
                    "content": "请求AI接口超时，判断跳过"
                }
            }
            json.dump(error_data, file, ensure_ascii=False, indent=4)
        print("请求AI接口超时，判断跳过")


def get_md5_of_filename(filename):
    """依据文件名称得到对应的md5值"""
    # Extract filename with extension but without path
    filename_with_extension = os.path.basename(filename)
    # Generate MD5 hash of filename
    filename_with_extension_md5_name = hashlib.md5(filename_with_extension.encode()).hexdigest()
            
    return filename_with_extension_md5_name

def read_llm_prompt_from_json(llm_prompt_file_name):
    '''
    从json文件中读取数据（为docx文件上传的时候使用的llm_prompt.json文件）

    返回值：str_prompt, str_llm_mode_name
    '''
    try:
        with open(llm_prompt_file_name, "r", encoding="utf-8") as json_file:
            data = json.load(json_file)
        
        str_prompt = data.get("str_prompt", "")
        str_llm_mode_name = data.get("str_llm_mode_name", "")
        
        return str_prompt, str_llm_mode_name
    except FileNotFoundError:
        print(f"Error: File '{llm_prompt_file_name}' not found.")
        return pub_default_prompt, pub_default_llm_mode_name
    except json.JSONDecodeError:
        print(f"Error: Failed to parse JSON from file '{llm_prompt_file_name}'.")
        return pub_default_prompt, pub_default_llm_mode_name
    except Exception as e:
        print(f"Error: {e}")
        return pub_default_prompt, pub_default_llm_mode_name

def read_json_file(filename_md5,folder_check):
    '''
    filename_md5 --原始文件md5之后的文件夹名称
    folder_check --经过模型分析后的文件夹名称（存放分析结果）
    '''
    
    '''
    函数：接收文件名称，文件格式为json格式

    json内容格式：
        {
            "type": "text",
            "content": "数字法院概论",
            "page": 1,
            "id": 1
        }
    将内容读取后，逐条输出    
    '''
    """
    Read JSON file and print each record.
    
    Args:
        filename (str): Path to JSON file
        
    Returns:
        list: List of JSON records
    """
    try:
        with open(filename_md5, 'r', encoding='utf-8') as file:
            data = json.load(file)
        
        #2025.03.25添加读取对应图书的提示词文件的代码
        #llm_promtp_file_name= os.path.join(folder_check,"1_Json", "llm_prompt.json")
        #从json文件中读取prompt和llm_mode_name，赋值给全局变量
        #pub_prompt, pub_llm_mode_name = read_llm_prompt_from_json(llm_promtp_file_name)
        pub_prompt, pub_llm_mode_name=pub_default_prompt,pub_default_llm_mode_name


        if not isinstance(data, list):
            print("错误：JSON 文件内容应为列表格式")
            return        
        count_text_items = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = []
            for item in data:
                if item.get('type') == 'text':
                    count_text_items += 1
                    futures.append(executor.submit(Check_Text_LingDaoRen, item, folder_check,pub_prompt, pub_llm_mode_name))
            
            # 等待所有线程完成
            for future in concurrent.futures.as_completed(futures):
                future.result()

        return count_text_items            
    except FileNotFoundError:
        print(f"Error: File '{filename_md5}' not found")
        return []
    except json.JSONDecodeError:
        print("Error: Invalid JSON format")
        return []
    except Exception as e:
        print(f"Error: {str(e)}")
        return []

def write_finish_info_v1(check_a_json_file_name, finish_num):
    '''
    记录分析动作的完成时间 2025.04.24
    '''
    data = {
        "finish": "ok",
        "finish_num": finish_num,
        "finish_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    with open(check_a_json_file_name, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def write_finish_info(check_a_json_file_name, finish_num):
    '''
    记录分析动作的完成时间 2025.08.13
    如果目标文件夹不存在则自动创建，并添加异常容错处理
    '''
    try:
        # 确保文件夹存在
        folder = os.path.dirname(check_a_json_file_name)
        if folder and not os.path.exists(folder):
            os.makedirs(folder, exist_ok=True)

        data = {
            "finish": "ok",
            "finish_num": finish_num,
            "finish_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        with open(check_a_json_file_name, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        print(f"[INFO] 完成信息已写入: {check_a_json_file_name}")

    except Exception as e:
        print(f"[ERROR] 写入完成信息失败: {e}")

'''
请编写函数 Check_A(records)，实现以下功能：
调用ollama 的接口，检查 records 中的每一条记录，返回检查结果。
'''

def Check_Text_LingDaoRen(records, created_folder, str_prompt, str_llm_mode_name):
    output_file_json = os.path.join(created_folder, '2_Check_LingDaoRen', f"{records.get('id')}.json")
    
    if os.path.exists(output_file_json):
        print(f"文件 {output_file_json} 已存在，跳过检查。")
        return
    
    print(f"id: {records.get('id')}")
    ollama_url = next(pub_ollama_url_cycle)
    
    max_attempts = 3
    attempt = 0
    while attempt < max_attempts:
        chat_with_ollama(
            ollama_url=ollama_url,
            model=str_llm_mode_name,
            system_prompt=str_prompt,
            user_input=records.get('content'),
            output_file=output_file_json,
            temperature=0.8,
            top_k=40,
            top_p=0.9
        )
        
        rec_content = records.get('content')
        print(f"rec_content={rec_content}")
        
        #llm_is_ok,check_llm_error_msg = Check_LLM_Return_Is_Ok(rec_content, output_file_json)
        #llm_is_ok,check_llm_error_msg=True,"llm_test_msg"
        #验证大模型返回的数据格式是否正确
        llm_is_ok,check_llm_error_msg =Check_LLM_Return_Is_Ok_LingDaoRen(rec_content, output_file_json)
        
        if llm_is_ok:
            return  # 成功返回
        
        attempt += 1
        #if attempt < max_attempts - 1:  # 只在前两次失败时移动文件
        if attempt < max_attempts :  #如果三次都错误，则移动文件到error_log（此id对应的json文件将不存在）
            error_path_log = os.path.join(created_folder, '2_Check_LingDaoRen', "error_log")
            os.makedirs(error_path_log, exist_ok=True)
            
            timestamp = time.strftime("%Y_%m_%d_%H_%M_%S")
            random_number = random.randint(1000, 9999)
            error_filename = f"{records.get('id')}_{timestamp}_{random_number}.json"
            error_filepath = os.path.join(error_path_log, error_filename)
            
            shutil.move(output_file_json, error_filepath)
            # 在 error_filepath 文件末尾追加信息 check_llm_error_msg
            with open(error_filepath, 'a', encoding='utf-8') as file:
                file.write(f"\n error={check_llm_error_msg}\n rec_content={rec_content}\n")  # 在文件末尾追加错误信息，并加上换行符

            print(f"error_msg={check_llm_error_msg}\r\n文件 {output_file_json} 移动到 {error_filepath}")


def Get_File_List_By_UserName(s_username: str) -> List[Tuple[str, float]]:
    #path_word_spit = "/your/base/path/"  # 请替换为实际路径
    #path_book_source = "book_source/"
    """获取用户上传的文件列表"""
    search_path = os.path.join(path_word_spit, path_book_source, s_username or "")
    
    if not os.path.exists(search_path):
        print(f"路径不存在: {search_path}")
        return []
    
    # 递归搜索所有 .docx 文件
    #search_pattern = os.path.join(search_path, "**", "*.docx")
    #file_list = glob.glob(search_pattern, recursive=True)

    # 递归搜索 .docx 和 .pdf 2025.08.12
    docx_pattern = os.path.join(search_path, "**", "*.docx")
    pdf_pattern = os.path.join(search_path, "**", "*.pdf")
    file_list = glob.glob(docx_pattern, recursive=True) + glob.glob(pdf_pattern, recursive=True)
    
    # 获取文件创建时间
    #files_with_time = [(file, os.path.getctime(file)) for file in file_list]
    # 获取文件创建时间，并格式化为年月日时间格式
    files_with_time = [(file, dt.datetime.fromtimestamp(os.path.getctime(file)).strftime('%Y-%m-%d %H:%M:%S')) for file in file_list]
    
    # 按创建时间升序排序
    files_with_time.sort(key=lambda x: x[1])
    
    return files_with_time

def main_check_json_file(s_username):
    #s_username = "admin2"  # 请替换为实际用户名
    file_list = Get_File_List_By_UserName(s_username)
    if not file_list:
        print("未找到符合条件的文件。")
        return
    
    for file, ctime in file_list:
        print(f"文件名: {os.path.basename(file)}, 创建时间: {ctime}")
        #添加功能依据os.path.basename(file)，得到对应的md5值，之后跟md5值，得到对应目录1_json目录下的原始文件内容，以及2_Check_A目录下的已经处理过的文件
        #记录处理没有处理过的记录
        filename_with_extension_md5_name = hashlib.md5(os.path.basename(file).encode()).hexdigest()
        #原始文件
        processed_data_json_file_name = os.path.join(path_word_spit, path_book_check_dist,filename_with_extension_md5_name,"1_Json", "processed_data.json")

        #创建目标文件夹 2_Check_LingDaoRen
        path_Check_LingDaoRen = os.path.join(path_word_spit, path_book_check_dist,filename_with_extension_md5_name, "2_Check_LingDaoRen")
        os.makedirs(path_Check_LingDaoRen, exist_ok=True)

        #Check_A是否完成的记录文件名称为：check_a.json
        check_lingdaoren_json_file_name = os.path.join(path_word_spit, path_book_check_dist,filename_with_extension_md5_name,"1_Json", "check_lingdaoren.json")
        #判断check_lawtiao_json_file_name 是否存在，如果存在，则跳过，如果不存在，则执行处理
        if not os.path.exists(check_lingdaoren_json_file_name):
            #目标文件夹
            folder_check=os.path.join(path_word_spit, path_book_check_dist,filename_with_extension_md5_name)
            finish_num=read_json_file(processed_data_json_file_name,folder_check)
            # 判断finish_num是否为空或读取失败 2025.10.28
            if not finish_num:
                print(f"文件 {processed_data_json_file_name} 不存在或者格式有错误。")
            else:
                #文件处理完成，则创建check_lingdaoren.json (finish_num -目前主要记录的是text类型的数据的分析数量)
                write_finish_info(check_lingdaoren_json_file_name, finish_num)
        else:
            print(f"{check_lingdaoren_json_file_name}文件已存在，跳过处理。")


# 示例代码: 遍历返回值并输出到控制台
def test_Get_File_List_By_UserName():
    s_username = "admin2"  # 请替换为实际用户名
    file_list = Get_File_List_By_UserName(s_username)
    
    if not file_list:
        print("未找到符合条件的文件。")
        return
    
    for file, ctime in file_list:
        print(f"文件名: {os.path.basename(file)}, 创建时间: {ctime}")

def Loop_Check_LingDaoRen():
    # 创建日志目录
    log_dir = os.path.join(path_check_log, "log_file")
    os.makedirs(log_dir, exist_ok=True)
    
    # 获取当前日期作为日志文件名
    log_filename = os.path.join(log_dir, datetime.now().strftime('%Y-%m-%d') + "_LingDaoRen.log")

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
        
        main_check_json_file("")
        
        end_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        logging.info(f'执行完毕 {end_time}')
        print(f'执行完毕 {end_time}')
        
        print(f'休眠 1 分钟...{end_time}')
        print(f'log file={log_filename}')
        time.sleep(60)  # 休眠 1 分钟

def read_check_json_content(filename):
    """
    读取：1_Json\1-n.json文件的内容

    Read model and content values from a JSON file.
    
    Args:
        filename (str): Path to JSON file
        
    Returns:
        tuple: (model, content) or (None, None) if error occurs
    """
    try:
        with open(filename, 'r', encoding='utf-8') as file:
            data = json.load(file)
            
        model = data.get('model')
        content = data.get('message', {}).get('content')
        
        return model, content
            
    except FileNotFoundError:
        print(f"Error: File '{filename}' not found")
        return "","" 
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON in file '{filename}'")
        return "","" 
    except Exception as e:
        print(f"Error: {str(e)}")
        return "","" 
def close_unclosed_html_tags(think_str):
    soup = BeautifulSoup(think_str, "html.parser")
    fixed_html = str(soup)
    
    if think_str.strip() != fixed_html.strip():
        fixed_html += "\n<!-- 代码闭合 -->"
    
    return fixed_html


def Check_LLM_Return_Is_Ok(rec_content, output_file_json):
    '''
    2025.03.25 检查LLM返回内容的格式是否正确
    '''
    # 第一步：读取文件内容
    check_a_model, check_a_content = read_check_json_content(output_file_json)
    if not check_a_content:
        return False, "文件内容为空或读取失败"
    
    # 第二步：检查是否有 "是否正确": true
    if '"是否正确": true' in check_a_content:
        return True, "正确"
    
    # 第三步：处理 LLM 返回内容
    #think_str = ""
    #think_match = re.search(r'<think>(.*?)</think>', check_a_content, re.DOTALL)
    #if think_match:
    #    think_str = think_match.group(1).strip()
    
    # 修正未闭合的 HTML 标签
    #think_str = close_unclosed_html_tags(think_str)
    
    try:
        # 提取 JSON 内容
        json_str = check_a_content[check_a_content.find('{'):check_a_content.rfind('}')+1]
        json_data = json.loads(json_str)
        
        # 检查是否 "是否正确" 为 False
        is_correct = not json_data.get("是否正确", True)
        if is_correct:
            #json_content = json_data.get("内容", "")
            check_list = []
            
            # 提取错误列表
            errors = json_data.get("错误列表", [])
            for error in errors:
                check_list.append({
                    "原始值": error.get("原始值", ""),
                    "建议修改值": error.get("建议修改值", "")
                })
            
            # 去除全角空格、半角空格、回车换行符以及HTML标签
            str_content = re.sub(r'\s+', ' ', rec_content)  # 去除所有空格、回车、换行
            str_content = re.sub(r'<[^>]*>', '', str_content)  # 去除HTML标签
            
            # 判断 error['原始值'] 是否全部存在于 str_content 中
            success = bool(check_list)  # 如果 check_list 为空，则 success 为 False
            if not success:  # 如果 check_list 为空，则直接返回
                return False, "错误列表为空"
            
            # 检查每个 error['原始值'] 是否都在 str_content 中
            for error in check_list:
                if not error['原始值'] or error['原始值'] not in str_content:
                    return False, f"错误值 '{error['原始值']}' 未在内容中找到"
                
                if error['原始值'] == error['建议修改值']:
                    return False, "原始值与建议修改值相等"
            
            return True, "正确"
        else:
            return True, "正确"
    except json.JSONDecodeError:
        return False, "JSON 解析失败"
    except Exception as e:
        return False, f"处理内容时发生错误: {str(e)}"


def Check_LLM_Return_Is_Ok_LingDaoRen(rec_content, output_file_json):
    '''
    2025.04.09 检查LLM返回内容的格式是否正确
    '''
    # 第一步：读取文件内容
    check_a_model, check_a_content = read_check_json_content(output_file_json)
    if not check_a_content:
        return False, "文件内容为空或读取失败"
    
    # 第二步：LLM返回内容中，是否包含："message": "发现人物言论信息" 或 "message": "没有发现人物言论信息"
    if '"message": "发现人物言论信息"' in check_a_content or '"message": "没有发现人物言论信息"' in check_a_content:
        return True, "正确"   
    
    
    try:
        # 提取 JSON 内容
        json_str = check_a_content[check_a_content.find('{'):check_a_content.rfind('}')+1]
        json_data = json.loads(json_str)
        
        # 1. 判断 message 字段
        if json_data.get("message") == "发现人物言论信息":
            check_list = []

            # 2. 遍历 people 节点
            for person in json_data["data"]["people"]:
                name = person.get("name", "").strip()
                position = person.get("position", "").strip()
                for quote in person.get("quotes", []):
                    text = quote.get("text", "").strip()
                    # 添加到 check_list
                    check_list.append({
                        "name": name,
                        "position": position,
                        "text": text
                    })

            # 去除全角空格、半角空格、回车换行符以及HTML标签(此处可能会有bug，暂时不处理)
            #str_content = re.sub(r'\s+', ' ', rec_content)  # 去除所有空格、回车、换行
            #str_content = re.sub(r'<[^>]*>', '', str_content)  # 去除HTML标签
            str_content=rec_content
            # 3. 检查 check_list 中的 name 和 text 是否都存在于 str_content 中
            if check_list:
                for item in check_list:
                    name = item["name"]
                    text = item["text"]
                    if name and text:
                        if name not in str_content or text not in str_content:
                            print("错误")
                            #2026.03.20 如果错误，将output_file_json文件的内容改为空，并返回False
                            print("错误--将文件内容改为置为空--并返回False")
                            clear_and_write_empty(output_file_json)
                            return False, f"错误值 '{name} 或者 {text}' 未在内容中找到"
                            break
                else:
                    print("正确")
                    return True, "正确"
            else:
                print("check_list 为空")
                return True, "正确"
        else:
            print("message 字段不符合要求")            
            return True, "正确"

    except json.JSONDecodeError:
        return False, "JSON 解析失败"
    except Exception as e:
        return False, f"处理内容时发生错误: {str(e)}"

'''
2026.03.20 
# 示例：调用函数
output_file_json = 'your_file_path.json'  # 替换为实际的文件路径
clear_and_write_empty(output_file_json)

'''    
def clear_and_write_empty(output_file_json):
    try:
        # 打开文件，模式为写入（'w'），会清空文件内容
        with open(output_file_json, 'w', encoding='utf-8') as file:
            file.write('')  # 将内容清空并写入空字符串
        print(f"文件 {output_file_json} 已清空并写入空内容。")
    except Exception as e:
        print(f"出现错误：{e}")

if __name__ == "__main__":    

    Loop_Check_LingDaoRen()

    


'''
# 示例 JSON 数据
data_json = {
    "message": "发现人物言论信息",
    "status": "success",
    "data": {
        "people": [
            {
                "name": "张三",
                "position": "公司CEO",
                "quotes": [
                    {
                        "text": "我们将持续创新，推动行业发展。",
                        "type": "direct",
                        "context": "张三在接受采访时表示"
                    }
                ]
            },
            {
                "name": "李四",
                "position": "技术总监",
                "quotes": [
                    {
                        "text": "技术是我们成功的关键。",
                        "type": "indirect",
                        "context": "李四在会议上强调"
                    }
                ]
            }
        ],
        "summary": {
            "total_people": 2,
            "total_quotes": 2
        }
    }
}

'''
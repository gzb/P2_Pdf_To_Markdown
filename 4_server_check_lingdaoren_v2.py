import json
import os
import hashlib
import requests
import glob
import datetime as dt
import concurrent.futures
import itertools
import time
import logging
from datetime import datetime
import shutil
import random
from typing import List, Tuple

# ======================== 配置常量 ========================

path_word_spit = f"E:\\faxin_ai_2023\\branches\\faxin_ai_uie_2023\\39_book_check_v2\\1_web_book_check_v2\\1_Server\\fastapi-auth-app\\"
path_check_log = f"E:\\faxin_ai_2023\\branches\\faxin_ai_uie_2023\\39_book_check_v2\\1_web_book_check_v2\\2_Server_Check\\"

path_book_source = "uploads" # 用户上传的文件保存的目录
path_book_check_dist = "check_book" # 大模型分析后的数据结果目录

pub_ollama_url_list = [
    "http://192.168.0.19:11435/api/chat",
    "http://192.168.0.19:11436/api/chat",
    "http://192.168.0.19:11437/api/chat",
    "http://192.168.0.19:11438/api/chat"
]
pub_ollama_url_cycle = itertools.cycle(pub_ollama_url_list)

pub_default_llm_mode_name = 'qwen2.5:7b'
pub_default_prompt = '''
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

# ======================== 核心函数 ========================

def chat_with_ollama(ollama_url: str, model: str, system_prompt: str, user_input: str, output_file: str, temperature: float = 0.8, top_k: int = 50, top_p: float = 0.9):
    print(f"正在与 Ollama 服务器 {ollama_url} 进行对话...")
    headers = {"Content-Type": "application/json"}
    
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"请分析这段内容：\r\n {user_input}"}
        ],
        "temperature": temperature,
        "top_k": top_k,
        "top_p": top_p,
        "stream": False
    }
    
    try:
        response = requests.post(ollama_url, headers=headers, json=payload, timeout=180)
        
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


def read_json_file(filename_md5, folder_check):
    """
    读取 JSON 文件并并发处理每条文本记录
    """
    try:
        with open(filename_md5, 'r', encoding='utf-8') as file:
            data = json.load(file)
        
        pub_prompt, pub_llm_mode_name = pub_default_prompt, pub_default_llm_mode_name

        if not isinstance(data, list):
            print("错误：JSON 文件内容应为列表格式")
            return        
        
        count_text_items = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = []
            for item in data:
                if item.get('type') == 'text':
                    count_text_items += 1
                    futures.append(executor.submit(Check_Text_LingDaoRen, item, folder_check, pub_prompt, pub_llm_mode_name))
            
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


def write_finish_info(check_a_json_file_name, finish_num):
    """
    记录分析动作的完成时间
    """
    try:
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


def Check_Text_LingDaoRen(records, created_folder, str_prompt, str_llm_mode_name):
    """
    调用ollama 的接口，检查 records 中的每一条记录，返回检查结果
    """
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
        
        llm_is_ok, check_llm_error_msg = Check_LLM_Return_Is_Ok_LingDaoRen(rec_content, output_file_json)
        
        if llm_is_ok:
            return  # 成功返回
        
        attempt += 1
        if attempt < max_attempts:  # 错误处理，移动文件到error_log
            error_path_log = os.path.join(created_folder, '2_Check_LingDaoRen', "error_log")
            os.makedirs(error_path_log, exist_ok=True)
            
            timestamp = time.strftime("%Y_%m_%d_%H_%M_%S")
            random_number = random.randint(1000, 9999)
            error_filename = f"{records.get('id')}_{timestamp}_{random_number}.json"
            error_filepath = os.path.join(error_path_log, error_filename)
            
            shutil.move(output_file_json, error_filepath)
            with open(error_filepath, 'a', encoding='utf-8') as file:
                file.write(f"\\n error={check_llm_error_msg}\\n rec_content={rec_content}\\n")

            print(f"error_msg={check_llm_error_msg}\\r\\n文件 {output_file_json} 移动到 {error_filepath}")


def Get_File_List_By_UserName(s_username: str) -> List[Tuple[str, str]]:
    """获取用户上传的文件列表"""
    search_path = os.path.join(path_word_spit, path_book_source, s_username or "")
    
    if not os.path.exists(search_path):
        print(f"路径不存在: {search_path}")
        return []
    
    docx_pattern = os.path.join(search_path, "**", "*.docx")
    pdf_pattern = os.path.join(search_path, "**", "*.pdf")
    file_list = glob.glob(docx_pattern, recursive=True) + glob.glob(pdf_pattern, recursive=True)
    
    files_with_time = [(file, dt.datetime.fromtimestamp(os.path.getctime(file)).strftime('%Y-%m-%d %H:%M:%S')) for file in file_list]
    files_with_time.sort(key=lambda x: x[1])
    
    return files_with_time


def main_check_json_file(s_username):
    file_list = Get_File_List_By_UserName(s_username)
    if not file_list:
        print("未找到符合条件的文件。")
        return
    
    for file, ctime in file_list:
        print(f"文件名: {os.path.basename(file)}, 创建时间: {ctime}")
        
        filename_with_extension_md5_name = hashlib.md5(os.path.basename(file).encode()).hexdigest()
        processed_data_json_file_name = os.path.join(path_word_spit, path_book_check_dist, filename_with_extension_md5_name, "1_Json", "processed_data.json")

        path_Check_LingDaoRen = os.path.join(path_word_spit, path_book_check_dist, filename_with_extension_md5_name, "2_Check_LingDaoRen")
        os.makedirs(path_Check_LingDaoRen, exist_ok=True)

        check_lingdaoren_json_file_name = os.path.join(path_word_spit, path_book_check_dist, filename_with_extension_md5_name, "1_Json", "check_lingdaoren.json")
        
        if not os.path.exists(check_lingdaoren_json_file_name):
            folder_check = os.path.join(path_word_spit, path_book_check_dist, filename_with_extension_md5_name)
            finish_num = read_json_file(processed_data_json_file_name, folder_check)
            
            if not finish_num:
                print(f"文件 {processed_data_json_file_name} 不存在或者格式有错误。")
            else:
                write_finish_info(check_lingdaoren_json_file_name, finish_num)
        else:
            print(f"{check_lingdaoren_json_file_name} 文件已存在，跳过处理。")


def Loop_Check_LingDaoRen():
    log_dir = os.path.join(path_check_log, "log_file")
    os.makedirs(log_dir, exist_ok=True)
    
    log_filename = os.path.join(log_dir, datetime.now().strftime('%Y-%m-%d') + "_LingDaoRen.log")

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
        time.sleep(60)


def read_check_json_content(filename):
    """
    读取：2_Check_LingDaoRen\\*.json文件的内容
    """
    try:
        with open(filename, 'r', encoding='utf-8') as file:
            data = json.load(file)
            
        model = data.get('model')
        content = data.get('message', {}).get('content')
        
        return model, content
            
    except FileNotFoundError:
        print(f"Error: File '{filename}' not found")
        return "", "" 
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON in file '{filename}'")
        return "", "" 
    except Exception as e:
        print(f"Error: {str(e)}")
        return "", "" 


def Check_LLM_Return_Is_Ok_LingDaoRen(rec_content, output_file_json):
    """
    检查LLM返回内容的格式是否正确，及关键提取信息是否确实存在于原文中
    """
    check_a_model, check_a_content = read_check_json_content(output_file_json)
    if not check_a_content:
        return False, "文件内容为空或读取失败"
    
    if '"message": "发现人物言论信息"' in check_a_content or '"message": "没有发现人物言论信息"' in check_a_content:
        pass   
    
    try:
        json_str = check_a_content[check_a_content.find('{'):check_a_content.rfind('}')+1]
        json_data = json.loads(json_str)
        
        if json_data.get("message") == "发现人物言论信息":
            check_list = []
            
            for person in json_data.get("data", {}).get("people", []):
                name = person.get("name", "").strip()
                position = person.get("position", "").strip()
                for quote in person.get("quotes", []):
                    text = quote.get("text", "").strip()
                    check_list.append({
                        "name": name,
                        "position": position,
                        "text": text
                    })

            str_content = rec_content
            if check_list:
                for item in check_list:
                    name = item["name"]
                    text = item["text"]
                    if name and text:
                        if name not in str_content or text not in str_content:
                            print("错误--将文件内容改为置为空--并返回False")
                            clear_and_write_empty(output_file_json)
                            return False, f"错误值 '{name}' 或者 '{text}' 未在内容中找到"
                print("正确")
                return True, "正确"
            else:
                print("check_list 为空")
                return True, "正确"
        else:
            print("message 字段不符合要求或者没有发现言论")            
            return True, "正确"

    except json.JSONDecodeError:
        return False, "JSON 解析失败"
    except Exception as e:
        return False, f"处理内容时发生错误: {str(e)}"


def clear_and_write_empty(output_file_json):
    try:
        with open(output_file_json, 'w', encoding='utf-8') as file:
            file.write('')  
        print(f"文件 {output_file_json} 已清空并写入空内容。")
    except Exception as e:
        print(f"出现错误：{e}")


if __name__ == "__main__":    
    Loop_Check_LingDaoRen()

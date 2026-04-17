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
import re

import urllib.request
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Tuple
'''
#2026.04.14
本工具采用 **“规则召回 + LLM判别/补全”** 的混合架构，旨在从复杂的中文文献中精准提取特定人物（如“习近平”）的讲话原话。
'''

# ======================== 配置常量 ========================

path_word_spit = f"C:\\1_web_book_check_v2\\1_Server\\fastapi-auth-app\\"
path_check_log = f"C:\\faxin_ai_uie_2023\\39_book_check_v2\\1_web_book_check_v2\\2_Server_Check\\"

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
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
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
    #2026.04.13 增加两个函数（测试类似功能）
    #1.使用规则提取
    #Check_Text_LingDaoRen_Reg(records, created_folder, str_prompt, str_llm_mode_name)
    #2.使用ollama(另外一个提示词语提取)
    '''
    qwen2.5:32b
    qwen3.5:35b
    gpt-oss:latest
    gpt-oss:120b
    '''
    #Check_Text_LingDaoRen_LLM_V2(records, created_folder, str_prompt, "qwen2.5:32b")
    #Check_Text_LingDaoRen_LLM_V2(records, created_folder, str_prompt, "qwen3.5:35b")
    #Check_Text_LingDaoRen_LLM_V2(records, created_folder, str_prompt, "gpt-oss:latest")
    #Check_Text_LingDaoRen_LLM_V2(records, created_folder, str_prompt, "gpt-oss:120b")

    Check_Text_LingDaoRen_LLM_V3(records, created_folder, str_prompt, "qwen2.5:32b")

    return

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

'''
使用规则方式提取领导人讲话内容
2026.04.13
'''
def Check_Text_LingDaoRen_Reg(records, created_folder, str_prompt, str_llm_mode_name):
    """
    调用ollama 的接口，检查 records 中的每一条记录，返回检查结果
    """
    output_file_json = os.path.join(created_folder, '2_Check_LingDaoRen', f"{records.get('id')}_reg.json")
    
    if os.path.exists(output_file_json):
        print(f"文件 {output_file_json} 已存在，跳过检查。")
        return
    
    print(f"id: {records.get('id')}")
    
    # 使用规则获取领导人讲话 2026.04.13    
     # 1. 测试方案1（规则提取）
    rec_content = records.get('content')
    print("\n【方案1：基于规则（正则表达式）的提取结果】")
    rule_results = extract_quotes_by_rule(rec_content)
    print(json.dumps(rule_results, ensure_ascii=False, indent=4))
    
    # 2. 将方案1的结果写入文件
    print(f"\n【将方案1的结果包装并写入文件】")
    save_rule_results_to_json(rule_results, output_file_json)
        
    llm_is_ok, check_llm_error_msg = Check_LLM_Return_Is_Ok_LingDaoRen(rec_content, output_file_json)
        
    if llm_is_ok:
        return  # 成功返回
        
    else:
        print(f"LLM_Error_Msg={check_llm_error_msg}")
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

# ==========================================================
# 方案1：基于规则（正则表达式）提取“习近平”讲过的语句
# ==========================================================
def extract_quotes_by_rule(text):
    """
    使用正则表达式提取文本中“习近平”讲过的语句。
    匹配逻辑：寻找包含“习近平”的句子，并提取其中双引号内的内容。
    返回规范的 JSON 数据格式。
    """
    quotes_list = []
    
    # 简单切分句子，按句号切分
    sentences = re.split(r'([。！？])', text)
    sentences = ["".join(i) for i in zip(sentences[0::2], sentences[1::2] + [""])]
    
    quote_pattern = re.compile(r'["“]([^"”]+)["”]')
    
    for sentence in sentences:
        if "习近平" in sentence:
            # 截取“习近平”出现位置到段落末尾的子串
            xi_context = sentence[sentence.find("习近平"):]
            
            # 检查是否有引导动词
            verbs = ["指出", "强调", "要求", "提出", "明确", "认为", "深刻指出", "强调指出", "指出："]
            if any(verb in xi_context[:50] for verb in verbs):
                # 提取双引号内的内容
                quotes = quote_pattern.findall(xi_context)
                if quotes:
                    # 过滤掉极短的可能不是整句的引用
                    valid_quotes = [q for q in quotes if len(q) > 2]
                    for q in valid_quotes:
                        # 尝试提取前文摘要作为 context (最多50字)
                        context = sentence[:50] + "..." if len(sentence) > 50 else sentence
                        quotes_list.append({
                            "text": q,
                            "type": "direct",
                            "context": context
                        })
                        
    if not quotes_list:
        return {
            "message": "没有发现人物言论信息",
            "status": "empty"
        }
        
    return {
        "message": "发现人物言论信息",
        "status": "success",
        "data": {
            "people": [
                {
                    "name": "习近平",
                    "position": "中共中央总书记、国家主席、中央军委主席",
                    "quotes": quotes_list
                }
            ],
            "summary": {
                "total_people": 1,
                "total_quotes": len(quotes_list)
            }
        }
    }

# ==========================================================
# 辅助函数：保存规则提取结果到指定格式的 JSON 文件
# ==========================================================
def save_rule_results_to_json(rule_results, out_file_json, model="reg", role="assistant"):
    """
    将提取的 rule_results 按指定的 JSON 结构包装并写入文件。
    模拟了类似 LLM API 返回的数据结构。
    """
    if isinstance(rule_results, str):
        try:
            rule_results = json.loads(rule_results)
        except json.JSONDecodeError:
            pass

    if isinstance(rule_results, (dict, list)):
        json_str = json.dumps(rule_results, ensure_ascii=False, indent=4)
    else:
        json_str = str(rule_results)
        
    # 添加 markdown json 代码块包装
    content_str = f"```json\n{json_str}\n```"
    
    current_time = datetime.now().isoformat() + "Z"
    
    wrapper_data = {
        "model": model,
        "created_at": current_time,
        "message": {
            "role": role,
            "content": content_str
        },
        "done": True,
        "done_reason": "stop",
        "total_duration": 0,
        "load_duration": 0,
        "prompt_eval_count": 0,
        "prompt_eval_duration": 0,
        "eval_count": 0,
        "eval_duration": 0
    }
    
    # 确保目录存在
    os.makedirs(os.path.dirname(os.path.abspath(out_file_json)), exist_ok=True)
    
    with open(out_file_json, 'w', encoding='utf-8') as f:
        json.dump(wrapper_data, f, ensure_ascii=False, indent=4)
        
    print(f"提取结果已成功包装并保存至: {out_file_json}")


'''
2026.04.13 重写了提取的提示词语
'''
def Check_Text_LingDaoRen_LLM_V2(records, created_folder, str_prompt, str_llm_mode_name):
    """
    调用ollama 的接口，检查 records 中的每一条记录，返回检查结果
    """

    str_prompt = '''
    # 角色定位
    你是一个专业的文本分析和信息抽取专家，擅长从复杂的中文文献中精准提取特定人物的言论。

    # 任务目标
    请阅读下方提供的【文本内容】，提取出其中所有由“习近平”直接讲过的语句，并以严格的 JSON 格式返回。

    # 提取规则
    1. 目标人物：仅提取“习近平”本人的讲话或论述内容。
    2. 内容范围：通常紧跟在“指出”、“强调”、“明确”等引导词之后，且被双引号“ ”包裹的内容。
    3. 数据清洗：提取时，请去掉内容结尾处可能附带的引用序号（如 ①, ②, ③ 等），仅保留讲话的纯文本内容。
    4. 间接引用：如果是作者的间接叙述而非习近平本人的原话引用，请不要提取。
    5. 完整性：如果一句话中有多个由逗号分隔的独立引号引用（如：“句话A”，“句话B”），请将它们作为独立的元素提取或合并为一个连贯的句子。

    # 输出格式规范（严格遵守以下 JSON 格式，不要输出其他多余的解释文字）
    
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

    2. 当内容中不包含领导人言论时：
    ```json
    {
      "message": "没有发现人物言论信息",
      "status": "empty"
    }
    ```
    '''

    # 将 "."、":" 和 "-" 替换为 "_"
    if str_llm_mode_name!="qwen2.5:7b":
        mode_name = "_"+str_llm_mode_name.replace(".", "_").replace(":", "_").replace("-", "_")
    else:
        mode_name = ""

    output_file_json = os.path.join(created_folder, '2_Check_LingDaoRen', f"{records.get('id')}{mode_name}.json")
    
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


def Check_Text_LingDaoRen_LLM_V3(records, created_folder, str_prompt, str_llm_mode_name):    

    # 将 "."、":" 和 "-" 替换为 "_"
    if str_llm_mode_name!="qwen2.5:7b":
        mode_name = "_"+str_llm_mode_name.replace(".", "_").replace(":", "_").replace("-", "_")
    else:
        mode_name = ""

    output_file_json = os.path.join(created_folder, '2_Check_LingDaoRen', f"{records.get('id')}{mode_name}.json")
    
    if os.path.exists(output_file_json):
        print(f"文件 {output_file_json} 已存在，跳过检查。")
        return
    
    print(f"id: {records.get('id')}")
    ollama_url = next(pub_ollama_url_cycle)
    ollama_url=ollama_url.replace("/api/chat", "") # 去掉 /api/chat 2026.04.14
    
    max_attempts = 3
    attempt = 0
    while attempt < max_attempts:
        extracted_data = extract_xjp_quotes(
            records.get('content'),
            use_llm=True,
            model=mode_name,
            base_url= ollama_url,
            api_provider="",
            api_key=""
        )
        # 2. 结果写入文件
        print(f"\n【将方案1的结果包装并写入文件】")
        save_rule_results_to_json(extracted_data, output_file_json, model=str_llm_mode_name)
        
        
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

#2026.04.14 Extract_Quotes Begin
CUE_VERBS = [
    "指出", "强调", "明确", "表示", "提出", "认为", "说", "称", "谈到", "写道",
    "要求", "号召", "重申", "阐明", "部署", "提出要求", "作出指示", "作出重要指示",
    "作出重要论述", "作出重要讲话", "发表重要讲话", "在.*?讲话", "在.*?强调"
]

SPEAKER_PAT = r"(习近平(?:总书记|主席|同志)?)"

QUOTE_MARKS = [
    ("“", "”"),
    ("\"", "\""),
    ("「", "」"),
    ("『", "』"),
]


def _strip_trailing_refs(s: str) -> str:
    s = s.strip()
    s = re.sub(r"[\u2460-\u2473①②③④⑤⑥⑦⑧⑨⑩]+$", "", s).strip()
    s = re.sub(r"(\[\d+\]|（\d+）|\(\d+\))+$", "", s).strip()
    s = re.sub(r"[，,;；:：]+$", "", s).strip()
    return s


def _window(text: str, start: int, end: int, w: int = 80) -> str:
    a = max(0, start - w)
    b = min(len(text), end + w)
    return text[a:b]


@dataclass
class Candidate:
    id: str
    text: str
    start: int
    end: int
    cue: str
    speaker: str
    context: str
    source: str


def _find_quoted_spans(text: str) -> List[Tuple[int, int]]:
    spans = []
    for lq, rq in QUOTE_MARKS:
        pattern = re.escape(lq) + r"([^" + re.escape(rq) + r"]{2,2000})" + re.escape(rq)
        for m in re.finditer(pattern, text):
            spans.append((m.start(1), m.end(1)))
    spans.sort()
    return spans


def extract_candidates(text: str) -> List[Candidate]:
    candidates: List[Candidate] = []
    quoted_spans = _find_quoted_spans(text)
    cue_pat = "|".join(map(re.escape, sorted(CUE_VERBS, key=len, reverse=True)))

    # 1. 带引号的明确引语
    for i, (qs, qe) in enumerate(quoted_spans):
        left_ctx = text[max(0, qs - 120):qs]
        # Find all matches and take the last one to ensure we get the closest speaker/cue
        speakers = list(re.finditer(SPEAKER_PAT, left_ctx))
        cues = list(re.finditer(r"(" + cue_pat + r")", left_ctx))
        
        if not (speakers and cues):
            continue
            
        m_speaker = speakers[-1]
        m_cue = cues[-1]

        quote_text = _strip_trailing_refs(text[qs:qe])
        if not quote_text:
            continue

        start = qs
        end = qs + len(quote_text)
        candidates.append(Candidate(
            id=f"Q{i}",
            text=quote_text,
            start=start,
            end=end,
            cue=m_cue.group(1),
            speaker=m_speaker.group(1),
            context=_window(text, start, end, 80),
            source="quoted"
        ))

    # 2. 冒号后面的大段引语（无引号）
    pat_colon = re.compile(
        SPEAKER_PAT
        + r".{0,40}?"
        + r"(" + cue_pat + r")"
        + r".{0,20}?[：:]"
        + r"([^。！？；\n]{6,500})"
    )

    idx = 0
    for m in pat_colon.finditer(text):
        speaker = m.group(1)
        cue = m.group(2)
        seg = _strip_trailing_refs(m.group(3))
        if not seg:
            continue
        s = m.start(3)
        e = s + len(seg)
        candidates.append(Candidate(
            id=f"C{idx}",
            text=seg,
            start=s,
            end=e,
            cue=cue,
            speaker=speaker,
            context=_window(text, s, e, 80),
            source="colon"
        ))
        idx += 1

    # 3. 逗号后或直接连着的无引号引语（明显原话）
    pat_noquote = re.compile(
        SPEAKER_PAT
        + r".{0,40}?"
        + r"(" + cue_pat + r")"
        + r"[，, ]*"
        + r"([^。！？；\n]{6,260})"
    )

    jdx = 0
    for m in pat_noquote.finditer(text):
        speaker = m.group(1)
        cue = m.group(2)
        seg = _strip_trailing_refs(m.group(3))
        if not seg:
            continue
        s = m.start(3)
        e = s + len(seg)
        candidates.append(Candidate(
            id=f"N{jdx}",
            text=seg,
            start=s,
            end=e,
            cue=cue,
            speaker=speaker,
            context=_window(text, s, e, 80),
            source="noquote"
        ))
        jdx += 1

    # 去重
    uniq: Dict[Tuple[int, int, str], Candidate] = {}
    for c in candidates:
        key = (c.start, c.end, c.text)
        uniq[key] = c
    merged = list(uniq.values())
    merged.sort(key=lambda x: (x.start, x.end))
    return merged


def _extract_json_object(s: str) -> Dict[str, Any]:
    i = s.find("{")
    j = s.rfind("}")
    if i == -1 or j == -1 or j <= i:
        raise ValueError("no_json_object")
    return json.loads(s[i:j + 1])


def _ollama_chat(url: str, model: str, messages: List[Dict[str, str]], temperature: float = 0.0) -> str:
    payload = {
        "model": model,
        "stream": False,
        "messages": messages,
        "options": {"temperature": temperature}
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url.rstrip("/") + "/api/chat", data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        raw = resp.read().decode("utf-8")
    obj = json.loads(raw)
    return (obj.get("message") or {}).get("content") or ""


def _bailian_chat(api_key: str, model: str, messages: List[Dict[str, str]], temperature: float = 0.0) -> str:
    url = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=120) as resp:
        raw = resp.read().decode("utf-8")
    obj = json.loads(raw)
    return obj["choices"][0]["message"]["content"]


def filter_with_llm(
    text: str,
    candidates: List[Candidate],
    model: str = "qwen2.5:32b",
    base_url: str = "http://localhost:11434",
    api_provider: str = "ollama",
    api_key: Optional[str] = None
) -> List[Dict[str, Any]]:
    cand_json = [
        {
            "id": c.id,
            "quote_text": c.text,
            "cue": c.cue,
            "speaker": c.speaker,
            "context": c.context,
            "source": c.source
        }
        for c in candidates
    ]

    system = (
        "你是中文文本证据驱动的信息抽取器。你只能基于输入原文与候选上下文判断。"
        "输出必须是严格JSON且只输出JSON。"
    )

    user = (
        "任务：判断候选片段是否为“习近平”的直接讲话原文或明显原话（可无引号），并返回严格JSON。\n"
        "判定标准（必须同时满足才keep=true）：\n"
        "1) 说话人能由原文证据指向“习近平”（含同指：习近平总书记/习近平主席）。\n"
        "2) 片段是其原话/直接引语。注意：紧跟在“强调”、“指出”、“提出”等提示词后面的句子，即使没有引号，也应认定为他的原话（keep=true）。\n"
        "3) 若是别人的话、会议文件条款、记者提问、网民评论、作者的自我论述等，keep=false。\n"
        "4) 清洗：去掉末尾①②③、[1]、（1）等引用标记；保留语义完整。\n\n"
        f"【原文】\n{text}\n\n"
        f"【候选列表(JSON)】\n{json.dumps(cand_json, ensure_ascii=False)}\n\n"
        "输出JSON格式如下（只允许这些字段）：\n"
        "{\n"
        '  "items": [\n'
        "    {\n"
        '      "id": "候选id",\n'
        '      "keep": true,\n'
        '      "type": "direct",\n'
        '      "text": "清洗后的引语",\n'
        '      "evidence": "用于判定的原文证据(<=60字)"\n'
        "    }\n"
        "  ]\n"
        "}\n"
    )

    def call_chat(messages, temp):
        if api_provider == "bailian":
            if not api_key:
                raise ValueError("api_key is required for Bailian API")
            return _bailian_chat(api_key, model, messages, temp)
        else:
            return _ollama_chat(base_url, model, messages, temp)

    content = call_chat([{"role": "system", "content": system}, {"role": "user", "content": user}], 0.0)

    try:
        out = _extract_json_object(content)
    except Exception:
        # Retry once if the output wasn't strict JSON
        fix_user = (
            "你上一次输出不是严格JSON。请只输出严格JSON对象，字段仅允许 items[id,keep,type,text,evidence]。不要输出任何解释。"
        )
        content2 = call_chat([{"role": "system", "content": system}, {"role": "user", "content": user}, {"role": "assistant", "content": content}, {"role": "user", "content": fix_user}], 0.0)
        out = _extract_json_object(content2)

    items = out.get("items") or []
    keep_map = {it.get("id"): it for it in items if isinstance(it, dict) and it.get("id")}
    results = []
    seen_texts = set()
    
    for c in candidates:
        it = keep_map.get(c.id)
        if not it:
            continue
        keep = bool(it.get("keep"))
        if not keep:
            continue
        qtext = _strip_trailing_refs(str(it.get("text") or ""))
        if not qtext:
            continue
            
        # 简单去重：去掉标点后如果已存在，则不再加入
        clean_qtext = re.sub(r'[^\w\s]', '', qtext)
        if clean_qtext in seen_texts:
            continue
        seen_texts.add(clean_qtext)
            
        results.append({
            "id": c.id,
            "text": qtext,
            "type": it.get("type") or "direct",
            "context": c.context
        })
    return results


def _remove_substring_quotes(quotes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    去重逻辑进阶版：如果一个 quote 的 text 是另一个 quote text 的子串，
    则保留较长的那个（通常是包含完整的原话）。
    """
    if not quotes:
        return quotes
        
    # 先按长度从长到短排序，方便判断子串
    quotes_sorted = sorted(quotes, key=lambda x: len(x["text"]), reverse=True)
    kept = []
    
    for q in quotes_sorted:
        q_clean = re.sub(r'[^\w]', '', q["text"])
        # 检查当前较短的句子是否被已经保留的较长句子包含
        is_sub = False
        for k in kept:
            k_clean = re.sub(r'[^\w]', '', k["text"])
            if q_clean in k_clean:
                is_sub = True
                break
        if not is_sub:
            kept.append(q)
            
    # 恢复在原文中出现的前后顺序（或者也可以保留其他顺序）
    # 这里简单保持原列表中元素的相对顺序
    original_order_kept = [q for q in quotes if q in kept]
    return original_order_kept


def extract_xjp_quotes(
    text: str,
    use_llm: bool = True,
    model: str = "qwen2.5:32b",
    base_url: str = "http://192.168.0.19:11435",
    api_provider: str = "ollama",
    api_key: Optional[str] = None
) -> Dict[str, Any]:
    candidates = extract_candidates(text)

    if not use_llm:
        quotes = []
        seen = set()
        for c in candidates:
            clean_text = re.sub(r'[^\w\s]', '', c.text)
            if clean_text not in seen:
                seen.add(clean_text)
                quotes.append({"text": c.text, "type": "direct", "context": c.context})
    else:
        kept = filter_with_llm(
            text, candidates,
            model=model, base_url=base_url,
            api_provider=api_provider, api_key=api_key
        )
        quotes = [{"text": k["text"], "type": k["type"], "context": k["context"]} for k in kept]

    # 去除包含关系的子串
    quotes = _remove_substring_quotes(quotes)

    if quotes:
        return {
            "message": "发现人物言论信息",
            "status": "success",
            "data": {
                "people": [
                    {
                        "name": "习近平",
                        "position": "",
                        "quotes": quotes
                    }
                ],
                "summary": {
                    "total_people": 1,
                    "total_quotes": len(quotes)
                }
            }
        }

    return {"message": "没有发现人物言论信息", "status": "empty"}
            
#2026.04.14 Extract_Quotes End


if __name__ == "__main__":    
    Loop_Check_LingDaoRen()

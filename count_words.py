import json
import os

def count_total_words(json_file_path, output_file_path):
    if not os.path.exists(json_file_path):
        print(f"文件不存在: {json_file_path}")
        return

    total_count = 0
    
    print(f"正在读取文件: {json_file_path}")
    with open(json_file_path, 'r', encoding='utf-8') as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"JSON 解析错误: {e}")
            return

    # 遍历 JSON 数组
    for item in data:
        content = item.get("content", "")
        if content:
            # 替换掉 '#'、空格，同时为了纯字数统计的准确性，也将换行符和制表符去掉
            clean_content = content.replace("#", "").replace(" ", "").replace("\n", "").replace("\r", "").replace("\t", "")
            # 也可以替换全角空格
            clean_content = clean_content.replace("　", "")
            
            total_count += len(clean_content)

    print(f"统计完成，总字数（不含#和空白字符）: {total_count}")
    
    # 将结果写入到输出文件中
    with open(output_file_path, 'w', encoding='utf-8') as f:
        f.write(f"总字数: {total_count}\n")
        
    print(f"统计结果已成功写入文件: {output_file_path}")

if __name__ == "__main__":
    # 指定要读取的 JSON 文件路径
    input_json = r"C:\1_web_book_check_v2\1_Server\fastapi-auth-app\check_book\3e66efbd75d5515ce9ff6939e1f03d5d\1_Json\processed_data_0420.json"
    
    # 设定结果输出文件（放在同一目录下，名为 total_word_count.txt）
    output_dir = os.path.dirname(input_json)
    output_txt = os.path.join(output_dir, "total_word_count.txt")
    
    # 确保输出目录存在
    if not os.path.exists(output_dir):
        print(f"目录不存在，请检查路径: {output_dir}")
    else:
        count_total_words(input_json, output_txt)

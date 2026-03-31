import os
import json
import re

def generate_html_report(json_folder, output_html):
    if not os.path.exists(json_folder):
        print(f"目录不存在: {json_folder}")
        return

    # 获取所有 json 文件并按数字顺序排序
    files = [f for f in os.listdir(json_folder) if f.endswith('.json')]
    
    # 尝试按文件名中的数字进行排序，假设文件名格式如 "1.json", "2.json" 等
    def sort_key(filename):
        # 提取文件名中的所有数字
        numbers = re.findall(r'\d+', filename)
        if numbers:
            return int(numbers[0])
        return 0
        
    files.sort(key=sort_key)
    
    report_data = []
    total_content_count = 0
    total_content_chars = 0

    print(f"共找到 {len(files)} 个 JSON 文件。正在处理...")

    for filename in files:
        filepath = os.path.join(json_folder, filename)
        with open(filepath, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
                
                # 兼容 data 是列表或字典的情况
                items = data if isinstance(data, list) else [data]
                
                for item in items:
                    item_id = item.get("id", "未知ID")
                    errors = item.get("errors", [])
                    
                    if not isinstance(errors, list):
                        continue
                        
                    for error in errors:
                        content = error.get("content", "")
                        right_sentences = error.get("rightSentences", "")
                        
                        # 只有当 content 存在时才记录
                        if content:
                            report_data.append({
                                "id": item_id,
                                "content": content,
                                "right_sentences": right_sentences,
                                "filename": filename
                            })
                            
                            total_content_count += 1
                            # 计算字数时，同样去除空白字符，让字数统计更真实
                            clean_content = content.replace(" ", "").replace("\n", "").replace("\r", "").replace("\t", "").replace("　", "")
                            total_content_chars += len(clean_content)
                            
            except json.JSONDecodeError as e:
                print(f"解析文件 {filename} 时出错: {e}")
                continue

    # 按 ID 排序 (尝试将 ID 转为整数，如果失败则按字符串)
    def sort_by_id(item):
        try:
            return int(item["id"])
        except (ValueError, TypeError):
            return 0
            
    report_data.sort(key=sort_by_id)

    # 生成 HTML
    html_content = f"""
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>文本检查报告</title>
        <style>
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background-color: #f5f7fa;
                color: #333;
                margin: 0;
                padding: 20px 40px;
            }}
            .header {{
                text-align: center;
                margin-bottom: 30px;
                padding-bottom: 20px;
                border-bottom: 2px solid #e1e4e8;
            }}
            h1 {{
                color: #2c3e50;
            }}
            .stats-container {{
                display: flex;
                justify-content: center;
                gap: 40px;
                margin-bottom: 30px;
            }}
            .stat-box {{
                background-color: #fff;
                padding: 15px 30px;
                border-radius: 8px;
                box-shadow: 0 4px 6px rgba(0,0,0,0.05);
                text-align: center;
                border-top: 4px solid #3498db;
            }}
            .stat-value {{
                font-size: 24px;
                font-weight: bold;
                color: #2980b9;
                margin-top: 5px;
            }}
            .card {{
                background-color: #fff;
                border-radius: 8px;
                box-shadow: 0 2px 5px rgba(0,0,0,0.05);
                margin-bottom: 20px;
                overflow: hidden;
                border-left: 5px solid #e74c3c;
            }}
            .card-header {{
                background-color: #f8f9fa;
                padding: 12px 20px;
                font-weight: bold;
                border-bottom: 1px solid #eee;
                display: flex;
                justify-content: space-between;
                color: #555;
            }}
            .id-badge {{
                background-color: #e74c3c;
                color: white;
                padding: 2px 10px;
                border-radius: 12px;
                font-size: 14px;
            }}
            .card-body {{
                padding: 20px;
            }}
            .field-row {{
                margin-bottom: 15px;
            }}
            .field-row:last-child {{
                margin-bottom: 0;
            }}
            .field-label {{
                font-weight: bold;
                color: #7f8c8d;
                margin-bottom: 5px;
                display: block;
                font-size: 14px;
            }}
            .content-box {{
                background-color: #fdf2e9;
                padding: 12px;
                border-radius: 4px;
                border: 1px solid #fadbd8;
                line-height: 1.6;
            }}
            .right-box {{
                background-color: #e8f8f5;
                padding: 12px;
                border-radius: 4px;
                border: 1px solid #d1f2eb;
                line-height: 1.6;
            }}
            .empty-text {{
                color: #95a5a6;
                font-style: italic;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>文本检查结果报告</h1>
        </div>
        
        <div class="stats-container">
            <div class="stat-box">
                <div>总检查项 (Content 数量)</div>
                <div class="stat-value">{total_content_count} 项</div>
            </div>
            <div class="stat-box">
                <div>涉及总字数 (Content 字符数)</div>
                <div class="stat-value">{total_content_chars} 字</div>
            </div>
        </div>
    """

    for item in report_data:
        right_text = item['right_sentences'] if item['right_sentences'] else '<span class="empty-text">无建议修改内容</span>'
        
        html_content += f"""
        <div class="card">
            <div class="card-header">
                <span><span class="id-badge">ID: {item['id']}</span></span>
                <span style="font-size: 12px; color: #999;">来源: {item['filename']}</span>
            </div>
            <div class="card-body">
                <div class="field-row">
                    <span class="field-label">原内容 (Content)</span>
                    <div class="content-box">{item['content']}</div>
                </div>
                <div class="field-row">
                    <span class="field-label">修改建议 (Right Sentences)</span>
                    <div class="right-box">{right_text}</div>
                </div>
            </div>
        </div>
        """

    html_content += """
    </body>
    </html>
    """

    with open(output_html, 'w', encoding='utf-8') as f:
        f.write(html_content)

    print(f"HTML 报告生成成功！路径: {output_html}")
    print(f"统计信息: 发现 {total_content_count} 个检查项，总计 {total_content_chars} 字。")

if __name__ == "__main__":
    json_folder = r"C:\1_web_book_check_v2\1_Server\fastapi-auth-app\check_book\3e66efbd75d5515ce9ff6939e1f03d5d\2_Check_H"
    
    # 将生成的 HTML 放在同一层级的目录下
    output_html = r"C:\1_web_book_check_v2\1_Server\fastapi-auth-app\check_book\3e66efbd75d5515ce9ff6939e1f03d5d\check_report.html"
    
    generate_html_report(json_folder, output_html)

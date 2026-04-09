import os
import json
import fitz  # PyMuPDF

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
                
                # 用一个集合记录已添加行的签名，用于去重
                # 签名格式可以是 (行文本, 约舍后的y坐标)
                seen_lines = set()
                
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
                        
                    # 1. 替换 "\u0007" 等特殊字符为空
                    line_text = line_text.replace('\u0007', '')
                    
                    # 2. 如果整行文本是 “……” + “ ” + “数字” (通常是目录的页码)，在其后添加 \r\n
                    import re
                    # 匹配任意数量的省略号（中英文点号）、空格，以及最后的数字
                    if re.match(r'^[\.。…\s]+\d+$', line_text.strip()):
                        line_text += "\r\n"
                        
                    # 去重逻辑：
                    # 一些 PDF 编辑软件（尤其是加粗或文字阴影效果）会在几乎同样的坐标下写两遍甚至多遍相同的文字
                    # 我们通过判断该行文字与该行的纵坐标（允许大约1~2像素误差，这里除以2然后取整相当于2像素网格）是否已存在
                    y_approx = int(line_bbox[1] / 2)
                    line_signature = (line_text.strip(), y_approx)
                    
                    if line_signature not in seen_lines:
                        seen_lines.add(line_signature)
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


if __name__ == "__main__":
    pdf_path = r"C:\gzb_file_to_github\P2_Pdf_To_Markdown\test_pdf\人民法院思想政治建设读本3.30.pdf"
    output_dir = r"C:\gzb_file_to_github\P2_Pdf_To_Markdown\pdf-2-json-python"
    
    # 检查输入文件是否存在
    if not os.path.exists(pdf_path):
        print(f"找不到测试 PDF 文件: {pdf_path}")
    else:
        extract_pdf_to_json(pdf_path, output_dir)

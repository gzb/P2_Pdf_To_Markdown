import fitz  # PyMuPDF
import json
import os

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
        
        # 使用 "blocks" 模式提取，返回的每个 block 是一个元组:
        # (x0, y0, x1, y1, "text", block_no, block_type)
        blocks = page.get_text("blocks")

        page_data = {
            "page": page_num + 1,
            "width": page.rect.width,
            "height": page.rect.height,
            "blocks": []
        }

        for b in blocks:
            # block_type == 0 代表文本块
            if b[6] == 0:
                text = b[4].strip()
                if text:  # 忽略空文本块
                    page_data["blocks"].append({
                        "bbox": [b[0], b[1], b[2], b[3]],
                        "text": text
                    })

        # 按页码生成 json 文件名 (例如: 1.json)
        json_filename = os.path.join(output_dir, f"{page_num + 1}.json")
        
        with open(json_filename, 'w', encoding='utf-8') as f:
            json.dump(page_data, f, ensure_ascii=False, indent=4)

    doc.close()
    print(f"提取完成！所有 JSON 文件已保存至: {output_dir}")

if __name__ == "__main__":
    pdf_file = r"c:\gzb_file_to_github\P2_Pdf_To_Markdown\test_data\人民法院思想政治建设读本3.7_2026_03_09_13_53_13.pdf"
    out_folder = r"c:\gzb_file_to_github\P2_Pdf_To_Markdown\pdf-2json-pyhton"
    
    extract_pdf_to_json(pdf_file, out_folder)

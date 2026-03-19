import fitz  # PyMuPDF
import json
import os
from PIL import Image, ImageDraw

def extract_pdf_to_json(pdf_path, output_dir, images_dir):
    # 如果输出目录不存在，则创建
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(images_dir, exist_ok=True)

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

        # 渲染页面为图片并保存
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2)) # 使用 2x 缩放提高图片清晰度
        image_filename = os.path.join(images_dir, f"{page_num + 1}.png")
        pix.save(image_filename)

    doc.close()
    print(f"提取完成！所有 JSON 文件已保存至: {output_dir}")
    print(f"图片已保存至: {images_dir}")

def draw_boxes_on_images(json_folder, img_folder, output_img_folder):
    os.makedirs(output_img_folder, exist_ok=True)
    
    # 遍历图片文件夹中的文件
    for img_name in os.listdir(img_folder):
        if not img_name.lower().endswith(('.png', '.jpg', '.jpeg')):
            continue
            
        base_name = os.path.splitext(img_name)[0]
        json_name = f"{base_name}.json"
        
        img_path = os.path.join(img_folder, img_name)
        json_path = os.path.join(json_folder, json_name)
        out_img_path = os.path.join(output_img_folder, img_name)
        
        if not os.path.exists(json_path):
            print(f"警告: 找不到对应的 JSON 文件 {json_path}")
            continue
            
        try:
            # 读取 JSON 数据
            with open(json_path, 'r', encoding='utf-8') as f:
                page_data = json.load(f)
                
            # 打开图片准备绘制
            with Image.open(img_path) as img:
                draw = ImageDraw.Draw(img)
                
                # 计算缩放比例 (因为之前保存图片时使用了 2x 缩放)
                # json 中的坐标是基于 PDF 原始尺寸的
                pdf_width = page_data.get("width", 1)
                img_width = img.width
                scale_factor = img_width / pdf_width
                
                # 绘制每个 block 的矩形框
                for block in page_data.get("blocks", []):
                    bbox = block.get("bbox")
                    if bbox and len(bbox) == 4:
                        # 将 PDF 坐标转换为图片坐标
                        x0, y0, x1, y1 = [coord * scale_factor for coord in bbox]
                        
                        # 绘制红色矩形框，线宽为 2
                        draw.rectangle([x0, y0, x1, y1], outline="red", width=2)
                        
                # 保存带有标记的图片
                img.save(out_img_path)
                print(f"已处理并保存图片: {out_img_path}")
                
        except Exception as e:
            print(f"处理文件 {img_name} 时发生错误: {e}")

if __name__ == "__main__":
    pdf_file = r"c:\gzb_file_to_github\P2_Pdf_To_Markdown\test_data\人民法院思想政治建设读本3.7_2026_03_09_13_53_13.pdf"
    out_folder = r"c:\gzb_file_to_github\P2_Pdf_To_Markdown\test_data\pdf-2-json-pyhton"
    img_folder = r"c:\gzb_file_to_github\P2_Pdf_To_Markdown\test_data\pdf-1-images"
    marked_img_folder = r"c:\gzb_file_to_github\P2_Pdf_To_Markdown\test_data\pdf-1-images-python"
    
    # 第一步：提取 JSON 和生成图片
    # extract_pdf_to_json(pdf_file, out_folder, img_folder)
    
    # 第二步：根据 JSON 在图片上绘制红框
    print("开始在图片上绘制区块红框...")
    draw_boxes_on_images(out_folder, img_folder, marked_img_folder)
    print("绘制完成！")

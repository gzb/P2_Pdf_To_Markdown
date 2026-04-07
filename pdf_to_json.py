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

def draw_boxes_on_images_ds_ocr(json_folder, img_folder, output_img_folder):
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
                
                # 读取 image_dims
                image_dims = page_data.get("image_dims", {})
                # image_dims 可能是字典或列表，做一下兼容
                if isinstance(image_dims, list) and len(image_dims) > 0:
                    image_dims = image_dims[0]
                
                orig_w = image_dims.get("w", img.width)
                
                # 根据提示，boxes 中的坐标是将原图宽度缩放到 1024 后的相对值。
                # 所以要将 boxes 的坐标还原到原图大小，再缩放到当前打开图片的实际大小。
                # 坐标在 1024 宽度下的值 -> 还原为实际图片宽度下的值: coord * (img.width / 1024)
                # (假设打开的 img.width 等于 orig_w，或者我们需要在当前 img 上画，所以基于 img.width)
                scale_factor = img.width / img.width
                
                # 获取 boxes (注意：不同格式可能叫 boxes 或 boxs，根据要求是 boxes)
                boxes = page_data.get("boxes", [])
                
                for bbox_obj in boxes:
                    # json 里的 boxes 是一个对象列表，例如 {"box": [x0, y0, x1, y1], "label": "..."}
                    bbox = bbox_obj.get("box") if isinstance(bbox_obj, dict) else bbox_obj
                    
                    if bbox and len(bbox) == 4:
                        # 将 1024 宽度的坐标转换为图片坐标
                        x0, y0, x1, y1 = [coord * scale_factor for coord in bbox]
                        
                        # 绘制红色矩形框，线宽为 2
                        draw.rectangle([x0, y0, x1, y1], outline="red", width=2)
                        
                # 保存带有标记的图片
                img.save(out_img_path)
                print(f"已处理并保存图片 (DS-OCR): {out_img_path}")
                
        except Exception as e:
            print(f"处理文件 {img_name} 时发生错误: {e}")

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
                                
                    # 从上到下排序 (Y优先)-Gzb修改不排序
                    #matches.sort(key=lambda x: x["ds_bbox"][1])
                    
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

if __name__ == "__main__":
    pdf_file = r"c:\gzb_file_to_github\P2_Pdf_To_Markdown\test_data\人民法院思想政治建设读本3.7_2026_03_09_13_53_13.pdf"
    out_folder = r"c:\gzb_file_to_github\P2_Pdf_To_Markdown\test_data\pdf-2-json-pyhton"
    img_folder = r"c:\gzb_file_to_github\P2_Pdf_To_Markdown\test_data\pdf-1-images"
    marked_img_folder = r"c:\gzb_file_to_github\P2_Pdf_To_Markdown\test_data\pdf-1-images-python"
    
    # 新需求路径
    ds_json_folder = r"c:\gzb_file_to_github\P2_Pdf_To_Markdown\test_data\pdf-2-json"
    ds_marked_img_folder = r"c:\gzb_file_to_github\P2_Pdf_To_Markdown\test_data\pdf-1-images-ds-ocr"
    merged_output_folder = r"c:\gzb_file_to_github\P2_Pdf_To_Markdown\test_data\pdf-2-json-py-to-ds"
    
    # 第一步：提取 JSON 和生成图片
    # extract_pdf_to_json(pdf_file, out_folder, img_folder)
    
    # 第二步：根据 PyMuPDF 的 JSON 在图片上绘制红框
    # print("开始在图片上绘制区块红框...")
    # draw_boxes_on_images(out_folder, img_folder, marked_img_folder)
    # print("绘制完成！")
    
    # 第三步：根据 ds-ocr 的 JSON (1024宽度基准) 在图片上绘制红框
    # print("开始根据 DS-OCR JSON 绘制红框...")
    # draw_boxes_on_images_ds_ocr(ds_json_folder, img_folder, ds_marked_img_folder)
    # print("DS-OCR 绘制完成！")
    
    # 第四步：合并 py_json 文本到 ds_json
    print("开始合并文本到 DS-OCR JSON...")
    merge_py_json_to_ds_json(ds_json_folder, out_folder, merged_output_folder)
    print("合并完成！")

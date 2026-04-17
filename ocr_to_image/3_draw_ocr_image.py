import json
import os
from PIL import Image, ImageDraw, ImageFont

def draw_ocr_result(json_path, output_path):
    # 1. 读取JSON文件
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 2. 获取图片尺寸信息
    image_info = data.get('image_info', [{}])[0]
    width = image_info.get('width', 1000)
    height = image_info.get('height', 1000)
    
    # 3. 创建空白背景图片
    image = Image.new('RGB', (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    
    # 尝试加载中文字体
    font_path = r"C:\Windows\Fonts\simsun.ttc"  # Windows 默认宋体
    if not os.path.exists(font_path):
        font_path = "arial.ttf"  # 备用字体
    
    page_data = data.get('data', [{}])[0]
    
    # 4. 遍历所有 layout 并绘制区域框
    layouts = page_data.get('layout', [])
    for layout in layouts:
        # 绘制主 layout 框 (蓝色虚线/细线)
        main_loc = layout.get('loc', [])
        if len(main_loc) == 4:
            x1, y1, x2, y2 = main_loc
            draw.rectangle([x1, y1, x2, y2], outline=(100, 100, 255), width=2)
            
        sub_layouts = layout.get('sub_layout', [])
        for sub_layout in sub_layouts:
            loc = sub_layout.get('loc', [])
            layout_type = sub_layout.get('type', '')
            if len(loc) == 4:
                # loc 格式为 [x_min, y_min, x_max, y_max]
                x1, y1, x2, y2 = loc
                draw.rectangle([x1, y1, x2, y2], outline=(0, 200, 0), width=2)
                # 绘制类型标签
                try:
                    font_layout = ImageFont.truetype(font_path, 20)
                except IOError:
                    font_layout = ImageFont.load_default()
                draw.text((x1, max(0, y1 - 25)), layout_type, fill=(0, 128, 0), font=font_layout)
    
    # 5. 遍历所有文本行并绘制
    text_lines = page_data.get('text_lines', [])
    for line in text_lines:
        poly = line.get('poly', [])
        text = line.get('text', '')
        
        if len(poly) == 8:
            # poly 格式为 [x1, y1, x2, y2, x3, y3, x4, y4]
            points = [(poly[0], poly[1]), (poly[2], poly[3]), 
                      (poly[4], poly[5]), (poly[6], poly[7])]
            
            # 计算边界框以便确定字体大小
            xs = [p[0] for p in points]
            ys = [p[1] for p in points]
            min_x, max_x = min(xs), max(xs)
            min_y, max_y = min(ys), max(ys)
            
            # 绘制多边形边框 (红色)
            draw.polygon(points, outline=(255, 0, 0), width=1)
            
            # 动态计算字体大小（高度）
            font_size = max(int(max_y - min_y), 10)
            try:
                font = ImageFont.truetype(font_path, font_size)
            except IOError:
                font = ImageFont.load_default()
            
            # 绘制文本 (黑色)，直接绘制在多边形的左上角
            draw.text((min_x, min_y), text, fill=(0, 0, 0), font=font)
    
    # 5. 保存生成的图片
    image.save(output_path)
    print(f"生成的图片已保存至: {output_path}")

def draw_ocr_result_v2(json_path, output_path):
    # 1. 读取JSON文件
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 2. 获取图片尺寸信息并放大2倍
    scale = 2
    image_info = data.get('image_info', [{}])[0]
    width = image_info.get('width', 1000) * scale
    height = image_info.get('height', 1000) * scale
    
    # 3. 创建空白背景图片
    image = Image.new('RGB', (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    
    # 尝试加载中文字体
    font_path = r"C:\Windows\Fonts\simsun.ttc"  # Windows 默认宋体
    if not os.path.exists(font_path):
        font_path = "arial.ttf"  # 备用字体
    
    page_data = data.get('data', [{}])[0]
    
    # 4. 遍历所有 layout 并绘制区域框
    layouts = page_data.get('layout', [])
    for layout in layouts:
        # 绘制主 layout 框 (蓝色虚线/细线)
        main_loc = layout.get('loc', [])
        if len(main_loc) == 4:
            x1, y1, x2, y2 = [v * scale for v in main_loc]
            draw.rectangle([x1, y1, x2, y2], outline=(100, 100, 255), width=2)
            
        sub_layouts = layout.get('sub_layout', [])
        for sub_layout in sub_layouts:
            loc = sub_layout.get('loc', [])
            layout_type = sub_layout.get('type', '')
            if len(loc) == 4:
                # loc 格式为 [x_min, y_min, x_max, y_max]
                x1, y1, x2, y2 = [v * scale for v in loc]
                draw.rectangle([x1, y1, x2, y2], outline=(0, 200, 0), width=2)
                # 绘制类型标签
                try:
                    font_layout = ImageFont.truetype(font_path, 20)
                except IOError:
                    font_layout = ImageFont.load_default()
                draw.text((x1, max(0, y1 - 25)), layout_type, fill=(0, 128, 0), font=font_layout)
    
    # 5. 遍历所有文本行并绘制
    text_lines = page_data.get('text_lines', [])
    for line in text_lines:
        poly = line.get('poly', [])
        text = line.get('text', '')
        
        if len(poly) == 8:
            # 原坐标
            orig_points = [(poly[0], poly[1]), (poly[2], poly[3]), 
                           (poly[4], poly[5]), (poly[6], poly[7])]
            # 放大坐标
            scaled_points = [(p[0] * scale, p[1] * scale) for p in orig_points]
            
            # 计算边界框以便确定原字体大小和新的位置
            orig_ys = [p[1] for p in orig_points]
            orig_min_y, orig_max_y = min(orig_ys), max(orig_ys)
            
            scaled_xs = [p[0] for p in scaled_points]
            scaled_ys = [p[1] for p in scaled_points]
            scaled_min_x, scaled_max_x = min(scaled_xs), max(scaled_xs)
            scaled_min_y, scaled_max_y = min(scaled_ys), max(scaled_ys)
            
            # 绘制多边形边框 (红色)
            draw.polygon(scaled_points, outline=(255, 0, 0), width=1)
            
            # 动态计算字体大小（高度），文字大小暂时不变，使用原坐标计算
            font_size = max(int(orig_max_y - orig_min_y), 10)
            try:
                font = ImageFont.truetype(font_path, font_size)
            except IOError:
                font = ImageFont.load_default()
            
            # 绘制文本 (黑色)，直接绘制在多边形的左上角
            draw.text((scaled_min_x, scaled_min_y), text, fill=(0, 0, 0), font=font)
    
    # 6. 保存生成的图片
    image.save(output_path)
    print(f"生成的图片(v2)已保存至: {output_path}")

if __name__ == "__main__":
    json_file = r"C:\gzb_file_to_github\P2_Pdf_To_Markdown\ocr_to_image\1_image_ocr_to_json.json"
    output_file = r"C:\gzb_file_to_github\P2_Pdf_To_Markdown\ocr_to_image\ocr_result_image.jpg"
    output_file_v2 = r"C:\gzb_file_to_github\P2_Pdf_To_Markdown\ocr_to_image\ocr_result_image_v2.jpg"
    
    # 原始 v1 版本
    # draw_ocr_result(json_file, output_file)
    
    # 扩大2倍且文字大小不变的 v2 版本
    draw_ocr_result_v2(json_file, output_file_v2)

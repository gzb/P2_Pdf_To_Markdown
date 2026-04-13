import os
import re

def extract_quotes():
    input_file = r"c:\gzb_file_to_github\P2_Pdf_To_Markdown\lingdaoren\output-py-to-ds-curpage-merged.md"
    output_file = r"c:\gzb_file_to_github\P2_Pdf_To_Markdown\lingdaoren\extracted_quotes.md"

    if not os.path.exists(input_file):
        print(f"Error: Input file does not exist at {input_file}")
        return

    count = 0
    # 正则表达式：匹配闭合双引号后紧跟带圈数字的模式（如：”① 或 ” ② 等，允许中间有空格或标点）
    # [\u2460-\u2473] 匹配 ① 到 ⑳
    pattern = re.compile(r'["”][^\u2460-\u2473]*[\u2460-\u2473]')

    with open(input_file, 'r', encoding='utf-8') as f_in, \
         open(output_file, 'w', encoding='utf-8') as f_out:
        
        for line in f_in:
            # 检查是否包含“习近平”
            if "习近平" in line:
                # 检查是否包含双引号且双引号后有类似“①”的字符
                if pattern.search(line):
                    f_out.write(line)
                    #添加空行
                    f_out.write("\n")
                    count += 1
                    
    print(f"Extraction complete! Found {count} matching lines.")
    print(f"Results saved to: {output_file}")

if __name__ == "__main__":
    extract_quotes()

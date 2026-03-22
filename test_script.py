import fitz
import json

pdf_file = r"c:\gzb_file_to_github\P2_Pdf_To_Markdown\test_data\人民法院思想政治建设读本3.7_2026_03_09_13_53_13.pdf"
doc = fitz.open(pdf_file)

# Let's check all pages for 'a', 'b' and see their font and size
import fitz
import json

pdf_file = r"c:\gzb_file_to_github\P2_Pdf_To_Markdown\test_data\人民法院思想政治建设读本3.7_2026_03_09_13_53_13.pdf"
doc = fitz.open(pdf_file)

CIRCLE_MAP = {
    'a': '①', 'b': '②', 'c': '③', 'd': '④', 'e': '⑤', 
    'f': '⑥', 'g': '⑦', 'h': '⑧', 'i': '⑨', 'j': '⑩',
    'k': '⑪', 'l': '⑫', 'm': '⑬', 'n': '⑭', 'o': '⑮',
    'p': '⑯', 'q': '⑰', 'r': '⑱', 's': '⑲', 't': '⑳'
}

found = 0
for page_num in range(18, 25):  # We saw it on page 19 (index 18)
    page = doc[page_num]
    dict_data = page.get_text("dict")
    for b in dict_data.get("blocks", []):
        if b.get("type") == 0:
            for line in b.get("lines", []):
                for span in line.get("spans", []):
                    text = span.get("text", "")
                    clean_text = text.strip()
                    
                    font_lower = span.get("font", "").lower()
                    font_is_symbol = any(x in font_lower for x in ['symbol', 'wingding', 'dingbat', 'ropesequencenumber'])
                    
                    if clean_text and all(c.isspace() or ('a' <= c.lower() <= 'z') for c in clean_text) and font_is_symbol:
                        new_text = "".join([CIRCLE_MAP.get(c.lower(), c) if 'a' <= c.lower() <= 'z' else c for c in text])
                        print(f"Page {page_num+1}: converted {repr(text)} -> {repr(new_text)}, Font: {span.get('font')}")
doc.close()



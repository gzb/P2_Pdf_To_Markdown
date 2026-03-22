import os
from backend.processor import PDFProcessor

pdf_file = r"c:\gzb_file_to_github\P2_Pdf_To_Markdown\test_data\人民法院思想政治建设读本3.7_2026_03_09_13_53_13.pdf"
processor = PDFProcessor(pdf_file)
print("Processing PDF...")
md, mappings = processor.process()
print("Done. Generated MD length:", len(md))
# check if '①' or '②' is in md
count_1 = md.count('①')
count_2 = md.count('②')
print(f"Count of ①: {count_1}")
print(f"Count of ②: {count_2}")

import fitz  # PyMuPDF
import pdfplumber
import json

class PDFProcessor:
    def __init__(self, pdf_path):
        self.pdf_path = pdf_path
        self.doc = fitz.open(self.pdf_path)

    def process(self):
        markdown_content = ""
        mappings = []
        current_md_line = 0

        # Global font stats for heading detection
        heading_threshold, max_font_size = self._analyze_fonts()

        with pdfplumber.open(self.pdf_path) as plumber_pdf:
            for page_num, page in enumerate(self.doc):
                # 1. Extract tables using pdfplumber
                try:
                    plumber_page = plumber_pdf.pages[page_num]
                    tables = plumber_page.extract_tables()
                    table_bboxes = []
                    
                    # Get table objects with bbox
                    # pdfplumber table extraction returns data, we need find_tables() for bbox
                    found_tables = plumber_page.find_tables()
                    
                    page_blocks = []

                    # Add tables to blocks
                    for i, table in enumerate(found_tables):
                        if i >= len(tables): break # Safety check
                        bbox = table.bbox # (x0, top, x1, bottom)
                        # Convert to PyMuPDF bbox format (x0, y0, x1, y1) - usually same
                        # But pdfplumber y is from top? Yes.
                        
                        # Get markdown content for table
                        table_data = tables[i]
                        if not table_data: continue
                        
                        md_table = self._table_to_markdown(table_data)
                        page_blocks.append({
                            "type": "table",
                            "bbox": bbox,
                            "text": md_table,
                            "content": md_table
                        })
                        table_bboxes.append(bbox)
                except Exception as e:
                    print(f"Error extracting tables on page {page_num}: {e}")
                    # Continue without tables if pdfplumber fails
                    page_blocks = []
                    table_bboxes = []

                # 2. Extract text blocks using PyMuPDF
                # Use "dict" to get font sizes
                try:
                    text_blocks = page.get_text("dict")["blocks"]
                except Exception as e:
                    print(f"Error getting text blocks on page {page_num}: {e}")
                    continue
                
                # If table extraction failed/skipped, initialize page_blocks
                if not 'page_blocks' in locals() or page_blocks is None:
                    page_blocks = []
                if not 'table_bboxes' in locals() or table_bboxes is None:
                    table_bboxes = []
                
                CIRCLE_MAP = {
                    'a': '①', 'b': '②', 'c': '③', 'd': '④', 'e': '⑤', 
                    'f': '⑥', 'g': '⑦', 'h': '⑧', 'i': '⑨', 'j': '⑩',
                    'k': '⑪', 'l': '⑫', 'm': '⑬', 'n': '⑭', 'o': '⑮',
                    'p': '⑯', 'q': '⑰', 'r': '⑱', 's': '⑲', 't': '⑳'
                }
                
                for block in text_blocks:
                    if block["type"] != 0: # 0 is text
                        continue
                        
                    block_bbox = block["bbox"]
                    
                    # Check if overlaps with any table
                    if self._is_overlapping(block_bbox, table_bboxes):
                        continue
                        
                    # Process text block
                    block_text = ""
                    max_span_size = 0
                    
                    # 辅助判断上下文是否有中文
                    block_has_chinese = False
                    if "lines" in block:
                        for line in block["lines"]:
                            for span in line["spans"]:
                                if any('\u4e00' <= c <= '\u9fff' for c in span["text"]):
                                    block_has_chinese = True
                                    break
                            if block_has_chinese: break
                    
                    for line in block["lines"]:
                        line_bbox = line.get("bbox", [0,0,0,0])
                        max_size_in_line = max((s.get("size", 10) for s in line.get("spans", [])), default=10)
                        
                        for i, span in enumerate(line["spans"]):
                            text = span["text"]
                            clean_text = text.strip()
                            
                            # 启发式处理脚注图标
                            if clean_text and all(c.isspace() or ('a' <= c.lower() <= 'z') for c in clean_text):
                                is_superscript = (span.get("flags", 0) & 1) != 0
                                span_bbox = span.get("bbox", [0,0,0,0])
                                is_smaller_and_higher = (span.get("size", 10) < max_size_in_line * 0.95) and (span_bbox[3] < line_bbox[3] - max_size_in_line * 0.1)
                                is_footnote_bottom = (i == 0 and block_has_chinese and line_bbox[1] > page.rect.height * 0.7)
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
                                    
                            block_text += text
                            if span["size"] > max_span_size:
                                max_span_size = span["size"]
                        block_text += " " # Add space between lines in a block
                    
                    block_text = block_text.strip()
                    if not block_text:
                        continue

                    # Heading detection
                    prefix = ""
                    if max_span_size >= heading_threshold:
                        prefix = "# " if max_span_size >= max_font_size * 0.9 else "## "
                    
                    final_text = f"{prefix}{block_text}"
                    
                    page_blocks.append({
                        "type": "text",
                        "bbox": block_bbox,
                        "text": block_text, # Plain text for search/mapping
                        "content": final_text # Markdown content
                    })

                # 3. Smart Sort (Column Detection)
                sorted_blocks = self._sort_blocks(page_blocks, page.rect.width)

                # 4. Generate Output
                for block in sorted_blocks:
                    content = block["content"]
                    markdown_content += content + "\n\n"
                    
                    # Calculate line count (rough approx)
                    lines = content.split('\n')
                    line_count = len(lines)
                    
                    mappings.append({
                        "md_line_index": current_md_line,
                        "page": page_num + 1,
                        "bbox": block["bbox"],
                        "text": block["text"][:100] + "..." if len(block["text"]) > 100 else block["text"]
                    })
                    
                    current_md_line += line_count + 1 # +1 for newline

        return markdown_content, mappings

    def save_results(self, output_md_path, output_json_path):
        md_content, mappings = self.process()
        
        with open(output_md_path, "w", encoding="utf-8") as f:
            f.write(md_content)
            
        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump(mappings, f, ensure_ascii=False, indent=2)

        return md_content, mappings

    def _analyze_fonts(self):
        font_sizes = []
        # Sample first 5 pages
        for page in self.doc[:5]:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" in block:
                    for line in block["lines"]:
                        for span in line["spans"]:
                            font_sizes.append(span["size"])
        
        if font_sizes:
            avg = sum(font_sizes) / len(font_sizes)
            return avg * 1.2, max(font_sizes)
        return 12, 12

    def _is_overlapping(self, bbox, table_bboxes):
        # bbox: (x0, y0, x1, y1)
        b_x0, b_y0, b_x1, b_y1 = bbox
        b_area = (b_x1 - b_x0) * (b_y1 - b_y0)
        
        for t_bbox in table_bboxes:
            t_x0, t_y0, t_x1, t_y1 = t_bbox
            
            # Intersection
            x_left = max(b_x0, t_x0)
            y_top = max(b_y0, t_y0)
            x_right = min(b_x1, t_x1)
            y_bottom = min(b_y1, t_y1)
            
            if x_right < x_left or y_bottom < y_top:
                continue

            intersection_area = (x_right - x_left) * (y_bottom - y_top)
            
            # If intersection is significant (>50% of block area), consider it overlapping
            if intersection_area > 0.5 * b_area:
                return True
        return False

    def _table_to_markdown(self, data):
        if not data: return ""
        # Clean None values
        cleaned_data = [[str(cell or "").replace("\n", " ") for cell in row] for row in data]
        
        # Markdown Table
        header = cleaned_data[0]
        rows = cleaned_data[1:]
        
        md = "| " + " | ".join(header) + " |\n"
        md += "| " + " | ".join(["---"] * len(header)) + " |\n"
        
        for row in rows:
            md += "| " + " | ".join(row) + " |\n"
            
        return md

    def _sort_blocks(self, blocks, page_width):
        if not blocks: return []
        
        # 1. Primary Sort: Top to Bottom (Y)
        # Use a tolerance for "same line" detection
        
        # Strategy:
        # Sort by Y-coordinate (top).
        # But for items on roughly the same line (e.g. within 5-10px), sort by X (left).
        # This is the "Reading Order" for standard single-column documents.
        
        # However, user requested: "先从左到右，在从上到下的顺序进行排序"
        # Wait, usually it is Top -> Bottom, Left -> Right.
        # "先从左到右" usually implies columns? Left column top-down, then Right column top-down?
        # Or does user mean literally: Scan X first, then Y? (Like vertical text?)
        # Standard English/Chinese horizontal text is: Top-Down, Left-Right.
        
        # Re-reading user request: "先从左到右，在从上到下的顺序进行排序"
        # If user literally means Sort by X, then Sort by Y...
        # That would mean reading column 1 line 1, column 2 line 1... which breaks column reading flow.
        # BUT, if the PDF is single column, or the user WANTS to ignore column flow and just read strictly geometrically:
        # "Top-Left" usually means: sort by Y, then by X.
        
        # Let's interpret "先从左到右" as primary key X? No, that would be weird for horizontal text.
        # It likely means: "For columns, read left column first".
        # AND "从上到下" means: "Inside column, read top down".
        
        # My previous complex logic tried to detect columns.
        # If the user says "Content is chaotic", maybe the column detection failed.
        # Let's try a simpler, robust approach:
        # Recursive XY Cut is best, but complex.
        # Let's use a Grid/Cluster approach.
        
        # New Simple Approach:
        # 1. Sort all blocks by Y first.
        # 2. Iterate and group blocks that vertically overlap (forming a "Row" or "Band").
        # 3. Sort blocks within each "Band" by X.
        
        # BUT, this merges columns: (Left Col Line 1) + (Right Col Line 1).
        # If the user wants to read Column 1 completely, then Column 2... this is bad.
        
        # Let's go back to the user's EXACT words: "先从左到右，在从上到下的顺序进行排序"
        # If I strictly follow: Primary Key = X, Secondary Key = Y.
        # This results in: Left Column (Top->Bottom), then Right Column (Top->Bottom).
        # This is EXACTLY what is needed for multi-column layout!
        # Because all Left Column blocks have X < PageWidth/2.
        # All Right Column blocks have X > PageWidth/2.
        # So sorting by X first separates the columns!
        
        # However, slight X variations (indentation) might break order.
        # e.g. Indented paragraph in Left Col has larger X than unindented header in Left Col.
        # So we need "Rough X" sorting (Column Binning).
        
        # Algorithm:
        # 1. Assign each block to a "Column Bin" based on its center X.
        #    - Bin 1: Left (0 to Width/2)
        #    - Bin 2: Right (Width/2 to Width)
        #    (Can be more granular if 3 columns, but 2 is standard)
        # 2. Sort Bins by X index.
        # 3. Inside each Bin, sort by Y.
        
        # Let's generalize to N columns using a histogram or gap detection?
        # Or just fixed 2-column split if we detect it?
        
        # Let's try the strict X-then-Y approach but with a tolerance/binning for X.
        # If |x1 - x2| < threshold, consider same X.
        
        # Better:
        # Split page into Vertical Strips (Columns) based on large vertical gaps.
        # Sort strips Left-to-Right.
        # Sort blocks in strips Top-to-Bottom.
        
        # 1. Identify vertical separators (gutters).
        # Project all blocks onto X-axis. 
        # Find gaps in X-projection.
        
        # Step 1: Filter out full-width elements (headers/footers/titles) that span across.
        # We process them separately or treat them as "page breaks".
        
        # Let's implement a robust "Detect Columns -> Sort" strategy.
        
        # 1. Identify "Full Width" blocks vs "Partial Width".
        full_width_threshold = page_width * 0.75
        
        segments = [] # List of {type: 'full'|'cols', blocks: []}
        current_blocks = []
        
        # Sort by Y first to process top-down
        blocks.sort(key=lambda b: b["bbox"][1])
        
        for block in blocks:
            width = block["bbox"][2] - block["bbox"][0]
            if width > full_width_threshold:
                # Flush current column blocks
                if current_blocks:
                    segments.append({'type': 'cols', 'blocks': current_blocks})
                    current_blocks = []
                # Add full width block
                segments.append({'type': 'full', 'blocks': [block]})
            else:
                current_blocks.append(block)
                
        if current_blocks:
            segments.append({'type': 'cols', 'blocks': current_blocks})
            
        final_sorted = []
        
        for seg in segments:
            if seg['type'] == 'full':
                final_sorted.extend(seg['blocks'])
            else:
                # Columnar section.
                # We need to split into columns.
                # Use X-center to assign to columns.
                # How many columns? Auto-detect.
                
                # Simple clustering of X-centers
                col_blocks = seg['blocks']
                if not col_blocks: continue
                
                # Sort by X-center
                col_blocks.sort(key=lambda b: (b["bbox"][0] + b["bbox"][2])/2)
                
                # Group by X-proximity
                columns = []
                if col_blocks:
                    current_col = [col_blocks[0]]
                    last_center = (col_blocks[0]["bbox"][0] + col_blocks[0]["bbox"][2])/2
                    
                    for b in col_blocks[1:]:
                        center = (b["bbox"][0] + b["bbox"][2])/2
                        # If center is far from last center, new column
                        # Threshold: 10% of page width?
                        if abs(center - last_center) > page_width * 0.15:
                             columns.append(current_col)
                             current_col = []
                        current_col.append(b)
                        last_center = center # Update center? Or keep column average?
                        # Better to keep moving average or first center?
                        # Let's just update last_center to track gaps.
                    
                    columns.append(current_col)
                
                # Now sort each column by Y
                for col in columns:
                    col.sort(key=lambda b: b["bbox"][1])
                    final_sorted.extend(col)
                    
        return final_sorted

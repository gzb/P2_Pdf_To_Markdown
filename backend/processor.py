import fitz  # PyMuPDF
import json

class PDFProcessor:
    def __init__(self, pdf_path):
        self.pdf_path = pdf_path
        self.doc = fitz.open(self.pdf_path)

    def process(self):
        markdown_content = ""
        mappings = []
        
        current_md_line = 0

        # Pre-scan for font sizes to determine headings
        font_sizes = []
        for page in self.doc:
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" in block:
                    for line in block["lines"]:
                        for span in line["spans"]:
                            font_sizes.append(span["size"])
        
        if font_sizes:
            avg_font_size = sum(font_sizes) / len(font_sizes)
            max_font_size = max(font_sizes)
            # Simple heuristic: significantly larger than average is a heading
            heading_threshold = avg_font_size * 1.2
        else:
            heading_threshold = 12 # Default fallback

        for page_num, page in enumerate(self.doc):
            blocks = page.get_text("dict")["blocks"]
            # Sort blocks by vertical position (y0), then horizontal (x0)
            blocks.sort(key=lambda b: (b["bbox"][1], b["bbox"][0]))

            for block in blocks:
                if "lines" in block:
                    for line in block["lines"]:
                        # Combine spans in a line
                        line_text = ""
                        line_bbox = line["bbox"]
                        max_span_size = 0
                        
                        for span in line["spans"]:
                            line_text += span["text"]
                            if span["size"] > max_span_size:
                                max_span_size = span["size"]
                        
                        line_text = line_text.strip()
                        if not line_text:
                            continue
                        
                        # Determine if it's a heading
                        prefix = ""
                        if max_span_size >= heading_threshold:
                            prefix = "# " if max_span_size >= max_font_size * 0.9 else "## "
                        
                        md_line = f"{prefix}{line_text}"
                        markdown_content += md_line + "\n\n"
                        
                        mappings.append({
                            "md_line_index": current_md_line,
                            "page": page_num + 1,
                            "bbox": line_bbox,
                            "text": line_text
                        })
                        
                        current_md_line += 2 # newline + blank line
        
        return markdown_content, mappings

    def save_results(self, output_md_path, output_json_path):
        md_content, mappings = self.process()
        
        with open(output_md_path, "w", encoding="utf-8") as f:
            f.write(md_content)
            
        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump(mappings, f, ensure_ascii=False, indent=2)

        return md_content, mappings

import json
import os
import sys

def process_ocr_json(filename):
    # Construct file paths
    base_dir = os.path.dirname(filename)
    basename = os.path.basename(filename)
    
    # Expected filename format: "X_processed_data.json" -> "X_mapping.json"
    if "_processed_data.json" not in basename:
        print("Error: Filename must end with '_processed_data.json'")
        return

    mapping_filename = basename.replace("_processed_data.json", "_mapping.json")
    mapping_path = os.path.join(base_dir, mapping_filename)
    
    output_filename = basename.replace("_processed_data.json", "_processed_data_new.json")
    output_path = os.path.join(base_dir, output_filename)

    print(f"Reading processed data from: {filename}")
    print(f"Reading mapping data from: {mapping_path}")

    try:
        with open(filename, 'r', encoding='utf-8') as f:
            processed_data = json.load(f)
            
        with open(mapping_path, 'r', encoding='utf-8') as f:
            mapping_data = json.load(f)
            
    except FileNotFoundError as e:
        print(f"Error: File not found - {e}")
        return
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON format - {e}")
        return

    # Create a lookup for mapping data: (page, bbox_tuple) -> text
    # mapping.json structure is a list of objects with "page", "bbox", "text"
    # mapping.json uses PDF Original Coordinates (Points)
    page_map = {}
    for entry in mapping_data:
        p = str(entry['page']) 
        if p not in page_map:
            page_map[p] = []
        page_map[p].append(entry)
        
    for item in processed_data:
        new_texts = []
        full_content = ""
        
        if 'pages' not in item or 'boxs' not in item:
            continue
            
        count = len(item['pages'])
        
        # Get page dimensions to calculate scale factor
        # processed_data coords are normalized to width=1024
        # We need to scale them back to PDF coordinates.
        # Assuming all pages in a block share the same dimensions or we use per-page dims.
        # processed_data['image_dims'] has dimensions per page.
        # Structure: "image_dims": [ [ {"w": 1225, "h": 1650} ], ... ]
        
        image_dims = item.get('image_dims', [])
        
        for i in range(count):
            page_list = item['pages'][i]
            box_list = item['boxs'][i]
            dims_list = image_dims[i] if i < len(image_dims) else []
            
            block_text_parts = []
            
            for j in range(len(page_list)):
                page_str = str(page_list[j])
                target_box_norm = box_list[j] # [x0, y0, x1, y1] normalized to 1024 width
                
                # Calculate scale factor for this page
                scale_factor = 1.0
                if j < len(dims_list):
                    orig_w = dims_list[j].get('w')
                    if orig_w:
                        scale_factor = orig_w / 1024.0
                
                # Convert target box back to Original PDF Coordinates
                target_box = [c * scale_factor for c in target_box_norm]
                
                if page_str not in page_map:
                    continue
                    
                matches = []
                # Use slightly expanded target rect to catch edge cases
                target_rect = target_box 
                
                for candidate in page_map[page_str]:
                    # candidate['bbox'] is [x0, y0, x1, y1] in PDF coords
                    if is_contained_or_overlap(candidate['bbox'], target_rect):
                        matches.append(candidate)
                
                # Sort matches: Top-Down, Left-Right
                matches.sort(key=lambda x: (x['bbox'][1], x['bbox'][0]))
                
                segment_text = "".join([m['text'] for m in matches])
                block_text_parts.append(segment_text)
            
            final_block_text = "".join(block_text_parts)
            new_texts.append(final_block_text)
            full_content += final_block_text + "\n"
            
        item['texts'] = new_texts
        item['content'] = full_content.strip()

    # Write output
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(processed_data, f, ensure_ascii=False, indent=4)
    
    print(f"Successfully created: {output_path}")

def is_contained_or_overlap(cand_box, target_box):
    # cand_box inside target_box?
    # cand: [x0, y0, x1, y1]
    # target: [X0, Y0, X1, Y1]
    
    # Relaxed containment: Center of cand is inside target
    cx = (cand_box[0] + cand_box[2]) / 2
    cy = (cand_box[1] + cand_box[3]) / 2
    
    if (target_box[0] <= cx <= target_box[2] and 
        target_box[1] <= cy <= target_box[3]):
        return True
        
    return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python ds_ocr_json_read.py <path_to_processed_data.json>")
    else:
        process_ocr_json(sys.argv[1])

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
import shutil
import os
import uuid
from pathlib import Path
from .processor import PDFProcessor

app = FastAPI()

# Enable CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
STATIC_DIR = BASE_DIR / "static"

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
async def read_root():
    return FileResponse(STATIC_DIR / "index.html")

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    file_id = str(uuid.uuid4())
    file_dir = UPLOAD_DIR / file_id
    os.makedirs(file_dir, exist_ok=True)
    
    pdf_path = file_dir / "original.pdf"
    
    with open(pdf_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    # Process the PDF
    processor = PDFProcessor(str(pdf_path))
    md_path = file_dir / "content.md"
    json_path = file_dir / "mapping.json"
    
    try:
        processor.save_results(str(md_path), str(json_path))
    except Exception as e:
        # Cleanup on failure
        shutil.rmtree(file_dir)
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")

    return {"file_id": file_id, "filename": file.filename}

@app.get("/files/{file_id}/pdf")
async def get_pdf(file_id: str):
    file_path = UPLOAD_DIR / file_id / "original.pdf"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path, media_type="application/pdf")

@app.get("/files/{file_id}/markdown")
async def get_markdown(file_id: str):
    file_path = UPLOAD_DIR / file_id / "content.md"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path, media_type="text/markdown")

@app.get("/files/{file_id}/mapping")
async def get_mapping(file_id: str):
    file_path = UPLOAD_DIR / file_id / "mapping.json"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path, media_type="application/json")

@app.post("/files/{file_id}/extract_text")
async def extract_text(file_id: str, payload: dict):
    pdf_path = UPLOAD_DIR / file_id / "original.pdf"
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
        
    page_num = payload.get("page")
    bbox = payload.get("bbox")
    
    if not page_num or not bbox:
        raise HTTPException(status_code=400, detail="Missing page or bbox")
        
    import fitz
    doc = fitz.open(pdf_path)
    try:
        page = doc[page_num - 1]
        text = page.get_text("text", clip=bbox)
        return {"text": text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        doc.close()

@app.get("/files/{file_id}/search")
async def search_content(file_id: str, q: str):
    pdf_path = UPLOAD_DIR / file_id / "original.pdf"
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
        
    import fitz
    doc = fitz.open(pdf_path)
    results = []
    # q is case-insensitive for search_for by default? No, need to check docs.
    # PyMuPDF search_for is case-insensitive by default? No.
    # We should probably make it case-insensitive if desired, but user didn't specify.
    # Let's assume case-insensitive for better UX.
    
    for page_num, page in enumerate(doc):
        # 1. Get precise bboxes for the search term
        hits = page.search_for(q) 
        
        if not hits:
            continue

        # Get text blocks to find context
        blocks = page.get_text("blocks")
        
        for hit in hits:
            # Find which block contains this hit to get context text
            context_text = ""
            for block in blocks:
                # block: (x0, y0, x1, y1, "text", block_no, block_type)
                if block[6] == 0: # text
                    # Check if hit is roughly inside block vertically
                    if hit.y0 >= block[1] - 5 and hit.y1 <= block[3] + 5:
                        context_text = block[4].strip().replace('\n', ' ')
                        break
            
            if not context_text:
                context_text = q # Fallback

            results.append({
                "page": page_num + 1,
                "bbox": [hit.x0, hit.y0, hit.x1, hit.y1],
                "text": context_text,
                "query": q
            })
            
    doc.close()
    return {"results": results}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

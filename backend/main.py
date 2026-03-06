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

@app.get("/files/{file_id}/search")
async def search_content(file_id: str, q: str):
    json_path = UPLOAD_DIR / file_id / "mapping.json"
    if not json_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
        
    import json
    with open(json_path, "r", encoding="utf-8") as f:
        mappings = json.load(f)
        
    results = []
    query = q.lower()
    
    for idx, item in enumerate(mappings):
        if query in item["text"].lower():
            # Add index for frontend reference
            item["index"] = idx
            results.append(item)
            
    return {"results": results}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

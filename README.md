# PDF to Markdown Converter

A web-based tool to convert PDF files to Markdown with synchronized viewing and search capabilities.

## Features

- **Upload PDF**: Converts PDF to Markdown while preserving layout structure.
- **Synchronized View**: Click on Markdown text to jump to the corresponding location in the PDF.
- **Search**: Search for text within the PDF and jump to the location.
- **PDF Controls**: Zoom in/out, jump to specific pages.

## Setup

1.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```

2.  Run the server:
    ```bash
    uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
    ```

3.  Open your browser at `http://127.0.0.1:8000`.

## Project Structure

- `backend/`: Python backend (FastAPI).
  - `main.py`: API endpoints.
  - `processor.py`: PDF processing logic using PyMuPDF.
  - `static/`: Frontend assets (HTML, JS, CSS).
  - `uploads/`: Storage for uploaded files.

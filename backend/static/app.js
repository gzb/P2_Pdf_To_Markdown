// Initialize PDF.js
pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/2.16.105/pdf.worker.min.js';

let currentPdfDoc = null;
let currentScale = 1.0;
let currentFileId = null;
let mappingData = [];
let currentHighlight = null; // { page: number, bbox: [x0, y0, x1, y1] }

async function uploadFile() {
    const fileInput = document.getElementById('fileInput');
    const file = fileInput.files[0];
    if (!file) {
        alert("Please select a file first.");
        return;
    }

    const formData = new FormData();
    formData.append("file", file);
    
    document.getElementById('uploadBtn').disabled = true;
    document.getElementById('uploadBtn').textContent = "Uploading...";

    try {
        const response = await fetch('/upload', {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            throw new Error(`Upload failed: ${response.statusText}`);
        }

        const data = await response.json();
        currentFileId = data.file_id;
        
        // Load PDF and Mapping
        await loadPDF(currentFileId);
        await loadMapping(currentFileId);
        
    } catch (error) {
        console.error("Error uploading file:", error);
        alert("Error uploading file: " + error.message);
    } finally {
        document.getElementById('uploadBtn').disabled = false;
        document.getElementById('uploadBtn').textContent = "Upload & Convert";
    }
}

async function loadPDF(fileId) {
    const url = `/files/${fileId}/pdf`;
    try {
        const loadingTask = pdfjsLib.getDocument(url);
        currentPdfDoc = await loadingTask.promise;
        document.getElementById('pageInfo').textContent = `Total Pages: ${currentPdfDoc.numPages}`;
        await renderAllPages();
    } catch (error) {
        console.error("Error loading PDF:", error);
    }
}

async function loadMapping(fileId) {
    const url = `/files/${fileId}/mapping`;
    try {
        const response = await fetch(url);
        mappingData = await response.json();
        renderMarkdownFromMapping(mappingData);
    } catch (error) {
        console.error("Error loading mapping:", error);
    }
}

function renderMarkdownFromMapping(mappings) {
    const container = document.getElementById('markdownContent');
    container.innerHTML = '';
    
    mappings.forEach((item, index) => {
        const div = document.createElement('div');
        div.className = 'md-line';
        div.textContent = item.text;
        div.dataset.index = index;
        div.onclick = () => handleLineClick(item, div);
        
        // Simple styling based on content
        if (item.text.startsWith('# ')) {
            div.style.fontSize = '24px';
            div.style.fontWeight = 'bold';
            div.style.marginTop = '20px';
        } else if (item.text.startsWith('## ')) {
            div.style.fontSize = '20px';
            div.style.fontWeight = 'bold';
            div.style.marginTop = '15px';
        } else if (item.text.startsWith('### ')) {
            div.style.fontSize = '16px';
            div.style.fontWeight = 'bold';
            div.style.marginTop = '10px';
        }
        
        container.appendChild(div);
    });
}

function handleLineClick(item, element) {
    // Highlight in Markdown view
    document.querySelectorAll('.md-line').forEach(el => el.classList.remove('active'));
    element.classList.add('active');
    
    // Jump to PDF page
    highlightOnPdf(item);
}

function highlightOnPdf(item) {
    currentHighlight = item;
    
    // In continuous mode, we just scroll to the highlight
    // We need to redraw highlights if we re-render, but since we render all pages,
    // we can just find the page container and draw on it.
    
    const pageContainer = document.getElementById(`page-container-${item.page}`);
    if (pageContainer) {
        // Remove existing highlights from ALL pages
        document.querySelectorAll('.highlight-box').forEach(el => el.remove());
        
        // We need viewport to calculate coordinates. 
        // We can get it from the stored page dimensions or re-fetch.
        // Re-fetching page is safer for correctness.
        currentPdfDoc.getPage(item.page).then(page => {
             const viewport = page.getViewport({ scale: currentScale });
             drawHighlightBox(item.bbox, viewport, pageContainer);
        });
    }
}

async function renderAllPages() {
    if (!currentPdfDoc) return;
    
    const container = document.getElementById('pdfViewer');
    container.innerHTML = ''; 
    
    for (let num = 1; num <= currentPdfDoc.numPages; num++) {
        const pageContainer = document.createElement('div');
        pageContainer.id = `page-container-${num}`;
        pageContainer.className = 'pdf-page-container';
        pageContainer.style.position = 'relative';
        pageContainer.style.marginBottom = '20px';
        pageContainer.style.border = '1px solid #ccc';
        container.appendChild(pageContainer);
        
        // Render each page
        await renderSinglePage(num, pageContainer);
    }
}

async function renderSinglePage(num, container) {
    const page = await currentPdfDoc.getPage(num);
    const viewport = page.getViewport({ scale: currentScale });
    
    const canvas = document.createElement('canvas');
    const context = canvas.getContext('2d');
    
    // High DPI support
    const outputScale = window.devicePixelRatio || 1;
    
    canvas.width = Math.floor(viewport.width * outputScale);
    canvas.height = Math.floor(viewport.height * outputScale);
    canvas.style.width = Math.floor(viewport.width) + "px";
    canvas.style.height = Math.floor(viewport.height) + "px";
    
    const transform = outputScale !== 1 
        ? [outputScale, 0, 0, outputScale, 0, 0] 
        : null;

    container.appendChild(canvas);
    
    const renderContext = {
        canvasContext: context,
        transform: transform,
        viewport: viewport
    };
    
    await page.render(renderContext).promise;
}

function drawHighlightBox(bbox, viewport, container) {
    const [x0, y0, x1, y1] = bbox;
    
    const width = (x1 - x0) * currentScale;
    const height = (y1 - y0) * currentScale;
    const left = x0 * currentScale;
    const top = y0 * currentScale;
    
    const div = document.createElement('div');
    div.className = 'highlight-box';
    div.style.left = `${left}px`;
    div.style.top = `${top}px`;
    div.style.width = `${width}px`;
    div.style.height = `${height}px`;
    div.style.backgroundColor = 'rgba(255, 0, 0, 0.3)'; // Red highlight
    div.style.border = '1px solid rgba(255, 0, 0, 0.5)';
    
    container.appendChild(div);
    
    div.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

function jumpToPage() {
    const page = parseInt(document.getElementById('pageJump').value);
    if (page >= 1 && page <= currentPdfDoc.numPages) {
        const pageContainer = document.getElementById(`page-container-${page}`);
        if (pageContainer) {
            pageContainer.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    }
}

function changeZoom(delta) {
    currentScale += delta;
    if (currentScale < 0.2) currentScale = 0.2;
    renderAllPages().then(() => {
        // Re-apply highlight if exists
        if (currentHighlight) {
            highlightOnPdf(currentHighlight);
        }
    });
}

// Search
async function performSearch() {
    const query = document.getElementById('searchInput').value;
    if (!query || !currentFileId) return;
    
    try {
        const response = await fetch(`/files/${currentFileId}/search?q=${encodeURIComponent(query)}`);
        const data = await response.json();
        
        const container = document.getElementById('markdownContent');
        container.innerHTML = ''; // Clear current content
        
        // Show clear button
        document.getElementById('clearSearchBtn').style.display = 'inline-block';
        
        if (data.results && data.results.length > 0) {
            const heading = document.createElement('h3');
            heading.textContent = `Search Results for "${query}" (${data.results.length} matches)`;
            container.appendChild(heading);
            
            data.results.forEach(result => {
                const div = document.createElement('div');
                div.className = 'search-result-item';
                div.style.padding = '10px';
                div.style.borderBottom = '1px solid #eee';
                div.style.cursor = 'pointer';
                div.style.backgroundColor = '#fff';
                
                const text = document.createElement('div');
                text.textContent = result.text;
                text.style.fontWeight = 'bold';
                
                const info = document.createElement('div');
                info.textContent = `Page ${result.page}`;
                info.style.fontSize = '12px';
                info.style.color = '#666';
                
                div.appendChild(text);
                div.appendChild(info);
                
                div.onclick = () => {
                    // Highlight in result list
                    document.querySelectorAll('.search-result-item').forEach(el => el.style.backgroundColor = '#fff');
                    div.style.backgroundColor = '#e6f7ff';
                    highlightOnPdf(result);
                };
                
                container.appendChild(div);
            });
        } else {
            container.innerHTML = '<p>No results found.</p>';
        }
    } catch (error) {
        console.error("Search error:", error);
    }
}

function clearSearch() {
    document.getElementById('searchInput').value = '';
    document.getElementById('clearSearchBtn').style.display = 'none';
    renderMarkdownFromMapping(mappingData);
}

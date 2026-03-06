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
    // bbox is [x0, y0, x1, y1] from PyMuPDF (top-left origin)
    // viewport.convertToViewportRectangle expects [x0, y0, x1, y1] but PDF coordinates (bottom-left origin)
    
    // PyMuPDF gives coordinates where y increases downwards (0,0 is top-left).
    // PDF.js default viewport expects coordinates where y increases upwards (0,0 is bottom-left).
    // HOWEVER, PyMuPDF can export in PDF coordinates too, but usually it's screen coordinates.
    // If PyMuPDF bbox is (x0, top, x1, bottom), we might need to flip Y.
    
    // But wait, if we use viewport.convertToViewportPoint for (x, y), it expects PDF point.
    // Let's look at how PyMuPDF extracts. get_text("blocks") returns (x0, y0, x1, y1, ...)
    // These are usually unscaled PDF coordinates, but Origin is Top-Left for PyMuPDF by default?
    // Actually PyMuPDF uses Top-Left origin for everything usually.
    // PDF uses Bottom-Left.
    
    // So y_pdf = page_height - y_pymupdf
    // Let's try to convert PyMuPDF y to PDF y.
    
    // We need page height. Viewport has it. viewport.rawDims.pageHeight?
    // Or just viewport.viewBox?
    
    // Actually, let's try a simpler approach. 
    // If PyMuPDF coordinates are (x, y) from top-left, and we render with PDF.js
    // PDF.js renders to a canvas. The canvas is just pixels.
    // We can just map PyMuPDF coordinates directly to Canvas pixels if we know the scale.
    // PyMuPDF coordinates are in "points" (1/72 inch).
    // PDF.js viewport.scale is pixels per point.
    
    // So: pixel_x = coord_x * scale
    //     pixel_y = coord_y * scale
    // This works IF PyMuPDF's (0,0) matches PDF.js rendered (0,0).
    // PDF.js renders the PDF page. If the PDF has a CropBox/MediaBox, it might be shifted.
    
    // Let's try simple scaling again, but ensure we use the right width/height logic.
    // And remove viewport.convertToViewportRectangle because that assumes PDF coordinates (bottom-left).
    
    const [x0, y0, x1, y1] = bbox;
    
    const div = document.createElement('div');
    div.className = 'highlight-box';
    div.style.position = 'absolute';
    div.style.zIndex = '10';
    div.style.pointerEvents = 'none';
    
    // Add flag icon
    const flag = document.createElement('div');
    flag.innerHTML = '🚩'; 
    flag.style.position = 'absolute';
    flag.style.top = '-20px';
    flag.style.left = '-5px';
    flag.style.fontSize = '16px';
    flag.style.zIndex = '100';
    div.appendChild(flag);

    // Check if we need to rely on viewport or simple scaling
    // Viewport handles rotation and offsets (crop box).
    // So using viewport.convertToViewportRectangle is better IF we pass the right PDF coordinates.
    // If PyMuPDF gave us Top-Left Y, and PDF.js expects Bottom-Left Y:
    // y_bottom_left = page_height - y_top_left
    
    // Let's try using simple scaling first as it worked partially before but maybe offset was wrong?
    // The previous implementation used simple scaling.
    // Let's stick to simple scaling but make sure we use the current scale of the viewport.
    
    // Note: viewport.scale is the scale factor.
    // But we should use the viewport's transform to be safe against rotation.
    // For now, let's assume no rotation and simple scaling.
    
    const width = (x1 - x0) * currentScale;
    const height = (y1 - y0) * currentScale;
    const left = x0 * currentScale;
    const top = y0 * currentScale;
    
    div.style.left = `${left}px`;
    div.style.top = `${top}px`;
    div.style.width = `${width}px`;
    div.style.height = `${height}px`;
    div.style.backgroundColor = 'rgba(255, 0, 0, 0.3)';
    div.style.border = '1px solid rgba(255, 0, 0, 0.8)';
    
    container.appendChild(div);
    div.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

let isSelectionMode = false;
let startX, startY;
let selectionBox = null;
let currentSelectionPage = null;

function jumpToPage() {
    const page = parseInt(document.getElementById('pageJump').value);
    if (page >= 1 && page <= currentPdfDoc.numPages) {
        const pageContainer = document.getElementById(`page-container-${page}`);
        if (pageContainer) {
            pageContainer.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    }
}

function toggleSelectionMode() {
    isSelectionMode = !isSelectionMode;
    const btn = document.getElementById('selectionModeBtn');
    btn.textContent = isSelectionMode ? 'Disable Selection' : 'Enable Selection';
    btn.style.backgroundColor = isSelectionMode ? '#ff4d4f' : '';
    btn.style.color = isSelectionMode ? 'white' : '';
    
    const viewer = document.getElementById('pdfViewer');
    if (isSelectionMode) {
        viewer.style.cursor = 'crosshair';
        viewer.addEventListener('mousedown', startSelection);
    } else {
        viewer.style.cursor = 'auto';
        viewer.removeEventListener('mousedown', startSelection);
        if (selectionBox) selectionBox.remove();
    }
}

function startSelection(e) {
    if (!isSelectionMode) return;
    
    // Find which page we are clicking on
    const pageContainer = e.target.closest('.pdf-page-container');
    if (!pageContainer) return;
    
    currentSelectionPage = parseInt(pageContainer.id.replace('page-container-', ''));
    
    const rect = pageContainer.getBoundingClientRect();
    startX = e.clientX - rect.left;
    startY = e.clientY - rect.top;
    
    if (selectionBox) selectionBox.remove();
    selectionBox = document.createElement('div');
    selectionBox.className = 'selection-box';
    selectionBox.style.left = startX + 'px';
    selectionBox.style.top = startY + 'px';
    pageContainer.appendChild(selectionBox);
    
    const onMouseMove = (moveEvent) => {
        const curX = moveEvent.clientX - rect.left;
        const curY = moveEvent.clientY - rect.top;
        
        const left = Math.min(startX, curX);
        const top = Math.min(startY, curY);
        const width = Math.abs(startX - curX);
        const height = Math.abs(startY - curY);
        
        selectionBox.style.left = left + 'px';
        selectionBox.style.top = top + 'px';
        selectionBox.style.width = width + 'px';
        selectionBox.style.height = height + 'px';
    };
    
    const onMouseUp = async (upEvent) => {
        document.removeEventListener('mousemove', onMouseMove);
        document.removeEventListener('mouseup', onMouseUp);
        
        // Extract coordinates in PDF points
        const finalRect = selectionBox.getBoundingClientRect();
        const containerRect = pageContainer.getBoundingClientRect();
        
        const x0 = (parseFloat(selectionBox.style.left)) / currentScale;
        const y0 = (parseFloat(selectionBox.style.top)) / currentScale;
        const x1 = (parseFloat(selectionBox.style.left) + parseFloat(selectionBox.style.width)) / currentScale;
        const y1 = (parseFloat(selectionBox.style.top) + parseFloat(selectionBox.style.height)) / currentScale;
        
        // Call backend to extract text
        await extractTextFromArea(currentSelectionPage, [x0, y0, x1, y1]);
    };
    
    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
}

async function extractTextFromArea(page, bbox) {
    if (!currentFileId) return;
    
    try {
        const response = await fetch(`/files/${currentFileId}/extract_text`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ page, bbox })
        });
        
        const data = await response.json();
        showFloatingPanel(data.text);
    } catch (error) {
        console.error("Extraction error:", error);
    }
}

function showFloatingPanel(text) {
    const panel = document.getElementById('floatingPanel');
    const content = document.getElementById('panelContent');
    content.textContent = text || "(No text found in this area)";
    panel.style.display = 'flex';
}

function closePanel() {
    document.getElementById('floatingPanel').style.display = 'none';
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
                // Highlight query in text
                const regex = new RegExp(`(${query})`, 'gi');
                text.innerHTML = result.text.replace(regex, '<span style="color: red; font-weight: bold;">$1</span>');
                // text.textContent = result.text; // Old way
                text.style.fontWeight = 'normal'; // Changed from bold to normal for better readability of context
                
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

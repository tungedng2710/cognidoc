const $ = (selector) => document.querySelector(selector);
const ui = {
  input: $("#file-input"), dropzone: $("#dropzone"), empty: $("#empty-state"),
  previewLoading: $("#preview-loading"), image: $("#image-preview"), pdfPages: $("#pdf-pages"),
  fileMeta: $("#file-meta"), fileName: $("#file-name"), fileSize: $("#file-size"),
  remove: $("#remove-button"), sample: $("#sample-button"), run: $("#run-button"),
  clear: $("#clear-button"), pageTools: $("#page-tools"),
  pageSelectionLabel: $("#page-selection-label"), selectAll: $("#select-all-button"),
  selectNone: $("#select-none-button"), outputEmpty: $("#output-empty"),
  processing: $("#processing"), markdown: $("#markdown-preview"),
  layout: $("#layout-preview"), layoutImage: $("#layout-image"),
  layoutStage: $("#layout-stage"), layoutCanvas: $("#layout-canvas"),
  layoutOverlay: $("#layout-overlay"), layoutLegend: $("#layout-legend"),
  resultToolbar: $("#result-toolbar"), resultPage: $("#result-page"),
  markdownTab: $("#markdown-tab"), layoutTab: $("#layout-tab"), rawTab: $("#raw-tab"),
  raw: $("#raw-markdown"),
  zoomControls: $("#zoom-controls"), zoomOut: $("#zoom-out-button"),
  zoomReset: $("#zoom-reset-button"), zoomIn: $("#zoom-in-button"),
  copy: $("#copy-button"), download: $("#download-button"),
  jsonDownload: $("#json-download-button"),
  resultStats: $("#result-stats"), runStatus: $("#run-status"),
  runLabel: $("#run-label"), serviceStatus: $("#service-status"),
  serviceLabel: $("#service-label"),
  elementEditor: $("#element-editor"), editorTitle: $("#element-editor-title"),
  editorContent: $("#element-content-input"), editorInclude: $("#element-include-input"),
  editorClose: $("#element-editor-close"), editorCancel: $("#element-editor-cancel"),
  editorSave: $("#element-editor-save"),
};

let selectedFile = null;
let previewUrl = null;
let selectedPages = new Set();
let parsedContent = "";
let pageResults = [];
let resultMetadata = null;
let editingElement = null;
let resultEdited = false;
let activeView = "markdown";
let fileVersion = 0;
let layoutZoom = 1;
let layoutBaseWidth = 0;
let layoutBaseHeight = 0;

const layoutColors = ["#19a974", "#e07a42", "#5c7cda", "#b45ac9", "#d4a72c", "#de5472"];
const minLayoutZoom = 0.5;
const maxLayoutZoom = 3;
const layoutZoomStep = 0.25;

function formatBytes(bytes) {
  return bytes < 1048576 ? `${(bytes / 1024).toFixed(1)} KB` : `${(bytes / 1048576).toFixed(1)} MB`;
}

function setStatus(label, kind = "") {
  ui.runLabel.textContent = label;
  ui.runStatus.className = `run-status ${kind}`.trim();
}

function clearPreview() {
  if (previewUrl) URL.revokeObjectURL(previewUrl);
  previewUrl = null;
  ui.image.removeAttribute("src");
  ui.image.hidden = true;
  ui.pdfPages.replaceChildren();
  ui.pdfPages.hidden = true;
  ui.previewLoading.hidden = true;
  ui.pageTools.hidden = true;
  selectedPages.clear();
}

function clearFile() {
  fileVersion += 1;
  clearPreview();
  selectedFile = null;
  ui.input.value = "";
  ui.empty.hidden = false;
  ui.empty.querySelector("strong").textContent = "Drop a document here";
  ui.empty.querySelector("span").textContent = "or click to browse · PNG, JPG, WebP, TIFF, PDF";
  ui.fileMeta.hidden = true;
  ui.run.disabled = true;
}

function clearResult() {
  closeElementEditor();
  parsedContent = "";
  pageResults = [];
  resultMetadata = null;
  resultEdited = false;
  ui.markdown.replaceChildren();
  ui.raw.textContent = "";
  ui.raw.hidden = true;
  ui.markdown.hidden = true;
  ui.layout.hidden = true;
  ui.zoomControls.hidden = true;
  layoutZoom = 1;
  layoutBaseWidth = 0;
  layoutBaseHeight = 0;
  ui.outputEmpty.hidden = false;
  ui.outputEmpty.querySelector("p").textContent = "Your parsed document will appear here.";
  ui.processing.hidden = true;
  ui.resultToolbar.hidden = true;
  ui.copy.disabled = true;
  ui.download.disabled = true;
  ui.jsonDownload.disabled = true;
  ui.resultStats.textContent = "Awaiting document";
}

function updatePageSelection() {
  const total = ui.pdfPages.children.length;
  const count = selectedPages.size;
  ui.pageSelectionLabel.textContent = `${count} of ${total} page${total === 1 ? "" : "s"} selected`;
  ui.pdfPages.querySelectorAll(".page-card").forEach((card) => {
    const selected = selectedPages.has(Number(card.dataset.page));
    card.classList.toggle("selected", selected);
    card.querySelector("input").checked = selected;
  });
  ui.run.disabled = !selectedFile || count === 0 || !ui.previewLoading.hidden;
  if (count === 0) setStatus("Select at least one page", "error");
  else setStatus(`${count} page${count === 1 ? "" : "s"} ready`, "ok");
}

function renderPdfPreviews(pages) {
  const fragment = document.createDocumentFragment();
  pages.forEach((page) => {
    const card = document.createElement("label");
    card.className = "page-card selected";
    card.dataset.page = page.page_number;
    const image = document.createElement("img");
    image.src = page.image_url;
    image.alt = `Page ${page.page_number}`;
    const footer = document.createElement("span");
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = true;
    checkbox.setAttribute("aria-label", `OCR page ${page.page_number}`);
    footer.append(checkbox, document.createTextNode(` Page ${page.page_number}`));
    card.append(image, footer);
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) selectedPages.add(page.page_number);
      else selectedPages.delete(page.page_number);
      updatePageSelection();
    });
    fragment.append(card);
    selectedPages.add(page.page_number);
  });
  ui.pdfPages.replaceChildren(fragment);
  ui.pdfPages.hidden = false;
  ui.pageTools.hidden = false;
  updatePageSelection();
}

async function inspectMultiPageFile(file, version) {
  ui.previewLoading.hidden = false;
  setStatus("Preparing page previews");
  const form = new FormData();
  form.append("file", file);
  try {
    const response = await fetch("/api/preview", { method: "POST", body: form });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Could not preview PDF");
    if (version !== fileVersion) return;
    ui.previewLoading.hidden = true;
    renderPdfPreviews(data.pages);
  } catch (error) {
    if (version !== fileVersion) return;
    ui.previewLoading.hidden = true;
    ui.empty.hidden = false;
    ui.empty.querySelector("strong").textContent = "Could not open this document";
    ui.empty.querySelector("span").textContent = error.message;
    setStatus(error.message, "error");
  }
}

function setFile(file) {
  if (!file) return clearFile();
  if (!(file.type.startsWith("image/") || file.type === "application/pdf")) {
    setStatus("Unsupported file type", "error"); return;
  }
  if (file.size > 30 * 1024 * 1024) {
    setStatus("File exceeds 30 MB", "error"); return;
  }

  fileVersion += 1;
  const version = fileVersion;
  clearPreview();
  clearResult();
  selectedFile = file;
  ui.empty.hidden = true;
  ui.fileName.textContent = file.name;
  const isPdf = file.type === "application/pdf";
  ui.fileSize.textContent = `${formatBytes(file.size)} · ${isPdf ? "PDF" : "IMAGE"}`;
  ui.fileMeta.hidden = false;

  if (isPdf) {
    ui.run.disabled = true;
    inspectMultiPageFile(file, version);
  } else if (file.type === "image/tiff") {
    ui.run.disabled = true;
    inspectMultiPageFile(file, version);
  } else {
    previewUrl = URL.createObjectURL(file);
    ui.image.src = previewUrl;
    ui.image.hidden = false;
    selectedPages.add(1);
    ui.run.disabled = false;
    setStatus("Document ready", "ok");
  }
}

async function loadSample() {
  try {
    const response = await fetch("/sample");
    if (!response.ok) throw new Error("Sample unavailable");
    setFile(new File([await response.blob()], "page-62.png", { type: "image/png" }));
    setStatus("Sample ready", "ok");
  } catch (error) { setStatus(error.message, "error"); }
}

function fallbackMarkdown(source) {
  const pre = document.createElement("pre");
  pre.textContent = source;
  return pre;
}

function renderMarkdown(source) {
  ui.markdown.replaceChildren();
  if (window.marked && window.DOMPurify) {
    const html = window.marked.parse(source, { gfm: true, breaks: false });
    ui.markdown.innerHTML = window.DOMPurify.sanitize(html);
    if (window.renderMathInElement) {
      window.renderMathInElement(ui.markdown, {
        delimiters: [
          { left: "$$", right: "$$", display: true },
          { left: "$", right: "$", display: false },
        ],
        throwOnError: false,
      });
    }
  } else {
    ui.markdown.append(fallbackMarkdown(source));
  }
}

function colorForLabel(label, labels) {
  return layoutColors[labels.indexOf(label) % layoutColors.length];
}

function elementIsIncluded(element) {
  if (typeof element.included_in_markdown === "boolean") return element.included_in_markdown;
  return !["page-header", "page-footer"].includes(element.label.trim().toLowerCase().replace(/[\s_]+/g, "-"));
}

function closeElementEditor() {
  editingElement = null;
  ui.elementEditor.hidden = true;
  ui.layoutOverlay?.querySelectorAll(".detection.selected").forEach((group) => group.classList.remove("selected"));
}

function openElementEditor(page, index) {
  const element = page.elements[index];
  if (!element) return;
  editingElement = { pageNumber: page.page_number, index };
  ui.editorTitle.textContent = `Page ${page.page_number} · ${index + 1} · ${element.label}`;
  ui.editorContent.value = element.content || "";
  ui.editorInclude.checked = elementIsIncluded(element);
  ui.elementEditor.hidden = false;
  ui.layoutOverlay.querySelectorAll(".detection").forEach((group) => {
    group.classList.toggle("selected", Number(group.dataset.elementIndex) === index);
  });
  requestAnimationFrame(() => ui.editorContent.focus());
}

function pageMarkdownFromElements(page) {
  return page.elements
    .filter(elementIsIncluded)
    .map((element) => (element.content || "").trim())
    .filter(Boolean)
    .join("\n\n")
    .replace(/\uFFFD/g, "")
    .trim();
}

function rebuildDocumentContent() {
  pageResults.forEach((page) => { page.markdown = pageMarkdownFromElements(page); });
  parsedContent = pageResults.length === 1
    ? pageResults[0].markdown
    : pageResults.map((page) => `<!-- Page ${page.page_number} -->\n\n${page.markdown}`).join("\n\n");
}

function updateResultStats() {
  if (!resultMetadata) return;
  const edited = resultEdited ? " · EDITED" : "";
  ui.resultStats.textContent = `${resultMetadata.page_count} OF ${resultMetadata.source_page_count} PAGE${resultMetadata.source_page_count === 1 ? "" : "S"} · ${parsedContent.length.toLocaleString()} CHAR · ${resultMetadata.elapsed_seconds.toFixed(2)} SEC${edited}`;
}

function applyLayoutZoom(center = true) {
  if (!layoutBaseWidth || !layoutBaseHeight) return;
  ui.layoutCanvas.style.width = `${layoutBaseWidth * layoutZoom}px`;
  ui.layoutCanvas.style.height = `${layoutBaseHeight * layoutZoom}px`;
  ui.zoomReset.textContent = `${Math.round(layoutZoom * 100)}%`;
  ui.zoomOut.disabled = layoutZoom <= minLayoutZoom;
  ui.zoomIn.disabled = layoutZoom >= maxLayoutZoom;
  if (center) {
    requestAnimationFrame(() => {
      ui.layoutStage.scrollLeft = (ui.layoutStage.scrollWidth - ui.layoutStage.clientWidth) / 2;
      ui.layoutStage.scrollTop = (ui.layoutStage.scrollHeight - ui.layoutStage.clientHeight) / 2;
    });
  }
}

function fitLayoutImage() {
  if (!ui.layoutImage.naturalWidth || !ui.layoutStage.clientWidth || !ui.layoutStage.clientHeight) return;
  const availableWidth = Math.max(1, ui.layoutStage.clientWidth - 32);
  const availableHeight = Math.max(1, ui.layoutStage.clientHeight - 32);
  const imageRatio = ui.layoutImage.naturalWidth / ui.layoutImage.naturalHeight;
  layoutBaseWidth = Math.min(ui.layoutImage.naturalWidth, availableWidth, availableHeight * imageRatio);
  layoutBaseHeight = layoutBaseWidth / imageRatio;
  applyLayoutZoom(false);
}

function setLayoutZoom(value) {
  layoutZoom = Math.max(minLayoutZoom, Math.min(maxLayoutZoom, value));
  applyLayoutZoom();
}

function renderLayout(page) {
  layoutZoom = 1;
  layoutBaseWidth = 0;
  layoutBaseHeight = 0;
  ui.zoomReset.textContent = "100%";
  ui.layoutImage.onload = fitLayoutImage;
  ui.layoutImage.src = page.image_url;
  ui.layoutOverlay.replaceChildren();
  ui.layoutOverlay.setAttribute("viewBox", `0 0 ${page.image_width} ${page.image_height}`);
  ui.layoutLegend.replaceChildren();
  const labels = [...new Set(page.elements.map((element) => element.label))];
  const svgNs = "http://www.w3.org/2000/svg";
  const labelSize = Math.max(18, Math.min(36, page.image_width / 65));
  const labelPadding = Math.max(4, labelSize * 0.3);

  page.elements.forEach((element, index) => {
    const [x1, y1, x2, y2] = element.bbox;
    const color = colorForLabel(element.label, labels);
    const group = document.createElementNS(svgNs, "g");
    group.classList.add("detection");
    group.dataset.elementIndex = index;
    group.setAttribute("tabindex", "0");
    group.setAttribute("role", "button");
    group.setAttribute("aria-label", `Edit ${element.label} element ${index + 1}`);
    if (editingElement?.pageNumber === page.page_number && editingElement.index === index) {
      group.classList.add("selected");
    }
    const rect = document.createElementNS(svgNs, "rect");
    rect.setAttribute("x", x1); rect.setAttribute("y", y1);
    rect.setAttribute("width", x2 - x1); rect.setAttribute("height", y2 - y1);
    rect.setAttribute("stroke", color);
    const tag = document.createElementNS(svgNs, "text");
    tag.setAttribute("x", x1 + labelPadding); tag.setAttribute("y", Math.max(labelSize, y1 - labelPadding));
    tag.style.fontSize = `${labelSize}px`;
    tag.setAttribute("fill", color); tag.textContent = `${index + 1} · ${element.label}`;
    const title = document.createElementNS(svgNs, "title");
    title.textContent = element.content.startsWith("![image](data:") ? element.label : (element.content || element.label);
    group.append(rect, tag, title);
    group.addEventListener("click", () => openElementEditor(page, index));
    group.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        openElementEditor(page, index);
      }
    });
    ui.layoutOverlay.append(group);
  });

  if (page.elements.length) {
    const hint = document.createElement("span");
    hint.className = "layout-hint";
    hint.textContent = "Click a box to edit";
    ui.layoutLegend.append(hint);
  }
  labels.forEach((label) => {
    const item = document.createElement("span");
    const dot = document.createElement("i");
    dot.style.background = colorForLabel(label, labels);
    item.append(dot, document.createTextNode(label));
    ui.layoutLegend.append(item);
  });
  if (!page.elements.length) {
    const item = document.createElement("span");
    item.textContent = "No structured bounding boxes returned";
    ui.layoutLegend.append(item);
  }
}

function showResultPage(pageNumber) {
  closeElementEditor();
  const page = pageResults.find((item) => item.page_number === Number(pageNumber));
  if (!page) return;
  ui.resultPage.value = String(page.page_number);
  renderMarkdown(page.markdown);
  ui.raw.textContent = page.markdown;
  renderLayout(page);
  setActiveView(activeView);
}

function setActiveView(view) {
  if (view !== "layout") closeElementEditor();
  activeView = view;
  const markdownActive = view === "markdown";
  const layoutActive = view === "layout";
  const rawActive = view === "raw";
  ui.markdownTab.classList.toggle("active", markdownActive);
  ui.layoutTab.classList.toggle("active", layoutActive);
  ui.rawTab.classList.toggle("active", rawActive);
  ui.markdownTab.setAttribute("aria-selected", String(markdownActive));
  ui.layoutTab.setAttribute("aria-selected", String(layoutActive));
  ui.rawTab.setAttribute("aria-selected", String(rawActive));
  ui.markdown.hidden = !markdownActive;
  ui.layout.hidden = !layoutActive;
  ui.raw.hidden = !rawActive;
  ui.zoomControls.hidden = !layoutActive;
  if (layoutActive) fitLayoutImage();
}

function populateResults(data) {
  parsedContent = data.content;
  pageResults = data.page_results;
  resultMetadata = {
    filename: data.filename,
    page_count: data.page_count,
    source_page_count: data.source_page_count,
    selected_pages: data.selected_pages,
    elapsed_seconds: data.elapsed_seconds,
  };
  resultEdited = false;
  ui.resultPage.replaceChildren();
  pageResults.forEach((page) => {
    const option = document.createElement("option");
    option.value = page.page_number;
    option.textContent = page.page_number;
    ui.resultPage.append(option);
  });
  ui.resultToolbar.hidden = false;
  ui.copy.disabled = false;
  ui.download.disabled = false;
  ui.jsonDownload.disabled = false;
  showResultPage(pageResults[0].page_number);
}

async function runOcr() {
  if (!selectedFile || !selectedPages.size) return;
  ui.run.disabled = true; ui.clear.disabled = true; ui.outputEmpty.hidden = true;
  ui.markdown.hidden = true; ui.layout.hidden = true; ui.raw.hidden = true; ui.resultToolbar.hidden = true;
  ui.processing.hidden = false; setStatus("Processing document");
  const form = new FormData();
  form.append("file", selectedFile);
  form.append("selected_pages", [...selectedPages].sort((a, b) => a - b).join(","));
  try {
    const response = await fetch("/api/parse", { method: "POST", body: form });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "OCR request failed");
    ui.processing.hidden = true;
    populateResults(data);
    updateResultStats();
    setStatus("OCR complete", "ok");
  } catch (error) {
    ui.processing.hidden = true; ui.outputEmpty.hidden = false;
    ui.outputEmpty.querySelector("p").textContent = error.message;
    setStatus(error.message, "error");
  } finally {
    ui.run.disabled = !selectedFile || selectedPages.size === 0;
    ui.clear.disabled = false;
  }
}

async function checkHealth() {
  try {
    const response = await fetch("/api/health"); const data = await response.json();
    const healthy = response.ok && data.status === "ok";
    ui.serviceStatus.className = `service-status ${healthy ? "ok" : "error"}`;
    ui.serviceLabel.textContent = healthy ? "Service online" : "Service degraded";
  } catch {
    ui.serviceStatus.className = "service-status error"; ui.serviceLabel.textContent = "Service offline";
  }
}

ui.dropzone.addEventListener("click", (event) => {
  if (!selectedFile && !event.target.closest(".page-card")) ui.input.click();
});
ui.dropzone.addEventListener("keydown", (event) => {
  if (!selectedFile && (event.key === "Enter" || event.key === " ")) ui.input.click();
});
ui.input.addEventListener("change", () => setFile(ui.input.files[0]));
["dragenter", "dragover"].forEach((name) => ui.dropzone.addEventListener(name, (event) => {
  event.preventDefault(); ui.dropzone.classList.add("dragging");
}));
["dragleave", "drop"].forEach((name) => ui.dropzone.addEventListener(name, (event) => {
  event.preventDefault(); ui.dropzone.classList.remove("dragging");
}));
ui.dropzone.addEventListener("drop", (event) => setFile(event.dataTransfer.files[0]));
window.addEventListener("paste", (event) => {
  const file = [...event.clipboardData.files].find((item) => item.type.startsWith("image/"));
  if (file) setFile(file);
});
ui.remove.addEventListener("click", () => { clearFile(); clearResult(); setStatus("Select a document"); });
ui.sample.addEventListener("click", loadSample);
ui.run.addEventListener("click", runOcr);
ui.clear.addEventListener("click", () => { clearFile(); clearResult(); setStatus("Select a document"); });
ui.selectAll.addEventListener("click", () => {
  ui.pdfPages.querySelectorAll(".page-card").forEach((card) => selectedPages.add(Number(card.dataset.page)));
  updatePageSelection();
});
ui.selectNone.addEventListener("click", () => { selectedPages.clear(); updatePageSelection(); });
ui.markdownTab.addEventListener("click", () => setActiveView("markdown"));
ui.layoutTab.addEventListener("click", () => setActiveView("layout"));
ui.rawTab.addEventListener("click", () => setActiveView("raw"));
ui.zoomOut.addEventListener("click", () => setLayoutZoom(layoutZoom - layoutZoomStep));
ui.zoomReset.addEventListener("click", () => setLayoutZoom(1));
ui.zoomIn.addEventListener("click", () => setLayoutZoom(layoutZoom + layoutZoomStep));
ui.layoutStage.addEventListener("wheel", (event) => {
  if (!(event.ctrlKey || event.metaKey)) return;
  event.preventDefault();
  setLayoutZoom(layoutZoom + (event.deltaY < 0 ? layoutZoomStep : -layoutZoomStep));
}, { passive: false });
ui.resultPage.addEventListener("change", () => showResultPage(ui.resultPage.value));
ui.editorClose.addEventListener("click", closeElementEditor);
ui.editorCancel.addEventListener("click", closeElementEditor);
ui.editorSave.addEventListener("click", () => {
  if (!editingElement) return;
  const page = pageResults.find((item) => item.page_number === editingElement.pageNumber);
  const element = page?.elements[editingElement.index];
  if (!page || !element) return closeElementEditor();

  const previousZoom = layoutZoom;
  element.content = ui.editorContent.value;
  element.included_in_markdown = ui.editorInclude.checked;
  rebuildDocumentContent();
  resultEdited = true;
  closeElementEditor();
  renderMarkdown(page.markdown);
  ui.raw.textContent = page.markdown;
  renderLayout(page);
  layoutZoom = previousZoom;
  if (ui.layoutImage.complete) fitLayoutImage();
  updateResultStats();
  setStatus("Changes saved", "ok");
});
ui.editorContent.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
    event.preventDefault();
    ui.editorSave.click();
  } else if (event.key === "Escape") {
    event.preventDefault();
    closeElementEditor();
  }
});
ui.copy.addEventListener("click", async () => {
  await navigator.clipboard.writeText(parsedContent); ui.copy.textContent = "Copied";
  setTimeout(() => { ui.copy.textContent = "Copy"; }, 1200);
});
ui.download.addEventListener("click", () => {
  const url = URL.createObjectURL(new Blob([parsedContent], { type: "text/markdown;charset=utf-8" }));
  const link = document.createElement("a"); link.href = url;
  link.download = `${(selectedFile?.name || "document").replace(/\.[^.]+$/, "")}.md`;
  link.click(); URL.revokeObjectURL(url);
});
ui.jsonDownload.addEventListener("click", () => {
  const payload = {
    ...resultMetadata,
    edited: resultEdited,
    content: parsedContent,
    pages: pageResults.map((page) => page.markdown),
    page_results: pageResults.map((page) => ({
      page_number: page.page_number,
      markdown: page.markdown,
      raw: page.raw,
      image_width: page.image_width,
      image_height: page.image_height,
      elements: page.elements.map((element) => ({
        bbox: element.bbox,
        label: element.label,
        content: element.content,
        included_in_markdown: elementIsIncluded(element),
      })),
    })),
  };
  const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: "application/json;charset=utf-8" }));
  const link = document.createElement("a"); link.href = url;
  link.download = `${(selectedFile?.name || "document").replace(/\.[^.]+$/, "")}.json`;
  link.click(); URL.revokeObjectURL(url);
});

window.addEventListener("resize", () => {
  if (activeView === "layout" && pageResults.length) fitLayoutImage();
});

clearResult(); checkHealth();

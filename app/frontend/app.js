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
  layoutOverlay: $("#layout-overlay"), layoutLegend: $("#layout-legend"),
  resultToolbar: $("#result-toolbar"), resultPage: $("#result-page"),
  markdownTab: $("#markdown-tab"), layoutTab: $("#layout-tab"),
  copy: $("#copy-button"), download: $("#download-button"),
  resultStats: $("#result-stats"), runStatus: $("#run-status"),
  runLabel: $("#run-label"), serviceStatus: $("#service-status"),
  serviceLabel: $("#service-label"),
};

let selectedFile = null;
let previewUrl = null;
let selectedPages = new Set();
let parsedContent = "";
let pageResults = [];
let activeView = "markdown";
let fileVersion = 0;

const layoutColors = ["#19a974", "#e07a42", "#5c7cda", "#b45ac9", "#d4a72c", "#de5472"];

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
  parsedContent = "";
  pageResults = [];
  ui.markdown.replaceChildren();
  ui.markdown.hidden = true;
  ui.layout.hidden = true;
  ui.outputEmpty.hidden = false;
  ui.outputEmpty.querySelector("p").textContent = "Your parsed document will appear here.";
  ui.processing.hidden = true;
  ui.resultToolbar.hidden = true;
  ui.copy.disabled = true;
  ui.download.disabled = true;
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
  } else {
    ui.markdown.append(fallbackMarkdown(source));
  }
}

function colorForLabel(label, labels) {
  return layoutColors[labels.indexOf(label) % layoutColors.length];
}

function renderLayout(page) {
  ui.layoutImage.src = page.image_url;
  ui.layoutOverlay.replaceChildren();
  ui.layoutLegend.replaceChildren();
  const labels = [...new Set(page.elements.map((element) => element.label))];
  const svgNs = "http://www.w3.org/2000/svg";

  page.elements.forEach((element, index) => {
    const [x1, y1, x2, y2] = element.bbox;
    const color = colorForLabel(element.label, labels);
    const group = document.createElementNS(svgNs, "g");
    group.classList.add("detection");
    const rect = document.createElementNS(svgNs, "rect");
    rect.setAttribute("x", x1); rect.setAttribute("y", y1);
    rect.setAttribute("width", x2 - x1); rect.setAttribute("height", y2 - y1);
    rect.setAttribute("stroke", color);
    const tag = document.createElementNS(svgNs, "text");
    tag.setAttribute("x", x1 + 4); tag.setAttribute("y", Math.max(13, y1 - 5));
    tag.setAttribute("fill", color); tag.textContent = `${index + 1} · ${element.label}`;
    const title = document.createElementNS(svgNs, "title");
    title.textContent = element.content || element.label;
    group.append(rect, tag, title);
    ui.layoutOverlay.append(group);
  });

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
  const page = pageResults.find((item) => item.page_number === Number(pageNumber));
  if (!page) return;
  ui.resultPage.value = String(page.page_number);
  renderMarkdown(page.markdown);
  renderLayout(page);
  setActiveView(activeView);
}

function setActiveView(view) {
  activeView = view;
  const markdownActive = view === "markdown";
  ui.markdownTab.classList.toggle("active", markdownActive);
  ui.layoutTab.classList.toggle("active", !markdownActive);
  ui.markdownTab.setAttribute("aria-selected", String(markdownActive));
  ui.layoutTab.setAttribute("aria-selected", String(!markdownActive));
  ui.markdown.hidden = !markdownActive;
  ui.layout.hidden = markdownActive;
}

function populateResults(data) {
  parsedContent = data.content;
  pageResults = data.page_results;
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
  showResultPage(pageResults[0].page_number);
}

async function runOcr() {
  if (!selectedFile || !selectedPages.size) return;
  ui.run.disabled = true; ui.clear.disabled = true; ui.outputEmpty.hidden = true;
  ui.markdown.hidden = true; ui.layout.hidden = true; ui.resultToolbar.hidden = true;
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
    ui.resultStats.textContent = `${data.page_count} OF ${data.source_page_count} PAGE${data.source_page_count === 1 ? "" : "S"} · ${parsedContent.length.toLocaleString()} CHAR · ${data.elapsed_seconds.toFixed(2)} SEC`;
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
    ui.serviceLabel.textContent = healthy ? `${data.model} online` : "Service degraded";
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
ui.resultPage.addEventListener("change", () => showResultPage(ui.resultPage.value));
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

clearResult(); checkHealth();

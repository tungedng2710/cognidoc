const $ = (selector) => document.querySelector(selector);
const ui = {
  input: $("#file-input"), dropzone: $("#dropzone"), empty: $("#empty-state"),
  image: $("#image-preview"), pdf: $("#pdf-preview"), fileMeta: $("#file-meta"),
  fileName: $("#file-name"), fileSize: $("#file-size"), remove: $("#remove-button"),
  sample: $("#sample-button"), run: $("#run-button"), clear: $("#clear-button"),
  output: $("#output"), outputEmpty: $("#output-empty"), processing: $("#processing"),
  copy: $("#copy-button"), download: $("#download-button"), resultStats: $("#result-stats"),
  runStatus: $("#run-status"), runLabel: $("#run-label"),
  serviceStatus: $("#service-status"), serviceLabel: $("#service-label"),
};

let selectedFile = null;
let previewUrl = null;
let parsedContent = "";

function formatBytes(bytes) {
  return bytes < 1048576 ? `${(bytes / 1024).toFixed(1)} KB` : `${(bytes / 1048576).toFixed(1)} MB`;
}

function setStatus(label, kind = "") {
  ui.runLabel.textContent = label;
  ui.runStatus.className = `run-status ${kind}`.trim();
}

function setFile(file) {
  if (!file) return clearFile();
  if (!(file.type.startsWith("image/") || file.type === "application/pdf")) {
    setStatus("Unsupported file type", "error"); return;
  }
  if (file.size > 30 * 1024 * 1024) {
    setStatus("File exceeds 30 MB", "error"); return;
  }
  if (previewUrl) URL.revokeObjectURL(previewUrl);
  selectedFile = file;
  previewUrl = URL.createObjectURL(file);
  const isPdf = file.type === "application/pdf";
  ui.image.hidden = isPdf; ui.pdf.hidden = !isPdf; ui.empty.hidden = true;
  if (isPdf) ui.pdf.src = previewUrl; else ui.image.src = previewUrl;
  ui.fileName.textContent = file.name;
  ui.fileSize.textContent = `${formatBytes(file.size)} · ${isPdf ? "PDF" : "IMAGE"}`;
  ui.fileMeta.hidden = false; ui.run.disabled = false; setStatus("Document ready", "ok");
}

function clearFile() {
  if (previewUrl) URL.revokeObjectURL(previewUrl);
  previewUrl = null; selectedFile = null; ui.input.value = "";
  ui.image.removeAttribute("src"); ui.pdf.removeAttribute("src");
  ui.image.hidden = true; ui.pdf.hidden = true; ui.empty.hidden = false;
  ui.fileMeta.hidden = true; ui.run.disabled = true;
}

function clearResult() {
  parsedContent = ""; ui.output.textContent = ""; ui.output.hidden = true;
  ui.outputEmpty.hidden = false;
  ui.outputEmpty.querySelector("p").textContent = "Your parsed document will appear here.";
  ui.processing.hidden = true; ui.copy.disabled = true; ui.download.disabled = true;
  ui.resultStats.textContent = "Awaiting document";
}

async function loadSample() {
  try {
    const response = await fetch("/sample");
    if (!response.ok) throw new Error("Sample unavailable");
    setFile(new File([await response.blob()], "page-62.png", { type: "image/png" }));
    setStatus("Sample ready", "ok");
  } catch (error) { setStatus(error.message, "error"); }
}

async function runOcr() {
  if (!selectedFile) return;
  ui.run.disabled = true; ui.clear.disabled = true; ui.outputEmpty.hidden = true;
  ui.output.hidden = true; ui.processing.hidden = false; setStatus("Processing document");
  const form = new FormData(); form.append("file", selectedFile);
  try {
    const response = await fetch("/api/parse", { method: "POST", body: form });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "OCR request failed");
    parsedContent = data.content; ui.output.textContent = parsedContent;
    ui.output.hidden = false; ui.processing.hidden = true;
    ui.copy.disabled = false; ui.download.disabled = false;
    ui.resultStats.textContent = `${data.page_count} PAGE${data.page_count === 1 ? "" : "S"} · ${parsedContent.length.toLocaleString()} CHAR · ${data.elapsed_seconds.toFixed(2)} SEC`;
    setStatus("OCR complete", "ok");
  } catch (error) {
    ui.processing.hidden = true; ui.outputEmpty.hidden = false;
    ui.outputEmpty.querySelector("p").textContent = error.message;
    setStatus(error.message, "error");
  } finally { ui.run.disabled = !selectedFile; ui.clear.disabled = false; }
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

ui.dropzone.addEventListener("click", () => ui.input.click());
ui.dropzone.addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === " ") ui.input.click();
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
ui.remove.addEventListener("click", (event) => {
  event.stopPropagation(); clearFile(); setStatus("Select a document");
});
ui.sample.addEventListener("click", loadSample);
ui.run.addEventListener("click", runOcr);
ui.clear.addEventListener("click", () => {
  clearFile(); clearResult(); setStatus("Select a document");
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

clearResult(); checkHealth(); loadSample();

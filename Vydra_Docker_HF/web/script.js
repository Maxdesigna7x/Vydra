const root = document.documentElement;
const themeToggle = document.getElementById("theme-toggle");
const langToggle = document.getElementById("lang-toggle");
const resultsArea = document.getElementById("results-area");
const emptyState = document.getElementById("empty-state");
const uploadTrigger = document.getElementById("upload-trigger");
const sequenceFile = document.getElementById("sequence-file");
const downloadResults = document.getElementById("download-results");
const modal = document.getElementById("cluster-modal");
const clusterOpen = document.getElementById("cluster-open");
const clusterBackdrop = modal?.querySelector(".modal-backdrop");
const infoModal = document.getElementById("cluster-info-modal");
const infoBackdrop = infoModal?.querySelector(".info-backdrop");
const clusterInfoTitle = document.getElementById("cluster-info-title");
const clusterInfoContent = document.getElementById("cluster-info-content");
const clusterDetailSequenceId = document.getElementById("cluster-detail-seq-id");
const clusterDetailClass = document.getElementById("cluster-detail-class");
const clusterDetailPath = document.getElementById("cluster-detail-path");
const clusterDetailPill = document.getElementById("cluster-detail-pill");
const clusterDetailCards = document.getElementById("cluster-detail-cards");
const progressPanel = document.getElementById("progress-panel");
const progressLabel = document.getElementById("progress-label");
const progressCount = document.getElementById("progress-count");
const progressBar = document.getElementById("progress-bar");
const resultNav = document.getElementById("result-nav");
const prevResult = document.getElementById("prev-result");
const nextResult = document.getElementById("next-result");
const resultPosition = document.getElementById("result-position");

const partAssets = { sequence: "assets/Parts/Seq_Protein.webp" };
const translations = {
  es: {
    "brand.subtitle": "Hierarchical Protein Annotation",
    "hero.title": "Inferencia jerarquica de <span>proteinas de fagos</span>",
    "hero.subtitle": "Pipeline de IA para anotar secuencias proteicas con una ruta biologica interpretable: origen celular o viral, rama de fago, estado estructural y contexto de cluster.",
    "actions.upload": "Subir Secuencias FASTA",
    "actions.download": "Descargar resultados",
    "pipeline.sequences": "Secuencias",
    "pipeline.mlps": "MLPs jerarquicos",
    "pipeline.classification": "Clasificacion",
    "pipeline.similarity": "Similitud",
    "pipeline.interpretation": "Interpretacion",
    "pipeline.biology": "Biologia",
    "schema.title": "Esquema de clasificacion jerarquica",
    "results.title": "Resultado de inferencia",
    "results.queryId": "ID de consulta",
    "results.estimatedTime": "Tiempo estimado",
    "empty.title": "No hay inferencia ejecutada",
    "empty.description": "Sube un archivo FASTA para ejecutar Vydra. Aqui se mostrara el progreso de ProstT5 y luego los resultados por secuencia.",
    "progress.detectedZero": "0 secuencias detectadas",
    "progress.fasta": "secuencias en el FASTA",
    "progress.readingFasta": "Leyendo FASTA",
    "progress.processingEmbeddings": "Procesando embeddings ProstT5",
    "progress.complete": "Completado",
    "progress.processing": "Procesando...",
    "status.demoComplete": "Prediccion demo completa",
    "status.noInference": "Sin inferencia",
    "status.error": "Error",
    "cards.prediction": "Prediccion principal",
    "cards.confidence": "Confianza",
    "cards.topClasses": "Top clases jerarquicas",
    "cards.clusterInfo": "Contexto biologico",
    "labels.class": "Clase",
    "labels.level": "Nivel",
    "confidence.veryHigh": "Muy alta",
    "confidence.high": "Alta",
    "confidence.medium": "Media",
    "confidence.low": "Baja",
    "cluster.assigned": "Cluster asignado",
    "cluster.size": "Tamano del cluster",
    "cluster.avgSimilarity": "Similitud promedio",
    "cluster.functions": "Funciones asociadas",
    "cluster.organisms": "Organismos representativos",
    "cluster.classContext": "Clase VirDetect-AI",
    "cluster.classSize": "Secuencias de la clase",
    "cluster.reference": "Accesion representativa",
    "cluster.viewDetail": "Ver cluster en detalle",
    "cluster.proteins": "proteinas",
    "cluster.moreCount": "+ 25 mas",
    "nav.previous": "Anterior",
    "nav.next": "Siguiente",
    "node.cellular": "Celular",
    "node.eukaryote": "Eukariota",
    "node.tenClasses": "10 clases",
    "modal.bioContext": "Biological context",
    "modal.sequenceId": "Sequence ID",
    "modal.label": "Label",
    "modal.level": "Level",
    "modal.confidence": "Confidence",
    "modal.clusterSize": "Cluster size",
    "modal.threshold": "Threshold",
    "modal.prototypeSimilarity": "Prototype similarity",
    "modal.nearestPrototype": "Nearest prototype",
    "modal.dominantFamily": "Dominant family",
    "modal.dominantHost": "Dominant host",
    "modal.moleculeType": "Molecule type",
    "modal.genus": "Genus",
    "modal.interpretation": "Interpretacion",
    "modal.interpretationText": "contexto de cluster, no validacion taxonomica directa de la query."
  },
  en: {
    "brand.subtitle": "Hierarchical Protein Annotation",
    "hero.title": "Hierarchical inference for <span>phage proteins</span>",
    "hero.subtitle": "AI pipeline for annotating protein sequences with an interpretable biological route: cellular or viral origin, phage branch, structural state and cluster context.",
    "actions.upload": "Upload FASTA Sequences",
    "actions.download": "Download results",
    "pipeline.sequences": "Sequences",
    "pipeline.mlps": "Hierarchical MLPs",
    "pipeline.classification": "Classification",
    "pipeline.similarity": "Similarity",
    "pipeline.interpretation": "Interpretation",
    "pipeline.biology": "Biology",
    "schema.title": "Hierarchical classification scheme",
    "results.title": "Inference result",
    "results.queryId": "Query ID",
    "results.estimatedTime": "Estimated time",
    "empty.title": "No inference has run",
    "empty.description": "Upload a FASTA file to run Vydra. ProstT5 progress and per-sequence results will appear here.",
    "progress.detectedZero": "0 sequences detected",
    "progress.fasta": "sequences in the FASTA",
    "progress.readingFasta": "Reading FASTA",
    "progress.processingEmbeddings": "Processing ProstT5 embeddings",
    "progress.complete": "Complete",
    "progress.processing": "Processing...",
    "status.demoComplete": "Demo prediction complete",
    "status.noInference": "No inference",
    "status.error": "Error",
    "cards.prediction": "Main prediction",
    "cards.confidence": "Confidence",
    "cards.topClasses": "Top hierarchical classes",
    "cards.clusterInfo": "Biological context",
    "labels.class": "Class",
    "labels.level": "Level",
    "confidence.veryHigh": "Very high",
    "confidence.high": "High",
    "confidence.medium": "Medium",
    "confidence.low": "Low",
    "cluster.assigned": "Assigned cluster",
    "cluster.size": "Cluster size",
    "cluster.avgSimilarity": "Average similarity",
    "cluster.functions": "Associated functions",
    "cluster.organisms": "Representative organisms",
    "cluster.classContext": "VirDetect-AI class",
    "cluster.classSize": "Class sequences",
    "cluster.reference": "Representative accession",
    "cluster.viewDetail": "View cluster details",
    "cluster.proteins": "proteins",
    "cluster.moreCount": "+ 25 more",
    "nav.previous": "Previous",
    "nav.next": "Next",
    "node.cellular": "Cellular",
    "node.eukaryote": "Eukaryote",
    "node.tenClasses": "10 classes",
    "modal.bioContext": "Biological context",
    "modal.sequenceId": "Sequence ID",
    "modal.label": "Label",
    "modal.level": "Level",
    "modal.confidence": "Confidence",
    "modal.clusterSize": "Cluster size",
    "modal.threshold": "Threshold",
    "modal.prototypeSimilarity": "Prototype similarity",
    "modal.nearestPrototype": "Nearest prototype",
    "modal.dominantFamily": "Dominant family",
    "modal.dominantHost": "Dominant host",
    "modal.moleculeType": "Molecule type",
    "modal.genus": "Genus",
    "modal.interpretation": "Interpretation",
    "modal.interpretationText": "cluster context, not direct taxonomic validation of the query."
  }
};

const confidenceLabelKeys = {
  "muy alta": "confidence.veryHigh",
  "very high": "confidence.veryHigh",
  alta: "confidence.high",
  high: "confidence.high",
  media: "confidence.medium",
  medium: "confidence.medium",
  baja: "confidence.low",
  low: "confidence.low"
};

function t(key) {
  return translations[currentLang]?.[key] || translations.es[key] || key;
}

function translatedConfidenceLabel(label) {
  const key = confidenceLabelKeys[String(label || "").trim().toLowerCase()];
  return key ? t(key) : label;
}

function translatedLevel(level) {
  return String(level || "").replace(/^(Nivel|Level)(\s*\d*)$/i, `${t("labels.level")}$2`);
}

function translatedStatus(status) {
  const normalized = String(status || "").trim().toLowerCase();
  if (["prediccion demo completa", "demo prediction complete"].includes(normalized)) return t("status.demoComplete");
  if (["sin inferencia", "no inference"].includes(normalized)) return t("status.noInference");
  if (["complete", "completed", "completado", "prediccion completa", "prediction complete"].includes(normalized)) return t("progress.complete");
  if (["processing", "procesando", "running"].includes(normalized)) return t("progress.processing");
  return status;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatPercent(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "N/A";
  return `${(number * 100).toFixed(1)}%`;
}

function formatNullable(value, fallback = "N/A") {
  const text = String(value ?? "").trim();
  return text ? text : fallback;
}

function clusterBioLabel(annotation) {
  if (annotation?.class_number) {
    const family = annotation.family_label_ncbi_2023 || annotation.family_label_ncbi_2021;
    return family ? `class:${annotation.class_number} - ${family}` : `class:${annotation.class_number}`;
  }
  const level = String(annotation?.best_taxonomic_level || "").trim();
  if (!level) return "unannotated";
  const dominantByLevel = {
    genus: annotation?.dominant_genus,
    family: annotation?.dominant_family,
    host: annotation?.dominant_host,
    virus: annotation?.dominant_virus_name
  };
  const dominant = dominantByLevel[level] || dominantByLevel.family || dominantByLevel.genus || dominantByLevel.host || dominantByLevel.virus;
  return dominant ? `${level}:${dominant}` : level;
}

function metricLine(value, purity, coverage) {
  const parts = [formatNullable(value)];
  if (purity !== undefined && purity !== null && String(purity).trim() !== "") parts.push(`purity ${formatPercent(purity)}`);
  if (coverage !== undefined && coverage !== null && String(coverage).trim() !== "") parts.push(`coverage ${formatPercent(coverage)}`);
  return parts.join(" - ");
}

function compactText(value, maxLength = 76) {
  const text = formatNullable(value);
  if (text.length <= maxLength) return text;
  return `${text.slice(0, maxLength - 1).trim()}...`;
}

function detailCardHtml(item, index) {
  const hasMore = item.forceMore || item.full.length > item.preview.length;
  return `
    <div class="bio-detail-card">
      <span>${escapeHtml(item.label)}</span>
      <b>${escapeHtml(item.preview)}</b>
      ${hasMore ? `<button class="detail-more" type="button" data-detail-index="${index}" aria-label="${escapeHtml(item.label)} detail">+</button>` : ""}
    </div>
  `;
}

function openInfoModal(index) {
  const item = detailInfoItems[index];
  if (!infoModal || !item) return;
  if (clusterInfoTitle) clusterInfoTitle.textContent = item.label;
  if (clusterInfoContent) clusterInfoContent.textContent = item.full;
  infoModal.classList.add("open");
  infoModal.setAttribute("aria-hidden", "false");
}

function closeInfoModal() {
  if (!infoModal) return;
  infoModal.classList.remove("open");
  infoModal.setAttribute("aria-hidden", "true");
}

function renderClusterDetail(result) {
  if (!modal) return;
  const cluster = result?.cluster || {};
  const annotation = cluster.annotation || {};
  const isViralEukClass = cluster.kind === "viral_euk_class";
  const hierarchy = Array.isArray(result?.hierarchy) ? result.hierarchy : [];
  const pathHtml = hierarchy
    .map((item, index) => {
      const chip = `<span>${escapeHtml(item?.label || "")}</span>`;
      return index < hierarchy.length - 1 ? `${chip}<i>&rarr;</i>` : chip;
    })
    .join("");
  const detailClass = formatNullable(result?.prediction?.class_label);
  const clusterId = formatNullable(cluster.id);
  const routeLabel = formatNullable(result?.prediction?.route_label);
  const clusterLabel = formatNullable(clusterBioLabel(annotation));
  const similarity = Number(cluster.avg_similarity);
  const similarityText = isViralEukClass ? "N/A" : Number.isFinite(similarity) ? similarity.toFixed(3) : "N/A";
  const clusterSize = Number(cluster.size);
  const clusterSizeText = Number.isFinite(clusterSize) ? clusterSize.toLocaleString("en-US") : "N/A";

  if (clusterDetailSequenceId) clusterDetailSequenceId.textContent = formatNullable(result?.query_id);
  if (clusterDetailClass) clusterDetailClass.textContent = detailClass;
  if (clusterDetailPath) clusterDetailPath.innerHTML = pathHtml;
  if (clusterDetailPill) clusterDetailPill.textContent = isViralEukClass
    ? `${clusterId} - ${routeLabel} - VirDetect-AI Table S1`
    : `${clusterId} - ${routeLabel} - sim ${similarityText}`;
  detailInfoItems = [
    { label: t("modal.label"), full: clusterLabel },
    { label: t("modal.level"), full: isViralEukClass ? formatNullable(annotation.molecule_type) : formatNullable(annotation.best_taxonomic_level) },
    { label: t("modal.confidence"), full: isViralEukClass ? formatNullable(annotation.protein_function_class) : formatNullable(annotation.confidence) },
    { label: t("modal.clusterSize"), full: clusterSizeText },
    { label: t("modal.threshold"), full: formatNullable(cluster.threshold) },
    { label: t("modal.prototypeSimilarity"), full: similarityText },
    { label: t("modal.nearestPrototype"), full: formatNullable(cluster.nearest_seq_id), forceMore: true },
    {
      label: t("modal.dominantFamily"),
      full: isViralEukClass
        ? formatNullable(annotation.family_label_ncbi_2023 || annotation.family_label_ncbi_2021)
        : metricLine(annotation.dominant_family, annotation.family_purity, annotation.family_coverage)
    },
    {
      label: t("modal.dominantHost"),
      full: isViralEukClass
        ? formatNullable(annotation.host)
        : metricLine(annotation.dominant_host, annotation.host_purity, annotation.host_coverage)
    },
    {
      label: "Representative product",
      full: isViralEukClass
        ? formatNullable(annotation.protein_description)
        : formatNullable(annotation.representative_product || annotation.dominant_product),
      forceMore: true
    },
    {
      label: "Genera / molecule",
      full: isViralEukClass
        ? formatNullable(annotation.genus || annotation.molecule_type)
        : metricLine(annotation.dominant_genus, annotation.genus_purity, annotation.genus_coverage)
    },
    {
      label: "Families / products",
      full: isViralEukClass
        ? formatNullable(annotation.families_in_class_2021)
        : formatNullable(annotation.families_in_cluster || annotation.products_in_cluster),
      forceMore: true
    },
    { label: t("modal.interpretation"), full: t("modal.interpretationText"), forceMore: true }
  ].map((item) => ({ ...item, preview: compactText(item.full) }));
  if (clusterDetailCards) clusterDetailCards.innerHTML = detailInfoItems.map(detailCardHtml).join("");
}

function renderUploadButton(processing = false) {
  if (!uploadTrigger) return;
  if (processing) {
    uploadTrigger.textContent = t("progress.processing");
    return;
  }
  uploadTrigger.innerHTML = `<img src="assets/seq.webp" alt=""><span data-i18n="actions.upload">${t("actions.upload")}</span><span>&rarr;</span>`;
}

function preferredTheme() {
  return "light";
}

function preferredLanguage() {
  return "en";
}

let currentTheme = preferredTheme();
let currentLang = preferredLanguage();
let allResults = [];
let currentResultIndex = 0;
let activeResult = null;
let activeJobId = null;
let pollTimer = null;
let isUploading = false;
let progressState = { processed: 0, total: 0, labelKey: "progress.detectedZero" };
let detailInfoItems = [];

function applyTheme(theme) {
  currentTheme = theme;
  root.setAttribute("data-theme", theme);
  localStorage.setItem("vydra-service-theme", theme);
  localStorage.setItem("vydra-theme", theme);
  if (themeToggle) themeToggle.textContent = theme === "dark" ? "Light" : "Dark";
}

function applyLanguage(lang) {
  currentLang = lang;
  localStorage.setItem("vydra-service-lang", lang);
  document.documentElement.lang = lang;
  document.querySelectorAll("[data-i18n]").forEach((node) => {
    const key = node.getAttribute("data-i18n");
    const text = translations[lang][key];
    if (!text) return;
    if (text.includes("<span>")) node.innerHTML = text;
    else node.textContent = text;
  });
  if (langToggle) langToggle.textContent = lang === "es" ? "EN" : "ES";
  document.title = lang === "es" ? "Vydra | Inferencia jerarquica" : "Vydra | Hierarchical inference";
  if (progressPanel && !progressPanel.hidden) setProgress(progressState.processed, progressState.total, progressState.labelKey);
  if (isUploading) renderUploadButton(true);
  if (allResults.length) renderInferenceResult(allResults[currentResultIndex]);
  else showEmptyState();
}

function showEmptyState() {
  resultsArea?.classList.add("no-results");
  clearRouteHighlight();
  activeResult = null;
  if (modal?.classList.contains("open")) closeModal();
  if (emptyState) emptyState.hidden = false;
  if (resultNav) resultNav.hidden = true;
  if (clusterOpen) clusterOpen.disabled = true;
  document.querySelector(".status-dot").textContent = t("status.noInference");
  if (downloadResults) downloadResults.hidden = true;
}

function routeNodesFromResult(result) {
  const labels = (result.hierarchy || []).map((item) => String(item.label || "").toLowerCase().replace(/_/g, " "));
  const nodes = ["protein-sequence"];
  if (labels.some((label) => label.includes("cellular") || label.includes("celular"))) {
    nodes.push("cellular");
    if (labels.some((label) => label.includes("bacteria"))) nodes.push("bacteria");
    else if (labels.some((label) => label.includes("archaea"))) nodes.push("archaea");
    else if (labels.some((label) => label.includes("euk"))) nodes.push("eukaryote-cellular");
    return nodes;
  }
  if (labels.some((label) => label.includes("viral"))) nodes.push("viral");
  if (labels.some((label) => label.includes("euk")) && !labels.some((label) => label.includes("phage"))) nodes.push("eukaryote-viral");
  if (labels.some((label) => label.includes("phage"))) nodes.push("phage");
  if (labels.some((label) => label.includes("non") || label.includes("no estructural"))) nodes.push("non-structural", "non-structural-clusters");
  else if (labels.some((label) => label.includes("structural") || label.includes("estructural") || label.includes("capsid") || label.includes("tail") || label.includes("portal"))) nodes.push("structural", "structural-10-classes", "structural-clusters");
  return nodes;
}

function highlightRoute(result) {
  const diagram = document.querySelector(".tree-diagram");
  const nodes = routeNodesFromResult(result);
  const nodeSet = new Set(nodes);
  diagram?.classList.add("has-route");
  document.querySelectorAll("[data-node]").forEach((node) => node.classList.toggle("route-active", nodeSet.has(node.getAttribute("data-node"))));
  document.querySelectorAll("[data-edge]").forEach((edge) => {
    const [from, to] = edge.getAttribute("data-edge").split(" ");
    edge.classList.toggle("route-active", nodeSet.has(from) && nodeSet.has(to));
  });
}

function clearRouteHighlight() {
  document.querySelector(".tree-diagram")?.classList.remove("has-route");
  document.querySelectorAll(".route-active").forEach((node) => node.classList.remove("route-active"));
}

function showResultsState() {
  resultsArea?.classList.remove("no-results");
  if (emptyState) emptyState.hidden = true;
  if (clusterOpen) clusterOpen.disabled = !activeResult;
}

function openModal() {
  if (!modal || !activeResult) return;
  renderClusterDetail(activeResult);
  modal.classList.add("open");
  modal.setAttribute("aria-hidden", "false");
  document.body.style.overflow = "hidden";
}

function closeModal() {
  if (!modal) return;
  closeInfoModal();
  modal.classList.remove("open");
  modal.setAttribute("aria-hidden", "true");
  document.body.style.overflow = "";
}

function mixColor(from, to, ratio) {
  const next = from.map((value, index) => Math.round(value + (to[index] - value) * ratio));
  return `rgb(${next[0]}, ${next[1]}, ${next[2]})`;
}

function confidenceColor(percent) {
  const clamped = Math.max(0, Math.min(100, percent));
  const red = [239, 68, 68];
  const yellow = [245, 203, 66];
  const green = [54, 221, 93];
  if (clamped <= 50) return mixColor(red, yellow, clamped / 50);
  return mixColor(yellow, green, (clamped - 50) / 50);
}

function formatScore(value) {
  return Number(value).toFixed(3);
}

function renderConfidenceRings() {
  document.querySelectorAll(".confidence-ring").forEach((ring) => {
    const percent = Number(ring.getAttribute("data-confidence") || 0);
    const clamped = Math.max(0, Math.min(100, percent));
    const circumference = 2 * Math.PI * 46;
    const progress = ring.querySelector(".confidence-progress");
    if (progress) progress.style.strokeDasharray = `${(clamped / 100) * circumference} ${circumference}`;
    ring.style.setProperty("--confidence-color", confidenceColor(percent));
  });
}

function renderInferenceResult(result) {
  activeResult = result;
  document.querySelector(".status-dot").textContent = translatedStatus(result.status);
  document.querySelector(".results-header p").innerHTML = `${t("results.queryId")}: <b>${result.query_id}</b> - ${t("results.estimatedTime")}: <b>${result.elapsed_seconds.toFixed(1)} s</b>`;
  document.querySelector(".prediction-card h3").textContent = result.prediction.route_label;
  const classPill = document.querySelector(".class-pill");
  const classIcon = document.createElement("img");
  const classText = document.createElement("span");
  classIcon.src = result.prediction.class_icon;
  classIcon.alt = "";
  classText.textContent = `${t("labels.class")}: ${result.prediction.class_label}`;
  classPill.replaceChildren(classIcon, classText);
  document.querySelector(".capsid-visual").src = result.prediction.visual_asset || partAssets.sequence;

  const confidencePercent = Math.round(result.confidence.value * 100);
  const confidenceRing = document.querySelector(".confidence-ring");
  confidenceRing.setAttribute("data-confidence", String(confidencePercent));
  confidenceRing.querySelector("strong").textContent = `${confidencePercent}%`;
  confidenceRing.querySelector("span").textContent = translatedConfidenceLabel(result.confidence.label);

  document.querySelector(".classes-card ul").innerHTML = result.hierarchy.map((item) => (
    `<li><span class="dot ${item.color}"></span><b>${translatedLevel(item.level)}</b><em>${item.label}</em><strong>${formatScore(item.score)}</strong></li>`
  )).join("");

  const isViralEukClass = result.cluster?.kind === "viral_euk_class";
  const contextTitle = isViralEukClass ? t("cluster.classContext") : t("cluster.assigned");
  const sizeTitle = isViralEukClass ? t("cluster.classSize") : t("cluster.size");
  document.querySelector(".cluster-cols").innerHTML = `
    <div><span>${contextTitle}</span><strong>${escapeHtml(formatNullable(result.cluster.id))}</strong></div>
    <div><span>${sizeTitle}</span><strong>${Number(result.cluster.size || 0).toLocaleString("en-US")}</strong></div>
  `;
  if (clusterOpen) clusterOpen.disabled = false;
  renderConfidenceRings();
  highlightRoute(result);
  if (modal?.classList.contains("open")) renderClusterDetail(result);
}

function updateResultNav() {
  const total = allResults.length;
  if (!total) return;
  resultNav.hidden = total <= 1;
  resultPosition.textContent = `${currentResultIndex + 1} / ${total}`;
  prevResult.disabled = currentResultIndex === 0;
  nextResult.disabled = currentResultIndex === total - 1;
}

function showResultAt(index) {
  if (!allResults.length) return;
  currentResultIndex = Math.max(0, Math.min(allResults.length - 1, index));
  renderInferenceResult(allResults[currentResultIndex]);
  updateResultNav();
  showResultsState();
}

function setProgress(processed, total, labelKey = "progress.processingEmbeddings") {
  const safeTotal = Math.max(0, Number(total || 0));
  const safeProcessed = Math.max(0, Number(processed || 0));
  progressState = { processed: safeProcessed, total: safeTotal, labelKey };
  const label = translations[currentLang]?.[labelKey] ? t(labelKey) : labelKey;
  progressPanel.hidden = false;
  progressLabel.textContent = `${safeTotal} ${t("progress.fasta")} - ${label}`;
  progressCount.textContent = `${safeProcessed} / ${safeTotal}`;
  progressBar.style.width = safeTotal ? `${Math.min(100, (safeProcessed / safeTotal) * 100)}%` : "0%";
}

async function startFileJob(file) {
  const form = new FormData();
  form.append("file", file);
  const response = await fetch("/api/jobs-file", { method: "POST", body: form });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || "Inference failed");
  }
  return response.json();
}

async function pollJob(jobId) {
  const response = await fetch(`/api/jobs/${jobId}`);
  if (!response.ok) throw new Error(currentLang === "es" ? "No se pudo consultar el progreso" : "Could not check progress");
  const job = await response.json();
  setProgress(job.processed, job.total, job.stage === "complete" ? "progress.complete" : "progress.processingEmbeddings");
  if (job.status === "error") throw new Error(job.error || "Inference failed");
  if (job.status === "complete") {
    clearInterval(pollTimer);
    pollTimer = null;
    allResults = job.results || [];
    currentResultIndex = 0;
    if (downloadResults && job.download_url) {
      downloadResults.href = job.download_url;
      downloadResults.hidden = false;
    }
    showResultAt(0);
    isUploading = false;
    uploadTrigger.disabled = false;
    renderUploadButton(false);
  }
}

async function handleSequenceFile(file) {
  if (!file) return;
  isUploading = true;
  renderUploadButton(true);
  uploadTrigger.disabled = true;
  if (downloadResults) downloadResults.hidden = true;
  allResults = [];
  currentResultIndex = 0;
  showEmptyState();
  setProgress(0, 0, "progress.readingFasta");
  try {
    const job = await startFileJob(file);
    activeJobId = job.job_id;
    setProgress(job.processed, job.total, "progress.processingEmbeddings");
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(() => pollJob(activeJobId).catch(handleJobError), 1000);
    await pollJob(activeJobId);
  } catch (error) {
    handleJobError(error);
  } finally {
    sequenceFile.value = "";
  }
}

function handleJobError(error) {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = null;
  isUploading = false;
  uploadTrigger.disabled = false;
  renderUploadButton(false);
  if (modal?.classList.contains("open")) closeModal();
  progressLabel.textContent = error.message;
  progressCount.textContent = t("status.error");
}

themeToggle?.addEventListener("click", () => applyTheme(currentTheme === "light" ? "dark" : "light"));
langToggle?.addEventListener("click", () => applyLanguage(currentLang === "es" ? "en" : "es"));
uploadTrigger?.addEventListener("click", () => sequenceFile?.click());
sequenceFile?.addEventListener("change", () => handleSequenceFile(sequenceFile.files?.[0]));
prevResult?.addEventListener("click", () => showResultAt(currentResultIndex - 1));
nextResult?.addEventListener("click", () => showResultAt(currentResultIndex + 1));
clusterOpen?.addEventListener("click", openModal);
clusterBackdrop?.addEventListener("click", closeModal);
infoBackdrop?.addEventListener("click", closeInfoModal);
clusterDetailCards?.addEventListener("click", (event) => {
  const button = event.target.closest(".detail-more");
  if (!button) return;
  openInfoModal(Number(button.dataset.detailIndex));
});

window.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  if (infoModal?.classList.contains("open")) closeInfoModal();
  else closeModal();
});

applyTheme(currentTheme);
applyLanguage(currentLang);
showEmptyState();

const toast = document.getElementById("toast");
const resultModal = document.getElementById("resultModal");
const resultTitle = document.getElementById("resultTitle");
const resultMeta = document.getElementById("resultMeta");
const resultViewer = document.getElementById("resultViewer");
const resultDownload = document.getElementById("resultDownload");
const closeResultModal = document.getElementById("closeResultModal");

const tasks = new Map();
const shownResultTaskIds = new Set();
let pollTimer = null;

closeResultModal.addEventListener("click", () => {
  resultModal.classList.add("hidden");
  resultViewer.innerHTML = "";
});

resultModal.addEventListener("click", (e) => {
  if (e.target === resultModal) {
    resultModal.classList.add("hidden");
    resultViewer.innerHTML = "";
  }
});

async function postForm(url, formData) {
  const res = await fetch(url, { method: "POST", body: formData });
  if (!res.ok) {
    throw new Error(await res.text());
  }
  return res.json();
}

async function submitVoiceDesign() {
  const text = document.getElementById("vd_text").value.trim();
  const instruct = document.getElementById("vd_instruct").value.trim();
  const language = document.getElementById("vd_language").value;
  if (!text) {
    alert("待合成文本不能为空");
    return;
  }
  const fd = new FormData();
  fd.append("text", text);
  fd.append("instruct", instruct);
  fd.append("language", language);
  const data = await postForm("/api/submit/voice-design", fd);
  tasks.set(data.task_id, { task_id: data.task_id, status: "queued", module: "voice_design" });
  showToast(`语音设计任务已进入队列（${data.task_id.slice(0, 8)}）`);
}

async function submitTts() {
  const ref = document.getElementById("tts_reference_audio").files[0];
  if (!ref) {
    alert("请上传参考音频");
    return;
  }
  const fd = new FormData();
  fd.append("text_input", document.getElementById("tts_text_input").value.trim());
  fd.append("reference_audio", ref);
  fd.append("emotion_happy", document.getElementById("emotion_happy").value || "0");
  fd.append("emotion_angry", document.getElementById("emotion_angry").value || "0");
  fd.append("emotion_sad", document.getElementById("emotion_sad").value || "0");
  fd.append("emotion_fear", document.getElementById("emotion_fear").value || "0");
  fd.append("emotion_disgust", document.getElementById("emotion_disgust").value || "0");
  fd.append("emotion_melancholy", document.getElementById("emotion_melancholy").value || "0");
  fd.append("emotion_surprise", document.getElementById("emotion_surprise").value || "0");
  fd.append("emotion_calm", document.getElementById("emotion_calm").value || "0");
  fd.append("use_random", document.getElementById("tts_use_random").value);
  const data = await postForm("/api/submit/tts", fd);
  tasks.set(data.task_id, { task_id: data.task_id, status: "queued", module: "tts" });
  showToast(`语音合成任务已进入队列（${data.task_id.slice(0, 8)}）`);
}

async function submitEnvAudio() {
  const video = document.getElementById("env_video").files[0];
  if (!video) {
    alert("请上传输入视频");
    return;
  }
  const fd = new FormData();
  fd.append("video", video);
  fd.append("prompt", document.getElementById("env_prompt").value.trim());
  fd.append("negative_prompt", document.getElementById("env_negative_prompt").value.trim());
  fd.append("audio_mix_mode", document.getElementById("env_audio_mix_mode").value);
  fd.append("ambient_volume", document.getElementById("env_ambient_volume").value);
  fd.append("bgm_volume", document.getElementById("env_bgm_volume").value);
  fd.append("num_steps", document.getElementById("env_num_steps").value);
  fd.append("cfg_strength", document.getElementById("env_cfg_strength").value);
  const data = await postForm("/api/submit/env-audio", fd);
  tasks.set(data.task_id, { task_id: data.task_id, status: "queued", module: "env_audio" });
  showToast(`环境音任务已进入队列（${data.task_id.slice(0, 8)}）`);
}

async function refreshQueue() {
  const res = await fetch("/api/queue");
  const data = await res.json();
  const queued = data.totals?.queued || 0;
  const running = data.totals?.running || 0;
  if (queued + running > 0) {
    showToast(`队列中 ${queued} 个，运行中 ${running} 个`);
  }
}

async function refreshTasks() {
  const ids = Array.from(tasks.keys());
  for (const taskId of ids) {
    const res = await fetch(`/api/task/${taskId}`);
    if (!res.ok) continue;
    const data = await res.json();
    const prev = tasks.get(taskId);
    tasks.set(taskId, data);
    if (prev && prev.status !== "done" && data.status === "done") {
      showResultIfAny(data);
    }
    if (prev && prev.status !== "failed" && data.status === "failed") {
      showToast(`${moduleName(data.module)}任务失败：${data.error || "未知错误"}`);
    }
  }
}

function moduleName(id) {
  if (id === "voice_design") return "个性化语音";
  if (id === "tts") return "语音生成";
  if (id === "env_audio") return "环境音效";
  return id;
}

function showToast(message) {
  if (!toast) {
    return;
  }
  toast.textContent = message;
  toast.classList.remove("hidden");
  window.clearTimeout(showToast._timer);
  showToast._timer = window.setTimeout(() => toast.classList.add("hidden"), 2500);
}

function inferMediaType(fileName = "") {
  const lower = String(fileName).toLowerCase();
  if (/\.(wav|mp3|m4a|aac|flac|ogg)$/.test(lower)) return "audio";
  if (/\.(mp4|mov|mkv|webm|avi)$/.test(lower)) return "video";
  if (/\.(png|jpg|jpeg|gif|webp|bmp)$/.test(lower)) return "image";
  return "other";
}

function showResultIfAny(task) {
  if (!task.download_url || shownResultTaskIds.has(task.task_id)) {
    return;
  }
  shownResultTaskIds.add(task.task_id);

  const mediaType = inferMediaType(task.output_file_name || "");
  const mediaUrl = task.download_url;
  resultTitle.textContent = `${moduleName(task.module)}任务完成`;
  resultMeta.textContent = `任务ID: ${task.task_id} | 文件: ${task.output_file_name || "result"}`;
  resultDownload.href = mediaUrl;
  resultViewer.innerHTML = "";

  if (mediaType === "audio") {
    resultViewer.innerHTML = `<audio controls autoplay src="${mediaUrl}"></audio>`;
  } else if (mediaType === "video") {
    resultViewer.innerHTML = `<video controls autoplay src="${mediaUrl}"></video>`;
  } else if (mediaType === "image") {
    resultViewer.innerHTML = `<img src="${mediaUrl}" alt="result image" />`;
  } else {
    resultViewer.innerHTML = `<div>任务已完成，点击下方按钮下载结果文件。</div>`;
  }
  resultModal.classList.remove("hidden");
}

function escapeHtml(str) {
  return str
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

async function refreshAll() {
  try {
    await refreshQueue();
    await refreshTasks();
  } catch (err) {
    showToast(`刷新失败: ${String(err)}`);
  }
}

document.getElementById("submitVoiceDesign").addEventListener("click", () =>
  submitVoiceDesign().catch((e) => alert(`提交失败: ${e.message}`))
);
document.getElementById("submitTts").addEventListener("click", () =>
  submitTts().catch((e) => alert(`提交失败: ${e.message}`))
);
document.getElementById("submitEnvAudio").addEventListener("click", () =>
  submitEnvAudio().catch((e) => alert(`提交失败: ${e.message}`))
);

refreshAll();
pollTimer = setInterval(refreshAll, 2000);

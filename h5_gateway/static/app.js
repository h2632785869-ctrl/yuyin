const moduleSelect = document.getElementById("moduleSelect");
const panels = {
  voice_design: document.getElementById("voiceDesignPanel"),
  tts: document.getElementById("ttsPanel"),
  env_audio: document.getElementById("envAudioPanel"),
};

const queueInfo = document.getElementById("queueInfo");
const taskList = document.getElementById("taskList");
const refreshBtn = document.getElementById("refreshBtn");

const tasks = new Map();
let pollTimer = null;

function switchModule(moduleId) {
  Object.entries(panels).forEach(([id, panel]) => {
    panel.classList.toggle("hidden", id !== moduleId);
  });
}

moduleSelect.addEventListener("change", (e) => switchModule(e.target.value));
refreshBtn.addEventListener("click", refreshAll);
switchModule(moduleSelect.value);

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
  renderTasks();
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
  renderTasks();
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
  renderTasks();
}

async function refreshQueue() {
  const res = await fetch("/api/queue");
  const data = await res.json();
  queueInfo.textContent =
    `队列中: ${data.queue_size} | 运行中: ${data.running_task_id || "无"} | ` +
    `统计: queued=${data.totals.queued}, running=${data.totals.running}, done=${data.totals.done}, failed=${data.totals.failed}`;
}

async function refreshTasks() {
  const ids = Array.from(tasks.keys());
  for (const taskId of ids) {
    const res = await fetch(`/api/task/${taskId}`);
    if (!res.ok) continue;
    const data = await res.json();
    tasks.set(taskId, data);
  }
  renderTasks();
}

function moduleName(id) {
  if (id === "voice_design") return "个性化语音";
  if (id === "tts") return "语音生成";
  if (id === "env_audio") return "环境音效";
  return id;
}

function renderTasks() {
  const ordered = Array.from(tasks.values()).sort((a, b) => (b.created_at || 0) - (a.created_at || 0));
  if (!ordered.length) {
    taskList.innerHTML = "<div class='task-body'>暂无任务</div>";
    return;
  }

  taskList.innerHTML = ordered
    .map((t) => {
      const createdAt = t.created_at ? new Date(t.created_at * 1000).toLocaleString() : "-";
      const download = t.download_url ? `<a class="download-link" href="${t.download_url}" target="_blank">下载结果</a>` : "";
      const err = t.error ? `<div>错误: ${escapeHtml(String(t.error))}</div>` : "";
      const result = t.result ? `<div>结果: ${escapeHtml(JSON.stringify(t.result))}</div>` : "";
      return `
        <div class="task-item">
          <div class="task-head">
            <span>${moduleName(t.module)}</span>
            <span class="status ${t.status}">${t.status}</span>
          </div>
          <div class="task-body">
            <div>ID: ${t.task_id}</div>
            <div>创建时间: ${createdAt}</div>
            ${download}
            ${err}
            ${result}
          </div>
        </div>
      `;
    })
    .join("");
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
    queueInfo.textContent = `刷新失败: ${String(err)}`;
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

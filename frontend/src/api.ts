import { invoke } from '@tauri-apps/api/core';

export type TaskStatus = 'queued' | 'running' | 'pausing' | 'paused' | 'blocked' | 'failed' | 'cancelling' | 'cancelled' | 'completed';

export type TaskView = {
  id: string;
  source_url: string;
  source_kind: 'video' | 'profile' | 'short' | 'local';
  platform_id: string | null;
  max_videos: number;
  status: TaskStatus;
  phase: string;
  success_count: number;
  failure_count: number;
  no_speech_count: number;
  stop_reason: string | null;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
};

type BackendConnection = { base_url: string; token: string };

let connection: BackendConnection | null = null;
let desktopMode = false;

export async function connectBackend(): Promise<void> {
  if ('__TAURI_INTERNALS__' in window) {
    desktopMode = true;
  } else {
    const base_url = import.meta.env.VITE_BACKEND_URL;
    const token = import.meta.env.VITE_BACKEND_TOKEN;
    if (!base_url || !token) {
      throw new Error('浏览器预览没有后端凭据。请运行Tauri，或配置仅供本机开发的VITE_BACKEND_URL和VITE_BACKEND_TOKEN。');
    }
    connection = { base_url, token };
  }
  // PyInstaller takes time to initialize. Probe *our authenticated backend*, not just an open port.
  let lastError = '';
  for (let i = 0; i < 60; i++) {
    try {
      await apiRequest('/api/health');
      return;
    } catch (error) {
      lastError = String(error);
      await new Promise(resolve => setTimeout(resolve, 750));
    }
  }
  throw new Error(`本地后端未就绪：${lastError}`);
}

export async function apiRequest<T>(path: string, method = 'GET', payload?: unknown): Promise<T> {
  if (desktopMode) {
    return await invoke<T>('backend_request', { path, method, body: payload ?? null });
  }
  if (!connection) throw new Error('后端连接尚未建立');
  const res = await fetch(`${connection.base_url}${path}`, {
    method,
    headers: { 'X-Analyst-Token': connection.token, 'Content-Type': 'application/json' },
    body: payload === undefined ? undefined : JSON.stringify(payload),
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const problem = (await res.json()) as { detail?: string };
      detail = problem.detail ?? detail;
    } catch { /* status text remains */ }
    throw new Error(detail);
  }
  return (await res.json()) as T;
}

export type VideoView = {
  id: string;
  platform: string;
  platform_video_id: string;
  author_platform_id: string;
  title: string;
  source_url: string;
  processing_status: string;
  media_sha256: string | null;
};

export type VideoDetail = {
  video: VideoView;
  transcript_versions: string[];
  analyses: { analysis_version: string; transcript_version: string; model_id: string; created_at: string }[];
};

export type TranscriptSegment = {
  video_id: string;
  transcript_version: string;
  segment_id: number;
  start_ms: number;
  end_ms: number;
  text: string;
  model_version: string;
};

export type Evidence = {
  video_id: string;
  transcript_version: string;
  segment_id: number;
  start_ms: number;
  end_ms: number;
  source_url?: string;
  analysis_version?: string;
};

export type Statement = {
  text: string;
  speaker_role: string;
  attribution_basis: string;
  creator_identity_verified: boolean;
  evidence: Evidence[];
};

export type VideoInsight = {
  summary: string;
  summary_evidence: Evidence[];
  primary_domain: string;
  secondary_topics: string[];
  content_format: string;
  key_claims: Statement[];
  explicitly_stated_preferences: Statement[];
  provenance: 'real_model' | 'test_fixture';
};

export type ReportMeta = {
  id: string;
  task_id: string;
  report_version: string;
  evidence_version: string;
  created_at?: string;
};

export type ReportRow = {
  name: string;
  count: number;
  percentage: number;
  evidence: Evidence[];
};

export type CreatorReport = {
  schema_version: string;
  provenance: 'real_model' | 'test_fixture';
  summary: string;
  creator_platform_id: string;
  sample: {
    requested_limit: number;
    collected_count: number;
    analyzed_count: number;
    failed_count: number;
    no_speech_count: number;
    unanalysed_count: number;
    stop_reason: string | null;
  };
  main_directions: ReportRow[];
  topic_tendencies: ReportRow[];
  frequently_discussed_entities: ReportRow[];
  creator_preferences_verified: Statement[];
  preferences_not_attributed_to_creator: Statement[];
  business_claim: string | null;
};

export async function exportTextFile(path: string): Promise<void> {
  const data = await apiRequest<{ filename: string; content: string }>(path);
  const safeName = data.filename.replace(/[\\/:*?"<>|]/g, '_');
  if (desktopMode) {
    await invoke('save_export', { filename: safeName, content: data.content });
    return;
  }
  const blob = new Blob([data.content], { type: 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = safeName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export async function selectLocalVideo(): Promise<string | null> {
  if (!desktopMode) throw new Error('本地文件选择请使用桌面应用。');
  return await invoke<string | null>('select_local_video');
}

export type RuntimeSettingsView = {
  model_provider: 'api' | 'chatgpt'; CHATGPT_MODEL: string;
  OPENAI_BASE_URL: string; OPENAI_MODEL: string; api_key_configured: boolean;
  api_key_encrypted: boolean; enable_live: boolean; cookie_file: string;
  collector_provider: 'f2' | 'browser';
  whisper_model: string; data_dir: string;
};

export type Diagnostics = {
  ffmpeg: boolean; ffprobe: boolean; data_dir: string; agent_enabled: boolean;
  packages: { f2: string | null; 'faster-whisper': string | null };
};

export async function getDesktopMediaUrl(videoId: string): Promise<string | null> {
  if (!desktopMode) return null;
  return await invoke<string>('backend_media_url', { videoId });
}

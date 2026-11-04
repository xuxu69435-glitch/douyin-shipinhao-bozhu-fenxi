import { invoke } from '@tauri-apps/api/core';

export type TaskStatus = 'queued' | 'running' | 'pausing' | 'paused' | 'blocked' | 'failed' | 'cancelling' | 'cancelled' | 'completed';

export type TaskView = {
  id: string;
  source_url: string;
  source_kind: 'video' | 'profile' | 'short';
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

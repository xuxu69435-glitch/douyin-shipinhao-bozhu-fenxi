import { useEffect, useState } from 'react';
import { apiRequest, type RuntimeSettingsView, type Diagnostics } from './api';
import ChatGPTConnection from './ChatGPTConnection';

export default function SettingsPage({ ready }: { ready: boolean }) {
  const [settings, setSettings] = useState<RuntimeSettingsView | null>(null);
  const [diagnostics, setDiagnostics] = useState<Diagnostics | null>(null);
  const [key, setKey] = useState('');
  const [clearKey, setClearKey] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    if (!ready) return;
    let active = true;
    void Promise.all([apiRequest<RuntimeSettingsView>('/api/settings'), apiRequest<Diagnostics>('/api/diagnostics')])
      .then(([configuration, checks]) => { if (active) { setSettings(configuration); setDiagnostics(checks); } })
      .catch(err => { if (active) setError(String(err)); });
    return () => { active = false; };
  }, [ready]);

  const save = async (test = false) => {
    if (!settings) return;
    setBusy(true); setMessage(''); setError('');
    try {
      const { api_key_configured: _configured, api_key_encrypted: _encrypted, data_dir: _directory, ...values } = settings;
      const saved = await apiRequest<RuntimeSettingsView>('/api/settings', 'POST', {
        ...values, OPENAI_API_KEY: clearKey ? '' : key || null,
      });
      setSettings(saved); setKey(''); setClearKey(false);
      if (test) {
        const result = await apiRequest<{ message: string }>('/api/settings/test', 'POST');
        setMessage(result.message);
      } else setMessage('已保存。新建或恢复的任务将使用新配置，无需重启。');
    } catch (err) { setError(String(err)); }
    finally { setBusy(false); }
  };

  return <section className="settings-page">
    <div className="eyebrow">LOCAL SETTINGS</div><h1>模型与采集设置</h1>
    <p className="muted">选择 ChatGPT 套餐授权或兼容 API 服务。分析时向所选服务发送字幕。</p>
    {error && <div className="warning" role="alert">{error}</div>}
    {message && <p className="success" role="status">{message}</p>}
    {!settings ? <p className="muted">{ready ? '正在读取配置…' : '请等待本地后端连接。'}</p> : <>
      <div className="settings-form">
        <label className="wide-field">模型接入方式 <select value={settings.model_provider}
          onChange={event => setSettings({ ...settings, model_provider: event.target.value as 'api' | 'chatgpt' })}>
          <option value="chatgpt">使用 ChatGPT 套餐（官方授权登录）</option><option value="api">使用 API Key</option>
        </select></label>
        {settings.model_provider === 'chatgpt' ? <ChatGPTConnection model={settings.CHATGPT_MODEL}
          onModel={model => setSettings(previous => previous && ({ ...previous, CHATGPT_MODEL: model }))}/> : <>
        <label>API 基础地址 <small>OPENAI_BASE_URL</small>
          <input type="url" value={settings.OPENAI_BASE_URL} placeholder="https://你的服务地址/v1"
            onChange={event => setSettings({ ...settings, OPENAI_BASE_URL: event.target.value })}/>
          <span>填写服务商提供的基础地址，不包含 /chat/completions。</span>
        </label>
        <label>模型名称 <small>OPENAI_MODEL</small>
          <input value={settings.OPENAI_MODEL} placeholder="填写服务商提供的实际模型 ID"
            onChange={event => setSettings({ ...settings, OPENAI_MODEL: event.target.value })}/>
        </label>
        <label className="wide-field">API 密钥 <small>OPENAI_API_KEY</small>
          <input type="password" autoComplete="off" value={key} placeholder={settings.api_key_configured ? '已配置；留空保持原密钥' : '粘贴你的 API Key'}
            onChange={event => { setKey(event.target.value); setClearKey(false); }}/>
          <span>{settings.api_key_encrypted ? '使用 Windows 用户加密，保存在本机应用数据目录。' : '仅保存于本机应用数据目录，请保护好该目录。'}密钥不会回显。</span>
        </label>
        {settings.api_key_configured && <label className="checkbox"><input type="checkbox" checked={clearKey} onChange={event => setClearKey(event.target.checked)}/>清除已保存的密钥</label>}
        </>}
        <label className="wide-field">本地语音识别模型
          <input value={settings.whisper_model} placeholder="small，或已下载模型的完整目录"
            onChange={event => setSettings({ ...settings, whisper_model: event.target.value })}/>
          <span>语音识别在本机运行。首次使用模型名称时会下载权重，也可填写本地模型目录。</span>
        </label>
        <details className="collector-settings"><summary>抖音采集设置 <span>{settings.enable_live ? '已启用' : '未启用'}</span></summary>
        <label className="checkbox"><input type="checkbox" checked={settings.enable_live} onChange={event => setSettings({ ...settings, enable_live: event.target.checked })}/>启用真实抖音采集</label>
        <p className="muted">默认关闭。仅在你确认有权访问样本并准备进行真实测试后开启；本地视频分析不需要开启此项。</p>
        <label>抖音 Cookie 文件路径（可选）
          <input value={settings.cookie_file} placeholder="留空，或填写你自行提供的本机文本文件路径"
            onChange={event => setSettings({ ...settings, cookie_file: event.target.value })}/>
          <span>不会从浏览器提取登录状态。文件只在本机读取。</span>
        </label>
        </details>
        <div className="actions"><button className="primary" disabled={busy} onClick={() => void save()}>保存配置</button>
          <button className="plain" disabled={busy} onClick={() => void save(true)}>{busy ? '正在处理…' : '保存并测试所选模型'}</button></div>
        <p className="muted">测试会发送一句示例字幕并产生少量所选服务的用量，不会采集抖音或下载语音模型。</p>
      </div>
      <section className="runtime-checks"><h2>本机环境</h2>
        {diagnostics && <p>FFmpeg：{diagnostics.ffmpeg ? '可用' : '缺失'} · FFprobe：{diagnostics.ffprobe ? '可用' : '缺失'} ·
          采集组件：{diagnostics.packages.f2 ?? '未安装'} · 语音组件：{diagnostics.packages['faster-whisper'] ?? '未安装'}</p>}
        <p className="muted">数据目录：<code>{settings.data_dir}</code></p>
        <p className="muted">固定流程负责转写、分析与证据校验，审查 Agent 暂缓启用。</p>
      </section>
    </>}
  </section>;
}

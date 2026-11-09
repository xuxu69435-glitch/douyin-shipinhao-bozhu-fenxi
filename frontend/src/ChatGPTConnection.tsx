import { useEffect, useState } from 'react';
import { apiRequest } from './api';

type Session = { status: string; sharing: boolean; identity?: { email?: string; name?: string }; error?: { message: string } };
type Model = { slug: string; displayName: string };

export default function ChatGPTConnection({ model, onModel }: { model: string; onModel: (model: string) => void }) {
  const [session, setSession] = useState<Session | null>(null);
  const [models, setModels] = useState<Model[]>([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const refresh = () => apiRequest<Session>('/api/chatgpt/status').then(setSession).catch(err => setError(String(err)));
  useEffect(() => { void refresh(); }, []);
  useEffect(() => {
    if (session?.status !== 'connecting') return;
    const interval = setInterval(() => { void refresh(); }, 2000);
    return () => clearInterval(interval);
  }, [session?.status]);
  useEffect(() => {
    if (!session?.sharing) { setModels([]); return; }
    void apiRequest<Model[]>('/api/chatgpt/models').then(setModels).catch(err => setError(String(err)));
  }, [session?.sharing]);
  const action = async (path: string) => {
    setError(''); setBusy(true);
    try { setSession(await apiRequest<Session>(`/api/chatgpt/${path}`, 'POST')); }
    catch (err) { await refresh(); setError(String(err)); }
    finally { setBusy(false); }
  };
  return <div className="chatgpt-connection wide-field">
    <strong>使用你的 ChatGPT 套餐</strong>
    <p className="muted">在浏览器中使用 ChatGPT 登录并授权本应用。分析会使用所选账户的套餐额度，无需 API Key；可在用量设置中管理本应用额度。</p>
    {session?.status === 'connected' && <p>{session.identity?.email ?? session.identity?.name ?? '已登录 ChatGPT'} · {session.sharing ? '已启用套餐用量' : '尚未授权套餐用量，请重新登录授权'}</p>}
    {session?.status === 'connecting' && <p role="status">请在浏览器中完成登录与授权，完成后会自动更新。</p>}
    {(error || session?.error) && <p className="reason" role="alert">{error || session?.error?.message}</p>}
    <div className="actions">
      {session?.status === 'connecting' ? <button disabled={busy} onClick={() => void action('cancel')}>取消登录</button> :
        <button disabled={busy} onClick={() => void action('sign-in')}>使用 ChatGPT 登录</button>}
      {session?.status === 'connected' && <button disabled={busy} onClick={() => void action('disconnect')}>断开连接</button>}
      <button className="plain" onClick={() => { void apiRequest('/api/chatgpt/usage', 'POST').catch(err => setError(String(err))); }}>管理套餐用量</button>
    </div>
    <label>套餐模型 <select value={model} onChange={event => onModel(event.target.value)} disabled={!models.length}>
      <option value="">{models.length ? '请选择账户可用模型' : '登录授权后读取可用模型'}</option>
      {models.map(item => <option key={item.slug} value={item.slug}>{item.displayName}</option>)}
    </select></label>
    <p className="muted">选择模型后保存配置。仅发送分析所需字幕；不会自动切换到 API Key。请求有次数、输入长度和超时限制，套餐通道不提供输出 token 费用硬上限。</p>
  </div>;
}

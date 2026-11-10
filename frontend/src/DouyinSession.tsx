import { useEffect, useState } from 'react';
import { apiRequest } from './api';

type Session = { configured: boolean; cookie_count: number; login_marker_present: boolean; saved_at: string | null };

export default function DouyinSession() {
  const [session, setSession] = useState<Session | null>(null);
  const [cookie, setCookie] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  useEffect(() => { void apiRequest<Session>('/api/douyin/session').then(setSession).catch(err => setError(String(err))); }, []);
  const save = async (clear = false) => {
    setBusy(true); setError(''); setMessage('');
    try {
      setSession(await apiRequest<Session>(clear ? '/api/douyin/session/clear' : '/api/douyin/session', 'POST', clear ? undefined : { cookie }));
      setCookie('');
      setMessage(clear ? '已清除加密保存的登录状态。' : '已在本机加密保存。请回任务中心检测原链接，确认平台当前允许访问。');
    } catch (err) { setError(String(err)); }
    finally { setBusy(false); }
  };
  return <div className="douyin-session">
    <strong>抖音登录状态</strong>
    <p className="muted">{session?.configured ? `已加密保存 ${session.cookie_count} 项 Cookie${session.login_marker_present ? '，包含登录标记' : '，未发现常见登录标记'}。` : '尚未导入。可以先匿名检测，遇到需要登录时再导入。'}格式有效不代表平台授权检测已通过。</p>
    <label>粘贴 Cookie 请求头的值
      <textarea className="secret-cookie" autoComplete="off" spellCheck={false} value={cookie} rows={2} maxLength={65536}
        placeholder="仅粘贴本机 Cookie，不要发送到聊天或提交到 Git" onChange={event => setCookie(event.target.value)}/>
    </label>
    <div className="actions"><button disabled={busy || !cookie.trim()} onClick={() => void save()}>加密保存登录状态</button>
      {session?.configured && <button className="plain" disabled={busy} onClick={() => void save(true)}>清除已保存状态</button>}</div>
    {error && <p className="reason" role="alert">{error}</p>}
    {message && <p className="success" role="status">{message}</p>}
    <details className="cookie-help"><summary>Cookie 从哪里获取？</summary>
      <ol>
        <li>在自己的浏览器打开抖音网页版并登录，确认能正常观看要分析的视频。</li>
        <li>按 F12 打开开发者工具，选择 Network（网络），再刷新抖音页面。</li>
        <li>在筛选框输入 domain:www.douyin.com，刷新后点击作品请求（如 feed、aweme 或 post），打开 Headers（标头）。Name 列可能不显示域名，请在 General（常规）的 Request URL（请求网址）确认以 https://www.douyin.com/ 开头；不要选 imapi 消息请求。</li>
        <li>在 Request Headers（请求标头）中找到 Cookie，复制它的值。不要复制 Set-Cookie、整段 cURL 或响应内容。</li>
        <li>粘贴到上方，点击“加密保存登录状态”；启用并保存真实采集后，在任务中心检测原链接。</li>
      </ol>
      <p className="muted">Cookie 相当于登录凭据，只使用自己的状态。保存在当前 Windows 账户下，不回显、不随安装包分发。过期后重新导入；持续 403 也可能是平台接口限制，不能据此保证导入 Cookie 就一定成功。</p>
    </details>
  </div>;
}

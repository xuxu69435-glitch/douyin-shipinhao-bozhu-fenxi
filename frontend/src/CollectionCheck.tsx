import { useState } from 'react';
import { apiRequest, exportTextFile } from './api';

type Result = { complete: boolean; resolved_url?: string; model_called: boolean;
  steps: { name: string; status: string; message: string }[] };
const labels: Record<string, string> = { link: '链接', author: '作者', works: '作品', page2: '第二页', media: '媒体' };
const states: Record<string, string> = { passed: '通过', blocked: '受阻', skipped: '未执行', pending: '等待' };

export default function CollectionCheck({ input, ready }: { input: string; ready: boolean }) {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState('');
  const check = async () => {
    setBusy(true); setError(''); setResult(null);
    try { setResult(await apiRequest<Result>('/api/diagnostics/douyin', 'POST', { input_text: input })); }
    catch (err) { setError(String(err)); }
    finally { setBusy(false); }
  };
  return <div className="collection-check">
    <button className="plain" disabled={!ready || busy || !input.trim()} onClick={() => void check()}>{busy ? '正在检测，最多约 45 秒…' : '检测此链接的采集能力（不调用模型）'}</button>
    {error && <p className="reason" role="alert">{error}</p>}
    {result && <details open><summary>{result.complete ? '采集检测通过' : '采集检测尚未全部通过'}</summary>
      {result.resolved_url && <p className="muted">{result.resolved_url}</p>}
      <ul>{result.steps.map(step => <li key={step.name}><b>{labels[step.name]} · {states[step.status]}</b>：{step.message}</li>)}</ul>
      <button className="plain" onClick={() => { void exportTextFile('/api/diagnostics/douyin/export').catch(err => setError(String(err))); }}>导出本次检测结果</button>
    </details>}
  </div>;
}

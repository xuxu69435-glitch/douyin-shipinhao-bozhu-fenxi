import { useEffect, useState } from 'react';
import {
  apiRequest, exportTextFile,
  type CreatorReport, type Evidence, type ReportMeta, type ReportRow, type TaskView,
} from './api';

function Breakdown({ title, items, onEvidence }: { title: string; items: ReportRow[]; onEvidence: (ref: Evidence) => void }) {
  return <section className="report-section">
    <h2>{title}</h2>
    {items.length === 0 ? <p className="muted">暂无可支持的结论。</p> : items.map(item => <div className="metric-row" key={item.name}>
      <strong>{item.name}</strong><div className="metric-bar"><span style={{ width: `${Math.min(item.percentage, 100)}%` }} /></div>
      <span>{item.count}条 · {item.percentage}%</span>
      <div className="metric-evidence">{item.evidence.slice(0, 3).map((ref: Evidence, i) =>
        <button className="plain" key={`${ref.video_id}-${i}`} onClick={() => onEvidence(ref)}>查看字幕证据 {i + 1}（{Math.round(ref.start_ms / 1000)}秒）</button>
      )}</div>
    </div>)}
  </section>;
}

export default function ReportPage({ ready, tasks, onEvidence }: { ready: boolean; tasks: TaskView[]; onEvidence: (ref: Evidence) => void }) {
  const [taskId, setTaskId] = useState<string>('');
  const [reportList, setReportList] = useState<ReportMeta[]>([]);
  const [reportId, setReportId] = useState<string>('');
  const [report, setReport] = useState<CreatorReport | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const creators = tasks.filter(task => task.source_kind === 'profile');

  useEffect(() => {
    if (!taskId && creators.length) setTaskId(creators[0].id);
  }, [taskId, creators]);

  useEffect(() => {
    if (!ready || !taskId) return;
    let active = true;
    setReport(null);
    void apiRequest<ReportMeta[]>(`/api/tasks/${taskId}/reports`).then(items => {
      if (!active) return;
      setReportList(items);
      setReportId(items[0]?.id ?? '');
    }).catch(err => { if (active) setError(String(err)); });
    return () => { active = false; };
  }, [ready, taskId]);

  useEffect(() => {
    if (!ready || !reportId) { setReport(null); return; }
    let active = true;
    void apiRequest<CreatorReport>(`/api/reports/${reportId}`).then(data => {
      if (active) setReport(data);
    }).catch(err => { if (active) setError(String(err)); });
    return () => { active = false; };
  }, [ready, reportId]);

  const build = async () => {
    if (!taskId) return;
    setBusy(true);
    setError('');
    try {
      const built = await apiRequest<ReportMeta>(`/api/tasks/${taskId}/reports/build`, 'POST');
      setReportId(built.id);
      setReport(await apiRequest<CreatorReport>(`/api/reports/${built.id}`));
      setReportList(await apiRequest<ReportMeta[]>(`/api/tasks/${taskId}/reports`));
    } catch (err) { setError(String(err)); }
    finally { setBusy(false); }
  };

  return <section className="report-page">
    <div className="eyebrow">M2 / CROSS-VIDEO EVIDENCE</div>
    <h1>博主内容报告</h1>
    <p className="muted">统计由程序计算，不把嘉宾、引用对象或身份不清的旁白直接当成博主本人。</p>
    <div className="report-controls">
      <label>分析任务 <select value={taskId} onChange={event => setTaskId(event.target.value)}>
        {creators.length === 0 && <option value="">暂无博主任务</option>}
        {creators.map(task => <option key={task.id} value={task.id}>{task.source_url.slice(0, 76)}</option>)}
      </select></label>
      <button className="primary" disabled={!taskId || busy || !ready} onClick={() => void build()}>{busy ? '核查证据中…' : '从已有视频生成报告'}</button>
      {reportList.length > 0 && <label>历史版本 <select value={reportId} onChange={event => setReportId(event.target.value)}>
        {reportList.map(meta => <option key={meta.id} value={meta.id}>{meta.report_version}</option>)}
      </select></label>}
    </div>
    {error && <div className="warning">{error}</div>}
    {!report && <div className="empty">尚无可查看的报告。只有存在通过证据核查的真实分析记录或明确标记的测试数据时，才能生成报告。</div>}
    {report && <>
      <div className="report-header"><span>{report.provenance === 'test_fixture' ? '测试数据 · 不代表真实抖音分析' : '真实模型分析'}</span>
        <div className="actions"><button className="plain" onClick={() => void exportTextFile(`/api/reports/${reportId}/export/md`).catch(err => setError(String(err)))}>导出Markdown</button>
          <button className="plain" onClick={() => void exportTextFile(`/api/reports/${reportId}/export/json`).catch(err => setError(String(err)))}>导出JSON</button></div></div>
      <h2 className="report-summary">{report.summary}</h2>
      <p className="muted">样本：{report.sample.collected_count}条已关联，{report.sample.analyzed_count}条有效，{report.sample.failed_count}条失败，{report.sample.no_speech_count}条无有效语音；停止原因：{report.sample.stop_reason ?? '未知'}</p>
      <Breakdown title="主要领域" items={report.main_directions} onEvidence={onEvidence}/>
      <Breakdown title="选题倾向" items={report.topic_tendencies} onEvidence={onEvidence}/>
      <Breakdown title="高频讨论对象" items={report.frequently_discussed_entities} onEvidence={onEvidence}/>
      <section className="report-section"><h2>公开表达的偏好</h2>
        {report.creator_preferences_verified.length === 0 && <p className="muted">当前没有经过独立身份核实、可归属于博主本人的偏好证据。</p>}
        {report.creator_preferences_verified.map((value, i) => <p key={i}>{value.text}</p>)}
        <p className="muted">其他主体或身份不明的偏好表达：{report.preferences_not_attributed_to_creator.length}条。完整来源见JSON报告。</p>
      </section>
      <section className="report-section"><h2>主营业务</h2><p className="muted">{report.business_claim ?? '公开证据不足，暂不推断。'}</p></section>
    </>}
  </section>;
}

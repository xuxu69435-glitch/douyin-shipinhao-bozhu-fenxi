import { useEffect, useState } from 'react';
import { apiRequest, connectBackend, selectLocalVideo, type Evidence, type TaskStatus, type TaskView } from './api';
import VideoLibrary from './VideoLibrary';
import ReportPage from './ReportPage';
import SettingsPage from './SettingsPage';

type View = 'tasks' | 'videos' | 'reports' | 'settings';

const statusText: Record<TaskStatus, string> = {
  queued: '排队中', running: '执行中', pausing: '准备暂停', paused: '已暂停',
  blocked: '需要处理', failed: '执行失败', cancelling: '准备取消', cancelled: '已取消', completed: '已完成'
};

function formatted(value: string) {
  return new Intl.DateTimeFormat('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(new Date(value));
}

export default function App() {
  const [view, setView] = useState<View>('tasks');
  const [input, setInput] = useState('');
  const [limit, setLimit] = useState<10 | 30>(10);
  const [tasks, setTasks] = useState<TaskView[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [targetEvidence, setTargetEvidence] = useState<Evidence | null>(null);
  const [ready, setReady] = useState(false);
  const [warning, setWarning] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [historyPage, setHistoryPage] = useState(0);

  const refresh = async () => {
    const data = await apiRequest<TaskView[]>('/api/tasks');
    setTasks(data);
  };

  useEffect(() => {
    let alive = true;
    let interval: ReturnType<typeof setInterval> | undefined;
    void connectBackend()
      .then(async () => {
        if (!alive) return;
        setReady(true);
        await refresh();
        interval = setInterval(() => { void refresh().catch(err => setWarning(String(err))); }, 2000);
      })
      .catch(error => { if (alive) setWarning(String(error)); });
    return () => { alive = false; if (interval) clearInterval(interval); };
  }, []);

  const createTask = async () => {
    setSubmitting(true);
    setWarning('');
    try {
      const task = await apiRequest<TaskView>('/api/tasks', 'POST', { input_text: input, max_videos: limit });
      setInput('');
      setHistoryPage(0);
      setSelected(task.id);
      await refresh();
    } catch (error) {
      setWarning(String(error));
    } finally {
      setSubmitting(false);
    }
  };

  const change = async (task: TaskView, action: 'pause' | 'resume' | 'cancel') => {
    try {
      setWarning('');
      await apiRequest(`/api/tasks/${task.id}/${action}`, 'POST');
      await refresh();
    } catch (error) {
      setWarning(String(error));
    }
  };

  const importVideo = async () => {
    setSubmitting(true); setWarning('');
    try {
      const path = await selectLocalVideo();
      if (!path) return;
      const task = await apiRequest<TaskView>('/api/local-videos', 'POST', { path });
      setSelected(task.id);
      setHistoryPage(0);
      await refresh();
    } catch (err) { setWarning(String(err)); }
    finally { setSubmitting(false); }
  };

  const active = tasks.find(task => task.id === selected);
  const pageCount = Math.max(1, Math.ceil(tasks.length / 8));
  const page = Math.min(historyPage, pageCount - 1);
  const visibleTasks = tasks.slice(page * 8, (page + 1) * 8);
  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand"><span className="brand-mark">影</span><div><strong>观影笔记</strong><small>视频内容分析工作台</small></div></div>
        <p className="nav-label">工作区</p>
        <nav aria-label="主导航">
          <button className={view === 'tasks' ? 'nav active' : 'nav'} onClick={() => setView('tasks')}>任务中心</button>
          <button className={view === 'videos' ? 'nav active' : 'nav'} onClick={() => setView('videos')}>视频与字幕</button>
          <button className={view === 'reports' ? 'nav active' : 'nav'} onClick={() => setView('reports')}>博主报告</button>
          <button className={view === 'settings' ? 'nav active' : 'nav'} onClick={() => setView('settings')}>模型与采集设置</button>
        </nav>
        <div className="sidebar-bottom"><span className={ready ? 'dot online' : 'dot'} />{ready ? '本地后端已连接' : '等待本地后端'}<p>本地工作区</p></div>
      </aside>
      <main>
        <header className="topline"><div>Douyin Analyst <span>/ 本地桌面</span></div><span>本机保存结果 · 模型服务接收字幕</span></header>
        {warning && <div className="warning" role="alert">{warning}</div>}
        {view === 'tasks' ? <>
          <section className="hero"><h1>内容分析工作台</h1><p>导入视频或粘贴分享文本，查看字幕、观点与来源证据。</p></section>
          <div className="task-workspace">
          <section className="create-panel"><div className="section-heading"><h2>新建分析</h2><span>每条结论都应追溯至原始视频</span></div>
            <label htmlFor="source">抖音链接 / 分享文本</label>
            <textarea id="source" value={input} onChange={event => setInput(event.target.value)} placeholder="可直接粘贴抖音完整分享文本、主页或作品链接" rows={4} />
            <div className="create-controls"><div className="limit-group"><span>博主视频数量</span><button className={limit === 10 ? 'chip selected' : 'chip'} onClick={() => setLimit(10)}>最近10条</button><button className={limit === 30 ? 'chip selected' : 'chip'} onClick={() => setLimit(30)}>最近30条</button></div>
              <button className="primary" disabled={!ready || submitting || !input.trim()} onClick={() => void createTask()}>{submitting ? '正在创建…' : '创建任务'} <span aria-hidden="true">↗</span></button></div>
            <div className="actions"><button className="plain" disabled={!ready || submitting} onClick={() => void importVideo()}>选择本地视频分析</button><button className="plain" onClick={() => setView('settings')}>配置模型 API</button></div>
            <p className="disclaimer">首次使用请配置模型 API。抖音采集需在设置中自行开启并验证；也可选择本地视频独立测试分析链路。</p>
          </section>
          <section className="history"><div className="section-heading"><h2>历史任务</h2><span>{tasks.length} 项</span></div>
            {tasks.length === 0 ? <div className="empty">暂无任务。先创建一个视频或博主分析任务。</div> : <div className="task-list">
              {visibleTasks.map(task => <article key={task.id} className={selected === task.id ? 'task-row expanded' : 'task-row'}>
                <button className="task-title" onClick={() => setSelected(selected === task.id ? null : task.id)}><span><strong>{task.source_kind === 'profile' ? '博主分析' : task.source_kind === 'video' ? '单视频分析' : task.source_kind === 'local' ? '本地视频分析' : '分享短链解析'}</strong><small>{formatted(task.created_at)} · {task.max_videos} 条上限</small></span><span className={`task-status status-${task.status}`}>{statusText[task.status]}</span></button>
                {selected === task.id && <div className="task-detail">{task.source_kind === 'local' ? <span>{task.source_url}</span> : <a href={task.source_url} target="_blank" rel="noreferrer">{task.source_url}</a>}<p>阶段：{task.phase} · 成功 {task.success_count} / 失败 {task.failure_count} / 无有效语音 {task.no_speech_count}</p>
                  {task.error_message && <p className="reason"><b>{task.error_code}：</b>{task.error_message}</p>}
                  <div className="actions">{['queued','running','blocked'].includes(task.status) && <button onClick={() => void change(task, 'pause')}>暂停</button>}
                    {['paused', 'blocked', 'failed'].includes(task.status) && <button onClick={() => void change(task, 'resume')}>恢复</button>}
                    {!['cancelled','completed','cancelling'].includes(task.status) && <button onClick={() => void change(task, 'cancel')}>取消</button>}</div>
                </div>}
              </article>)}
            </div>}
            {pageCount > 1 && <div className="history-pagination"><button className="plain" disabled={page === 0} onClick={() => setHistoryPage(page - 1)}>上一页</button><span>{page + 1} / {pageCount}</span><button className="plain" disabled={page === pageCount - 1} onClick={() => setHistoryPage(page + 1)}>下一页</button></div>}
            {active && <p className="tip">已选：{active.source_url}</p>}
          </section>
          </div>
        </> : view === 'videos' ? <VideoLibrary ready={ready} targetEvidence={targetEvidence} /> : view === 'settings' ? <SettingsPage ready={ready} /> : <ReportPage ready={ready} tasks={tasks} onEvidence={(ref) => { setTargetEvidence(ref); setView('videos'); }} />}
      </main>
    </div>
  );
}

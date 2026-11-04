import { useEffect, useState } from 'react';
import { apiRequest, connectBackend, type Evidence, type TaskStatus, type TaskView } from './api';
import VideoLibrary from './VideoLibrary';
import ReportPage from './ReportPage';

type View = 'tasks' | 'videos' | 'reports';

const statusText: Record<TaskStatus, string> = {
  queued: '排队中', running: '执行中', pausing: '准备暂停', paused: '已暂停',
  blocked: '等待采集验收', failed: '执行失败', cancelling: '准备取消', cancelled: '已取消', completed: '已完成'
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

  const active = tasks.find(task => task.id === selected);
  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand"><span className="brand-mark">影</span><div><strong>观影笔记</strong><small>视频内容分析工作台</small></div></div>
        <p className="nav-label">工作区</p>
        <nav aria-label="主导航">
          <button className={view === 'tasks' ? 'nav active' : 'nav'} onClick={() => setView('tasks')}>任务中心</button>
          <button className={view === 'videos' ? 'nav active' : 'nav'} onClick={() => setView('videos')}>视频与字幕 <span>M1</span></button>
          <button className={view === 'reports' ? 'nav active' : 'nav'} onClick={() => setView('reports')}>博主报告 <span>M2</span></button>
        </nav>
        <div className="sidebar-bottom"><span className={ready ? 'dot online' : 'dot'} />{ready ? '本地后端已连接' : '等待本地后端'}<p>R0 → M2 · 开发版本</p></div>
      </aside>
      <main>
        <header className="topline"><div>Douyin Analyst <span>/ 本地桌面</span></div><span>数据留在本机 · 仅分析有权访问的内容</span></header>
        {warning && <div className="warning" role="alert">{warning}</div>}
        {view === 'tasks' ? <>
          <section className="hero"><div className="eyebrow">WORKSPACE / 001</div><h1>从视频出发，<br /><em>理解创作者的公开表达。</em></h1><p>粘贴抖音博主主页、视频链接或分享文本，创建可追溯的分析任务。</p></section>
          <section className="create-panel"><div className="section-heading"><h2>新建分析</h2><span>每条结论都应追溯至原始视频</span></div>
            <label htmlFor="source">抖音链接 / 分享文本</label>
            <textarea id="source" value={input} onChange={event => setInput(event.target.value)} placeholder="粘贴 https://www.douyin.com/user/... 或作品链接" rows={3} />
            <div className="create-controls"><div className="limit-group"><span>博主视频数量</span><button className={limit === 10 ? 'chip selected' : 'chip'} onClick={() => setLimit(10)}>最近10条</button><button className={limit === 30 ? 'chip selected' : 'chip'} onClick={() => setLimit(30)}>最近30条</button></div>
              <button className="primary" disabled={!ready || submitting || !input.trim()} onClick={() => void createTask()}>{submitting ? '正在创建…' : '创建任务'} <span aria-hidden="true">↗</span></button></div>
            <p className="disclaimer">分析与报告模块已具备独立验证入口。真实抖音采集仍需R0验收；在此之前新建任务将明确显示为“等待采集验收”。</p>
          </section>
          <section className="history"><div className="section-heading"><h2>历史任务</h2><span>{tasks.length} 项</span></div>
            {tasks.length === 0 ? <div className="empty">暂无任务。先创建一个视频或博主分析任务。</div> : <div className="task-list">
              {tasks.map(task => <article key={task.id} className={selected === task.id ? 'task-row expanded' : 'task-row'}>
                <button className="task-title" onClick={() => setSelected(selected === task.id ? null : task.id)}><span><strong>{task.source_kind === 'profile' ? '博主分析' : task.source_kind === 'video' ? '单视频分析' : '分享短链解析'}</strong><small>{formatted(task.created_at)} · {task.max_videos} 条上限</small></span><span className={`task-status status-${task.status}`}>{statusText[task.status]}</span></button>
                {selected === task.id && <div className="task-detail"><a href={task.source_url} target="_blank" rel="noreferrer">{task.source_url}</a><p>阶段：{task.phase} · 成功 {task.success_count} / 失败 {task.failure_count} / 无有效语音 {task.no_speech_count}</p>
                  {task.error_message && <p className="reason"><b>{task.error_code}：</b>{task.error_message}</p>}
                  <div className="actions">{['queued','running','blocked'].includes(task.status) && <button onClick={() => void change(task, 'pause')}>暂停</button>}
                    {['paused', 'blocked', 'failed'].includes(task.status) && <button onClick={() => void change(task, 'resume')}>恢复</button>}
                    {!['cancelled','completed','cancelling'].includes(task.status) && <button onClick={() => void change(task, 'cancel')}>取消</button>}</div>
                </div>}
              </article>)}
            </div>}
            {active && <p className="tip">已选任务：{active.id}</p>}
          </section>
        </> : view === 'videos' ? <VideoLibrary ready={ready} targetEvidence={targetEvidence} /> : <ReportPage ready={ready} tasks={tasks} onEvidence={(ref) => { setTargetEvidence(ref); setView('videos'); }} />}
      </main>
    </div>
  );
}

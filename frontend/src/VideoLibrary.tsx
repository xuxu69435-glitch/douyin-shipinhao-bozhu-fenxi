import { useEffect, useRef, useState } from 'react';
import {
  apiRequest, exportTextFile, getDesktopMediaUrl,
  type VideoView, type VideoDetail, type VideoInsight, type TranscriptSegment,
  type Evidence, type Statement,
} from './api';

function seconds(ms: number): string {
  const m = Math.floor(ms / 60000);
  const s = (ms % 60000) / 1000;
  return `${String(m).padStart(2, '0')}:${s.toFixed(1).padStart(4, '0')}`;
}

export default function VideoLibrary({ ready, targetEvidence }: { ready: boolean; targetEvidence: Evidence | null }) {
  const [videos, setVideos] = useState<VideoView[]>([]);
  const [detail, setDetail] = useState<VideoDetail | null>(null);
  const [segments, setSegments] = useState<TranscriptSegment[]>([]);
  const [insight, setInsight] = useState<VideoInsight | null>(null);
  const [focused, setFocused] = useState<number | null>(null);
  const [chosenVersion, setChosenVersion] = useState<string | null>(null);
  const [mediaUrl, setMediaUrl] = useState<string | null>(null);
  const player = useRef<HTMLVideoElement>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!ready) return;
    let active = true;
    void apiRequest<VideoView[]>('/api/videos').then(data => {
      if (active) setVideos(data);
    }).catch(err => { if (active) setError(String(err)); });
    return () => { active = false; };
  }, [ready]);

  const openVideo = async (video: VideoView, destination?: Evidence) => {
    setBusy(true);
    setError('');
    setFocused(null);
    setInsight(null);
    setSegments([]);
    setMediaUrl(null);
    try {
      const data = await apiRequest<VideoDetail>(`/api/videos/${video.id}`);
      setDetail(data);
      try { setMediaUrl(await getDesktopMediaUrl(video.id)); }
      catch { setMediaUrl(null); /* Player is optional; evidence remains available. */ }
      const selectedAnalysis = destination?.analysis_version
        ? data.analyses.find(analysis => analysis.analysis_version === destination.analysis_version)
        : destination?.transcript_version
          ? data.analyses.find(analysis => analysis.transcript_version === destination.transcript_version)
          : data.analyses[0];
      if (destination?.analysis_version && !selectedAnalysis) throw new Error('该证据对应的分析版本已不可用。');
      const version = destination?.transcript_version ?? selectedAnalysis?.transcript_version ?? data.transcript_versions[0];
      setChosenVersion(version ?? null);
      if (version) {
        const subtitles = await apiRequest<TranscriptSegment[]>(`/api/videos/${video.id}/transcripts/${version}`);
        setSegments(subtitles);
        if (destination) setFocused(destination.segment_id);
      }
      if (selectedAnalysis) {
        const result = await apiRequest<VideoInsight>(`/api/videos/${video.id}/analyses/${selectedAnalysis.analysis_version}`);
        setInsight(result);
      }
    } catch (err) { setError(String(err)); }
    finally { setBusy(false); }
  };

  useEffect(() => {
    if (!targetEvidence || !videos.length) return;
    const video = videos.find(item => item.id === targetEvidence.video_id);
    if (video) void openVideo(video, targetEvidence);
  // A new target requests a fresh selection; avoid repeated requests on every render.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [targetEvidence?.video_id, targetEvidence?.segment_id, targetEvidence?.transcript_version, targetEvidence?.analysis_version, videos]);

  useEffect(() => {
    if (focused !== null && segments.length) {
      const segment = segments.find(item => item.segment_id === focused);
      document.getElementById(`evidence-${focused}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      if (segment && player.current) {
        player.current.currentTime = segment.start_ms / 1000;
      }
    }
  }, [focused, segments]);

  const seekTo = (reference: Evidence) => {
    if (!detail || reference.video_id !== detail.video.id) {
      setError('该证据来自另一视频，请在相应视频详情中打开。');
      return;
    }
    setFocused(reference.segment_id);
    if (player.current) player.current.currentTime = reference.start_ms / 1000;
    document.getElementById(`evidence-${reference.segment_id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  };

  const showStatements = (items: Statement[], title: string) => items.length > 0 && <section className="insight-section">
    <h3>{title}</h3>
    {items.map((item, index) => <div className="insight-claim" key={`${title}-${index}`}>
      <div>{item.text}</div>
      <p>表达主体：{item.speaker_role} · {item.creator_identity_verified ? '已核实' : '未核实上传者身份'} · {item.attribution_basis}</p>
      <div className="evidence-links">{item.evidence.map(ref => <button key={`${ref.transcript_version}-${ref.segment_id}`} onClick={() => seekTo(ref)}>证据 {seconds(ref.start_ms)}</button>)}</div>
    </div>)}
  </section>;

  const transcriptVersion = chosenVersion;
  return <section className="library-page">
    <div className="eyebrow">M1 / VERSIONED EVIDENCE</div>
    <h1>视频与字幕</h1>
    <p className="muted">只展示已持久化的真实处理结果或明确标记的测试数据。每条引用可回到原始字幕片段。</p>
    {error && <div className="warning">{error}</div>}
    <div className="library-grid">
      <div className="library-list">
        <div className="section-heading"><h2>视频记录</h2><span>{videos.length} 条</span></div>
        {videos.length === 0 && <p className="muted">暂无视频。可以先用本地视频分析命令验证链路；抖音采集尚待R0真实验收。</p>}
        {videos.map(video => <button key={video.id} className={detail?.video.id === video.id ? 'library-item selected' : 'library-item'} onClick={() => void openVideo(video)}>
          <strong>{video.title || video.platform_video_id}</strong><small>{video.platform} · {video.processing_status}</small>
        </button>)}
      </div>
      <div className="library-detail">
        {!detail && <p className="muted">选择左侧视频，查看字幕、摘要和证据。</p>}
        {busy && <p className="muted">正在读取已保存的结果…</p>}
        {detail && <>
          <h2>{detail.video.title || detail.video.platform_video_id}</h2>
          <p className="muted">作品ID：{detail.video.platform_video_id} · {detail.video.processing_status}</p>
          {detail.video.platform === 'douyin' && <a href={detail.video.source_url} target="_blank" rel="noreferrer">打开原作品</a>}
          {mediaUrl && <video ref={player} className="video-player" controls preload="metadata" src={mediaUrl} aria-label="本地视频证据播放" />}
          {!mediaUrl && <p className="muted">桌面端如已保存媒体，可在这里播放。浏览器预览暂不提供本地视频访问。</p>}
          {insight && <div className="insight-overview">
            <h3>视频摘要 <span>{insight.provenance === 'test_fixture' ? '测试替身结果' : '真实模型结果'}</span></h3>
            <p>{insight.summary}</p>
            <p className="muted">领域：{insight.primary_domain} · 主题：{insight.secondary_topics.join('、') || '未归类'} · 类型：{insight.content_format}</p>
            <div className="evidence-links">{insight.summary_evidence.map(ref => <button key={ref.segment_id} onClick={() => seekTo(ref)}>摘要证据 {seconds(ref.start_ms)}</button>)}</div>
          </div>}
          {insight && showStatements(insight.key_claims, '重要观点')}
          {insight && showStatements(insight.explicitly_stated_preferences, '偏好表达（主体须核实）')}
          <div className="section-heading transcript-heading"><h2>带时间戳的字幕</h2>
            {transcriptVersion && <span><button className="plain" onClick={() => void exportTextFile(`/api/videos/${detail.video.id}/subtitles/${transcriptVersion}/srt`).catch(err => setError(String(err)))}>导出SRT</button>
              <button className="plain" onClick={() => void exportTextFile(`/api/videos/${detail.video.id}/subtitles/${transcriptVersion}/vtt`).catch(err => setError(String(err)))}>导出VTT</button></span>}
          </div>
          {segments.length === 0 ? <p className="muted">暂无有效语音字幕。</p> : segments.map(part => <div key={part.segment_id} id={`evidence-${part.segment_id}`} className={focused === part.segment_id ? 'transcript-line focused' : 'transcript-line'}>
            <span>{seconds(part.start_ms)}–{seconds(part.end_ms)}</span><p>{part.text}</p><small>#{part.segment_id}</small>
          </div>)}
          {transcriptVersion && <p className="version-note">字幕版本：{transcriptVersion}</p>}
        </>}
      </div>
    </div>
  </section>;
}

import React, { useRef, useEffect, useState } from 'react';
import './Dashboard-2.css';

// ── Markdown-lite parser ──
function parseMarkdown(text) {
  if (!text) return '';
  let result = text;
  // Escape HTML
  result = result.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  // Bold
  result = result.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  result = result.replace(/__(.*?)__/g, '<strong>$1</strong>');
  // Italic
  result = result.replace(/\*(.*?)\*/g, '<em>$1</em>');
  result = result.replace(/_(.*?)_/g, '<em>$1</em>');
  // Inline code
  result = result.replace(/`(.*?)`/g, '<code class="d2-inline-code">$1</code>');
  return result;
}

function MarkdownText({ children }) {
  if (!children) return null;
  return <span dangerouslySetInnerHTML={{ __html: parseMarkdown(children) }} />;
}

/** Normalize escaped newlines/tabs from LLM output into real whitespace */
function normalizeNewlines(str) {
  if (!str) return '';
  return str
    .replace(/\\n/g, '\n')
    .replace(/\\t/g, '\t')
    .replace(/\\r/g, '');
}

/** Renders a block of LLM text that may contain fenced code blocks, headings, bullets, etc. */
function renderStructuredText(text) {
  if (!text) return null;
  const raw = normalizeNewlines(typeof text === 'string' ? text : JSON.stringify(text, null, 2));

  // Split into segments: code blocks vs prose
  const segments = [];
  const codeBlockRe = /```(\w*)?\n?([\s\S]*?)```/g;
  let lastIdx = 0;
  let match;
  while ((match = codeBlockRe.exec(raw)) !== null) {
    if (match.index > lastIdx) {
      segments.push({ type: 'prose', content: raw.slice(lastIdx, match.index) });
    }
    segments.push({ type: 'code', lang: match[1] || '', content: match[2] });
    lastIdx = match.index + match[0].length;
  }
  if (lastIdx < raw.length) {
    segments.push({ type: 'prose', content: raw.slice(lastIdx) });
  }

  return segments.map((seg, si) => {
    if (seg.type === 'code') {
      return (
        <div key={si} className="d2-code-block-wrap">
          {seg.lang && <div className="d2-code-lang-label">{seg.lang}</div>}
          <pre className="d2-code-block">{seg.content}</pre>
        </div>
      );
    }
    // Prose: split by newline and render structured
    const lines = seg.content.split('\n').filter(l => l.trim());
    return lines.map((line, li) => {
      const trimmed = line.trim();
      if (trimmed.startsWith('### ')) return <h4 key={`${si}-${li}`} className="d2-sub-heading">{trimmed.replace(/^###\s*/, '').replace(/\*\*/g, '')}</h4>;
      if (trimmed.startsWith('## ')) return <h3 key={`${si}-${li}`} className="d2-section-heading">{trimmed.replace(/^##\s*/, '').replace(/\*\*/g, '')}</h3>;
      if (trimmed.startsWith('# ')) return <h2 key={`${si}-${li}`} className="d2-main-heading">{trimmed.replace(/^#\s*/, '').replace(/\*\*/g, '')}</h2>;
      if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
        return (<div key={`${si}-${li}`} className="d2-bullet-item"><span className="d2-bullet-dot" /><span><MarkdownText>{trimmed.replace(/^[-*]\s/, '')}</MarkdownText></span></div>);
      }
      if (/^\d+\.\s/.test(trimmed)) {
        const num = trimmed.match(/^(\d+)\./)[1];
        return (<div key={`${si}-${li}`} className="d2-numbered-item"><span className="d2-numbered-num">{num}</span><span><MarkdownText>{trimmed.replace(/^\d+\.\s*/, '')}</MarkdownText></span></div>);
      }
      if (/^\*\*.+\*\*:?\s*$/.test(trimmed)) return <h4 key={`${si}-${li}`} className="d2-inline-heading">{trimmed.replace(/\*\*/g, '').replace(/:$/, '')}</h4>;
      return <p key={`${si}-${li}`} className="d2-paragraph"><MarkdownText>{trimmed}</MarkdownText></p>;
    });
  });
}

/** Renders a parameter value, handling nested objects/arrays gracefully */
function renderParamValue(val) {
  if (val === null || val === undefined) return '—';
  if (typeof val === 'string') return val;
  if (typeof val === 'number' || typeof val === 'boolean') return String(val);
  if (Array.isArray(val)) {
    if (val.every(v => typeof v === 'string' || typeof v === 'number')) {
      return val.join(', ');
    }
    return JSON.stringify(val, null, 2);
  }
  if (typeof val === 'object') {
    // Render nested object as sub-params
    return (
      <div className="d2-nested-params">
        {Object.entries(val).map(([k, v], i) => (
          <div key={i} className="d2-nested-param-row">
            <span className="d2-impl-param-key">{k}</span>
            <span className="d2-impl-param-val">{typeof v === 'object' ? JSON.stringify(v) : String(v)}</span>
          </div>
        ))}
      </div>
    );
  }
  return String(val);
}

export default function Dashboard2({ analysisResult, onBack, userProfile }) {
  const [activeTab, setActiveTab] = useState('summary');
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [pdfViewerOpen, setPdfViewerOpen] = useState(false);
  const [pdfViewerPage, setPdfViewerPage] = useState(1);
  const [pdfClickedLabel, setPdfClickedLabel] = useState('');
  const [splitRatio, setSplitRatio] = useState(45);
  const [isDraggingState, setIsDraggingState] = useState(false);
  const contentRef = useRef(null);
  const isDragging = useRef(false);
  const dragStartX = useRef(0);
  const dragStartRatio = useRef(45);

  useEffect(() => {
    if (contentRef.current) contentRef.current.scrollTo(0, 0);
  }, [activeTab]);

  if (!analysisResult) {
    return (
      <div className="d2-page">
        <div className="d2-bg-effects" />
        <div className="d2-empty-state">
          <div className="d2-empty-icon-wrap">
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.2">
              <circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
          </div>
          <h2>No Analysis Data</h2>
          <p>Return and run an analysis first.</p>
          <button className="d2-back-btn" onClick={onBack}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M19 12H5M12 19l-7-7 7-7" /></svg>
            Back
          </button>
        </div>
      </div>
    );
  }

  const {
    summary = '',
    key_insights = [],
    methodology = '',
    results = '',
    limitations = '',
    visual_groups = [],
    chunk_summaries = [],
    total_chunks = 0,
    pages_processed = 0,
    title = '',
    authors = [],
    year = 0,
    venue = '',
    doi = '',
    arxiv_id = '',
    pdf_url = '',
    pdf_hash = '',
    comparison = '',
    compared_analyses = [],
    implementation = {},
    message = '',
    mode = '',
    papers_used = [],
    paper_contributions = [],
    research_gaps = '',
  } = analysisResult;

  const ALL_TABS = [
    { id: 'summary', label: 'Summary', always: true },
    { id: 'insights', label: 'Insights', count: key_insights.length },
    { id: 'methodology', label: 'Methodology', hasData: !!methodology },
    { id: 'results', label: 'Results', hasData: !!results },
    { id: 'limitations', label: 'Limitations', hasData: !!limitations },
    { id: 'visuals', label: 'Visuals', count: visual_groups.length },
    { id: 'comparison', label: 'Comparison', hasData: !!comparison },
    { id: 'implementation', label: 'Implementation', hasData: Object.keys(implementation).length > 0 },
  ];

  const tabs = ALL_TABS.filter(tab =>
    tab.always || (tab.count && tab.count > 0) || tab.hasData
  );

  // ── Render: Summary ──
  const renderSummary = () => {
    const paragraphs = summary.split('\n').filter((p) => p.trim());

    return (
      <div className="d2-summary-content">
        {title && (
          <div className="d2-paper-header-card">
            <h2 className="d2-paper-title-main">{title}</h2>
            <div className="d2-paper-meta-strip">
              {authors.length > 0 && (
                <span className="d2-meta-item">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="8" r="4" /><path d="M4 21v-1a4 4 0 014-4h8a4 4 0 014 4v1" /></svg>
                  {authors.slice(0, 4).join(', ')}{authors.length > 4 && ` +${authors.length - 4} more`}
                </span>
              )}
              {year > 0 && (
                <span className="d2-meta-item">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <rect x="3" y="4" width="18" height="18" rx="2" />
                    <line x1="16" y1="2" x2="16" y2="6" />
                    <line x1="8" y1="2" x2="8" y2="6" />
                    <line x1="3" y1="10" x2="21" y2="10" />
                  </svg>
                  {year}
                </span>
              )}
              {venue && (
                <span className="d2-meta-item">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M4 19.5A2.5 2.5 0 016.5 17H20" />
                    <path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z" />
                  </svg>
                  {venue}
                </span>
              )}
              {doi && (
                <a href={`https://doi.org/${doi}`} target="_blank" rel="noopener noreferrer" className="d2-meta-link">
                  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ marginRight: '4px', display: 'inline-block', verticalAlign: '-1px' }}>
                    <path d="M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71" />
                    <path d="M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71" />
                  </svg>
                  DOI
                </a>
              )}
            </div>

            {pdf_url && (
              <a
                href={pdf_url}
                target="_blank"
                rel="noopener noreferrer"
                className="d2-pdf-open-action"
                onClick={(e) => e.stopPropagation()}
              >
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                  <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
                  <polyline points="14,2 14,8 20,8" />
                  <line x1="16" y1="13" x2="8" y2="13" />
                  <line x1="16" y1="17" x2="8" y2="17" />
                  <polyline points="10,9 9,9 8,9" />
                </svg>
                <span>Open Full PDF</span>
              </a>
            )}

            {pages_processed > 0 && (
              <div className="d2-processing-info">
                Processed {pages_processed} pages → {total_chunks} chunks → unified summary
              </div>
            )}
          </div>
        )}

        <div className="d2-section-card">
          <h3 className="d2-section-heading">Summary</h3>
          {paragraphs.length > 0 ? (
            paragraphs.map((para, i) => {
              const trimmed = para.trim();
              if (trimmed.startsWith('### ')) return <h4 key={i} className="d2-sub-heading">{trimmed.replace(/^###\s*/, '').replace(/\*\*/g, '')}</h4>;
              if (trimmed.startsWith('## ')) return <h3 key={i} className="d2-section-heading">{trimmed.replace(/^##\s*/, '').replace(/\*\*/g, '')}</h3>;
              if (trimmed.startsWith('# ')) return <h2 key={i} className="d2-main-heading">{trimmed.replace(/^#\s*/, '').replace(/\*\*/g, '')}</h2>;
              if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
                return (<div key={i} className="d2-bullet-item"><span className="d2-bullet-dot" /><span><MarkdownText>{trimmed.replace(/^[-*]\s/, '')}</MarkdownText></span></div>);
              }
              if (/^\d+\.\s/.test(trimmed)) {
                const num = trimmed.match(/^(\d+)\./)[1];
                return (<div key={i} className="d2-numbered-item"><span className="d2-numbered-num">{num}</span><span><MarkdownText>{trimmed.replace(/^\d+\.\s*/, '')}</MarkdownText></span></div>);
              }
              if (/^\*\*.+\*\*:?\s*$/.test(trimmed)) return <h4 key={i} className="d2-inline-heading">{trimmed.replace(/\*\*/g, '').replace(/:$/, '')}</h4>;
              return <p key={i} className="d2-paragraph"><MarkdownText>{trimmed}</MarkdownText></p>;
            })
          ) : (
            <div className="d2-no-data">No summary available. The paper may not have been accessible.</div>
          )}
        </div>
      </div>
    );
  };

  // ── Render: Insights ──
  const renderInsights = () => (
    <div className="d2-list-content">
      {key_insights.length === 0 ? <div className="d2-no-data">No insights extracted.</div> :
        key_insights.map((insight, i) => (
          <div key={i} className="d2-insight-card" style={{ animationDelay: `${i * 0.05}s` }}>
            <div className="d2-insight-number">{String(i + 1).padStart(2, '0')}</div>
            <div className="d2-insight-text"><MarkdownText>{typeof insight === 'string' ? insight : JSON.stringify(insight)}</MarkdownText></div>
          </div>
        ))}
    </div>
  );

  // ── Render: Methodology ──
  const renderMethodology = () => {
    const paragraphs = methodology.split('\n').filter(p => p.trim());
    return (
      <div className="d2-summary-content">
        <div className="d2-section-card">
          <h3 className="d2-section-heading">Methodology & Approach</h3>
          {paragraphs.map((para, i) => {
            const trimmed = para.trim();
            if (trimmed.startsWith('### ')) return <h4 key={i} className="d2-sub-heading">{trimmed.replace(/^###\s*/, '').replace(/\*\*/g, '')}</h4>;
            if (trimmed.startsWith('## ')) return <h3 key={i} className="d2-section-heading">{trimmed.replace(/^##\s*/, '').replace(/\*\*/g, '')}</h3>;
            if (trimmed.startsWith('# ')) return <h2 key={i} className="d2-main-heading">{trimmed.replace(/^#\s*/, '').replace(/\*\*/g, '')}</h2>;
            if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
              return (<div key={i} className="d2-bullet-item"><span className="d2-bullet-dot" /><span><MarkdownText>{trimmed.replace(/^[-*]\s/, '')}</MarkdownText></span></div>);
            }
            if (/^\d+\.\s/.test(trimmed)) {
              const num = trimmed.match(/^(\d+)\./)[1];
              return (<div key={i} className="d2-numbered-item"><span className="d2-numbered-num">{num}</span><span><MarkdownText>{trimmed.replace(/^\d+\.\s*/, '')}</MarkdownText></span></div>);
            }
            if (/^\*\*.+\*\*:?\s*$/.test(trimmed)) return <h4 key={i} className="d2-inline-heading">{trimmed.replace(/\*\*/g, '').replace(/:$/, '')}</h4>;
            return <p key={i} className="d2-paragraph"><MarkdownText>{trimmed}</MarkdownText></p>;
          })}
        </div>
      </div>
    );
  };

  // ── Render: Results ──
  const renderResults = () => {
    const paragraphs = results.split('\n').filter(p => p.trim());
    return (
      <div className="d2-summary-content">
        <div className="d2-section-card">
          <h3 className="d2-section-heading">Results & Findings</h3>
          {paragraphs.map((para, i) => {
            const trimmed = para.trim();
            if (trimmed.startsWith('### ')) return <h4 key={i} className="d2-sub-heading">{trimmed.replace(/^###\s*/, '').replace(/\*\*/g, '')}</h4>;
            if (trimmed.startsWith('## ')) return <h3 key={i} className="d2-section-heading">{trimmed.replace(/^##\s*/, '').replace(/\*\*/g, '')}</h3>;
            if (trimmed.startsWith('# ')) return <h2 key={i} className="d2-main-heading">{trimmed.replace(/^#\s*/, '').replace(/\*\*/g, '')}</h2>;
            if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
              return (<div key={i} className="d2-bullet-item"><span className="d2-bullet-dot" /><span><MarkdownText>{trimmed.replace(/^[-*]\s/, '')}</MarkdownText></span></div>);
            }
            if (/^\d+\.\s/.test(trimmed)) {
              const num = trimmed.match(/^(\d+)\./)[1];
              return (<div key={i} className="d2-numbered-item"><span className="d2-numbered-num">{num}</span><span><MarkdownText>{trimmed.replace(/^\d+\.\s*/, '')}</MarkdownText></span></div>);
            }
            if (/^\*\*.+\*\*:?\s*$/.test(trimmed)) return <h4 key={i} className="d2-inline-heading">{trimmed.replace(/\*\*/g, '').replace(/:$/, '')}</h4>;
            return <p key={i} className="d2-paragraph"><MarkdownText>{trimmed}</MarkdownText></p>;
          })}
        </div>
      </div>
    );
  };

  // ── Render: Limitations ──
  const renderLimitations = () => {
    const paragraphs = limitations.split('\n').filter(p => p.trim());
    return (
      <div className="d2-summary-content">
        <div className="d2-section-card">
          <h3 className="d2-section-heading">Limitations & Future Work</h3>
          {paragraphs.map((para, i) => {
            const trimmed = para.trim();
            if (trimmed.startsWith('### ')) return <h4 key={i} className="d2-sub-heading">{trimmed.replace(/^###\s*/, '').replace(/\*\*/g, '')}</h4>;
            if (trimmed.startsWith('## ')) return <h3 key={i} className="d2-section-heading">{trimmed.replace(/^##\s*/, '').replace(/\*\*/g, '')}</h3>;
            if (trimmed.startsWith('# ')) return <h2 key={i} className="d2-main-heading">{trimmed.replace(/^#\s*/, '').replace(/\*\*/g, '')}</h2>;
            if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
              return (<div key={i} className="d2-bullet-item"><span className="d2-bullet-dot" /><span><MarkdownText>{trimmed.replace(/^[-*]\s/, '')}</MarkdownText></span></div>);
            }
            if (/^\d+\.\s/.test(trimmed)) {
              const num = trimmed.match(/^(\d+)\./)[1];
              return (<div key={i} className="d2-numbered-item"><span className="d2-numbered-num">{num}</span><span><MarkdownText>{trimmed.replace(/^\d+\.\s*/, '')}</MarkdownText></span></div>);
            }
            if (/^\*\*.+\*\*:?\s*$/.test(trimmed)) return <h4 key={i} className="d2-inline-heading">{trimmed.replace(/\*\*/g, '').replace(/:$/, '')}</h4>;
            return <p key={i} className="d2-paragraph"><MarkdownText>{trimmed}</MarkdownText></p>;
          })}
        </div>
      </div>
    );
  };

  // ── Handle visual click → open PDF panel ──
  const handleVisualClick = (item) => {
    const pageNum = item.page_number || 1;
    setPdfViewerPage(pageNum);
    setPdfClickedLabel(item.label || item.type || 'Visual');
    setPdfViewerOpen(true);
  };

  const closePdfViewer = () => {
    setPdfViewerOpen(false);
    setPdfClickedLabel('');
  };

  // ── Resizable split drag handlers ──
  const handleDragStart = (e) => {
    e.preventDefault();
    isDragging.current = true;
    setIsDraggingState(true);
    dragStartX.current = e.clientX || (e.touches && e.touches[0].clientX) || 0;
    dragStartRatio.current = splitRatio;
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    document.addEventListener('mousemove', handleDragMove);
    document.addEventListener('mouseup', handleDragEnd);
    document.addEventListener('touchmove', handleDragMove);
    document.addEventListener('touchend', handleDragEnd);
  };

  const handleDragMove = (e) => {
    if (!isDragging.current) return;
    const clientX = e.clientX || (e.touches && e.touches[0].clientX) || 0;
    const sidebarWidth = sidebarCollapsed ? 52 : 258;
    const availableWidth = window.innerWidth - sidebarWidth;
    if (availableWidth <= 0) return;
    const mouseXInSplit = clientX - sidebarWidth;
    const newRatio = Math.min(75, Math.max(25, (mouseXInSplit / availableWidth) * 100));
    setSplitRatio(newRatio);
  };

  const handleDragEnd = () => {
    isDragging.current = false;
    setIsDraggingState(false);
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
    document.removeEventListener('mousemove', handleDragMove);
    document.removeEventListener('mouseup', handleDragEnd);
    document.removeEventListener('touchmove', handleDragMove);
    document.removeEventListener('touchend', handleDragEnd);
  };

  // Visual type icon (SVG-based, no emojis)
  const getVisualTypeInfo = (item, groupType) => {
    const type = (item.type || groupType || '').toLowerCase();

    const FigureIcon = () => (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="3" width="18" height="18" rx="2" />
        <circle cx="8.5" cy="8.5" r="1.5" />
        <polyline points="21,15 16,10 5,21" />
      </svg>
    );

    const TableIcon = () => (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="3" width="18" height="18" rx="2" />
        <line x1="3" y1="9" x2="21" y2="9" />
        <line x1="3" y1="15" x2="21" y2="15" />
        <line x1="9" y1="3" x2="9" y2="21" />
        <line x1="15" y1="3" x2="15" y2="21" />
      </svg>
    );

    const EquationIcon = () => (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M4 6h16" />
        <path d="M4 12h10" />
        <path d="M4 18h7" />
        <path d="M15 15l6 6" />
        <path d="M21 15l-6 6" />
      </svg>
    );

    const DiagramIcon = () => (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="3" width="7" height="7" rx="1" />
        <rect x="14" y="3" width="7" height="7" rx="1" />
        <rect x="3" y="14" width="7" height="7" rx="1" />
        <rect x="14" y="14" width="7" height="7" rx="1" />
        <line x1="10" y1="6.5" x2="14" y2="6.5" />
        <line x1="6.5" y1="10" x2="6.5" y2="14" />
      </svg>
    );

    const AlgorithmIcon = () => (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="16,18 22,12 16,6" />
        <polyline points="8,6 2,12 8,18" />
      </svg>
    );

    if (type.includes('figure') || type.includes('chart') || type.includes('graph') || type.includes('plot'))
      return { Icon: FigureIcon, colorClass: 'figure', typeLabel: 'Figure' };
    if (type.includes('table'))
      return { Icon: TableIcon, colorClass: 'table', typeLabel: 'Table' };
    if (type.includes('equation') || type.includes('formula') || type.includes('math'))
      return { Icon: EquationIcon, colorClass: 'equation', typeLabel: 'Equation' };
    if (type.includes('diagram') || type.includes('architecture'))
      return { Icon: DiagramIcon, colorClass: 'figure', typeLabel: 'Diagram' };
    if (type.includes('algorithm') || type.includes('pseudo'))
      return { Icon: AlgorithmIcon, colorClass: 'equation', typeLabel: 'Algorithm' };
    return { Icon: FigureIcon, colorClass: 'figure', typeLabel: 'Visual' };
  };

  const getGroupTypeIcon = (groupType) => {
    const type = (groupType || '').toLowerCase();
    if (type.includes('figure') || type.includes('chart')) {
      return (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <rect x="3" y="3" width="18" height="18" rx="2" />
          <circle cx="8.5" cy="8.5" r="1.5" />
          <polyline points="21,15 16,10 5,21" />
        </svg>
      );
    }
    if (type.includes('equation') || type.includes('formula')) {
      return (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M4 6h16" />
          <path d="M4 12h10" />
          <path d="M4 18h7" />
          <path d="M15 15l6 6" />
          <path d="M21 15l-6 6" />
        </svg>
      );
    }
    return (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="3" width="18" height="18" rx="2" />
        <line x1="3" y1="9" x2="21" y2="9" />
        <line x1="3" y1="15" x2="21" y2="15" />
        <line x1="9" y1="3" x2="9" y2="21" />
        <line x1="15" y1="3" x2="15" y2="21" />
      </svg>
    );
  };

  // ── Render: Visuals ──
  const renderVisuals = () => (
    <div className="d2-list-content">
      {visual_groups.length > 0 && pdf_url && (
        <div className="d2-visual-instruction-banner">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M9 12l2 2 4-4" />
            <circle cx="12" cy="12" r="10" />
          </svg>
          <span>Click any visual below to open the PDF and jump to the exact page</span>
        </div>
      )}

      {visual_groups.length === 0 ? (
        <div className="d2-no-data">No figures, tables, or equations found. Visuals are extracted from PDF full text.</div>
      ) : visual_groups.map((group, gi) => {
        const totalItems = (group.items || []).length;
        return (
          <div key={gi} className="d2-visual-group-card" style={{ animationDelay: `${gi * 0.08}s` }}>
            <div className="d2-visual-group-header">
              <div className="d2-visual-group-type-icon">
                {getGroupTypeIcon(group.group_type)}
              </div>
              <div className="d2-visual-group-header-info">
                <h4 className="d2-visual-group-label">{group.group_label || group.group_type || 'Visual Group'}</h4>
                <span className="d2-visual-group-count">{totalItems} {totalItems === 1 ? 'item' : 'items'}</span>
              </div>
            </div>
            {group.group_summary && (
              <div className="d2-visual-group-summary-block">
                <div className="d2-visual-group-summary-label">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
                    <polyline points="14,2 14,8 20,8" />
                  </svg>
                  Group Summary
                </div>
                {group.group_summary.split('\n').filter(p => p.trim()).map((para, si) => {
                  const trimmed = para.trim();
                  if (trimmed.startsWith('### ')) return <h4 key={si} className="d2-sub-heading">{trimmed.replace(/^###\s*/, '').replace(/\*\*/g, '')}</h4>;
                  if (trimmed.startsWith('## ')) return <h3 key={si} className="d2-section-heading">{trimmed.replace(/^##\s*/, '').replace(/\*\*/g, '')}</h3>;
                  if (trimmed.startsWith('# ')) return <h2 key={si} className="d2-main-heading">{trimmed.replace(/^#\s*/, '').replace(/\*\*/g, '')}</h2>;
                  if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
                    return (<div key={si} className="d2-bullet-item"><span className="d2-bullet-dot" /><span><MarkdownText>{trimmed.replace(/^[-*]\s/, '')}</MarkdownText></span></div>);
                  }
                  if (/^\d+\.\s/.test(trimmed)) {
                    const num = trimmed.match(/^(\d+)\./)[1];
                    return (<div key={si} className="d2-numbered-item"><span className="d2-numbered-num">{num}</span><span><MarkdownText>{trimmed.replace(/^\d+\.\s*/, '')}</MarkdownText></span></div>);
                  }
                  if (/^\*\*.+\*\*:?\s*$/.test(trimmed)) return <h4 key={si} className="d2-inline-heading">{trimmed.replace(/\*\*/g, '').replace(/:$/, '')}</h4>;
                  return <p key={si} className="d2-paragraph"><MarkdownText>{trimmed}</MarkdownText></p>;
                })}
              </div>
            )}
            <div className="d2-visual-items">
              {(group.items || []).map((item, ii) => {
                const typeInfo = getVisualTypeInfo(item, group.group_type);
                const IconComponent = typeInfo.Icon;
                const isClickable = !!pdf_url && !!item.page_number;
                const isActive = pdfViewerOpen && pdfClickedLabel === (item.label || item.type || 'Visual');
                return (
                  <div
                    key={ii}
                    className={`d2-visual-item-enhanced ${isClickable ? 'clickable' : ''} ${isActive ? 'active-in-pdf' : ''}`}
                    onClick={() => isClickable && handleVisualClick(item)}
                    title={isClickable ? `Click to view in PDF — Page ${item.page_number}` : ''}
                  >
                    <div className="d2-visual-item-left">
                      <div className={`d2-visual-type-icon ${typeInfo.colorClass}`}>
                        <IconComponent />
                      </div>
                    </div>
                    <div className="d2-visual-item-body">
                      <div className="d2-visual-item-header-row">
                        <span className="d2-visual-item-label-enhanced">{item.label || item.type || 'Item'}</span>
                        <span className={`d2-visual-item-type-badge ${typeInfo.colorClass}`}>{typeInfo.typeLabel}</span>
                      </div>

                      {item.explanation && (
                        <div className="d2-visual-item-explanation">
                          {item.explanation.split('\n').filter(p => p.trim()).map((para, ei) => {
                            const trimmed = para.trim();
                            if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
                              return (<div key={ei} className="d2-bullet-item"><span className="d2-bullet-dot" /><span><MarkdownText>{trimmed.replace(/^[-*]\s/, '')}</MarkdownText></span></div>);
                            }
                            if (/^\d+\.\s/.test(trimmed)) {
                              const num = trimmed.match(/^(\d+)\./)[1];
                              return (<div key={ei} className="d2-numbered-item"><span className="d2-numbered-num">{num}</span><span><MarkdownText>{trimmed.replace(/^\d+\.\s*/, '')}</MarkdownText></span></div>);
                            }
                            if (/^\*\*.+\*\*:?\s*$/.test(trimmed)) return <h4 key={ei} className="d2-inline-heading">{trimmed.replace(/\*\*/g, '').replace(/:$/, '')}</h4>;
                            return <p key={ei} className="d2-paragraph" style={{ margin: '4px 0', fontSize: '13.5px', lineHeight: '1.7' }}><MarkdownText>{trimmed}</MarkdownText></p>;
                          })}
                        </div>
                      )}

                      {item.caption && !item.explanation && (
                        <div className="d2-visual-item-caption">
                          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" />
                          </svg>
                          <span>{item.caption}</span>
                        </div>
                      )}

                      {item.caption && item.explanation && (
                        <div className="d2-visual-item-caption-sub">
                          <em>Caption</em>{item.caption}
                        </div>
                      )}

                      <div className="d2-visual-item-footer">
                        {item.page_number && (
                          <span className={`d2-visual-page-tag-enhanced ${isClickable ? 'clickable' : ''}`}>
                            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                              <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
                              <polyline points="14,2 14,8 20,8" />
                            </svg>
                            Page {item.page_number}
                          </span>
                        )}
                        {isClickable && (
                          <span className="d2-visual-click-hint">
                            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                              <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6" />
                              <polyline points="15,3 21,3 21,9" />
                              <line x1="10" y1="14" x2="21" y2="3" />
                            </svg>
                            View in PDF
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );

  // ── Render: Comparison ──
  const renderComparison = () => {
    const comparisonParagraphs = (comparison || '').split('\n').filter(p => p.trim());
    const hasStructuredData = papers_used.length > 0 || paper_contributions.length > 0;

    return (
      <div className="d2-summary-content">
        {papers_used.length > 0 && (
          <div className="d2-section-card">
            <h3 className="d2-section-heading">Papers Used</h3>
            <div className="d2-compare-papers-list">
              {papers_used.map((p, i) => (
                <div key={i} className="d2-compare-paper-item" style={{ animationDelay: `${i * 0.05}s` }}>
                  <span className="d2-compare-paper-num">{String(i + 1).padStart(2, '0')}</span>
                  <div className="d2-compare-paper-info">
                    <span className="d2-compare-paper-title">{p.title || 'Untitled'}</span>
                    <div className="d2-compare-paper-meta">
                      {p.year > 0 && (
                        <span>
                          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <rect x="3" y="4" width="18" height="18" rx="2" />
                            <line x1="16" y1="2" x2="16" y2="6" />
                            <line x1="8" y1="2" x2="8" y2="6" />
                            <line x1="3" y1="10" x2="21" y2="10" />
                          </svg>
                          {p.year}
                        </span>
                      )}
                      {p.venue && (
                        <span>
                          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M4 19.5A2.5 2.5 0 016.5 17H20" />
                            <path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z" />
                          </svg>
                          {p.venue}
                        </span>
                      )}
                      {p.authors && p.authors.length > 0 && (
                        <span>
                          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <circle cx="12" cy="8" r="4" />
                            <path d="M4 21v-1a4 4 0 014-4h8a4 4 0 014 4v1" />
                          </svg>
                          {p.authors.slice(0, 2).join(', ')}{p.authors.length > 2 ? ` +${p.authors.length - 2}` : ''}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {paper_contributions.length > 0 && (
          <div className="d2-section-card">
            <h3 className="d2-section-heading">Key Contributions</h3>
            {paper_contributions.map((pc, i) => (
              <div key={i} className="d2-contribution-item" style={{ animationDelay: `${i * 0.05}s` }}>
                <div className="d2-contribution-title">
                  <span className="d2-contribution-num">{String(i + 1).padStart(2, '0')}</span>
                  <strong>{pc.paper_title || `Paper ${i + 1}`}</strong>
                </div>
                <p className="d2-paragraph" style={{ paddingLeft: '44px' }}>
                  <MarkdownText>{pc.contribution || 'No contribution summary available.'}</MarkdownText>
                </p>
              </div>
            ))}
          </div>
        )}

        {comparisonParagraphs.length > 0 && (
          <div className="d2-section-card">
            <h3 className="d2-section-heading">Detailed Comparison</h3>
            {comparisonParagraphs.map((para, i) => {
              const trimmed = para.trim();
              if (trimmed.startsWith('### ')) return <h4 key={i} className="d2-sub-heading">{trimmed.replace(/^###\s*/, '').replace(/\*\*/g, '')}</h4>;
              if (trimmed.startsWith('## ')) return <h3 key={i} className="d2-section-heading">{trimmed.replace(/^##\s*/, '').replace(/\*\*/g, '')}</h3>;
              if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
                return (<div key={i} className="d2-bullet-item"><span className="d2-bullet-dot" /><span><MarkdownText>{trimmed.replace(/^[-*]\s/, '')}</MarkdownText></span></div>);
              }
              return <p key={i} className="d2-paragraph"><MarkdownText>{trimmed}</MarkdownText></p>;
            })}
          </div>
        )}

        {research_gaps && (
          <div className="d2-section-card d2-research-gaps-card">
            <h3 className="d2-section-heading">Research Gaps & Future Directions</h3>
            {research_gaps.split('\n').filter(p => p.trim()).map((para, i) => {
              const trimmed = para.trim();
              if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
                return (<div key={i} className="d2-bullet-item"><span className="d2-bullet-dot" /><span><MarkdownText>{trimmed.replace(/^[-*]\s/, '')}</MarkdownText></span></div>);
              }
              return <p key={i} className="d2-paragraph"><MarkdownText>{trimmed}</MarkdownText></p>;
            })}
          </div>
        )}

        {!hasStructuredData && comparisonParagraphs.length === 0 && (
          <div className="d2-no-data">No comparison data available. Select at least 2 papers to compare.</div>
        )}
      </div>
    );
  };

  // ── Render: Implementation ──
  const renderImplementation = () => {
    const impl = implementation;
    const hasData = impl && (impl.topic_definition || impl.paper_extractions?.length || impl.generated_code || impl.code || impl.explanation);

    if (!hasData) {
      return <div className="d2-no-data">No implementation guide available. Select "Implement Topic" mode with Student or Teacher persona.</div>;
    }

    const paperExtractions = impl.paper_extractions || [];
    const allParams = impl.all_parameters || impl.parameters || {};
    const generatedCode = impl.generated_code || impl.code || '';
    const topicDef = impl.topic_definition || impl.explanation || '';

    // Normalize escaped newlines in the generated code
    const normalizedCode = normalizeNewlines(generatedCode);

    // Strip fenced code block wrappers from generated code so it renders cleanly
    const cleanCode = typeof normalizedCode === 'string'
      ? normalizedCode.replace(/^```\w*\n?/, '').replace(/\n?```$/, '').trim()
      : normalizedCode;

    // Detect language from fenced block header if present
    const langMatch = typeof generatedCode === 'string' && generatedCode.match(/^```(\w+)/);
    const codeLang = langMatch ? langMatch[1] : 'python';

    return (
      <div className="d2-summary-content">
        {topicDef && (
          <div className="d2-section-card d2-topic-def-card">
            <h3 className="d2-section-heading">What is {title || 'this topic'}?</h3>
            <div className="d2-topic-definition">{renderStructuredText(topicDef)}</div>
          </div>
        )}

        {paperExtractions.length > 0 && (
          <div className="d2-section-card">
            <h3 className="d2-section-heading">Code & Implementation from Papers ({paperExtractions.length} papers)</h3>
            {paperExtractions.map((pe, pi) => (
              <div key={pi} className="d2-paper-extraction" style={{ animationDelay: `${pi * 0.06}s` }}>
                <div className="d2-paper-extraction-header">
                  <span className="d2-paper-extraction-num">{String(pi + 1).padStart(2, '0')}</span>
                  <span className="d2-paper-extraction-title">{pe.paper_title || `Paper ${pi + 1}`}</span>
                </div>

                {pe.code_snippets && pe.code_snippets.length > 0 && (
                  <div className="d2-code-snippets">
                    {pe.code_snippets.map((cs, ci) => {
                      const isClickable = !!pe.pdf_url && !!cs.page_number;
                      const snippetCode = normalizeNewlines(typeof cs.code === 'string'
                        ? cs.code.replace(/^```\w*\n?/, '').replace(/\n?```$/, '')
                        : cs.code);
                      return (
                        <div
                          key={ci}
                          className={`d2-code-snippet-card ${isClickable ? 'clickable' : ''}`}
                          onClick={() => isClickable && handleVisualClick({ page_number: cs.page_number, label: `Code from ${pe.paper_title}` })}
                          title={isClickable ? `Click to view in PDF — Page ${cs.page_number}` : ''}
                        >
                          {cs.description && <div className="d2-code-snippet-desc">{cs.description}</div>}
                          <pre className="d2-code-block"><code>{snippetCode}</code></pre>
                          <div className="d2-code-snippet-footer">
                            {cs.page_number && (
                              <span className="d2-visual-page-tag-enhanced clickable">
                                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                  <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
                                  <polyline points="14,2 14,8 20,8" />
                                </svg>
                                Page {cs.page_number}
                              </span>
                            )}
                            {isClickable && (
                              <span className="d2-visual-click-hint">
                                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                  <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6" />
                                  <polyline points="15,3 21,3 21,9" />
                                  <line x1="10" y1="14" x2="21" y2="3" />
                                </svg>
                                View in PDF
                              </span>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}

                {pe.how_to_implement && (
                  <div className="d2-impl-how-to">
                    {renderStructuredText(pe.how_to_implement)}
                  </div>
                )}

                {pe.key_techniques && pe.key_techniques.length > 0 && (
                  <div className="d2-impl-techniques">
                    {pe.key_techniques.map((tech, ti) => (
                      <span key={ti} className="d2-impl-dep-tag">{tech}</span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {Object.keys(allParams).length > 0 && (
          <div className="d2-section-card">
            <h3 className="d2-section-heading">Parameters from Literature</h3>
            <div className="d2-impl-params-grid">
              {Object.entries(allParams).map(([key, val], i) => (
                <div key={i} className="d2-impl-param">
                  <span className="d2-impl-param-key">{key}</span>
                  <span className="d2-impl-param-val">{renderParamValue(val)}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {cleanCode && (
          <div className="d2-section-card">
            <h3 className="d2-section-heading">Generated Implementation Code</h3>
            <p className="d2-paragraph" style={{ marginBottom: '12px', opacity: 0.7 }}>Auto-generated based on techniques and parameters extracted from {paperExtractions.length} papers.</p>
            <div className="d2-code-block-wrap">
              <div className="d2-code-lang-label">{codeLang}</div>
              <pre className="d2-code-block d2-generated-code"><code>{cleanCode}</code></pre>
            </div>
          </div>
        )}

        {!paperExtractions.length && impl.hyperparameters && Object.keys(impl.hyperparameters).length > 0 && (
          <div className="d2-section-card">
            <h3 className="d2-section-heading">Hyperparameters</h3>
            <div className="d2-impl-params-grid">
              {Object.entries(impl.hyperparameters).map(([key, val], i) => (
                <div key={i} className="d2-impl-param">
                  <span className="d2-impl-param-key">{key}</span>
                  <span className="d2-impl-param-val">{renderParamValue(val)}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {impl.tuning_guide && (
          <div className="d2-section-card">
            <h3 className="d2-section-heading">Tuning Guide</h3>
            {renderStructuredText(typeof impl.tuning_guide === 'string' ? impl.tuning_guide : JSON.stringify(impl.tuning_guide, null, 2))}
          </div>
        )}

        {impl.dependencies?.length > 0 && (
          <div className="d2-section-card">
            <h3 className="d2-section-heading">Dependencies</h3>
            <div className="d2-impl-deps">
              {impl.dependencies.map((dep, i) => (
                <span key={i} className="d2-impl-dep-tag">{dep}</span>
              ))}
            </div>
          </div>
        )}

        {impl.how_to_run && (
          <div className="d2-section-card">
            <h3 className="d2-section-heading">How to Run</h3>
            <pre className="d2-code-block">{typeof impl.how_to_run === 'string' ? impl.how_to_run : JSON.stringify(impl.how_to_run, null, 2)}</pre>
          </div>
        )}
      </div>
    );
  };

  const modeLabel = mode === 'compare' ? 'Comparison' : mode === 'implement' ? 'Implementation' : pages_processed > 0 ? 'Full Text Analysis' : 'Summary';
  const pdfEmbedUrl = pdf_url ? `${pdf_url}#page=${pdfViewerPage}` : '';

  // ── Main content (shared between split and non-split modes) ──
  const renderMainContent = () => (
    <>
      <header className="d2-topbar">
        <div className="d2-topbar-left">
          <h1 className="d2-topbar-title">Results</h1>
          <div className="d2-topbar-mode">{modeLabel}</div>
        </div>
        <div className="d2-topbar-right">
          <div className="d2-status-badge"><span className="d2-status-dot" /> Complete</div>
        </div>
      </header>

      <div className="d2-tabs">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            className={`d2-tab ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => {
              setActiveTab(tab.id);
              if (tab.id !== 'visuals' && tab.id !== 'implementation') closePdfViewer();
            }}
          >
            <span className="d2-tab-label">{tab.label}</span>
            {tab.count != null && tab.count > 0 && <span className="d2-tab-count">{tab.count}</span>}
          </button>
        ))}
      </div>

      <div className="d2-content" ref={contentRef}>
        <div className="d2-content-inner">
          {activeTab === 'summary' && renderSummary()}
          {activeTab === 'insights' && renderInsights()}
          {activeTab === 'methodology' && renderMethodology()}
          {activeTab === 'results' && renderResults()}
          {activeTab === 'limitations' && renderLimitations()}
          {activeTab === 'visuals' && renderVisuals()}
          {activeTab === 'comparison' && renderComparison()}
          {activeTab === 'implementation' && renderImplementation()}
        </div>
      </div>
    </>
  );

  // ── PDF Panel (shared) ──
  const renderPdfPanel = () => (
    <div className="d2-pdf-panel">
      <div className="d2-pdf-panel-header">
        <div className="d2-pdf-panel-title-area">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
            <polyline points="14,2 14,8 20,8" />
          </svg>
          <div className="d2-pdf-panel-title-wrap">
            <span className="d2-pdf-panel-title">PDF Viewer</span>
            <span className="d2-pdf-panel-subtitle">{pdfClickedLabel} — Page {pdfViewerPage}</span>
          </div>
        </div>
        <div className="d2-pdf-panel-controls">
          <button
            className="d2-pdf-page-btn"
            onClick={() => setPdfViewerPage(Math.max(1, pdfViewerPage - 1))}
            disabled={pdfViewerPage <= 1}
            title="Previous page"
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M15 18l-6-6 6-6" /></svg>
          </button>
          <span className="d2-pdf-page-indicator">Page {pdfViewerPage}</span>
          <button
            className="d2-pdf-page-btn"
            onClick={() => setPdfViewerPage(pdfViewerPage + 1)}
            title="Next page"
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M9 18l6-6-6-6" /></svg>
          </button>
          <a
            href={pdf_url}
            target="_blank"
            rel="noopener noreferrer"
            className="d2-pdf-open-external"
            title="Open PDF in new tab"
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6" />
              <polyline points="15,3 21,3 21,9" />
              <line x1="10" y1="14" x2="21" y2="3" />
            </svg>
          </a>
          <button className="d2-pdf-close-btn" onClick={closePdfViewer} title="Close PDF viewer">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
      </div>
      <div className="d2-pdf-panel-body">
        <iframe
          key={pdfEmbedUrl}
          src={pdfEmbedUrl}
          className="d2-pdf-iframe"
          title="PDF Viewer"
        />
      </div>
    </div>
  );

  const splitActive = pdfViewerOpen && pdf_url;

  return (
    <div className={`d2-page ${splitActive ? 'pdf-split-active' : ''}`}>
      <div className="d2-bg-effects" />

      {/* ═══ Sidebar ═══ */}
      <aside className={`d2-sidebar ${sidebarCollapsed ? 'collapsed' : ''}`}>
        <div className="d2-sidebar-header">
          <div className="d2-sidebar-logo">
            <div className="d2-logo-mark">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
                <path d="M2 16.5L12 22L22 16.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" opacity="0.35" />
                <path d="M2 12L12 17.5L22 12" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" opacity="0.6" />
                <path d="M12 2L2 7.5L12 13L22 7.5L12 2Z" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" fill="rgba(138,103,38,0.1)" />
              </svg>
            </div>
            {!sidebarCollapsed && <span className="d2-sidebar-logo-text">CogniView.AI</span>}
          </div>
          <button className="d2-sidebar-toggle" onClick={() => setSidebarCollapsed(!sidebarCollapsed)}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              {sidebarCollapsed ? <path d="M9 18l6-6-6-6" /> : <path d="M15 18l-6-6 6-6" />}
            </svg>
          </button>
        </div>

        {!sidebarCollapsed && (
          <>
            <button className="d2-sidebar-new-btn" onClick={onBack}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" /></svg>
              New Analysis
            </button>

            {title && (
              <div className="d2-sidebar-paper-info">
                <div className="d2-sidebar-section-label">Current Paper</div>
                <div className="d2-sidebar-paper-title">{title}</div>
                {year > 0 && <div className="d2-sidebar-paper-year">{year}{venue ? ` • ${venue}` : ''}</div>}
                {pages_processed > 0 && (
                  <div className="d2-sidebar-paper-stats">
                    <span>{pages_processed} pages</span>
                    <span>{total_chunks} chunks</span>
                  </div>
                )}
              </div>
            )}

            <div className="d2-sidebar-section-label">Chat History</div>
            <div className="d2-chat-history-empty">
              <div className="d2-chat-empty-icon">
                <svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1">
                  <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" opacity="0.4" />
                  <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" strokeWidth="1.5" />
                </svg>
              </div>
              <span className="d2-chat-empty-badge">Coming Soon</span>
              <span className="d2-chat-empty-title">No conversations yet</span>
              <span className="d2-chat-empty-desc">Your past analyses will appear here.</span>
              <div className="d2-chat-skeleton-list">
                {[1, 2, 3].map((_, i) => (
                  <div key={i} className="d2-chat-skeleton-item" style={{ opacity: 1 - i * 0.25 }}>
                    <div className="d2-chat-skeleton-dot" />
                    <div className="d2-chat-skeleton-lines"><div className="d2-chat-skeleton-line long" /><div className="d2-chat-skeleton-line short" /></div>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}

        {sidebarCollapsed && (
          <div className="d2-sidebar-collapsed-icons">
            <button className="d2-sidebar-collapsed-btn" onClick={onBack} title="New Analysis">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" /></svg>
            </button>
            <button className="d2-sidebar-collapsed-btn disabled" title="Chat History — Coming Soon">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" /></svg>
            </button>
          </div>
        )}

        <div className="d2-sidebar-footer">
          <button className={sidebarCollapsed ? 'd2-sidebar-back-icon' : 'd2-sidebar-back-btn'} onClick={onBack}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M19 12H5M12 19l-7-7 7-7" /></svg>
            {!sidebarCollapsed && 'Back to Dashboard'}
          </button>
        </div>
      </aside>

      {/* ═══ Split Container (when PDF is open) ═══ */}
      {splitActive ? (
        <div
          className={`d2-split-container ${sidebarCollapsed ? 'sidebar-collapsed' : 'sidebar-expanded'} ${isDraggingState ? 'is-dragging' : ''}`}
        >
          {/* Main content - constrained width */}
          <div
            className="d2-main pdf-panel-open"
            style={{ width: `${splitRatio}%`, flex: `0 0 ${splitRatio}%` }}
          >
            {renderMainContent()}
          </div>

          {/* Drag Handle */}
          <div
            className={`d2-split-drag-handle ${isDraggingState ? 'dragging' : ''}`}
            onMouseDown={handleDragStart}
            onTouchStart={handleDragStart}
            title="Drag to resize panels"
          >
            <div className="d2-split-drag-indicator">
              <span /><span /><span /><span /><span />
            </div>
          </div>

          {/* PDF Panel */}
          {renderPdfPanel()}
        </div>
      ) : (
        /* Normal main (no PDF) */
        <div className={`d2-main ${sidebarCollapsed ? 'sidebar-collapsed' : ''}`}>
          {renderMainContent()}
        </div>
      )}
    </div>
  );
}
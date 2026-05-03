import React, { useState, useRef, useEffect } from 'react';
import './PaperDetail.css';

const API_BASE = 'http://localhost:8000';

export default function PaperDetail({ analysis, onBack }) {
    const [activeTab, setActiveTab] = useState('summary');
    const [pdfPage, setPdfPage] = useState(1);
    const pdfIframeRef = useRef(null);

    const hasPdf = analysis?.pdf_hash;
    const pdfUrl = hasPdf ? `${API_BASE}/pdf/${analysis.pdf_hash}#page=${pdfPage}` : null;

    // Navigate PDF to a specific page
    const navigateToPage = (page) => {
        setPdfPage(page);
        if (pdfIframeRef.current) {
            pdfIframeRef.current.src = `${API_BASE}/pdf/${analysis.pdf_hash}#page=${page}`;
        }
    };

    const tabs = [
        { id: 'summary', label: 'Summary' },
        { id: 'visuals', label: `Figures & Visuals (${countVisualItems(analysis?.visual_groups || [])})` },
        { id: 'methodology', label: 'Methodology' },
        { id: 'results', label: 'Results' },
        { id: 'insights', label: 'Key Insights' },
    ];

    return (
        <div className="paper-detail">
            {/* ── Left: Analysis Panel ── */}
            <div className="analysis-panel">
                {/* Back button + Title */}
                <div style={{ marginBottom: '1.5rem' }}>
                    <button
                        onClick={onBack}
                        style={{
                            background: 'none', border: 'none', color: 'var(--accent)',
                            cursor: 'pointer', fontSize: '0.9rem', padding: 0,
                            fontFamily: 'var(--font-body)', marginBottom: '0.75rem',
                            display: 'flex', alignItems: 'center', gap: '0.4rem',
                        }}
                    >
                        ← Back to papers
                    </button>

                    <h1 style={{ fontSize: '1.8rem', lineHeight: 1.3, marginBottom: '0.4rem' }}>
                        {analysis?.title || 'Paper Analysis'}
                    </h1>

                    {analysis?.authors?.length > 0 && (
                        <p style={{ color: 'var(--text-secondary)', fontFamily: 'var(--font-heading)', fontStyle: 'italic', fontSize: '1rem' }}>
                            {analysis.authors.join(', ')}
                        </p>
                    )}

                    <div style={{ display: 'flex', gap: '0.75rem', marginTop: '0.5rem', flexWrap: 'wrap' }}>
                        {analysis?.year && <span className="meta-tag">{analysis.year}</span>}
                        {analysis?.venue && <span className="meta-tag">{analysis.venue}</span>}
                        {analysis?.doi && <span className="meta-tag">DOI: {analysis.doi}</span>}
                        {analysis?.pages_processed > 0 && (
                            <span className="meta-tag">{analysis.pages_processed} pages processed</span>
                        )}
                    </div>
                </div>

                {/* Chunk progress */}
                {analysis?.chunk_summaries?.length > 0 && (
                    <div className="chunk-progress">
                        {analysis.chunk_summaries.map((cs, i) => (
                            <div
                                key={i}
                                className={`chunk-dot active ${cs.importance === 'high' ? 'high' : ''}`}
                                title={`Pages ${cs.page_range}: ${cs.section_type}`}
                            />
                        ))}
                    </div>
                )}

                {/* Tabs */}
                <div className="section-tabs">
                    {tabs.map(tab => (
                        <button
                            key={tab.id}
                            className={`section-tab ${activeTab === tab.id ? 'active' : ''}`}
                            onClick={() => setActiveTab(tab.id)}
                        >
                            {tab.label}
                        </button>
                    ))}
                </div>

                {/* Tab Content */}
                {activeTab === 'summary' && (
                    <div className="analysis-section">
                        <p style={{ color: 'var(--text-secondary)', lineHeight: 1.75, fontSize: '0.98rem' }}>
                            {analysis?.summary || 'No summary available.'}
                        </p>
                        {analysis?.limitations && (
                            <>
                                <h3 style={{ marginTop: '1.5rem' }}>Limitations</h3>
                                <p>{analysis.limitations}</p>
                            </>
                        )}
                    </div>
                )}

                {activeTab === 'visuals' && (
                    <VisualGroups
                        visualGroups={analysis?.visual_groups || []}
                        onNavigate={navigateToPage}
                        hasPdf={hasPdf}
                    />
                )}

                {activeTab === 'methodology' && (
                    <div className="analysis-section">
                        <p>{analysis?.methodology || 'No methodology section extracted.'}</p>
                    </div>
                )}

                {activeTab === 'results' && (
                    <div className="analysis-section">
                        <p>{analysis?.results || 'No results section extracted.'}</p>
                    </div>
                )}

                {activeTab === 'insights' && (
                    <div className="analysis-section">
                        <ul className="insight-list">
                            {(analysis?.key_insights || []).map((insight, i) => (
                                <li key={i} className="insight-item">{insight}</li>
                            ))}
                        </ul>
                    </div>
                )}
            </div>

            {/* ── Right: PDF Panel ── */}
            <div className="pdf-panel">
                <div className="pdf-panel-header">
                    <span>📄 PDF Viewer</span>
                    {hasPdf && (
                        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                            Page {pdfPage}
                        </span>
                    )}
                </div>
                {hasPdf ? (
                    <iframe
                        ref={pdfIframeRef}
                        className="pdf-iframe"
                        src={pdfUrl}
                        title="PDF Viewer"
                    />
                ) : (
                    <div className="pdf-placeholder">
                        <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                            <polyline points="14 2 14 8 20 8" />
                            <line x1="16" y1="13" x2="8" y2="13" />
                            <line x1="16" y1="17" x2="8" y2="17" />
                            <polyline points="10 9 9 9 8 9" />
                        </svg>
                        <p>PDF not available for this paper</p>
                    </div>
                )}
            </div>
        </div>
    );
}

function VisualGroups({ visualGroups, onNavigate, hasPdf }) {
    if (!visualGroups || visualGroups.length === 0) {
        return (
            <div className="analysis-section">
                <p style={{ color: 'var(--text-muted)' }}>No visual elements extracted from this paper.</p>
            </div>
        );
    }

    return (
        <div className="visual-groups-container">
            {visualGroups.map((group, gi) => (
                <div key={gi} className="visual-group">
                    <div className="visual-group-header">
                        <div className={`group-icon ${getGroupType(group)}`}>
                            {getGroupIcon(group)}
                        </div>
                        <h4>{group.group_label || 'Visual Elements'}</h4>
                    </div>

                    {group.group_summary && (
                        <p className="visual-group-summary">{group.group_summary}</p>
                    )}

                    <div className="visual-items-list">
                        {(group.items || []).map((item, ii) => (
                            <a
                                key={ii}
                                className="visual-item-link"
                                onClick={(e) => {
                                    e.preventDefault();
                                    if (hasPdf && item.page_number) {
                                        onNavigate(item.page_number);
                                    }
                                }}
                                style={{ cursor: hasPdf && item.page_number ? 'pointer' : 'default' }}
                            >
                                <span className={`item-type ${item.element_type || 'figure'}`}>
                                    {item.element_type || 'fig'}
                                </span>
                                <span className="item-label">
                                    {item.label || `Item ${ii + 1}`}
                                    {item.description && (
                                        <span style={{ display: 'block', fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '0.15rem' }}>
                                            {item.description.substring(0, 100)}{item.description.length > 100 ? '…' : ''}
                                        </span>
                                    )}
                                </span>
                                {item.page_number && (
                                    <span className="item-page">p.{item.page_number}</span>
                                )}
                                {hasPdf && item.page_number && (
                                    <span className="navigate-arrow">→</span>
                                )}
                            </a>
                        ))}
                    </div>
                </div>
            ))}
        </div>
    );
}

function countVisualItems(groups) {
    return (groups || []).reduce((sum, g) => sum + (g.items?.length || 0), 0);
}

function getGroupType(group) {
    const items = group.items || [];
    if (items.some(i => i.element_type === 'equation')) return 'equation';
    if (items.some(i => i.element_type === 'graph')) return 'graph';
    return 'figure';
}

function getGroupIcon(group) {
    const type = getGroupType(group);
    if (type === 'equation') return '∑';
    if (type === 'graph') return '📊';
    return '🖼';
}
// Dashboard.jsx — CogniView.AI  |  Forest × Parchment Edition
import React, { useState, useRef, useEffect, useCallback } from 'react';
import Dashboard2 from './Dashboard-2';
import './Dashboard.css';

const API_BASE_URL = 'http://localhost:8000';

/* ═══════════════════════════════════════════════════════════
   MAPPING: Frontend UI labels → Backend API enum values
   ═══════════════════════════════════════════════════════════ */

const DEPTH_TO_API = { Skim: 'Skim', Understand: 'Understand', 'Deep Dive': 'DeepDive' };
const TIME_BUDGET_TO_API = { quick: 'Quick', focused: 'Focused', deep: 'DeepResearch' };
const GOAL_TO_API = { learn: 'Learn', teach: 'Teach', build: 'Build', write: 'Publish' };
const FORMAT_TO_API = { bullets: 'Bullet', structured: 'Structured', report: 'Report' };

/* ── Persona-based defaults ── */
const PERSONA_DEFAULTS = {
    Learner: { knowledge_level: 'Beginner', goal: 'Learn', output_format: 'Bullet' },
    Educator: { knowledge_level: 'Intermediate', goal: 'Teach', output_format: 'Structured' },
    Researcher: { knowledge_level: 'Advanced', goal: 'Publish', output_format: 'Report' },
};

/* ═══════════════════════════════════════════════════════════
   CONTEXT MODEL
   ═══════════════════════════════════════════════════════════ */

const PERSONAS = [
    { id: 'Learner', label: 'Student / Curious Beginner', icon: 'learner' },
    { id: 'Educator', label: 'Teaching / Explaining', icon: 'educator' },
    { id: 'Researcher', label: 'Academic / Deep Analysis', icon: 'researcher' },
];

const TIME_BUDGETS = [
    { id: 'quick', label: 'Quick Overview', desc: '~5 min read' },
    { id: 'focused', label: 'Focused Study', desc: '15-30 min read' },
    { id: 'deep', label: 'Deep Research', desc: 'Long read' },
];

const DEPTH_STOPS = [
    { value: 0, label: 'Quick surface-level overview' },
    { value: 50, label: 'Balanced depth with key details' },
    { value: 100, label: 'Deep Dive — thorough comprehensive analysis' },
];

const BROAD_FIELDS = [
    { value: '', label: 'Auto-detect / Interdisciplinary' },
    { value: 'Computer Science and Artificial Intelligence', label: 'Computer Science & AI' },
    { value: 'Electrical and Electronics', label: 'Electrical & Electronics' },
    { value: 'Engineering and Technology', label: 'Engineering & Technology' },
    { value: 'Mathematics and Statistics', label: 'Mathematics & Statistics' },
    { value: 'Physics and Astronomy', label: 'Physics & Astronomy' },
    { value: 'Chemistry', label: 'Chemistry' },
    { value: 'Biology and Life Sciences', label: 'Biology & Life Sciences' },
    { value: 'Medicine and Health Sciences', label: 'Medicine & Health Sciences' },
    { value: 'Neuroscience', label: 'Neuroscience' },
    { value: 'Psychology', label: 'Psychology' },
    { value: 'Social Sciences', label: 'Social Sciences' },
    { value: 'Economics and Business', label: 'Economics & Business' },
    { value: 'Education', label: 'Education' },
    { value: 'Environmental and Earth Sciences', label: 'Environmental & Earth Sciences' },
    { value: 'Agriculture and Food Science', label: 'Agriculture & Food Science' },
    { value: 'Law and Public Policy', label: 'Law & Public Policy' },
    { value: 'Arts and Humanities', label: 'Arts & Humanities' },
    { value: 'Linguistics and Communication', label: 'Linguistics & Communication' },
    { value: 'Materials Science', label: 'Materials Science' },
];

/* ═══════════════════════════════════════════════════════════
   SVG ICONS
   ═══════════════════════════════════════════════════════════ */

const LearnerIcon = () => (
    <svg viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg" className="role-svg-icon">
        <path d="M20 6L4 14L20 22L36 14L20 6Z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
        <path d="M8 17V27L20 33L32 27V17" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M36 14V26" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
);

const EducatorIcon = () => (
    <svg viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg" className="role-svg-icon">
        <rect x="6" y="8" width="28" height="20" rx="2" stroke="currentColor" strokeWidth="2" />
        <path d="M14 32H26" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        <path d="M20 28V32" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        <path d="M12 14H20" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        <path d="M12 18H28" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        <path d="M12 22H24" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
);

const ResearcherIcon = () => (
    <svg viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg" className="role-svg-icon">
        <circle cx="17" cy="17" r="9" stroke="currentColor" strokeWidth="2" />
        <path d="M24 24L34 34" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
        <path d="M14 14L20 20" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        <path d="M14 20L20 14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
);

const PERSONA_ICONS = { learner: LearnerIcon, educator: EducatorIcon, researcher: ResearcherIcon };

/* ═══════════════════════════════════════════════════════════
   GENERATE KEYWORDS
   ═══════════════════════════════════════════════════════════ */

const generateKeywords = (topic, profile) => {
    const keywords = [];
    if (topic) keywords.push(...topic.split(/\s+/).filter(w => w.length > 3).map(w => w.toLowerCase()));
    if (profile.fieldOfStudy) keywords.push(...profile.fieldOfStudy.split(/\s+/).filter(w => w.length > 3).map(w => w.toLowerCase()));
    keywords.push(profile.persona.toLowerCase());
    keywords.push(profile.depthLabel.toLowerCase().replace(' ', '-'));
    return [...new Set(keywords)];
};

/* ═══════════════════════════════════════════════════════════
   TRANSITION ANIMATION
   ═══════════════════════════════════════════════════════════ */

const TransitionAnimation = ({ active, onComplete, minDuration = 2000 }) => {
    const [visible, setVisible] = useState(false);
    const [exiting, setExiting] = useState(false);
    const [activeStep, setActiveStep] = useState(0);
    const timerRef = useRef(null);
    const stepRef = useRef(null);

    useEffect(() => {
        if (active) {
            setVisible(true);
            setExiting(false);
            setActiveStep(0);
            let step = 0;
            stepRef.current = setInterval(() => {
                step = (step + 1) % 3;
                setActiveStep(step);
            }, minDuration / 3);
            timerRef.current = setTimeout(() => {
                clearInterval(stepRef.current);
                setExiting(true);
                setTimeout(() => { setVisible(false); onComplete?.(); }, 350);
            }, minDuration);
        } else {
            clearTimeout(timerRef.current);
            clearInterval(stepRef.current);
            if (visible) {
                setExiting(true);
                setTimeout(() => setVisible(false), 350);
            }
        }
        return () => { clearTimeout(timerRef.current); clearInterval(stepRef.current); };
    }, [active]);

    if (!visible) return null;

    return (
        <div className={`transition-animation-overlay${exiting ? ' exiting' : ''}`}>
            <div className="trans-orb" />
            <span className="trans-label">
                {active ? 'Searching the research landscape…' : 'Preparing your results…'}
            </span>
            <div className="trans-steps">
                {[0, 1, 2].map(i => (
                    <div key={i} className={`trans-step${activeStep === i ? ' active' : ''}`} />
                ))}
            </div>
        </div>
    );
};

/* ═══════════════════════════════════════════════════════════
   MY RESEARCH PAGE
   ═══════════════════════════════════════════════════════════ */

const MyResearchPage = ({ onBack }) => {
    const [file, setFile] = useState(null);
    const [dragOver, setDragOver] = useState(false);
    const [query, setQuery] = useState('');
    const [analysisType, setAnalysisType] = useState('summary');
    const fileInputRef = useRef(null);

    useEffect(() => {
        const handlePop = () => onBack();
        window.addEventListener('popstate', handlePop);
        return () => window.removeEventListener('popstate', handlePop);
    }, [onBack]);

    const handleDrop = (e) => {
        e.preventDefault(); setDragOver(false);
        const f = e.dataTransfer.files[0];
        if (f) setFile(f);
    };

    const handleFileSelect = (e) => { if (e.target.files[0]) setFile(e.target.files[0]); };

    return (
        <div className="research-page">
            <div className="research-header">
                <button className="back-btn" onClick={() => window.history.back()}>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M19 12H5M12 19l-7-7 7-7" />
                    </svg>
                    Back to Dashboard
                </button>
                <h1 className="research-title">Work With My Research Paper</h1>
                <p className="research-subtitle">Upload your paper and let AI analyze, summarize, or visualize it</p>
            </div>

            <div className="research-content">
                <div
                    className={`upload-zone ${dragOver ? 'drag-over' : ''} ${file ? 'has-file' : ''}`}
                    onDragOver={e => { e.preventDefault(); setDragOver(true); }}
                    onDragLeave={() => setDragOver(false)}
                    onDrop={handleDrop}
                    onClick={() => !file && fileInputRef.current?.click()}
                >
                    <input ref={fileInputRef} type="file" accept=".pdf,.docx,.txt" onChange={handleFileSelect} style={{ display: 'none' }} />
                    {file ? (
                        <div className="file-info">
                            <div className="file-icon">
                                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                                    <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
                                    <polyline points="14,2 14,8 20,8" />
                                </svg>
                            </div>
                            <div className="file-details">
                                <span className="file-name">{file.name}</span>
                                <span className="file-size">{(file.size / 1024 / 1024).toFixed(2)} MB</span>
                            </div>
                            <button className="remove-file" onClick={e => { e.stopPropagation(); setFile(null); }}>
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                    <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
                                </svg>
                            </button>
                        </div>
                    ) : (
                        <>
                            <div className="upload-icon">
                                <svg viewBox="0 0 48 48" fill="none" stroke="currentColor" strokeWidth="2">
                                    <path d="M24 32V12M24 12L16 20M24 12L32 20" strokeLinecap="round" strokeLinejoin="round" />
                                    <path d="M8 32V38C8 40.2 9.8 42 12 42H36C38.2 42 40 40.2 40 38V32" strokeLinecap="round" strokeLinejoin="round" />
                                </svg>
                            </div>
                            <p className="upload-text">Drop your research paper here</p>
                            <p className="upload-hint">or click to browse — PDF, DOCX, TXT</p>
                        </>
                    )}
                </div>

                <div className="analysis-options">
                    <h3>What would you like to do?</h3>
                    <div className="analysis-grid">
                        {[
                            { id: 'summary', title: 'Generate Summary', desc: 'Concise summary of key findings' },
                            { id: 'visualize', title: 'Visualize Concepts', desc: 'Concept map of relationships' },
                            { id: 'critique', title: 'Critical Analysis', desc: 'Strengths, weaknesses, gaps' },
                            { id: 'citations', title: 'Citation Network', desc: 'Map related research connections' },
                            { id: 'simplify', title: 'Simplify Language', desc: 'Rewrite in plain language' },
                            { id: 'questions', title: 'Generate Questions', desc: 'Discussion or exam questions' },
                        ].map(opt => (
                            <button key={opt.id}
                                className={`analysis-card ${analysisType === opt.id ? 'active' : ''}`}
                                onClick={() => setAnalysisType(opt.id)}>
                                <span className="analysis-card-title">{opt.title}</span>
                                <span className="analysis-card-desc">{opt.desc}</span>
                            </button>
                        ))}
                    </div>
                </div>

                <div className="custom-query">
                    <h3>Or ask anything about your paper</h3>
                    <div className="query-input-wrap">
                        <input type="text" className="query-input"
                            placeholder="e.g. What are the main limitations?"
                            value={query} onChange={e => setQuery(e.target.value)} />
                        <button className="query-submit" disabled={!file}>Analyze</button>
                    </div>
                </div>

                <button className="research-submit" disabled={!file}>
                    {file
                        ? `Analyze "${file.name.substring(0, 30)}${file.name.length > 30 ? '…' : ''}"`
                        : 'Upload a paper to begin'}
                </button>
            </div>
        </div>
    );
};

/* ═══════════════════════════════════════════════════════════
   DISCRETE DEPTH SLIDER
   ═══════════════════════════════════════════════════════════ */

const DiscreteDepthSlider = ({ value, onChange }) => {
    const [isDragging, setIsDragging] = useState(false);
    const trackRef = useRef(null);

    const snapToNearest = val => {
        const stops = DEPTH_STOPS.map(s => s.value);
        let closest = stops[0], minDist = Math.abs(val - stops[0]);
        for (let i = 1; i < stops.length; i++) {
            const dist = Math.abs(val - stops[i]);
            if (dist < minDist) { minDist = dist; closest = stops[i]; }
        }
        return closest;
    };

    const getPositionFromEvent = useCallback(e => {
        if (!trackRef.current) return 0;
        const rect = trackRef.current.getBoundingClientRect();
        const clientX = e.touches ? e.touches[0].clientX : e.clientX;
        return Math.max(0, Math.min(1, (clientX - rect.left) / rect.width)) * 100;
    }, []);

    const handlePointerDown = useCallback(e => {
        e.preventDefault(); setIsDragging(true);
        onChange(snapToNearest(getPositionFromEvent(e)));
    }, [getPositionFromEvent, onChange]);

    useEffect(() => {
        if (!isDragging) return;
        const handleMove = e => onChange(snapToNearest(getPositionFromEvent(e)));
        const handleUp = () => setIsDragging(false);
        window.addEventListener('mousemove', handleMove);
        window.addEventListener('mouseup', handleUp);
        window.addEventListener('touchmove', handleMove);
        window.addEventListener('touchend', handleUp);
        return () => {
            window.removeEventListener('mousemove', handleMove);
            window.removeEventListener('mouseup', handleUp);
            window.removeEventListener('touchmove', handleMove);
            window.removeEventListener('touchend', handleUp);
        };
    }, [isDragging, getPositionFromEvent, onChange]);

    const currentStop = DEPTH_STOPS.find(s => s.value === value) || DEPTH_STOPS[0];

    return (
        <div className="depth-slider-container">
            <span className="depth-main-label">Depth</span>
            <div className="depth-track-wrap" ref={trackRef} onMouseDown={handlePointerDown} onTouchStart={handlePointerDown}>
                <div className="depth-stops-track">
                    <div className="depth-track-fill" style={{ width: `${value}%` }} />
                </div>
                {DEPTH_STOPS.map(stop => (
                    <div key={stop.value}
                        className={`depth-stop-dot ${value === stop.value ? 'active' : ''}`}
                        style={{ left: `${stop.value}%` }}
                        onClick={e => { e.stopPropagation(); onChange(stop.value); }}
                    />
                ))}
            </div>
            <div className="depth-label-box">
                <div className={`depth-label-display level-${value}`}>
                    {currentStop.label}
                </div>
            </div>
        </div>
    );
};

/* ═══════════════════════════════════════════════════════════
   KEYWORDS DISPLAY
   ═══════════════════════════════════════════════════════════ */

const KeywordsDisplay = ({ keywords }) => {
    if (!keywords || keywords.length === 0) return null;
    return (
        <div className="keywords-section">
            <div className="keywords-header">
                <span className="keywords-title">Keywords</span>
            </div>
            <div className="keywords-list">
                {keywords.map((kw, i) => <span key={i} className="keyword-tag">{kw}</span>)}
            </div>
        </div>
    );
};

/* ═══════════════════════════════════════════════════════════
   PAPER SELECTION MODAL
   ═══════════════════════════════════════════════════════════ */

const PaperSelectionModal = ({ papers, mode, onSelectPaper, onCompare, onCancel, loading, compareLimit = 3 }) => {
    const [selectedPapers, setSelectedPapers] = useState([]);

    const togglePaper = index => {
        if (mode === 'summarize') { onSelectPaper(papers[index]); return; }
        setSelectedPapers(prev => {
            if (prev.includes(index)) return prev.filter(i => i !== index);
            if (prev.length >= compareLimit) return prev;
            return [...prev, index];
        });
    };

    const handleCompare = () => {
        const selected = selectedPapers.map(i => papers[i]);
        if (selected.length >= 2) onCompare(selected);
    };

    const getPublisher = paper => paper.journal || paper.venue || paper.source || 'Unknown Publisher';

    return (
        <div className="psm-overlay">
            <div className="psm-modal" style={{ position: 'relative' }}>
                <div className="psm-header">
                    <div>
                        <h2 className="psm-title">
                            {mode === 'summarize' ? 'Select a Paper to Summarize' : 'Select Papers to Compare'}
                        </h2>
                        <p className="psm-subtitle">
                            {mode === 'summarize'
                                ? 'Click on a paper to generate a detailed summary'
                                : `Select ${compareLimit} papers to compare (${selectedPapers.length}/${compareLimit} selected)`}
                        </p>
                    </div>
                    <button className="psm-close-btn" onClick={onCancel}>
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
                        </svg>
                    </button>
                </div>

                <div className="psm-list">
                    {papers.map((paper, index) => {
                        const isSelected = mode === 'compare' && selectedPapers.includes(index);
                        const qualityScore = paper.quality_score || 0;
                        const llmRelevanceScore = paper.relevance_score || 0;
                        const badges = paper.quality_badges || [];
                        const citations = paper.citation_count || 0;
                        const validationSummary = paper.validation_summary || '';
                        const llmScorePercent = Math.round(llmRelevanceScore * 100);

                        return (
                            <div key={index}
                                className={`psm-paper-card ${isSelected ? 'selected' : ''}`}
                                onClick={() => togglePaper(index)}>
                                {mode === 'compare' && (
                                    <div className={`psm-checkbox ${isSelected ? 'checked' : ''}`}>
                                        {isSelected && (
                                            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                                                <polyline points="20,6 9,17 4,12" />
                                            </svg>
                                        )}
                                    </div>
                                )}

                                <div className="psm-paper-info">
                                    <div className="psm-title-row">
                                        <div className="psm-paper-title">{paper.title}</div>
                                        {llmRelevanceScore > 0 && (
                                            <div className={`psm-llm-score-pill ${llmScorePercent >= 70 ? 'high' : llmScorePercent >= 40 ? 'medium' : 'low'}`}>
                                                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                                    <path d="M12 2L2 7l10 5 10-5-10-5z" />
                                                    <path d="M2 17l10 5 10-5" />
                                                    <path d="M2 12l10 5 10-5" />
                                                </svg>
                                                LLM: {llmScorePercent}%
                                            </div>
                                        )}
                                    </div>

                                    {/* Authors */}
                                    {paper.authors && paper.authors.length > 0 && (
                                        <div className="psm-paper-authors">
                                            {(Array.isArray(paper.authors) ? paper.authors : [paper.authors]).slice(0, 4).join(', ')}
                                            {Array.isArray(paper.authors) && paper.authors.length > 4 && ` et al.`}
                                        </div>
                                    )}

                                    {badges.length > 0 && (
                                        <div className="psm-badges-row">
                                            {badges.slice(0, 4).map((badge, bi) => (
                                                <span key={bi} className={`psm-badge psm-badge-${badge.type}`}>
                                                    {badge.label}
                                                </span>
                                            ))}
                                        </div>
                                    )}

                                    {/* Abstract preview */}
                                    {paper.abstract && (
                                        <div className="psm-paper-abstract">
                                            {paper.abstract.length > 280
                                                ? paper.abstract.slice(0, 280).trim() + '…'
                                                : paper.abstract}
                                        </div>
                                    )}

                                    <div className="psm-paper-meta-minimal">
                                        {paper.year && (
                                            <span className="psm-meta-chip year">
                                                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                                    <rect x="3" y="4" width="18" height="18" rx="2" />
                                                    <line x1="16" y1="2" x2="16" y2="6" />
                                                    <line x1="8" y1="2" x2="8" y2="6" />
                                                    <line x1="3" y1="10" x2="21" y2="10" />
                                                </svg>
                                                {paper.year}
                                            </span>
                                        )}
                                        {citations > 0 && (
                                            <span className="psm-meta-chip citations">
                                                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                                    <path d="M3 21l1.65-3.8a9 9 0 1113.04-10.62" />
                                                </svg>
                                                {citations.toLocaleString()} citations
                                            </span>
                                        )}
                                        <span className="psm-meta-chip publisher">
                                            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                                <path d="M4 19.5A2.5 2.5 0 016.5 17H20" />
                                                <path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z" />
                                            </svg>
                                            {getPublisher(paper)}
                                        </span>
                                    </div>

                                    {qualityScore > 0 && (
                                        <div className="psm-quality-row">
                                            <span className="psm-quality-tag">LLM Score</span>
                                            <div className="psm-quality-bar">
                                                <div className={`psm-quality-fill ${qualityScore >= 70 ? 'high' : qualityScore >= 40 ? 'medium' : 'low'}`}
                                                    style={{ width: `${qualityScore}%` }} />
                                            </div>
                                            <span className="psm-quality-label">{Math.round(qualityScore)}%</span>
                                        </div>
                                    )}

                                    {validationSummary && (
                                        <div className="psm-validation">{validationSummary}</div>
                                    )}
                                </div>

                                {mode === 'summarize' && (
                                    <div className="psm-arrow">
                                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                            <path d="M5 12h14M12 5l7 7-7 7" />
                                        </svg>
                                    </div>
                                )}
                            </div>
                        );
                    })}
                </div>

                {mode === 'compare' && (
                    <div className="psm-footer">
                        <button className="psm-cancel-btn" onClick={onCancel}>Cancel</button>
                        <button className="psm-compare-btn"
                            disabled={selectedPapers.length < 2 || loading}
                            onClick={handleCompare}>
                            {loading
                                ? <span className="signin-btn-loading"><span className="spinner" /> Comparing…</span>
                                : `Compare ${selectedPapers.length} Papers`}
                        </button>
                    </div>
                )}
            </div>
        </div>
    );
};

/* ═══════════════════════════════════════════════════════════
   MODE SELECTOR
   ═══════════════════════════════════════════════════════════ */

const ModeSelector = ({ mode, onModeChange, persona }) => {
    const isResearcher = persona === 'Researcher';
    const isTeacherOrStudent = persona === 'Educator' || persona === 'Learner';

    return (
        <div className="mode-selector">
            <button className={`mode-btn ${mode === 'summarize' ? 'active' : ''}`} onClick={() => onModeChange('summarize')}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
                    <polyline points="14,2 14,8 20,8" />
                    <line x1="16" y1="13" x2="8" y2="13" />
                    <line x1="16" y1="17" x2="8" y2="17" />
                </svg>
                <div className="mode-btn-text">
                    <span className="mode-btn-title">Summarize Paper</span>
                    <span className="mode-btn-desc">Pick one paper for detailed analysis</span>
                </div>
            </button>

            {isResearcher && (
                <button className={`mode-btn ${mode === 'compare' ? 'active' : ''}`} onClick={() => onModeChange('compare')}>
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <rect x="2" y="3" width="8" height="18" rx="1" />
                        <rect x="14" y="3" width="8" height="18" rx="1" />
                        <path d="M10 9h4" strokeLinecap="round" />
                        <path d="M10 15h4" strokeLinecap="round" />
                    </svg>
                    <div className="mode-btn-text">
                        <span className="mode-btn-title">Compare Papers</span>
                        <span className="mode-btn-desc">Select up to 5 papers to compare</span>
                    </div>
                </button>
            )}

            {isTeacherOrStudent && (
                <button className={`mode-btn ${mode === 'implement' ? 'active' : ''}`} onClick={() => onModeChange('implement')}>
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <polyline points="16,18 22,12 16,6" />
                        <polyline points="8,6 2,12 8,18" />
                        <line x1="14" y1="4" x2="10" y2="20" />
                    </svg>
                    <div className="mode-btn-text">
                        <span className="mode-btn-title">Implement Topic</span>
                        <span className="mode-btn-desc">Auto-extract code &amp; params from top papers</span>
                    </div>
                </button>
            )}
        </div>
    );
};

/* ═══════════════════════════════════════════════════════════
   DASHBOARD — MAIN COMPONENT
   ═══════════════════════════════════════════════════════════ */

export default function Dashboard() {
    const user = { name: 'User', email: 'user@cogniview.ai' };
    const [showUserMenu, setShowUserMenu] = useState(false);

    const [searchValue, setSearchValue] = useState('');
    const [showResearchPage, setShowResearchPage] = useState(false);
    const [expandedCard, setExpandedCard] = useState(null);
    const [isTransitioning, setIsTransitioning] = useState(false);

    const [analysisResult, setAnalysisResult] = useState(null);
    const [showDashboard2, setShowDashboard2] = useState(false);
    const [analyzing, setAnalyzing] = useState(false);
    const [analyzeError, setAnalyzeError] = useState('');

    const [analysisMode, setAnalysisMode] = useState('summarize');

    const [discoveredPapers, setDiscoveredPapers] = useState(null);
    const [showPaperSelection, setShowPaperSelection] = useState(false);
    const [searchingPapers, setSearchingPapers] = useState(false);

    const [paperMode, setPaperMode] = useState('latest');

    const [compareLimit, setCompareLimit] = useState(5);
    const [papersForImplement, setPapersForImplement] = useState(null);

    const [showTransition, setShowTransition] = useState(false);
    const [transitionPhase, setTransitionPhase] = useState(null);
    const [pendingResult, setPendingResult] = useState(null);
    const [transitionDone, setTransitionDone] = useState(false);
    const [pendingPapers, setPendingPapers] = useState(null);
    const [searchTransitionDone, setSearchTransitionDone] = useState(false);

    const [persona, setPersona] = useState('Learner');
    const [fieldOfStudy, setFieldOfStudy] = useState('');
    const [timeBudget, setTimeBudget] = useState('quick');
    const [depthValue, setDepthValue] = useState(0);

    const [uploadedFiles, setUploadedFiles] = useState([]);
    const [uploadWarning, setUploadWarning] = useState('');
    const [uploadingFiles, setUploadingFiles] = useState(false);

    const [papers, setPapers] = useState([]);
    const [loadingPapers, setLoadingPapers] = useState(true);
    const [generatedKeywords, setGeneratedKeywords] = useState([]);

    const searchRef = useRef(null);
    const userMenuRef = useRef(null);
    const fileInputRef = useRef(null);
    const transitionTimeoutRef = useRef(null);

    const depthLabel = depthValue === 0 ? 'Skim' : depthValue === 100 ? 'Deep Dive' : 'Understand';
    const personaDefaults = PERSONA_DEFAULTS[persona] || PERSONA_DEFAULTS.Learner;

    const currentProfile = {
        persona,
        fieldOfStudy,
        timeBudget: TIME_BUDGETS.find(t => t.id === timeBudget)?.label || timeBudget,
        depthValue, depthLabel,
    };

    /* ── Keywords ── */
    useEffect(() => {
        if (searchValue.trim()) setGeneratedKeywords(generateKeywords(searchValue, currentProfile));
        else setGeneratedKeywords([]);
    }, [searchValue, persona, fieldOfStudy, timeBudget, depthValue]);

    /* ── Reset mode on persona change ── */
    useEffect(() => {
        if (persona === 'Researcher' && analysisMode === 'implement') setAnalysisMode('summarize');
        if ((persona === 'Educator' || persona === 'Learner') && analysisMode === 'compare') setAnalysisMode('summarize');
        if (persona !== 'Researcher' && uploadedFiles.length > 1) {
            setUploadedFiles(prev => [prev[0]]);
        }
    }, [persona]);

    /* ── Clear warning after 4s ── */
    useEffect(() => {
        if (!uploadWarning) return;
        const t = setTimeout(() => setUploadWarning(''), 4000);
        return () => clearTimeout(t);
    }, [uploadWarning]);

    /* ═══════════════════════════════════════════════════════════
       SMOOTH CARD TOGGLE (with lock)
       ═══════════════════════════════════════════════════════════ */

    const toggleCard = useCallback((index) => {
        if (isTransitioning) return;  // prevent mid-animation clicks
        setIsTransitioning(true);
        setExpandedCard(current => current === index ? null : index);

        clearTimeout(transitionTimeoutRef.current);
        transitionTimeoutRef.current = setTimeout(() => {
            setIsTransitioning(false);
        }, 650);  // matches CSS duration
    }, [isTransitioning]);

    useEffect(() => {
        return () => clearTimeout(transitionTimeoutRef.current);
    }, []);

    /* ═══════════════════════════════════════════════════════════
       FILE UPLOAD HANDLER
       ═══════════════════════════════════════════════════════════ */

    const handleFileAttach = (e) => {
        const files = Array.from(e.target.files || []);
        if (!files.length) return;
        e.target.value = '';

        const pdfFiles = files.filter(f => f.name.toLowerCase().endsWith('.pdf'));
        if (pdfFiles.length === 0) {
            setUploadWarning('Only PDF files are supported.');
            return;
        }

        const isCompareMode = persona === 'Researcher' && analysisMode === 'compare';

        if (pdfFiles.length > 1 && !isCompareMode) {
            setUploadWarning('Multiple files are only allowed in Researcher + Compare mode. Please select Researcher role and Compare mode first.');
            return;
        }

        const maxFiles = isCompareMode ? 5 : 1;
        const merged = [...uploadedFiles, ...pdfFiles].slice(0, maxFiles);

        if (pdfFiles.length + uploadedFiles.length > maxFiles) {
            setUploadWarning(`Maximum ${maxFiles} file${maxFiles > 1 ? 's' : ''} allowed${isCompareMode ? ' for comparison' : ''}.`);
        }

        setUploadedFiles(merged);
    };

    const removeUploadedFile = (index) => {
        setUploadedFiles(prev => prev.filter((_, i) => i !== index));
    };

    const hasUploadedFiles = uploadedFiles.length > 0;

    /* ═══════════════════════════════════════════════════════════
       FETCH PAPERS — OpenAlex → Semantic Scholar fallback
       ═══════════════════════════════════════════════════════════ */

    const fetchPapers = useCallback(async () => {
        setLoadingPapers(true);
        try {
            const today = new Date();
            today.setHours(23, 59, 59, 999);

            const getSafePublicationDate = (dateValue, yearValue = null) => {
                if (dateValue) {
                    const parsed = new Date(`${dateValue}T00:00:00`);
                    if (!Number.isNaN(parsed.getTime()) && parsed <= today) return parsed;
                }
                if (yearValue && yearValue <= today.getFullYear()) {
                    return new Date(`${yearValue}-12-31T00:00:00`);
                }
                return null;
            };

            const formatPaperDate = (dateValue, yearValue = null) => {
                const safeDate = getSafePublicationDate(dateValue, yearValue);
                if (safeDate && dateValue) {
                    return safeDate.toLocaleDateString('en-US', {
                        month: 'short', day: 'numeric', year: 'numeric',
                    });
                }
                return yearValue && yearValue <= today.getFullYear() ? `${yearValue}` : 'Date unavailable';
            };

            const formatAuthors = (authorList = []) => {
                const names = authorList.map(author => author?.name).filter(Boolean);
                if (names.length === 0) return 'Authors unavailable';
                if (names.length === 1) return names[0];
                if (names.length === 2) return `${names[0]} and ${names[1]}`;
                return `${names[0]}, ${names[1]} et al.`;
            };

            const markFreshness = (dateValue) => {
                if (!dateValue) return 'Recent';
                const publishedAt = new Date(dateValue);
                if (Number.isNaN(publishedAt.getTime())) return 'Recent';
                const diffDays = Math.floor((Date.now() - publishedAt.getTime()) / 86400000);
                if (diffDays <= 1) return 'Today';
                if (diffDays <= 3) return 'New';
                return 'Recent';
            };

            const sevenDaysAgo = new Date(Date.now() - 7 * 86400000).toISOString().slice(0, 10);
            const todayStr = today.toISOString().slice(0, 10);

            const res = await fetch(
                `https://api.openalex.org/works?filter=from_publication_date:${sevenDaysAgo},to_publication_date:${todayStr},type:article&sort=publication_date:desc&per_page=8`,
                {
                    headers: { 'Accept': 'application/json' },
                    cache: 'no-store',
                },
            );

            if (!res.ok) throw new Error(`OpenAlex API error: ${res.status}`);

            const data = await res.json();
            const formatted = (data.results || [])
                .map(paper => ({
                    paper,
                    safePublicationDate: getSafePublicationDate(paper.publication_date, paper.publication_year),
                }))
                .filter(({ safePublicationDate }) => safePublicationDate)
                .sort((a, b) => b.safePublicationDate - a.safePublicationDate)
                .slice(0, 6)
                .map(({ paper }) => {
                    const publicationDate = paper.publication_date || null;
                    const authors = formatAuthors((paper.authorships || []).map(item => ({ name: item.author?.display_name })));
                    const venue = paper.primary_location?.source?.display_name || 'Research archive';
                    const url = paper.doi ? `https://doi.org/${paper.doi}` : paper.id;

                    return {
                        title: paper.title || 'Untitled paper',
                        tag: markFreshness(publicationDate),
                        authors,
                        publishedAt: formatPaperDate(publicationDate, paper.publication_year),
                        venue,
                        url,
                        openAccess: Boolean(paper.open_access?.is_oa),
                    };
                });

            setPapers(
                formatted.length > 0
                    ? formatted
                    : [{ title: 'No recent papers found right now.', tag: 'Info', authors: '', publishedAt: '', venue: '', url: '#' }],
            );
        } catch (err) {
            try {
                const fields = 'title,year,citationCount,externalIds,venue,publicationDate,isOpenAccess,authors';
                const res2 = await fetch(
                    `https://api.semanticscholar.org/graph/v1/paper/search?query=latest research&fields=${fields}&limit=10&sort=publicationDate:desc`,
                    { headers: { 'Accept': 'application/json' }, cache: 'no-store' },
                );

                if (!res2.ok) throw new Error(`Semantic Scholar API error: ${res2.status}`);

                const today = new Date();
                today.setHours(23, 59, 59, 999);

                const getSafePublicationDate = (dateValue, yearValue = null) => {
                    if (dateValue) {
                        const parsed = new Date(`${dateValue}T00:00:00`);
                        if (!Number.isNaN(parsed.getTime()) && parsed <= today) return parsed;
                    }
                    if (yearValue && yearValue <= today.getFullYear()) return new Date(`${yearValue}-12-31T00:00:00`);
                    return null;
                };

                const data2 = await res2.json();
                const fallback = (data2.data || [])
                    .map(paper => ({
                        paper,
                        safePublicationDate: getSafePublicationDate(paper.publicationDate, paper.year),
                    }))
                    .filter(({ safePublicationDate }) => safePublicationDate)
                    .sort((a, b) => b.safePublicationDate - a.safePublicationDate)
                    .slice(0, 6)
                    .map(({ paper: p }) => {
                        const authorNames = (p.authors || []).map(author => author?.name).filter(Boolean);
                        const authors = authorNames.length === 0
                            ? 'Authors unavailable'
                            : authorNames.length === 1
                                ? authorNames[0]
                                : authorNames.length === 2
                                    ? `${authorNames[0]} and ${authorNames[1]}`
                                    : `${authorNames[0]}, ${authorNames[1]} et al.`;
                        return {
                            title: p.title || 'Untitled paper',
                            tag: p.publicationDate && (Date.now() - new Date(p.publicationDate).getTime()) / 86400000 <= 1 ? 'Today'
                                : p.publicationDate && (Date.now() - new Date(p.publicationDate).getTime()) / 86400000 <= 3 ? 'New' : 'Recent',
                            authors,
                            publishedAt: p.publicationDate
                                ? new Date(p.publicationDate).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
                                : (p.year ? `${p.year}` : 'Date unavailable'),
                            venue: p.venue || 'Research archive',
                            url: p.externalIds?.DOI ? `https://doi.org/${p.externalIds.DOI}` : `https://www.semanticscholar.org/paper/${p.paperId}`,
                            openAccess: Boolean(p.isOpenAccess),
                        };
                    });
                setPapers(fallback);
            } catch {
                setPapers([{ title: 'Failed to load latest papers. Check your connection.', tag: 'Error', authors: '', publishedAt: '', venue: '', url: '#' }]);
            }
        }
        setLoadingPapers(false);
    }, []);

    useEffect(() => {
        fetchPapers();
        const intervalId = window.setInterval(() => {
            fetchPapers();
        }, 120000);
        return () => window.clearInterval(intervalId);
    }, [fetchPapers]);

    /* ── Click outside ── */
    useEffect(() => {
        const h = e => {
            if (showUserMenu && userMenuRef.current && !userMenuRef.current.contains(e.target)) setShowUserMenu(false);
        };
        document.addEventListener('mousedown', h);
        return () => document.removeEventListener('mousedown', h);
    }, [showUserMenu]);

    useEffect(() => {
        const h = e => {
            if (e.key === 'Escape') {
                setExpandedCard(null);
                setShowUserMenu(false);
                setShowPaperSelection(false);
            }
        };
        document.addEventListener('keydown', h);
        return () => document.removeEventListener('keydown', h);
    }, []);

    useEffect(() => {
        if (expandedCard === 1 && searchRef.current) searchRef.current.focus();
    }, [expandedCard]);

    /* ── Search transition ── */
    useEffect(() => {
        if (pendingPapers && searchTransitionDone) {
            const timer = setTimeout(() => {
                if (analysisMode === 'implement') {
                    const ps = [...pendingPapers];
                    setShowTransition(false); setPendingPapers(null);
                    setSearchTransitionDone(false); setTransitionPhase(null);
                    setPapersForImplement(ps);
                } else {
                    setDiscoveredPapers(pendingPapers);
                    setShowPaperSelection(true);
                    setShowTransition(false); setPendingPapers(null);
                    setSearchTransitionDone(false); setTransitionPhase(null);
                }
            }, 200);
            return () => clearTimeout(timer);
        }
    }, [pendingPapers, searchTransitionDone, analysisMode]);

    /* ── Analyze transition ── */
    useEffect(() => {
        if (pendingResult && transitionDone) {
            const timer = setTimeout(() => {
                setAnalysisResult(pendingResult);
                setShowDashboard2(true);
                setShowTransition(false); setPendingResult(null);
                setTransitionDone(false); setTransitionPhase(null);
            }, 300);
            return () => clearTimeout(timer);
        }
    }, [pendingResult, transitionDone]);

    const handleTransitionComplete = useCallback(() => {
        if (transitionPhase === 'searching') setSearchTransitionDone(true);
        else if (transitionPhase === 'analyzing') setTransitionDone(true);
    }, [transitionPhase]);

    /* ── STEP 1: Search papers (or direct-process uploaded files) ── */
    const handleSearchPapers = async () => {
        if (hasUploadedFiles) {
            setAnalyzeError(''); setUploadingFiles(true);
            setTransitionPhase('analyzing'); setShowTransition(true);
            setPendingResult(null); setTransitionDone(false);

            try {
                const paperDicts = [];
                for (const file of uploadedFiles) {
                    const formData = new FormData();
                    formData.append('file', file);
                    const upRes = await fetch(`${API_BASE_URL}/upload`, {
                        method: 'POST', body: formData,
                    });
                    if (!upRes.ok) {
                        const err = await upRes.json().catch(() => ({}));
                        throw new Error(err.detail || `Upload failed: ${upRes.status}`);
                    }
                    const upData = await upRes.json();
                    paperDicts.push({
                        title: upData.title, pdf_url: upData.pdf_url,
                        pdf_hash: upData.pdf_hash,
                        authors: [], year: 0, venue: '', doi: '', arxiv_id: '',
                        abstract: '', citation_count: 0,
                    });
                }

                let response;
                if (analysisMode === 'compare' && paperDicts.length >= 2) {
                    response = await fetch(`${API_BASE_URL}/compare`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            papers: paperDicts, persona,
                            field_of_study: fieldOfStudy,
                            depth: DEPTH_TO_API[depthLabel] || 'Understand',
                            knowledge_level: personaDefaults.knowledge_level,
                            time_budget: TIME_BUDGET_TO_API[timeBudget] || 'Focused',
                            goal: personaDefaults.goal,
                            output_format: personaDefaults.output_format,
                            topic: paperDicts.map(p => p.title).join(' vs '),
                        }),
                    });
                } else if (analysisMode === 'implement') {
                    response = await fetch(`${API_BASE_URL}/implement`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            papers: paperDicts, persona,
                            field_of_study: fieldOfStudy,
                            topic: paperDicts[0]?.title || 'Uploaded paper',
                        }),
                    });
                } else {
                    response = await fetch(`${API_BASE_URL}/summarize`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            paper: paperDicts[0], persona,
                            field_of_study: fieldOfStudy,
                            depth: DEPTH_TO_API[depthLabel] || 'Understand',
                            knowledge_level: personaDefaults.knowledge_level,
                            time_budget: TIME_BUDGET_TO_API[timeBudget] || 'Focused',
                            goal: personaDefaults.goal,
                            output_format: personaDefaults.output_format,
                            topic: paperDicts[0]?.title || 'Uploaded paper',
                        }),
                    });
                }

                if (!response.ok) {
                    const errorData = await response.json().catch(() => ({}));
                    throw new Error(errorData.detail || `API error: ${response.status}`);
                }
                setPendingResult(await response.json());
            } catch (err) {
                setAnalyzeError(err.message || 'Failed to process uploaded files.');
                setShowTransition(false); setPendingResult(null);
                setTransitionDone(false); setTransitionPhase(null);
            } finally {
                setUploadingFiles(false);
            }
            return;
        }

        if (!searchValue.trim()) return;
        setSearchingPapers(true); setAnalyzeError('');
        setPendingPapers(null); setSearchTransitionDone(false);
        setTransitionPhase('searching'); setShowTransition(true);

        try {
            const response = await fetch(`${API_BASE_URL}/discover`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    topic: searchValue.trim(),
                    persona,
                    field_of_study: fieldOfStudy,
                    depth: DEPTH_TO_API[depthLabel] || 'Understand',
                    knowledge_level: personaDefaults.knowledge_level,
                    time_budget: TIME_BUDGET_TO_API[timeBudget] || 'Focused',
                    goal: personaDefaults.goal,
                    output_format: personaDefaults.output_format,
                    temporal_focus: paperMode === 'latest' ? 'cutting_edge' : 'any',
                    time_filter: paperMode,
                }),
            });
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.detail || `API error: ${response.status}`);
            }
            const result = await response.json();
            if (!result.papers || result.papers.length === 0)
                throw new Error('No papers found for this topic. Try a different search term.');
            setPendingPapers(result.papers);
            setCompareLimit(result.compare_limit || 5);
        } catch (err) {
            setAnalyzeError(err.message || 'Failed to search papers.');
            setShowTransition(false); setPendingPapers(null);
            setSearchTransitionDone(false); setTransitionPhase(null);
        } finally {
            setSearchingPapers(false);
        }
    };

    /* ── Auto-implement ── */
    useEffect(() => {
        if (papersForImplement && papersForImplement.length > 0) {
            handleImplementDirect(papersForImplement);
            setPapersForImplement(null);
        }
    }, [papersForImplement]);

    const handleImplementDirect = async (papers) => {
        setShowPaperSelection(false); setAnalyzing(true);
        setPendingResult(null); setTransitionDone(false);
        setTransitionPhase('analyzing'); setShowTransition(true);

        try {
            const response = await fetch(`${API_BASE_URL}/implement`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    papers: papers.slice(0, 10),
                    persona,
                    field_of_study: fieldOfStudy,
                    topic: searchValue.trim(),
                }),
            });
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.detail || `API error: ${response.status}`);
            }
            setPendingResult(await response.json());
        } catch (err) {
            setAnalyzeError(err.message || 'Failed to generate implementation.');
            setShowTransition(false); setPendingResult(null);
            setTransitionDone(false); setTransitionPhase(null);
        } finally {
            setAnalyzing(false);
        }
    };

    /* ── STEP 2a: Summarize ── */
    const handleSummarizePaper = async (paper) => {
        setShowPaperSelection(false); setAnalyzing(true);
        setPendingResult(null); setTransitionDone(false);
        setTransitionPhase('analyzing'); setShowTransition(true);

        try {
            const response = await fetch(`${API_BASE_URL}/summarize`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    paper, persona,
                    field_of_study: fieldOfStudy,
                    depth: DEPTH_TO_API[depthLabel] || 'Understand',
                    knowledge_level: personaDefaults.knowledge_level,
                    time_budget: TIME_BUDGET_TO_API[timeBudget] || 'Focused',
                    goal: personaDefaults.goal,
                    output_format: personaDefaults.output_format,
                    topic: searchValue.trim(),
                }),
            });
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.detail || `API error: ${response.status}`);
            }
            setPendingResult(await response.json());
        } catch (err) {
            setAnalyzeError(err.message || 'Failed to summarize paper.');
            setShowTransition(false); setPendingResult(null);
            setTransitionDone(false); setTransitionPhase(null);
        } finally {
            setAnalyzing(false);
        }
    };

    /* ── STEP 2b: Compare ── */
    const handleCompare = async (selectedPapers) => {
        setShowPaperSelection(false); setAnalyzing(true);
        setPendingResult(null); setTransitionDone(false);
        setTransitionPhase('analyzing'); setShowTransition(true);

        try {
            const response = await fetch(`${API_BASE_URL}/compare`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    papers: selectedPapers, persona,
                    field_of_study: fieldOfStudy,
                    depth: DEPTH_TO_API[depthLabel] || 'Understand',
                    knowledge_level: personaDefaults.knowledge_level,
                    time_budget: TIME_BUDGET_TO_API[timeBudget] || 'Focused',
                    goal: personaDefaults.goal,
                    output_format: personaDefaults.output_format,
                    topic: searchValue.trim(),
                }),
            });
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.detail || `API error: ${response.status}`);
            }
            setPendingResult(await response.json());
        } catch (err) {
            setAnalyzeError(err.message || 'Failed to compare papers.');
            setShowTransition(false); setPendingResult(null);
            setTransitionDone(false); setTransitionPhase(null);
        } finally {
            setAnalyzing(false);
        }
    };

    /* ══════════════════ ROUTING ══════════════════ */

    if (showDashboard2 && analysisResult) {
        return (
            <Dashboard2
                analysisResult={analysisResult}
                userProfile={currentProfile}
                onBack={() => { setShowDashboard2(false); setAnalysisResult(null); }}
            />
        );
    }

    if (showResearchPage) {
        return <MyResearchPage onBack={() => setShowResearchPage(false)} />;
    }

    const userInitials = user.name
        ? user.name.split(' ').map(w => w[0]).join('').toUpperCase().slice(0, 2)
        : user.email[0].toUpperCase();
    const compactRoles = PERSONAS.slice(0, 3);
    const isPapersShrunk = expandedCard !== null && expandedCard !== 0;
    const isSearchShrunk = expandedCard !== null && expandedCard !== 1;
    const isSearchMedium = expandedCard === null;

    /* ══════════════════ RENDER ══════════════════ */

    return (
        <>
            <TransitionAnimation
                active={showTransition}
                onComplete={handleTransitionComplete}
                minDuration={2200}
            />

            {showPaperSelection && discoveredPapers && (
                <PaperSelectionModal
                    papers={discoveredPapers}
                    mode={analysisMode}
                    onSelectPaper={handleSummarizePaper}
                    onCompare={handleCompare}
                    onCancel={() => setShowPaperSelection(false)}
                    loading={analyzing}
                    compareLimit={compareLimit}
                />
            )}

            <div className="dashboard">
                {/* Background */}
                <div className="bg-animation">
                    <div className="bg-grid" />
                    <div className="bg-grain" />
                    <div className="bg-gradient-top" />
                </div>

                {/* ── TOP BAR ── */}
                <header className="topbar">
                    <div className="topbar-left">
                        <div className="logo-icon">
                            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                                <path d="M12 2L2 7l10 5 10-5-10-5z" />
                                <path d="M2 17l10 5 10-5" />
                                <path d="M2 12l10 5 10-5" />
                            </svg>
                        </div>
                        <span className="logo-text">CogniView.AI</span>
                    </div>

                    <div className="topbar-right">
                        <div style={{ position: 'relative' }} ref={userMenuRef}>
                            <button className="user-avatar-btn"
                                onClick={() => setShowUserMenu(!showUserMenu)}
                                title={user.name || user.email}>
                                {userInitials}
                            </button>

                            {showUserMenu && (
                                <div className="user-menu">
                                    <div className="user-menu-header">
                                        <div className="user-menu-avatar">{userInitials}</div>
                                        <div className="user-menu-info">
                                            <div className="user-menu-name">{user.name}</div>
                                            <div className="user-menu-email">{user.email}</div>
                                        </div>
                                    </div>
                                    <div className="user-menu-divider" />
                                    <button className="user-menu-item">
                                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                            <circle cx="12" cy="8" r="4" />
                                            <path d="M4 21v-1a4 4 0 014-4h8a4 4 0 014 4v1" />
                                        </svg>
                                        Profile
                                    </button>
                                    <button className="user-menu-item">
                                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                            <circle cx="12" cy="12" r="3" />
                                            <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z" />
                                        </svg>
                                        Settings
                                    </button>
                                    <div className="user-menu-divider" />
                                    <button className="user-menu-item danger" onClick={() => setShowUserMenu(false)}>
                                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                            <path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4" />
                                            <polyline points="16,17 21,12 16,7" />
                                            <line x1="21" y1="12" x2="9" y2="12" />
                                        </svg>
                                        Sign Out
                                    </button>
                                </div>
                            )}
                        </div>
                    </div>
                </header>

                <div className={`cards-section ${expandedCard !== null ? `active-${expandedCard}` : ''} ${isTransitioning ? 'transitioning' : ''}`}>

                    {/* Card 0: Papers */}
                    <div
                        className={`dash-card ${expandedCard === 0 ? 'expanded' : expandedCard !== null ? 'shrunk' : ''}`}
                        onClick={() => toggleCard(0)}
                    >
                        <div className="card-header">
                            <h3>Papers</h3>
                            <span className="paper-feed-badge">Live Latest Feed</span>
                        </div>

                        <div className="card-content-wrapper">
                            <div className={`papers-list ${isPapersShrunk ? 'compact' : ''}`}>
                                {loadingPapers ? (
                                    <div className="loading-placeholder">
                                        <div className="loading-dots">
                                            <span /><span /><span />
                                        </div>
                                        Syncing latest papers…
                                    </div>
                                ) : papers.slice(0, isPapersShrunk ? 3 : papers.length).map((p, i) => (
                                    <a
                                        key={i}
                                        className={`paper-item ${isPapersShrunk ? 'compact' : ''}`}
                                        href={p.url}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        onClick={(e) => e.stopPropagation()}
                                    >
                                        <div className="paper-title">{p.title}</div>
                                        <div className={`paper-authors ${isPapersShrunk ? 'compact' : ''}`}>{p.authors}</div>
                                        <div className={`paper-date-line ${isPapersShrunk ? 'compact' : ''}`}>
                                            <span className="paper-time">{p.publishedAt}</span>
                                            {p.venue && <span className="paper-time">· {p.venue}</span>}
                                        </div>
                                        {!isPapersShrunk && (
                                            <div className="paper-meta">
                                                <span className={`paper-tag ${p.tag === 'New' || p.tag === 'Recent' ? 'trending' : ''}`}>
                                                    {p.tag}
                                                </span>
                                                {p.openAccess && (
                                                    <span className="paper-tag" style={{ background: 'rgba(61,107,50,0.12)', color: 'var(--green-bright)' }}>
                                                        Open Access
                                                    </span>
                                                )}
                                            </div>
                                        )}
                                    </a>
                                ))}
                            </div>
                        </div>
                    </div>

                    {/* Card 1: Search */}
                    <div
                        className={`dash-card search-card ${expandedCard === 1 ? 'expanded' : expandedCard !== null ? 'shrunk' : ''}`}
                        onClick={() => toggleCard(1)}
                    >
                        <div className="card-header search-card-header">
                                <h3>Search Research</h3>
                        </div>

                        <div className="card-content-wrapper">
                            <div className="search-card-shell">
                                <div className="search-bar search-bar-inline" onClick={(e) => e.stopPropagation()}>
                                    <span className="search-icon">
                                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                            <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
                                        </svg>
                                    </span>
                                    <input
                                        ref={searchRef}
                                        type="text"
                                        className="search-input"
                                        placeholder={hasUploadedFiles ? 'PDF attached — search disabled' : 'Enter Research Topic: "CRISPR gene editing applications"'}
                                        value={searchValue}
                                        onChange={e => setSearchValue(e.target.value)}
                                        onClick={(e) => e.stopPropagation()}
                                        onKeyDown={e => { if (e.key === 'Enter' && !analyzing && !searchingPapers && !uploadingFiles) handleSearchPapers(); }}
                                        disabled={analyzing || searchingPapers || uploadingFiles || hasUploadedFiles}
                                    />
                                    {searchValue && !analyzing && !searchingPapers && (
                                        <button
                                            type="button"
                                            className="search-clear"
                                            onClick={e => { e.stopPropagation(); setSearchValue(''); }}
                                        >
                                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                                <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
                                            </svg>
                                        </button>
                                    )}

                                    {/* File attach button */}
                                    <input
                                        ref={fileInputRef}
                                        type="file"
                                        accept=".pdf"
                                        multiple={persona === 'Researcher' && analysisMode === 'compare'}
                                        onChange={handleFileAttach}
                                        style={{ display: 'none' }}
                                    />
                                    <button
                                        type="button"
                                        className={`search-attach-btn ${hasUploadedFiles ? 'has-files' : ''}`}
                                        title={hasUploadedFiles ? 'Change attached files' : 'Attach PDF file(s)'}
                                        onClick={e => { e.stopPropagation(); fileInputRef.current?.click(); }}
                                        disabled={analyzing || searchingPapers || uploadingFiles}
                                    >
                                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                            <path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48" />
                                        </svg>
                                    </button>
                                </div>

                                {/* Uploaded file chips */}
                                {hasUploadedFiles && (
                                    <div className="uploaded-files-strip" onClick={(e) => e.stopPropagation()}>
                                        {uploadedFiles.map((file, i) => (
                                            <div key={i} className="uploaded-file-chip">
                                                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                                    <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
                                                    <polyline points="14,2 14,8 20,8" />
                                                </svg>
                                                <span className="uploaded-file-name">{file.name.length > 28 ? file.name.substring(0, 25) + '…' : file.name}</span>
                                                <span className="uploaded-file-size">{(file.size / 1024 / 1024).toFixed(1)}MB</span>
                                                <button
                                                    type="button"
                                                    className="uploaded-file-remove"
                                                    onClick={() => removeUploadedFile(i)}
                                                >
                                                    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                                                        <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
                                                    </svg>
                                                </button>
                                            </div>
                                        ))}
                                        <button
                                            type="button"
                                            className="uploaded-files-clear-all"
                                            onClick={() => { setUploadedFiles([]); setSearchValue(''); }}
                                        >
                                            Clear all
                                        </button>
                                    </div>
                                )}

                                {/* Upload warning toast */}
                                {uploadWarning && (
                                    <div className="upload-warning-toast" onClick={(e) => e.stopPropagation()}>
                                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                            <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
                                            <line x1="12" y1="9" x2="12" y2="13" />
                                            <line x1="12" y1="17" x2="12.01" y2="17" />
                                        </svg>
                                        {uploadWarning}
                                    </div>
                                )}

                                <div className="search-role-strip" onClick={(e) => e.stopPropagation()}>
                                    {compactRoles.map(p => {
                                        const Icon = PERSONA_ICONS[p.icon];
                                        return (
                                            <button
                                                key={p.id}
                                                type="button"
                                                className={`search-role-btn ${persona === p.id ? 'active' : ''}`}
                                                onClick={() => setPersona(p.id)}
                                            >
                                                <Icon />
                                                <span>{p.id}</span>
                                            </button>
                                        );
                                    })}
                                </div>

                                {analyzeError && (
                                    <div className="form-error" style={{ marginTop: '4px' }} onClick={(e) => e.stopPropagation()}>
                                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                            <circle cx="12" cy="12" r="10" />
                                            <line x1="12" y1="8" x2="12" y2="12" />
                                            <line x1="12" y1="16" x2="12.01" y2="16" />
                                        </svg>
                                        {analyzeError}
                                    </div>
                                )}

                                {expandedCard === 1 ? (
                                    <div className="search-advanced-panel" onClick={(e) => e.stopPropagation()}>
                                        <ModeSelector mode={analysisMode} onModeChange={setAnalysisMode} persona={persona} />

                                        <div className="field-of-study-section">
                                            <span className="section-label">Field of Study</span>
                                            <div className="field-select-wrap">
                                                <select
                                                    className="field-select"
                                                    value={fieldOfStudy}
                                                    onChange={(e) => setFieldOfStudy(e.target.value)}
                                                    disabled={analyzing || searchingPapers || uploadingFiles}
                                                >
                                                    {BROAD_FIELDS.map(field => (
                                                        <option key={field.label} value={field.value}>
                                                            {field.label}
                                                        </option>
                                                    ))}
                                                </select>
                                                <span className="field-select-arrow">
                                                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                                        <path d="M6 9l6 6 6-6" />
                                                    </svg>
                                                </span>
                                            </div>
                                        </div>

                                        {!hasUploadedFiles && (
                                            <div className="source-selector">
                                                <span className="source-label">Paper Priority</span>
                                                <div className="source-toggle-wrap">
                                                    <button type="button" className={`source-toggle-btn ${paperMode === 'relevant' ? 'active' : ''}`} onClick={() => setPaperMode('relevant')}>
                                                        Most Relevant
                                                    </button>
                                                    <button type="button" className={`source-toggle-btn ${paperMode === 'latest' ? 'active' : ''}`} onClick={() => setPaperMode('latest')}>
                                                        Latest Papers
                                                    </button>
                                                </div>
                                            </div>
                                        )}

                                        <DiscreteDepthSlider value={depthValue} onChange={setDepthValue} />

                                        <div className="expanded-context">
                                            <div className="context-section">
                                                <span className="section-label">Time Budget</span>
                                                <div className="chip-row">
                                                    {TIME_BUDGETS.map(tb => (
                                                        <button
                                                            key={tb.id}
                                                            type="button"
                                                            className={`chip chip-wide ${timeBudget === tb.id ? 'active' : ''}`}
                                                            onClick={() => setTimeBudget(tb.id)}
                                                        >
                                                            <span className="chip-main">{tb.label}</span>
                                                            <span className="chip-sub">{tb.desc}</span>
                                                        </button>
                                                    ))}
                                                </div>
                                            </div>

                                            <KeywordsDisplay keywords={generatedKeywords} />
                                        </div>

                                        <button
                                            type="button"
                                            className="analyze-btn"
                                            onClick={handleSearchPapers}
                                            disabled={analyzing || searchingPapers || uploadingFiles || (!searchValue.trim() && !hasUploadedFiles)}
                                        >
                                            {uploadingFiles ? (
                                                <span style={{ display: 'flex', alignItems: 'center', gap: '8px', justifyContent: 'center' }}>
                                                    <span className="spinner" /> Uploading & processing…
                                                </span>
                                            ) : searchingPapers ? (
                                                <span style={{ display: 'flex', alignItems: 'center', gap: '8px', justifyContent: 'center' }}>
                                                    <span className="spinner" /> Searching papers…
                                                </span>
                                            ) : analyzing ? (
                                                <span style={{ display: 'flex', alignItems: 'center', gap: '8px', justifyContent: 'center' }}>
                                                    <span className="spinner" /> Analyzing…
                                                </span>
                                            ) : hasUploadedFiles ? (
                                                `${analysisMode === 'compare' ? 'Compare' : analysisMode === 'implement' ? 'Implement' : 'Summarize'} Uploaded ${uploadedFiles.length > 1 ? `${uploadedFiles.length} Papers` : 'Paper'}`
                                            ) : (
                                                `Find ${paperMode === 'latest' ? 'Latest' : 'Relevant'} Papers & ${analysisMode === 'compare' ? 'Compare' : analysisMode === 'implement' ? 'Implement' : 'Summarize'}`
                                            )}
                                        </button>
                                    </div>
                                ) : isSearchMedium ? (
                                    <button
                                        type="button"
                                        className="analyze-btn search-card-analyze"
                                        onClick={(e) => {
                                            e.stopPropagation();
                                            handleSearchPapers();
                                        }}
                                        disabled={analyzing || searchingPapers || uploadingFiles || (!searchValue.trim() && !hasUploadedFiles)}
                                    >
                                        {uploadingFiles ? (
                                            <span style={{ display: 'flex', alignItems: 'center', gap: '8px', justifyContent: 'center' }}>
                                                <span className="spinner" /> Processing…
                                            </span>
                                        ) : searchingPapers ? (
                                            <span style={{ display: 'flex', alignItems: 'center', gap: '8px', justifyContent: 'center' }}>
                                                <span className="spinner" /> Searching papers…
                                            </span>
                                        ) : analyzing ? (
                                            <span style={{ display: 'flex', alignItems: 'center', gap: '8px', justifyContent: 'center' }}>
                                                <span className="spinner" /> Analyzing…
                                            </span>
                                        ) : hasUploadedFiles ? (
                                            `Process Uploaded Paper${uploadedFiles.length > 1 ? 's' : ''}`
                                        ) : (
                                            `Find ${paperMode === 'latest' ? 'Latest' : 'Relevant'} Papers`
                                        )}
                                    </button>
                                ) : (
                                    <p className="search-card-hint">Click the card to reopen advanced filters.</p>
                                )}
                            </div>
                        </div>
                    </div>

                    {/* Card 2: Chat History */}
                    <div
                        className={`dash-card ${expandedCard === 2 ? 'expanded' : expandedCard !== null ? 'shrunk' : ''}`}
                        onClick={() => toggleCard(2)}
                    >
                        <div className="card-header"><h3>Chat History</h3></div>

                        <div className="card-content-wrapper">
                            <div className="coming-soon-content">
                                <div className="coming-soon-icon">
                                    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.2">
                                        <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" />
                                    </svg>
                                </div>
                                <h4 className="coming-soon-title">Chat History</h4>
                                <p className="coming-soon-text">Will be available soon.</p>
                            </div>
                        </div>
                    </div>

                </div>
            </div>
        </>
    );
}

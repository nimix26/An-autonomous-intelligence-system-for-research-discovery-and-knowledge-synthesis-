import React, { useEffect, useRef } from 'react';
import './TransitionAnimation.css';

/**
 * TransitionAnimation — Revolving papers animation (Dark Theme)
 *
 * Multiple pages revolve in non-linear circular motion around a center page.
 * Each revolving page has a connection line to the still center page.
 * Papers remain white on a dark background.
 *
 * Props:
 *   - active: boolean — whether the animation is visible
 *   - onComplete: function — called when minimum duration has passed (optional)
 *   - minDuration: number — minimum ms before onComplete fires (default 2500)
 */
const PAPER_COUNT_ANIM = 8;

export default function TransitionAnimation({ active, onComplete, minDuration = 2500 }) {
    const canvasRef = useRef(null);
    const startTimeRef = useRef(null);
    const animFrameRef = useRef(null);
    const completedRef = useRef(false);

    useEffect(() => {
        if (!active) {
            completedRef.current = false;
            startTimeRef.current = null;
            if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
            return;
        }

        startTimeRef.current = Date.now();
        const canvas = canvasRef.current;
        if (!canvas) return;
        const ctx = canvas.getContext('2d');

        const resize = () => {
            canvas.width = window.innerWidth * window.devicePixelRatio;
            canvas.height = window.innerHeight * window.devicePixelRatio;
            canvas.style.width = window.innerWidth + 'px';
            canvas.style.height = window.innerHeight + 'px';
            ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
        };
        resize();
        window.addEventListener('resize', resize);

        const cx = () => window.innerWidth / 2;
        const cy = () => window.innerHeight / 2;

        // Paper properties — each has unique orbit params for non-linear motion
        const papers = Array.from({ length: PAPER_COUNT_ANIM }, (_, i) => ({
            angle: (i / PAPER_COUNT_ANIM) * Math.PI * 2,
            radiusX: 140 + Math.random() * 60,
            radiusY: 100 + Math.random() * 50,
            speed: 0.6 + Math.random() * 0.5,
            phaseX: Math.random() * Math.PI * 2,
            phaseY: Math.random() * Math.PI * 2,
            wobbleAmp: 8 + Math.random() * 15,
            wobbleFreq: 1.5 + Math.random() * 2,
            width: 36 + Math.random() * 12,
            height: 48 + Math.random() * 14,
            rotation: Math.random() * 0.3 - 0.15,
        }));

        const drawPaper = (x, y, w, h, rot, alpha, isCenter) => {
            ctx.save();
            ctx.translate(x, y);
            ctx.rotate(rot);
            ctx.globalAlpha = alpha;

            // Shadow — purple glow on dark bg
            ctx.shadowColor = isCenter
                ? 'rgba(37, 102, 184, 0.35)'
                : 'rgba(37, 102, 184, 0.15)';
            ctx.shadowBlur = isCenter ? 24 : 12;
            ctx.shadowOffsetY = 3;

            // Paper body — stays white
            ctx.fillStyle = '#fbfbf8';
            ctx.beginPath();
            const r = 4;
            ctx.moveTo(-w / 2 + r, -h / 2);
            ctx.lineTo(w / 2 - r, -h / 2);
            ctx.quadraticCurveTo(w / 2, -h / 2, w / 2, -h / 2 + r);
            ctx.lineTo(w / 2, h / 2 - r);
            ctx.quadraticCurveTo(w / 2, h / 2, w / 2 - r, h / 2);
            ctx.lineTo(-w / 2 + r, h / 2);
            ctx.quadraticCurveTo(-w / 2, h / 2, -w / 2, h / 2 - r);
            ctx.lineTo(-w / 2, -h / 2 + r);
            ctx.quadraticCurveTo(-w / 2, -h / 2, -w / 2 + r, -h / 2);
            ctx.closePath();
            ctx.fill();

            // Border
            ctx.shadowColor = 'transparent';
            ctx.strokeStyle = isCenter
                ? 'rgba(37, 102, 184, 0.5)'
                : 'rgba(37, 102, 184, 0.2)';
            ctx.lineWidth = isCenter ? 1.5 : 1;
            ctx.stroke();

            // Lines on paper — dark ink on white paper
            const lineCount = isCenter ? 6 : 4;
            const lineStartY = -h / 2 + (isCenter ? 14 : 10);
            for (let i = 0; i < lineCount; i++) {
                const ly = lineStartY + i * (isCenter ? 7 : 6);
                const lw = (w - (isCenter ? 16 : 12)) * (i === lineCount - 1 ? 0.5 : 0.7 + Math.random() * 0.3);
                ctx.fillStyle = isCenter
                    ? 'rgba(30, 30, 30, 0.3)'
                    : 'rgba(30, 30, 30, 0.15)';
                ctx.fillRect(-w / 2 + (isCenter ? 8 : 6), ly, lw, 1.5);
            }

            // Accent dot for center
            if (isCenter) {
                ctx.fillStyle = '#2566b8';
                ctx.beginPath();
                ctx.arc(-w / 2 + 8, -h / 2 + 8, 2.5, 0, Math.PI * 2);
                ctx.fill();
            }

            ctx.restore();
        };

        const drawConnection = (fromX, fromY, toX, toY, alpha) => {
            ctx.save();
            ctx.globalAlpha = alpha * 0.5;
            ctx.strokeStyle = '#2566b8';
            ctx.lineWidth = 1.2;
            ctx.setLineDash([4, 4]);

            // Curved connection
            const midX = (fromX + toX) / 2 + (fromY - toY) * 0.1;
            const midY = (fromY + toY) / 2 + (toX - fromX) * 0.1;

            ctx.beginPath();
            ctx.moveTo(fromX, fromY);
            ctx.quadraticCurveTo(midX, midY, toX, toY);
            ctx.stroke();

            // Glow dot at connection point near center
            ctx.setLineDash([]);
            ctx.globalAlpha = alpha * 0.7;
            ctx.fillStyle = '#4a9cd6';
            ctx.beginPath();
            ctx.arc(toX + (fromX - toX) * 0.15, toY + (fromY - toY) * 0.15, 2, 0, Math.PI * 2);
            ctx.fill();

            ctx.restore();
        };

        const animate = () => {
            const elapsed = (Date.now() - startTimeRef.current) / 1000;
            const w = window.innerWidth;
            const h = window.innerHeight;

            ctx.clearRect(0, 0, w, h);

            const centerX = cx();
            const centerY = cy();

            // Fade in
            const fadeIn = Math.min(elapsed / 0.5, 1);

            // Subtle background radial glow
            const bgGrad = ctx.createRadialGradient(centerX, centerY, 0, centerX, centerY, 300);
            bgGrad.addColorStop(0, `rgba(37, 102, 184, ${0.08 * fadeIn})`);
            bgGrad.addColorStop(1, 'transparent');
            ctx.fillStyle = bgGrad;
            ctx.fillRect(0, 0, w, h);

            // Draw connections and revolving papers
            papers.forEach((p, i) => {
                const t = elapsed * p.speed + p.angle;

                // Non-linear orbit: elliptical + wobble
                const px = centerX + Math.cos(t + p.phaseX) * p.radiusX
                    + Math.sin(t * p.wobbleFreq) * p.wobbleAmp;
                const py = centerY + Math.sin(t + p.phaseY) * p.radiusY
                    + Math.cos(t * p.wobbleFreq * 0.7) * p.wobbleAmp * 0.6;

                const rot = p.rotation + Math.sin(t * 1.3) * 0.15;
                const alpha = fadeIn * (0.5 + Math.sin(t * 0.8 + i) * 0.2);

                // Draw connection line
                drawConnection(px, py, centerX, centerY, fadeIn * 0.7);

                // Draw revolving paper
                drawPaper(px, py, p.width, p.height, rot, alpha, false);
            });

            // Draw center paper (still, slightly larger)
            drawPaper(centerX, centerY, 52, 68, 0, fadeIn, true);

            // Outer pulse ring — purple glow
            const pulseRadius = 30 + Math.sin(elapsed * 2) * 5;
            ctx.save();
            ctx.globalAlpha = fadeIn * 0.15;
            ctx.strokeStyle = '#2566b8';
            ctx.lineWidth = 1.5;
            ctx.beginPath();
            ctx.arc(centerX, centerY, pulseRadius, 0, Math.PI * 2);
            ctx.stroke();
            ctx.restore();

            // Second larger pulse ring
            const pulseRadius2 = 60 + Math.sin(elapsed * 1.4 + 1) * 8;
            ctx.save();
            ctx.globalAlpha = fadeIn * 0.06;
            ctx.strokeStyle = '#4a9cd6';
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.arc(centerX, centerY, pulseRadius2, 0, Math.PI * 2);
            ctx.stroke();
            ctx.restore();

            // Check if minimum duration passed for onComplete callback
            if (!completedRef.current && onComplete && Date.now() - startTimeRef.current >= minDuration) {
                completedRef.current = true;
                onComplete();
            }

            animFrameRef.current = requestAnimationFrame(animate);
        };

        animFrameRef.current = requestAnimationFrame(animate);

        return () => {
            window.removeEventListener('resize', resize);
            if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
        };
    }, [active, onComplete, minDuration]);

    if (!active) return null;

    return (
        <div className="transition-animation-overlay">
            <canvas ref={canvasRef} className="transition-animation-canvas" />
            <div className="transition-animation-label">Synthesizing Research...</div>
        </div>
    );
}
import React, { useEffect, useRef, useMemo, useState, useCallback } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { EffectComposer, Bloom, Vignette } from '@react-three/postprocessing';
import * as THREE from 'three';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import './App.css';

gsap.registerPlugin(ScrollTrigger);

import TransitionAnimation from './TransitionAnimation';
import Dashboard from './Dashboard';

/* ═══════════════ CONSTANTS ═══════════════ */
const PAPER_COUNT = 10;

const LAYER_SPACING = 5;
const FIRST_LAYER_Y = 0;
const LAYERS = [
    { count: 8, y: FIRST_LAYER_Y },
    { count: 5, y: FIRST_LAYER_Y - LAYER_SPACING },
    { count: 3, y: FIRST_LAYER_Y - LAYER_SPACING * 2 },
    { count: 1, y: FIRST_LAYER_Y - LAYER_SPACING * 3 },
];

const OUTPUT_OFFSET_Y = -5;

const P = {
    stack: [0.00, 0.03],
    fly: [0.03, 0.10],
    cloudsIn: [0.10, 0.18],
    cloudsOut: [0.18, 0.26],
    facility: [0.26, 0.34],
    paperToInput: [0.30, 0.40],
    inputNodes: [0.34, 0.42],
    layer1to2: [0.42, 0.52],
    layer2to3: [0.52, 0.62],
    layer3toOut: [0.62, 0.70],
    outputConn: [0.70, 0.76],
    paperForm: [0.76, 0.86],
    summary: [0.86, 0.92],
    blurCta: [0.92, 1.00],
};

const CAMERA_TARGETS = {
    stack: { y: 8, z: 16 },
    fly: { y: 6, z: 16 },
    cloudsIn: { y: 4, z: 14 },
    cloudsOut: { y: 2, z: 13 },
    facility: { y: FIRST_LAYER_Y + 2, z: 12 },
    inputNodes: { y: FIRST_LAYER_Y, z: 11 },
    layer1to2: { y: (FIRST_LAYER_Y + FIRST_LAYER_Y - LAYER_SPACING) / 2, z: 12 },
    layer2to3: { y: (FIRST_LAYER_Y - LAYER_SPACING + FIRST_LAYER_Y - LAYER_SPACING * 2) / 2, z: 12 },
    layer3toOut: { y: (FIRST_LAYER_Y - LAYER_SPACING * 2 + FIRST_LAYER_Y - LAYER_SPACING * 3) / 2, z: 12 },
    outputConn: { y: FIRST_LAYER_Y - LAYER_SPACING * 3 - 2, z: 11 },
    paperForm: { y: FIRST_LAYER_Y - LAYER_SPACING * 3 + OUTPUT_OFFSET_Y, z: 9 },
    summary: { y: FIRST_LAYER_Y - LAYER_SPACING * 3 + OUTPUT_OFFSET_Y, z: 8 },
    blurCta: { y: FIRST_LAYER_Y - LAYER_SPACING * 3 + OUTPUT_OFFSET_Y - 2, z: 10 },
};

/* ═══════════════ HELPERS ═══════════════ */
const ph = (s, a, b) => THREE.MathUtils.clamp((s - a) / (b - a), 0, 1);
const sm = (t) => t * t * (3 - 2 * t);
const easeInOut = (t) => t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t;
const lA = (o, a, b, t) => {
    o[0] = THREE.MathUtils.lerp(a[0], b[0], t);
    o[1] = THREE.MathUtils.lerp(a[1], b[1], t);
    o[2] = THREE.MathUtils.lerp(a[2], b[2], t);
};

/* ═══════════════ NN GRAPH ═══════════════ */
const buildNodes = () =>
    LAYERS.map((l) =>
        Array.from({ length: l.count }, (_, i) => {
            const GAP = 1.8;
            const x = l.count === 1 ? 0 : (i - (l.count - 1) / 2) * GAP;
            const z = Math.sin((i + 1) * 1.73 + l.y * 0.31) * 0.34;
            return new THREE.Vector3(x, l.y, z);
        })
    );

const buildSparseConnections = (nodes) => {
    const connections = [];
    const seededRandom = (seed) => {
        let s = seed;
        return () => { s = (s * 16807 + 0) % 2147483647; return s / 2147483647; };
    };
    for (let l = 0; l < nodes.length - 1; l++) {
        const fromLayer = nodes[l];
        const toLayer = nodes[l + 1];
        const rng = seededRandom(l * 1000 + 42);
        const toConnected = new Set();
        for (let fi = 0; fi < fromLayer.length; fi++) {
            const numConns = 1 + (rng() > 0.5 ? 1 : 0);
            for (let c = 0; c < numConns; c++) {
                const idealIdx = Math.round((fi / Math.max(fromLayer.length - 1, 1)) * (toLayer.length - 1));
                let targetIdx;
                if (rng() > 0.3) {
                    const offset = Math.floor((rng() - 0.5) * 2);
                    targetIdx = THREE.MathUtils.clamp(idealIdx + offset, 0, toLayer.length - 1);
                } else {
                    targetIdx = Math.floor(rng() * toLayer.length);
                }
                const exists = connections.some(conn =>
                    conn.layer === l && conn.from.equals(fromLayer[fi]) && conn.to.equals(toLayer[targetIdx])
                );
                if (!exists) {
                    connections.push({
                        from: fromLayer[fi].clone(), to: toLayer[targetIdx].clone(),
                        layer: l, fromIdx: fi, toIdx: targetIdx,
                    });
                    toConnected.add(targetIdx);
                }
            }
        }
        for (let ti = 0; ti < toLayer.length; ti++) {
            if (!toConnected.has(ti)) {
                const fi = Math.round((ti / Math.max(toLayer.length - 1, 1)) * (fromLayer.length - 1));
                connections.push({
                    from: fromLayer[fi].clone(), to: toLayer[ti].clone(),
                    layer: l, fromIdx: fi, toIdx: ti,
                });
            }
        }
    }
    return connections;
};

/* ═══════════════ TEXTURES ═══════════════ */
const createScribbleTexture = (seed = 0) => {
    if (typeof document === 'undefined') return null;
    const c = document.createElement('canvas');
    c.width = 512; c.height = 720;
    const ctx = c.getContext('2d');
    let s = seed * 9301 + 49297;
    const rng = () => { s = (s * 9301 + 49297) % 233280; return s / 233280; };

    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, 512, 720);

    for (let i = 0; i < 1800; i++) {
        const warm = rng() > 0.48;
        ctx.fillStyle = warm ? `rgba(170,178,188,${0.006 + rng() * 0.016})` : `rgba(230,236,244,${0.008 + rng() * 0.018})`;
        ctx.fillRect(rng() * 512, rng() * 720, 0.7 + rng() * 1.6, 0.7 + rng() * 1.8);
    }

    ctx.strokeStyle = 'rgba(168, 184, 204, 0.08)';
    ctx.lineWidth = 0.8;
    for (let i = 0; i < 70; i++) {
        const y = rng() * 720;
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.bezierCurveTo(160, y + (rng() - 0.5) * 18, 340, y + (rng() - 0.5) * 16, 512, y + (rng() - 0.5) * 10);
        ctx.stroke();
    }

    ctx.font = '700 32px "Playfair Display", serif';
    ctx.fillStyle = '#0d1f3a'; ctx.textAlign = 'left';
    ctx.fillText('Research Paper', 40, 58);
    ctx.strokeStyle = 'rgba(45,102,184,0.55)'; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(40, 68); ctx.lineTo(280, 68); ctx.stroke();
    ctx.strokeStyle = 'rgba(72,54,30,0.18)'; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(40, 80); ctx.lineTo(472, 80); ctx.stroke();
    ctx.lineCap = 'round'; ctx.lineJoin = 'round';
    for (let l = 0; l < 22; l++) {
        const y = 100 + l * 27 + (rng() - 0.5) * 3;
        const isShort = l >= 20 || l === 8 || l === 14;
        const w = isShort ? 60 + rng() * 100 : 280 + rng() * 150;
        ctx.strokeStyle = `rgba(30,30,30,${0.24 + rng() * 0.18})`;
        ctx.lineWidth = 1.35 + rng() * 0.55;
        ctx.beginPath();
        let lx = 40; ctx.moveTo(lx, y);
        while (lx < 40 + w) { lx += 3 + rng() * 8; ctx.lineTo(Math.min(lx, 40 + w), y + (rng() - 0.5) * 1.2); }
        ctx.stroke();
    }

    ctx.strokeStyle = 'rgba(176, 190, 208, 0.45)'; ctx.lineWidth = 3;
    ctx.strokeRect(3, 3, 506, 714);
    ctx.strokeStyle = 'rgba(255,255,255,0.72)'; ctx.lineWidth = 1;
    ctx.strokeRect(8, 8, 496, 704);

    const t = new THREE.CanvasTexture(c);
    t.needsUpdate = true; t.anisotropy = 16;
    return t;
};

const createPixelRevealTexture = (pixelProgress, borderProgress) => {
    if (typeof document === 'undefined') return null;
    const c = document.createElement('canvas');
    c.width = 512; c.height = 720;
    const ctx = c.getContext('2d');
    ctx.clearRect(0, 0, 512, 720);
    if (pixelProgress <= 0) return new THREE.CanvasTexture(c);
    const fullCanvas = document.createElement('canvas');
    fullCanvas.width = 512; fullCanvas.height = 720;
    const fullCtx = fullCanvas.getContext('2d');
    fullCtx.fillStyle = '#ffffff'; fullCtx.fillRect(0, 0, 512, 720);
    let s = 77;
    const rng = () => { s = (s * 9301 + 49297) % 233280; return s / 233280; };
    fullCtx.font = '700 36px "Playfair Display", serif';
    fullCtx.fillStyle = '#0d1f3a'; fullCtx.textAlign = 'left';
    fullCtx.fillText('SUMMARY', 50, 70);
    fullCtx.strokeStyle = 'rgba(45,102,184,0.45)'; fullCtx.lineWidth = 2;
    fullCtx.beginPath(); fullCtx.moveTo(50, 82); fullCtx.lineTo(240, 82); fullCtx.stroke();
    fullCtx.strokeStyle = 'rgba(0,0,0,0.07)'; fullCtx.lineWidth = 1;
    fullCtx.beginPath(); fullCtx.moveTo(50, 95); fullCtx.lineTo(462, 95); fullCtx.stroke();
    for (let l = 0; l < 20; l++) {
        const y = 120 + l * 26 + (rng() - 0.5) * 2;
        const isShort = l === 19 || l === 8 || l === 14;
        const lineWidth = isShort ? 80 + rng() * 100 : 340 + rng() * 90;
        fullCtx.strokeStyle = `rgba(13,31,58,${0.38 + rng() * 0.22})`;
        fullCtx.lineWidth = 1.3 + rng() * 0.4; fullCtx.lineCap = 'round';
        fullCtx.beginPath();
        let lx = 50; fullCtx.moveTo(lx, y);
        while (lx < 50 + lineWidth) { lx += 3 + rng() * 7; fullCtx.lineTo(Math.min(lx, 50 + lineWidth), y + (rng() - 0.5) * 1); }
        fullCtx.stroke();
    }
    const blockSize = 8;
    const cols = Math.ceil(512 / blockSize), rows = Math.ceil(720 / blockSize);
    const centerX = cols / 2, centerY = rows / 2;
    const blocks = []; let maxDist = 0;
    for (let r = 0; r < rows; r++) {
        for (let c2 = 0; c2 < cols; c2++) {
            const dx = c2 - centerX, dy = r - centerY;
            const dist = Math.sqrt(dx * dx + dy * dy);
            const jitter = ((c2 * 7 + r * 13) % 17) / 17.0 * 3;
            const finalDist = dist + jitter;
            if (finalDist > maxDist) maxDist = finalDist;
            blocks.push({ c: c2, r, dist: finalDist });
        }
    }
    const fadeWindow = 0.25;
    for (let i = 0; i < blocks.length; i++) {
        const block = blocks[i];
        const startFade = (block.dist / maxDist) * (1.0 - fadeWindow);
        let blockAlpha = (pixelProgress - startFade) / fadeWindow;
        blockAlpha = Math.max(0, Math.min(1, blockAlpha));
        if (blockAlpha > 0) {
            ctx.globalAlpha = blockAlpha;
            const sx = block.c * blockSize, sy = block.r * blockSize;
            ctx.drawImage(fullCanvas, sx, sy, blockSize, blockSize, sx, sy, blockSize, blockSize);
        }
    }
    ctx.globalAlpha = 1.0;
    if (borderProgress > 0) {
        ctx.strokeStyle = '#0d1f3a'; ctx.lineWidth = 3;
        const w = 508, h = 716, perimeter = (w + h) * 2;
        ctx.beginPath(); ctx.rect(2, 2, w, h);
        ctx.setLineDash([borderProgress * perimeter, perimeter]); ctx.stroke();
    }
    const t = new THREE.CanvasTexture(c);
    t.needsUpdate = true; t.anisotropy = 16;
    return t;
};

/* ═══════════════ CLOUD TEXTURE ═══════════════ */
const createCloudTexture = (seed = 0) => {
    if (typeof document === 'undefined') return null;
    const size = 512;
    const c = document.createElement('canvas');
    c.width = size; c.height = size;
    const ctx = c.getContext('2d');

    let s = seed * 7919 + 104729;
    const rng = () => { s = (s * 16807) % 2147483647; return s / 2147483647; };

    ctx.clearRect(0, 0, size, size);

    const blobs = 52 + Math.floor(rng() * 18);
    const cx = size / 2;
    const cy = size / 2;

    for (let i = 0; i < blobs; i++) {
        const angle = rng() * Math.PI * 2;
        const dist = rng() * size * 0.34;
        const bx = cx + Math.cos(angle) * dist;
        const by = cy + Math.sin(angle) * dist * 0.42 - size * 0.03;
        const r = size * (0.08 + rng() * 0.18);

        const g = ctx.createRadialGradient(bx, by, 0, bx, by, r);
        const w = 248 + Math.floor(rng() * 7);
        g.addColorStop(0, `rgba(${w},${w},255,${0.46 + rng() * 0.22})`);
        g.addColorStop(0.48, `rgba(${w - 10},${w - 8},${w + 1},${0.26 + rng() * 0.14})`);
        g.addColorStop(1, 'rgba(215,230,247,0)');

        ctx.fillStyle = g;
        ctx.beginPath();
        ctx.ellipse(bx, by, r * (1 + rng() * 0.5), r * (0.45 + rng() * 0.25), rng() * 0.4 - 0.2, 0, Math.PI * 2);
        ctx.fill();
    }

    const under = ctx.createLinearGradient(0, size * 0.5, 0, size);
    under.addColorStop(0, 'rgba(0,0,0,0)');
    under.addColorStop(0.65, 'rgba(180,205,232,0.045)');
    under.addColorStop(1, 'rgba(92,122,170,0.13)');
    ctx.fillStyle = under;
    ctx.fillRect(0, 0, size, size);

    const t = new THREE.CanvasTexture(c);
    t.needsUpdate = true;
    return t;
};

/* ═══════════════ SINGLE CLOUD MESH ═══════════════ */
const CloudMesh = ({ cloudData, scrollProgress }) => {
    const meshRef = useRef(null);
    const { baseX, fixedY, fixedZ, speed, scaleX, scaleY, seed, side } = cloudData;
    const texture = useMemo(() => createCloudTexture(seed), [seed]);

    useFrame(({ clock }) => {
        if (!meshRef.current) return;
        const t = clock.getElapsedTime();
        const s = scrollProgress.current;

        const cloudsInP = sm(ph(s, ...P.cloudsIn));
        const cloudsOutP = sm(ph(s, ...P.cloudsOut));

        const drift = ((t * speed * 0.4 + seed * 10) % 60) - 30;
        const restX = baseX + drift;
        const rushTarget = side * 0.15;
        const rushX = THREE.MathUtils.lerp(restX, rushTarget, cloudsInP);
        const retreatX = THREE.MathUtils.lerp(rushX, restX + side * 14, cloudsOutP);
        const finalX = retreatX;
        const finalY = fixedY + Math.sin(t * 0.08 + seed * 2.3) * 0.15;

        meshRef.current.position.set(finalX, finalY, fixedZ);
        meshRef.current.scale.set(scaleX, scaleY, 1);

        let opacity;
        if (s < P.cloudsIn[0]) {
            opacity = 0.45 + Math.sin(t * 0.1 + seed) * 0.04;
        } else if (s < P.cloudsIn[1]) {
            opacity = THREE.MathUtils.lerp(0.45, 0.98, cloudsInP);
        } else if (s < P.cloudsOut[1]) {
            opacity = THREE.MathUtils.lerp(0.98, 0, cloudsOutP);
        } else {
            opacity = 0;
        }

        meshRef.current.material.opacity = opacity;
    });

    return (
        <mesh ref={meshRef} position={[baseX, fixedY, fixedZ]}>
            <planeGeometry args={[0, 0]} />
            <meshBasicMaterial
                map={texture}
                transparent
                opacity={0}
                depthWrite={false}
            />
        </mesh>
    );
};

/* ═══════════════ CLOUD SYSTEM ═══════════════ */
const CloudSystem = ({ scrollProgress }) => {
    const clouds = useMemo(() => {
        const result = [];
        let s = 42;
        const rng = () => { s = (s * 16807) % 2147483647; return s / 2147483647; };

        const count = 26;
        for (let i = 0; i < count; i++) {
            const side = i < count / 2 ? -1 : 1;
            const row = i % 4;
            result.push({
                baseX: side * (4 + rng() * 6),
                fixedY: 6 + row * 2.2 + (rng() - 0.5) * 1.5,
                fixedZ: -2.5 - rng() * 4 - row * 1.4,
                speed: 0.05 + rng() * 0.1,
                scaleX: 5 + rng() * 7,
                scaleY: 2.8 + rng() * 2.3,
                seed: i * 13 + 7,
                side: side,
            });
        }
        return result;
    }, []);

    return (
        <group>
            {clouds.map((cloud, i) => (
                <CloudMesh
                    key={`cloud-${i}`}
                    cloudData={cloud}
                    scrollProgress={scrollProgress}
                />
            ))}
        </group>
    );
};

/* ═══════════════ AMBIENT PARTICLES ═══════════════ */
const AmbientParticles = ({ scrollProgress }) => {
    const ref = useRef(null);
    const N = 60;
    const basePositions = useMemo(() => {
        const p = new Float32Array(N * 3);
        for (let i = 0; i < N; i++) {
            p[i * 3] = (Math.random() - 0.5) * 30;
            p[i * 3 + 1] = (Math.random() - 0.5) * 80 + FIRST_LAYER_Y - LAYER_SPACING * 1.5;
            p[i * 3 + 2] = -12 - Math.random() * 10;
        }
        return p;
    }, []);

    useFrame(({ clock }) => {
        if (!ref.current) return;
        const t = clock.getElapsedTime();
        const s = scrollProgress.current;
        const facilityP = sm(ph(s, ...P.facility));
        const arr = ref.current.geometry.attributes.position.array;
        for (let i = 0; i < N; i++) {
            arr[i * 3 + 1] = basePositions[i * 3 + 1] + Math.sin(t * 0.12 + i * 0.4) * 0.2;
        }
        ref.current.geometry.attributes.position.needsUpdate = true;
        ref.current.material.opacity = facilityP * 0.10;
    });

    return (
        <points ref={ref}>
            <bufferGeometry>
                <bufferAttribute attach="attributes-position" args={[basePositions, 3]} />
            </bufferGeometry>
            <pointsMaterial color="#2566b8" transparent opacity={0} size={0.025} sizeAttenuation />
        </points>
    );
};

/* ═══════════════ PAPER CARD ═══════════════ */
const PaperCard = ({ index, phases, stackPos, flyPos, inputTarget, scrollProgress }) => {
    const meshRef = useRef(null);
    const pos = useMemo(() => [0, 0, 0], []);
    const texture = useMemo(() => createScribbleTexture(index), [index]);

    const waveParams = useMemo(() => ({
        freq1: 1.5 + Math.random() * 1.5, freq2: 0.8 + Math.random() * 1.0, freq3: 2.0 + Math.random() * 1.0,
        amp1: 0.12 + Math.random() * 0.08, amp2: 0.06 + Math.random() * 0.06, amp3: 0.04 + Math.random() * 0.03,
        phase1: Math.random() * Math.PI * 2, phase2: Math.random() * Math.PI * 2, phase3: Math.random() * Math.PI * 2,
    }), []);

    const rRot = useMemo(() => [Math.random() * 4 - 2, Math.random() * 4 - 2, Math.random() * 4 - 2], []);
    const geometry = useMemo(() => new THREE.PlaneGeometry(5, 6.5, 14, 18), []);
    const origPositions = useMemo(() => geometry.attributes.position.array.slice(), [geometry]);

    useFrame(({ clock }) => {
        if (!meshRef.current) return;
        const t = clock.getElapsedTime();
        const s = scrollProgress.current;

        const flyP = phases.current.fly;
        const toNodeP = phases.current.paperToInput;

        lA(pos, stackPos, flyPos, flyP);

        // No idle bobbing — papers sit perfectly still until scroll begins
        const arriveP = sm(ph(toNodeP, 0.0, 0.65));

        if (inputTarget) {
            pos[0] = THREE.MathUtils.lerp(pos[0], inputTarget.x, arriveP);
            pos[1] = THREE.MathUtils.lerp(pos[1], inputTarget.y, arriveP);
            pos[2] = THREE.MathUtils.lerp(pos[2], inputTarget.z + 0.02, arriveP);
        }

        meshRef.current.position.set(pos[0], pos[1], pos[2]);

        // Rotation waves only kick in once fly phase starts, and settle when arriving
        const bz = index * 0.035;
        const rotateSettle = 1 - arriveP;
        meshRef.current.rotation.set(
            rRot[0] * flyP * rotateSettle + Math.sin(t * waveParams.freq1 + waveParams.phase1) * 0.2 * flyP * rotateSettle,
            rRot[1] * flyP * rotateSettle + Math.sin(t * waveParams.freq2 + waveParams.phase2) * 0.8 * flyP * rotateSettle,
            bz * (1 - flyP) + rRot[2] * flyP * rotateSettle + Math.sin(t * waveParams.freq3 + waveParams.phase3) * 0.12 * flyP * rotateSettle
        );

        // Flip and vanish happen ONLY after arriving
        const flipP = sm(ph(toNodeP, 0.65, 1.0));
        meshRef.current.rotation.y += Math.PI * 1.25 * flipP;
        meshRef.current.rotation.x += Math.PI * 0.15 * flipP;

        // Shrink to node size while arriving, then shrink into nothingness while flipping
        let scaleNow = 1.3;
        if (arriveP < 1.0) {
            scaleNow = THREE.MathUtils.lerp(1.3, 0.35, arriveP);
        } else {
            scaleNow = THREE.MathUtils.lerp(0.35, 0.0, flipP);
        }
        meshRef.current.scale.setScalar(scaleNow);

        const bendIntensity = flyP * rotateSettle;
        const positions = meshRef.current.geometry.attributes.position.array;
        if (bendIntensity > 0.01) {
            const segW = 14, segH = 18, vpr = segW + 1;
            for (let j = 0; j <= segH; j++) {
                for (let i = 0; i <= segW; i++) {
                    const idx = (j * vpr + i) * 3;
                    const ox = origPositions[idx], oy = origPositions[idx + 1], oz = origPositions[idx + 2];
                    const nx = (ox / 2.8) + 0.5, ny = (oy / 3.5) + 0.5;
                    const w1 = Math.sin(nx * Math.PI * 2.5 + t * waveParams.freq1 * 2.5) * waveParams.amp1 * bendIntensity;
                    const w2 = Math.sin(ny * Math.PI * 2.0 + t * waveParams.freq2 * 2.5) * waveParams.amp2 * bendIntensity;
                    const ef = Math.sin(nx * Math.PI) * Math.sin(ny * Math.PI);
                    const fl = Math.sin(t * 5.0 + ny * Math.PI * 4) * 0.06 * bendIntensity * ef;
                    positions[idx] = ox; positions[idx + 1] = oy; positions[idx + 2] = oz + w1 + w2 + fl;
                }
            }
            meshRef.current.geometry.attributes.position.needsUpdate = true;
            meshRef.current.geometry.computeVertexNormals();
        } else {
            for (let k = 0; k < positions.length; k++) positions[k] = origPositions[k];
            meshRef.current.geometry.attributes.position.needsUpdate = true;
        }

        const vanishP = sm(ph(toNodeP, 0.70, 0.95));
        const finalOpacity = 1.0 * (1 - vanishP);
        meshRef.current.material.transparent = finalOpacity < 0.995;
        meshRef.current.material.opacity = finalOpacity;
        meshRef.current.visible = finalOpacity > 0.015;

        if (s > P.paperToInput[1] - 0.01) {
            meshRef.current.material.opacity = 0;
            meshRef.current.visible = false;
        }
    });

    return (
        <group>
            <mesh ref={meshRef} geometry={geometry}>
                <meshBasicMaterial map={texture || null} transparent={false} toneMapped={false} side={THREE.DoubleSide} color="#ffffff" />
            </mesh>
        </group>
    );
};

/* ═══════════════ NODE GLOW TEXTURE ═══════════════ */
const _glowTexture = (() => {
    if (typeof document === 'undefined') return null;
    const c = document.createElement('canvas');
    c.width = 128; c.height = 128;
    const ctx = c.getContext('2d');
    const g = ctx.createRadialGradient(64, 64, 0, 64, 64, 64);
    g.addColorStop(0, 'rgba(14,35,130,0.6)');
    g.addColorStop(0.3, 'rgba(10,25,100,0.35)');
    g.addColorStop(0.6, 'rgba(6,18,80,0.14)');
    g.addColorStop(1, 'rgba(3,8,40,0)');
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, 128, 128);
    const t = new THREE.CanvasTexture(c);
    t.needsUpdate = true;
    return t;
})();

/* ═══════════════ NETWORK NODE ═══════════════ */
const NetworkNode = ({ position, phases, isOutput, layerIndex }) => {
    const groupRef = useRef(null);
    const coreRef = useRef(null);
    const glowRef = useRef(null);
    const nodeColor = useMemo(() => new THREE.Color('#155fbd'), []);
    const outputColor = useMemo(() => new THREE.Color('#155fbd'), []);
    const darkColor = useMemo(() => new THREE.Color('#07183f'), []);

    useFrame(({ clock }) => {
        if (!coreRef.current) return;
        const t = clock.getElapsedTime();
        let nodeAppear = 0;
        const baseSize = isOutput ? 0.50 : 0.25;

        if (groupRef.current) {
            const depthDrift = Math.sin(t * 0.28 + layerIndex * 1.8 + position.x * 0.35) * 0.045;
            const lateralDrift = Math.cos(t * 0.22 + layerIndex * 1.2) * 0.012;
            groupRef.current.position.set(position.x + lateralDrift, position.y, position.z + depthDrift);
        }

        if (layerIndex === 0) nodeAppear = phases.current.inputNodes;
        else if (layerIndex === 1) nodeAppear = sm(ph(phases.current.layer1to2Raw, 0.5, 1.0));
        else if (layerIndex === 2) nodeAppear = sm(ph(phases.current.layer2to3Raw, 0.5, 1.0));
        else if (layerIndex === 3) nodeAppear = sm(ph(phases.current.layer3toOutRaw, 0.5, 1.0));

        const a = sm(nodeAppear);
        coreRef.current.scale.setScalar(a * baseSize);
        const tc = isOutput ? outputColor : nodeColor;
        const dc = new THREE.Color().lerpColors(darkColor, tc, a);
        coreRef.current.material.color.copy(dc);
        coreRef.current.material.emissive.copy(dc);
        coreRef.current.material.emissiveIntensity = a * (isOutput ? 1.85 : 1.45);
        coreRef.current.material.opacity = a;

        // Glow halo — scales larger than node, pulses gently
        if (glowRef.current) {
            const glowScale = a * baseSize * (isOutput ? 6.2 : 4.8);
            const pulse = 1 + Math.sin(t * 2.0 + layerIndex * 1.5) * 0.12;
            glowRef.current.scale.setScalar(glowScale * pulse);
            glowRef.current.material.opacity = a * (isOutput ? 0.34 : 0.24);
        }
    });

    return (
        <group ref={groupRef} position={position}>
            {/* Glow halo — behind the node */}
            <mesh ref={glowRef} position={[0, 0, -0.05]}>
                <planeGeometry args={[1, 1]} />
                <meshBasicMaterial
                    map={_glowTexture || null}
                    transparent
                    opacity={0}
                    depthWrite={false}
                    blending={THREE.AdditiveBlending}
                    side={THREE.DoubleSide}
                />
            </mesh>
            {/* Core sphere */}
            <mesh ref={coreRef}>
                <sphereGeometry args={[1, 36, 36]} />
                <meshStandardMaterial color="#0a1840" emissive="#0a1840" emissiveIntensity={0} transparent opacity={0} />
            </mesh>
        </group>
    );
};

/* ═══════════════ CURVED CONNECTION ═══════════════ */
const CurvedConnection = ({ from, to, phases, layer, connectionIndex }) => {
    const groupRef = useRef(null);
    const curveLineRef = useRef(null);
    const ghostLineRef = useRef(null);
    const particleRef = useRef(null);
    const particleTwoRef = useRef(null);

    const { curve } = useMemo(() => {
        const cp1 = new THREE.Vector3(from.x, from.y + (to.y - from.y) * 0.7, Math.abs(to.x - from.x) * 0.04);
        const cp2 = new THREE.Vector3(to.x, to.y - (to.y - from.y) * 0.1, Math.abs(to.x - from.x) * 0.02);
        return { curve: new THREE.CubicBezierCurve3(from, cp1, cp2, to) };
    }, [from, to]);

    const particleDelay = useMemo(() => connectionIndex * 0.3 + Math.random() * 1.0, [connectionIndex]);
    const particleSpeed = useMemo(() => 0.45 + Math.random() * 0.2, []);

    useFrame(({ clock }) => {
        if (!curveLineRef.current) return;
        const t = clock.getElapsedTime();

        if (groupRef.current) {
            groupRef.current.position.z = Math.sin(t * 0.24 + layer * 1.7 + connectionIndex * 0.19) * 0.032;
            groupRef.current.position.x = Math.cos(t * 0.18 + connectionIndex * 0.13) * 0.008;
        }

        let cp = 0;
        if (layer === 0) cp = sm(ph(phases.current.layer1to2Raw, 0.0, 0.45));
        else if (layer === 1) cp = sm(ph(phases.current.layer2to3Raw, 0.0, 0.45));
        else if (layer === 2) cp = sm(ph(phases.current.layer3toOutRaw, 0.0, 0.45));

        if (cp > 0.005) {
            const numPts = Math.max(2, Math.floor(120 * cp));
            const partialPoints = [];
            for (let i = 0; i <= numPts; i++) partialPoints.push(curve.getPoint((i / numPts) * cp));
            const ng = new THREE.BufferGeometry().setFromPoints(partialPoints);
            if (curveLineRef.current.geometry) curveLineRef.current.geometry.dispose();
            curveLineRef.current.geometry = ng;
            if (ghostLineRef.current) {
                if (ghostLineRef.current.geometry) ghostLineRef.current.geometry.dispose();
                ghostLineRef.current.geometry = ng.clone();
            }
        }

        const signalWave = 0.72 + Math.sin(t * 1.9 + connectionIndex * 0.65) * 0.18;
        curveLineRef.current.material.opacity = cp > 0.005 ? (0.22 + cp * 0.34) * signalWave : 0;
        if (ghostLineRef.current) ghostLineRef.current.material.opacity = cp > 0.005 ? 0.10 + cp * 0.16 : 0;

        let particleT = -1;
        if (cp > 0.9) {
            const flowTime = (t - particleDelay) * particleSpeed;
            if (flowTime > 0) {
                const cycleTime = flowTime % 1.8;
                if (cycleTime < 1.2) particleT = easeInOut(Math.min(cycleTime / 1.2, 1.0));
            }
        }

        if (particleRef.current) {
            if (particleT >= 0 && particleT <= 1) {
                const particlePos = curve.getPoint(particleT);
                particleRef.current.position.copy(particlePos);
                particleRef.current.scale.setScalar(0.075);
                particleRef.current.material.opacity = 0.88;
            } else {
                particleRef.current.scale.setScalar(0);
                particleRef.current.material.opacity = 0;
            }
        }

        if (particleTwoRef.current) {
            const delayedT = particleT >= 0 ? Math.max(0, particleT - 0.34) : -1;
            if (delayedT >= 0 && delayedT <= 1) {
                particleTwoRef.current.position.copy(curve.getPoint(delayedT));
                particleTwoRef.current.scale.setScalar(0.045);
                particleTwoRef.current.material.opacity = 0.34;
            } else {
                particleTwoRef.current.scale.setScalar(0);
                particleTwoRef.current.material.opacity = 0;
            }
        }
    });

    const initGeo = useMemo(() => new THREE.BufferGeometry().setFromPoints([from.clone(), from.clone()]), [from]);

    return (
        <group ref={groupRef}>
            <line ref={curveLineRef} geometry={initGeo}>
                <lineBasicMaterial color="#1e6eff" transparent opacity={0} linewidth={1} />
            </line>
            <line ref={ghostLineRef} geometry={initGeo.clone()}>
                <lineBasicMaterial color="#bdeaff" transparent opacity={0} linewidth={1} />
            </line>
            <mesh ref={particleRef} scale={0}>
                <sphereGeometry args={[1, 16, 16]} />
                <meshStandardMaterial color="#5ab8e6" emissive="#287fc0" emissiveIntensity={1.7} transparent opacity={0} />
            </mesh>
            <mesh ref={particleTwoRef} scale={0}>
                <sphereGeometry args={[1, 12, 12]} />
                <meshStandardMaterial color="#a8dcf2" emissive="#2c77a8" emissiveIntensity={1.2} transparent opacity={0} />
            </mesh>
        </group>
    );
};

/* ═══════════════ OUTPUT CONNECTION ═══════════════ */
const OutputConnection = ({ phases, outputNodePos }) => {
    const lineRef = useRef(null);
    const particleRef = useRef(null);

    const startPos = useMemo(() => outputNodePos.clone().add(new THREE.Vector3(0, 0, -0.35)), [outputNodePos]);
    const endPos = useMemo(
        () => new THREE.Vector3(outputNodePos.x, outputNodePos.y + OUTPUT_OFFSET_Y, outputNodePos.z - 0.35),
        [outputNodePos]
    );
    const curve = useMemo(() => {
        const cp1 = new THREE.Vector3(startPos.x + 0.3, startPos.y + OUTPUT_OFFSET_Y * 0.3, 0.2);
        const cp2 = new THREE.Vector3(endPos.x - 0.3, endPos.y - OUTPUT_OFFSET_Y * 0.1, 0.15);
        return new THREE.CubicBezierCurve3(startPos, cp1, cp2, endPos);
    }, [startPos, endPos]);

    useFrame(({ clock }) => {
        if (!lineRef.current) return;
        const t = clock.getElapsedTime();
        const cp = sm(phases.current.outputConn);

        if (cp > 0.01) {
            const numPts = Math.max(2, Math.floor(40 * cp));
            const points = [];
            for (let i = 0; i <= numPts; i++) points.push(curve.getPoint((i / numPts) * cp));
            const ng = new THREE.BufferGeometry().setFromPoints(points);
            if (lineRef.current.geometry) lineRef.current.geometry.dispose();
            lineRef.current.geometry = ng;
        }

        lineRef.current.material.opacity = cp > 0.01 ? 0.2 + cp * 0.2 : 0;

        if (particleRef.current && cp > 0.95) {
            const pt = ((t * 0.12) % 2.5);
            if (pt < 1.5) {
                const pp = curve.getPoint(easeInOut(pt / 1.5));
                particleRef.current.position.copy(pp);
                particleRef.current.scale.setScalar(0.06);
                particleRef.current.material.opacity = 0.7;
            } else {
                particleRef.current.scale.setScalar(0);
            }
        }
    });

    const initGeo = useMemo(() => new THREE.BufferGeometry().setFromPoints([startPos.clone(), startPos.clone()]), [startPos]);

    return (
        <group>
            <line ref={lineRef} geometry={initGeo}>
                <lineBasicMaterial color="#1240b0" transparent opacity={0} linewidth={1} />
            </line>
            <mesh ref={particleRef} scale={0}>
                <sphereGeometry args={[1, 10, 10]} />
                <meshStandardMaterial color="#3a7ef5" emissive="#3a7ef5" emissiveIntensity={2.0} transparent opacity={0} />
            </mesh>
        </group>
    );
};

/* ═══════════════ OUTPUT CARD ═══════════════ */
const OutputCard = ({ phases, scrollProgress, outputNodePos }) => {
    const gRef = useRef(null);
    const pixelRef = useRef(null);
    const cardPos = useMemo(() => new THREE.Vector3(outputNodePos.x, outputNodePos.y + OUTPUT_OFFSET_Y, outputNodePos.z), [outputNodePos]);
    const currentTextureRef = useRef(null);
    const lastPP = useRef(-1);
    const lastBP = useRef(-1);

    useFrame(({ clock }) => {
        if (!gRef.current) return;
        const t = clock.getElapsedTime();
        const s = scrollProgress.current;
        const paperP = sm(ph(s, ...P.paperForm));
        const summP = sm(ph(s, ...P.summary));
        const appear = sm(Math.min(paperP * 1.5, 1));

        gRef.current.position.set(cardPos.x, cardPos.y + Math.sin(t * 0.8) * 0.03 * appear, cardPos.z);
        gRef.current.scale.setScalar(appear * 1.8);

        if (pixelRef.current) {
            const pd = Math.abs(paperP - lastPP.current);
            const bd = Math.abs(summP - lastBP.current);
            if (pd > 0.008 || bd > 0.008) {
                lastPP.current = paperP; lastBP.current = summP;
                if (currentTextureRef.current) currentTextureRef.current.dispose();
                currentTextureRef.current = createPixelRevealTexture(paperP, summP);
                pixelRef.current.material.map = currentTextureRef.current;
                pixelRef.current.material.needsUpdate = true;
            }
        }
    });

    return (
        <group ref={gRef} scale={0}>
            <mesh ref={pixelRef}>
                <planeGeometry args={[2.5, 3.5]} />
                <meshBasicMaterial transparent toneMapped={false} side={THREE.DoubleSide} />
            </mesh>
        </group>
    );
};

/* ═══════════════ TRACKING CAMERA ═══════════════ */
const TrackingCamera = ({ scrollProgress }) => {
    const { camera } = useThree();
    const currentY = useRef(CAMERA_TARGETS.stack.y);
    const currentZ = useRef(CAMERA_TARGETS.stack.z);
    const lookAtY = useRef(CAMERA_TARGETS.stack.y);

    useFrame(({ clock }) => {
        const t = clock.getElapsedTime();
        const s = scrollProgress.current;

        let targetY, targetZ;
        const cameraPhases = [
            { range: P.stack, from: CAMERA_TARGETS.stack, to: CAMERA_TARGETS.stack },
            { range: P.fly, from: CAMERA_TARGETS.stack, to: CAMERA_TARGETS.fly },
            { range: P.cloudsIn, from: CAMERA_TARGETS.fly, to: CAMERA_TARGETS.cloudsIn },
            { range: P.cloudsOut, from: CAMERA_TARGETS.cloudsIn, to: CAMERA_TARGETS.cloudsOut },
            { range: P.facility, from: CAMERA_TARGETS.cloudsOut, to: CAMERA_TARGETS.facility },
            { range: P.inputNodes, from: CAMERA_TARGETS.facility, to: CAMERA_TARGETS.inputNodes },
            { range: P.layer1to2, from: CAMERA_TARGETS.inputNodes, to: CAMERA_TARGETS.layer1to2 },
            { range: P.layer2to3, from: CAMERA_TARGETS.layer1to2, to: CAMERA_TARGETS.layer2to3 },
            { range: P.layer3toOut, from: CAMERA_TARGETS.layer2to3, to: CAMERA_TARGETS.layer3toOut },
            { range: P.outputConn, from: CAMERA_TARGETS.layer3toOut, to: CAMERA_TARGETS.outputConn },
            { range: P.paperForm, from: CAMERA_TARGETS.outputConn, to: CAMERA_TARGETS.paperForm },
            { range: P.summary, from: CAMERA_TARGETS.paperForm, to: CAMERA_TARGETS.summary },
            { range: P.blurCta, from: CAMERA_TARGETS.summary, to: CAMERA_TARGETS.blurCta },
        ];

        let found = false;
        for (const phase of cameraPhases) {
            if (s <= phase.range[1]) {
                const p = easeInOut(ph(s, ...phase.range));
                targetY = THREE.MathUtils.lerp(phase.from.y, phase.to.y, p);
                targetZ = THREE.MathUtils.lerp(phase.from.z, phase.to.z, p);
                found = true;
                break;
            }
        }
        if (!found) {
            targetY = CAMERA_TARGETS.blurCta.y;
            targetZ = CAMERA_TARGETS.blurCta.z;
        }

        const dampSpeed = 0.04;
        currentY.current += (targetY - currentY.current) * dampSpeed;
        currentZ.current += (targetZ - currentZ.current) * dampSpeed;
        lookAtY.current += (targetY - lookAtY.current) * dampSpeed;

        const breathX = Math.sin(t * 0.12) * 0.06;
        const breathY = Math.cos(t * 0.1) * 0.04;

        camera.position.set(breathX, currentY.current + breathY, currentZ.current);
        camera.lookAt(0, lookAtY.current, 0);
    });

    return null;
};

/* ═══════════════ SCENE ═══════════════ */
const Scene = ({ scrollProgress }) => {
    const phases = useRef({
        fly: 0, inputNodes: 0, paperToInput: 0,
        layer1to2: 0, layer1to2Raw: 0,
        layer2to3: 0, layer2to3Raw: 0,
        layer3toOut: 0, layer3toOutRaw: 0,
        outputConn: 0, paperForm: 0,
        cloudsIn: 0, cloudsOut: 0, facility: 0,
    });

    const stackPositions = useMemo(() =>
        Array.from({ length: PAPER_COUNT }, (_, i) => [
            7.5 + (Math.random() - 0.5) * 0.4,
            8 + (Math.random() - 0.5) * 0.4,
            i * 0.035,
        ]), []);

    const flyPositions = useMemo(() =>
        Array.from({ length: PAPER_COUNT }, (_, i) => {
            const angle = (i / PAPER_COUNT) * Math.PI * 2 + Math.random() * 0.8;
            const r = 4 + Math.random() * 4;
            return [r * Math.cos(angle) * 0.6, 6 + r * Math.sin(angle) * 0.5, (Math.random() - 0.5) * 2.5];
        }), []);

    const networkNodes = useMemo(() => buildNodes(), []);
    const connections = useMemo(() => buildSparseConnections(networkNodes), [networkNodes]);

    const flatNodes = useMemo(() => {
        const r = [];
        networkNodes.forEach((layer, li) =>
            layer.forEach((pos, ni) => r.push({
                pos, layerIndex: li, nodeIndex: ni,
                isOutput: li === networkNodes.length - 1,
            }))
        );
        return r;
    }, [networkNodes]);

    const inputLayerNodes = useMemo(() => networkNodes[0], [networkNodes]);
    const paperTargets = useMemo(
        () => Array.from({ length: PAPER_COUNT }, (_, i) => inputLayerNodes[i % inputLayerNodes.length]),
        [inputLayerNodes]
    );

    const outputNodePos = useMemo(() => networkNodes[networkNodes.length - 1][0], [networkNodes]);

    useFrame(() => {
        const s = scrollProgress.current;
        const p = phases.current;
        const lerpSpeed = 0.12;

        p.fly += (sm(ph(s, ...P.fly)) - p.fly) * lerpSpeed;
        p.paperToInput += (sm(ph(s, ...P.paperToInput)) - p.paperToInput) * lerpSpeed;
        p.inputNodes += (sm(ph(s, ...P.inputNodes)) - p.inputNodes) * lerpSpeed;

        p.layer1to2Raw += (ph(s, ...P.layer1to2) - p.layer1to2Raw) * lerpSpeed;
        p.layer1to2 = sm(p.layer1to2Raw);
        p.layer2to3Raw += (ph(s, ...P.layer2to3) - p.layer2to3Raw) * lerpSpeed;
        p.layer2to3 = sm(p.layer2to3Raw);
        p.layer3toOutRaw += (ph(s, ...P.layer3toOut) - p.layer3toOutRaw) * lerpSpeed;
        p.layer3toOut = sm(p.layer3toOutRaw);

        p.outputConn += (sm(ph(s, ...P.outputConn)) - p.outputConn) * lerpSpeed;
        p.paperForm += (sm(ph(s, ...P.paperForm)) - p.paperForm) * lerpSpeed;
        p.cloudsIn += (sm(ph(s, ...P.cloudsIn)) - p.cloudsIn) * lerpSpeed;
        p.cloudsOut += (sm(ph(s, ...P.cloudsOut)) - p.cloudsOut) * lerpSpeed;
        p.facility += (sm(ph(s, ...P.facility)) - p.facility) * lerpSpeed;
    });

    return (
        <group>
            <TrackingCamera scrollProgress={scrollProgress} />
            <AmbientParticles scrollProgress={scrollProgress} />
            <CloudSystem scrollProgress={scrollProgress} />

            {Array.from({ length: PAPER_COUNT }, (_, i) => (
                <PaperCard
                    key={i}
                    index={i}
                    phases={phases}
                    stackPos={stackPositions[i]}
                    flyPos={flyPositions[i]}
                    inputTarget={paperTargets[i]}
                    scrollProgress={scrollProgress}
                />
            ))}

            {flatNodes.map((n, i) => (
                <NetworkNode key={`n${i}`} position={n.pos} phases={phases} isOutput={n.isOutput} layerIndex={n.layerIndex} />
            ))}

            {connections.map((c, i) => (
                <CurvedConnection key={`c${i}`} from={c.from} to={c.to} phases={phases} layer={c.layer} connectionIndex={i} />
            ))}

            <OutputConnection phases={phases} outputNodePos={outputNodePos} />
            <OutputCard phases={phases} scrollProgress={scrollProgress} outputNodePos={outputNodePos} />

            <EffectComposer>
                <Bloom intensity={0.5} luminanceThreshold={0.9} luminanceSmoothing={0.8} radius={0.6} />
                <Vignette eskil={false} offset={0.15} darkness={0.2} />
            </EffectComposer>
        </group>
    );
};

/* ═══════════════ PROGRESS BAR ═══════════════ */
const ProgressBar = ({ scrollProgress }) => {
    const ref = useRef(null);
    useEffect(() => {
        let raf;
        const tick = () => {
            if (ref.current) ref.current.style.transform = `scaleY(${scrollProgress.current})`;
            raf = requestAnimationFrame(tick);
        };
        tick();
        return () => cancelAnimationFrame(raf);
    }, [scrollProgress]);
    return <div ref={ref} className="progress-bar" />;
};

/* ═══════════════ SKY BACKGROUND ═══════════════ */
const SkyBackground = ({ scrollProgress }) => {
    const skyRef = useRef(null);
    const facilityRef = useRef(null);

    // CSS clouds config — five unique sizes/speeds/positions
    const cssCloudClasses = ['bg-cloud bg-cloud-a', 'bg-cloud bg-cloud-b', 'bg-cloud bg-cloud-c', 'bg-cloud bg-cloud-d', 'bg-cloud bg-cloud-e'];

    useEffect(() => {
        let raf;
        const tick = () => {
            const s = scrollProgress.current;
            const skyFade = sm(ph(s, P.cloudsOut[0], P.facility[1]));
            const facilityP = sm(ph(s, ...P.facility));
            if (skyRef.current) skyRef.current.style.opacity = 1 - skyFade;
            if (facilityRef.current) facilityRef.current.style.opacity = facilityP;
            raf = requestAnimationFrame(tick);
        };
        tick();
        return () => cancelAnimationFrame(raf);
    }, [scrollProgress]);

    return (
        <div className="sky-background">
            <div ref={skyRef} className="sky-gradient">
                {/* CSS floating background clouds */}
                <div className="sky-cloud-layer">
                    {cssCloudClasses.map((cls, i) => (
                        <div key={i} className={cls} />
                    ))}
                </div>
            </div>
            <div ref={facilityRef} className="facility-gradient" style={{ opacity: 0 }} />
        </div>
    );
};

/* ═══════════════ FACILITY WELCOME ═══════════════ */
const FacilityWelcome = ({ scrollProgress }) => {
    const ref = useRef(null);

    useEffect(() => {
        let raf;
        const tick = () => {
            const s = scrollProgress.current;
            const facilityP = sm(ph(s, ...P.facility));
            const fadeOut = sm(ph(s, P.facility[1], P.inputNodes[0] + 0.02));
            const opacity = facilityP * (1 - fadeOut);
            if (ref.current) {
                ref.current.style.opacity = opacity;
                ref.current.style.transform = `translateY(${(1 - facilityP) * 40 + fadeOut * -30}px)`;
            }
            raf = requestAnimationFrame(tick);
        };
        tick();
        return () => cancelAnimationFrame(raf);
    }, [scrollProgress]);

    return (
        <div ref={ref} className="facility-welcome-overlay" style={{ opacity: 0 }}>
            <div className="facility-welcome-content">
                <div className="facility-welcome-line" />
                <span className="facility-welcome-sub">// system initialized</span>
                <h2 className="facility-welcome-title">Welcome to the CogniView.AI Facility</h2>
                <p className="facility-welcome-desc">Neural processing engine activated. Preparing knowledge synthesis...</p>
                <div className="facility-welcome-line" />
            </div>
        </div>
    );
};

/* ═══════════════ BIRD ABOUT (replaces AboutDropdown) ═══════════════ */
const BirdAbout = () => {
    const [hovered, setHovered] = useState(false);

    return (
        <div className="bird-nav-container">
            <div
                className={`bird-wrapper${hovered ? ' bird-stopped' : ''}`}
                onMouseEnter={() => setHovered(true)}
                onMouseLeave={() => setHovered(false)}
            >
                {/* Bird SVG — side profile, facing right */}
                <div className="bird-svg-wrap">
                    <svg
                        className="bird-svg"
                        viewBox="0 0 80 40"
                        xmlns="http://www.w3.org/2000/svg"
                        aria-label="About us"
                    >
                        {/* Tail feathers */}
                        <path d="M16 23 L6 19 M16 23 L6 23 M16 23 L7 27"
                            stroke="#0d2247" strokeWidth="1.6" strokeLinecap="round" fill="none" />

                        {/* Body */}
                        <ellipse cx="32" cy="23" rx="16" ry="7" fill="#1a3461" />

                        {/* Upper wing — animated */}
                        <g className="bird-wing-top">
                            <path d="M29 21 Q22 9 11 14 Q22 18 29 21Z" fill="#2d5a9e" />
                        </g>
                        {/* Lower wing shadow */}
                        <g className="bird-wing-btm">
                            <path d="M29 26 Q22 34 13 30 Q22 27 29 26Z" fill="#0f1f40" opacity="0.55" />
                        </g>

                        {/* Wing highlight edge */}
                        <path d="M29 21 Q22 9 11 14" stroke="rgba(255,255,255,0.22)" strokeWidth="0.8" fill="none"
                            className="bird-wing-top" style={{ transformOrigin: '33px 20px' }} />

                        {/* Neck */}
                        <ellipse cx="46" cy="20" rx="5" ry="6" fill="#1a3461" />

                        {/* Head */}
                        <circle cx="52" cy="16" r="6.5" fill="#1a3461" />

                        {/* Eye highlight */}
                        <circle cx="54.5" cy="14.5" r="2.2" fill="white" />
                        <circle cx="55.2" cy="14.5" r="1.1" fill="#0a1528" />
                        <circle cx="55.6" cy="14.0" r="0.4" fill="white" />

                        {/* Beak */}
                        <path d="M58 16 L67 13.5 L64 18.5Z" fill="#e8951a" />
                        <path d="M58 16 L67 13.5" stroke="#c87010" strokeWidth="0.6" fill="none" />
                    </svg>
                </div>

                {/* Paper scroll-out on hover */}
                <div className="paper-scroll-reveal">
                    <div className="paper-curl" />
                    <div className="paper-scroll-content">
                        <span className="paper-label">About Us</span>
                        <div className="paper-rule" />
                        <h3 className="paper-heading">CogniView.AI</h3>
                        <p className="paper-body">
                            We transform stacks of research papers and complex PDFs into clear, structured insights — powered by neural intelligence.
                        </p>
                        <p className="paper-body-small">
                            Built by researchers, for researchers.
                        </p>
                    </div>
                </div>
            </div>
        </div>
    );
};

/* ═══════════════ APP ═══════════════ */
export default function App() {
    const scrollContainerRef = useRef(null);
    const ctaBtnRef = useRef(null);
    const heroRef = useRef(null);
    const blurOverlayRef = useRef(null);
    const blurTextRef = useRef(null);
    const canvasWrapperRef = useRef(null);
    const scrollProgress = useRef(0);
    const ctaVisible = useRef(false);
    const heroHidden = useRef(false);
    const scrollReady = useRef(false);
    const scrollLocked = useRef(false);

    const [loading, setLoading] = useState(true);
    const [phaseInfo, setPhaseInfo] = useState({ step: '', title: '', visible: false });
    const [showDashboard, setShowDashboard] = useState(false);
    const [showTransition, setShowTransition] = useState(false);

    const phaseLabels = useMemo(() => [
        { r: [P.stack[0], P.stack[1]], step: 'Phase 01', title: 'Paper Stack' },
        { r: [P.fly[0], P.fly[1]], step: 'Phase 02', title: 'Papers Take Flight' },
        { r: [P.cloudsIn[0], P.cloudsIn[1]], step: 'Phase 03', title: 'Into the Clouds' },
        { r: [P.cloudsOut[0], P.cloudsOut[1]], step: 'Phase 04', title: 'Clouds Part' },
        { r: [P.facility[0], P.facility[1]], step: 'Phase 05', title: 'System Awakens' },
        { r: [P.paperToInput[0], P.paperToInput[1]], step: 'Phase 06', title: 'Papers to Input Nodes' },
        { r: [P.inputNodes[0], P.inputNodes[1]], step: 'Phase 07', title: 'Input Layer' },
        { r: [P.layer1to2[0], P.layer1to2[1]], step: 'Phase 08', title: 'Hidden Layer 1' },
        { r: [P.layer2to3[0], P.layer2to3[1]], step: 'Phase 09', title: 'Hidden Layer 2' },
        { r: [P.layer3toOut[0], P.layer3toOut[1]], step: 'Phase 10', title: 'Output Node' },
        { r: [P.outputConn[0], P.outputConn[1]], step: 'Phase 11', title: 'Generating Output' },
        { r: [P.paperForm[0], P.summary[1]], step: 'Phase 12', title: 'Forming Summary' },
    ], []);

    useEffect(() => {
        const timer = setTimeout(() => setLoading(false), 1800);
        const fallback = setTimeout(() => setLoading(false), 5000);
        return () => { clearTimeout(timer); clearTimeout(fallback); };
    }, []);

    useEffect(() => {
        if (loading || showDashboard || showTransition) return;

        ScrollTrigger.getAll().forEach(t => t.kill());
        window.scrollTo(0, 0);
        scrollProgress.current = 0;
        heroHidden.current = false;
        ctaVisible.current = false;
        scrollReady.current = false;
        scrollLocked.current = false;

        if (heroRef.current) gsap.set(heroRef.current, { opacity: 1, y: 0 });
        if (ctaBtnRef.current) gsap.set(ctaBtnRef.current, { opacity: 0, y: 60 });
        if (blurOverlayRef.current) gsap.set(blurOverlayRef.current, { opacity: 0 });

        const initTimeout = setTimeout(() => {
            window.scrollTo(0, 0);
            ScrollTrigger.refresh(true);

            const trigger = ScrollTrigger.create({
                trigger: scrollContainerRef.current,
                start: 'top top',
                end: 'bottom bottom',
                scrub: 1.6,
                onUpdate: (self) => {
                    if (scrollLocked.current) return;
                    scrollProgress.current = self.progress;

                    if (!scrollReady.current) {
                        if (self.progress < 0.01) scrollReady.current = true;
                        return;
                    }

                    if (self.progress > 0.02 && !heroHidden.current) {
                        heroHidden.current = true;
                        if (heroRef.current) gsap.to(heroRef.current, { opacity: 0, y: -50, duration: 0.7, ease: 'power3.in' });
                    } else if (self.progress <= 0.02 && heroHidden.current) {
                        heroHidden.current = false;
                        if (heroRef.current) gsap.to(heroRef.current, { opacity: 1, y: 0, duration: 0.8, ease: 'power3.out' });
                    }

                    if (canvasWrapperRef.current) {
                        const canvasOpacity = self.progress > 0.90 ? Math.max(0, 1 - ph(self.progress, 0.90, 0.96)) : 1;
                        canvasWrapperRef.current.style.opacity = canvasOpacity;
                    }

                    if (blurOverlayRef.current) {
                        const blurP = sm(ph(self.progress, ...P.blurCta));
                        blurOverlayRef.current.style.opacity = blurP;
                        blurOverlayRef.current.style.pointerEvents = blurP > 0.3 ? 'all' : 'none';
                        blurOverlayRef.current.style.backdropFilter = `blur(${blurP * 22}px)`;
                        blurOverlayRef.current.style.webkitBackdropFilter = `blur(${blurP * 22}px)`;
                    }

                    if (blurTextRef.current) {
                        const textP = sm(ph(self.progress, 0.94, 0.97));
                        blurTextRef.current.style.opacity = textP;
                        blurTextRef.current.style.transform = `translateY(${(1 - textP) * 50}px)`;
                    }

                    if (self.progress > 0.96 && !ctaVisible.current) {
                        ctaVisible.current = true;
                        if (ctaBtnRef.current) gsap.to(ctaBtnRef.current, { opacity: 1, y: 0, duration: 0.9, ease: 'power3.out' });
                    } else if (self.progress <= 0.96 && ctaVisible.current) {
                        ctaVisible.current = false;
                        if (ctaBtnRef.current) gsap.to(ctaBtnRef.current, { opacity: 0, y: 60, duration: 0.3, ease: 'power2.in' });
                    }

                    if (self.progress >= 0.998) scrollLocked.current = true;

                    const active = phaseLabels.find(l => self.progress >= l.r[0] && self.progress < l.r[1]);
                    if (active) setPhaseInfo({ step: active.step, title: active.title, visible: true });
                    else setPhaseInfo(prev => ({ ...prev, visible: false }));
                },
            });
            // store for cleanup
            return trigger;
        }, 300);

        const triggerRef = { current: null };
        const preventOverscroll = (e) => { if (scrollLocked.current && e.deltaY > 0) e.preventDefault(); };
        window.addEventListener('wheel', preventOverscroll, { passive: false });

        return () => {
            clearTimeout(initTimeout);
            if (triggerRef.current) triggerRef.current.kill();
            ScrollTrigger.getAll().forEach(t => t.kill());
            window.removeEventListener('wheel', preventOverscroll);
        };
    }, [loading, showDashboard, showTransition, phaseLabels]);

    const handleGetStarted = useCallback(() => { setShowTransition(true); }, []);
    const handleTransitionComplete = useCallback(() => {
        setTimeout(() => { setShowDashboard(true); setShowTransition(false); }, 400);
    }, []);

    if (showDashboard) {
        ScrollTrigger.getAll().forEach(t => t.kill());
        gsap.killTweensOf('*');
        document.body.style.overflow = '';
        document.documentElement.style.overflow = '';
        return <Dashboard />;
    }

    return (
        <>
            <TransitionAnimation active={showTransition} onComplete={handleTransitionComplete} minDuration={5000} />

            <div className={`loading-screen ${!loading ? 'hidden' : ''}`}>
                <div className="loading-logo">
                    <div className="loading-ring" />
                    <div className="loading-ring-inner" />
                </div>
                <div className="loading-text">CogniView.AI</div>
            </div>

            <SkyBackground scrollProgress={scrollProgress} />

            <div ref={scrollContainerRef} className="scroll-container">
                <section className="scroll-page page-hero">
                    <nav className="top-nav">
                        <a className="nav-logo" href="#">
                            <div className="nav-logo-icon">
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                                    <path d="M12 2L2 7l10 5 10-5-10-5z" />
                                    <path d="M2 17l10 5 10-5" />
                                    <path d="M2 12l10 5 10-5" />
                                </svg>
                            </div>
                            <span className="nav-logo-text">CogniView<span className="nav-logo-dot">.</span>AI</span>
                        </a>

                        {/* Bird flies across the nav bar — hover to reveal About Us */}
                        <BirdAbout />
                    </nav>

                    <div ref={heroRef} className="hero-overlay">
                        <div className="hero-content">
                            <div className="hero-badge">
                                <span className="hero-badge-dot" />
                                Process of Stack-to-Sheet
                            </div>
                            <h1 className="hero-title">
                                Turn Complex Bundles<br />
                                <span className="hero-gradient">Into Meaningful Personalised Insight</span>
                            </h1>
                        </div>
                        <div className="scroll-indicator">
                            <span className="scroll-text">Scroll down to discover</span>
                            <div className="scroll-mouse"><div className="scroll-dot" /></div>
                        </div>
                    </div>
                </section>

                <section className="scroll-page page-fly" />
                <section className="scroll-page page-clouds" />
                <section className="scroll-page page-facility" />
                <section className="scroll-page page-input" />
                <section className="scroll-page page-layer1" />
                <section className="scroll-page page-layer2" />
                <section className="scroll-page page-output" />
                <section className="scroll-page page-paper" />
                <section className="scroll-page page-cta" />
            </div>

            <div ref={canvasWrapperRef} className="canvas-overlay">
                <ProgressBar scrollProgress={scrollProgress} />

                <Canvas
                    camera={{ position: [0, CAMERA_TARGETS.stack.y, CAMERA_TARGETS.stack.z], fov: 50 }}
                    dpr={[1, 2]}
                    gl={{
                        antialias: true,
                        alpha: true,
                        powerPreference: 'high-performance',
                        toneMapping: THREE.NoToneMapping
                    }}
                    style={{ background: 'transparent' }}
                >
                    {/* Bright daytime lighting */}
                    <ambientLight intensity={1.4} color="#d8eeff" />
                    <directionalLight position={[8, 14, 10]} intensity={0.6} color="#fff5e8" />
                    <directionalLight position={[-4, 6, 4]} intensity={0.25} color="#c8e4ff" />
                    <Scene scrollProgress={scrollProgress} />
                </Canvas>
            </div>

            <FacilityWelcome scrollProgress={scrollProgress} />

            <div ref={blurOverlayRef} className="blur-cta-overlay" style={{ opacity: 0 }}>
                <div className="blur-cta-content">
                    <h2 ref={blurTextRef} className="blur-main-text" style={{ opacity: 0 }}>
                        Tired of Reading Those Big PDFs?
                    </h2>
                    <div ref={ctaBtnRef} className="cta-wrapper" style={{ opacity: 0, transform: 'translateY(60px)' }}>
                        <button className="cta-button cta-button-large" onClick={handleGetStarted}>
                            <span>Get Started</span>
                            <svg className="cta-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                                strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                <path d="M5 12h14M12 5l7 7-7 7" />
                            </svg>
                        </button>
                        <span className="cta-subtext">No credit card required</span>
                    </div>
                </div>
            </div>
        </>
    );
}
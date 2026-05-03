import React, { useEffect, useRef, useMemo, useState, useCallback } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { EffectComposer, Bloom, Vignette } from '@react-three/postprocessing';
import * as THREE from 'three';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import './App_sphere.css';

gsap.registerPlugin(ScrollTrigger);

/* ═══════════════════════════════════════════════════════
   CONSTANTS
   ═══════════════════════════════════════════════════════ */
const SPHERE_RADIUS = 5.5;
const ROWS = 7;
const GAP = 0.08;

// Solar system: smaller spheres behind main one
const SOLAR_SPHERES = [
  { scale: 0.35, z: -12, x: -3, y: 1.2 },
  { scale: 0.25, z: -18, x: 4, y: -0.8 },
  { scale: 0.20, z: -24, x: -5, y: 0.3 },
  { scale: 0.30, z: -15, x: 6, y: 1.5 },
  { scale: 0.18, z: -28, x: -1, y: -1.0 },
  { scale: 0.22, z: -22, x: 7, y: 0.0 },
];

/* scroll phases (0→1) — page ends exactly at animation end */
const P = {
  titleFade: [0.00, 0.07],
  sphereRetreat: [0.02, 0.22],
  solarFade: [0.02, 0.14],
  glassDetach: [0.16, 0.38],
  glassFlip: [0.20, 0.56],
  glassScale: [0.26, 0.42],
  beamExtend: [0.36, 0.56],
  beamRefract: [0.48, 0.62],
  paperReveal: [0.52, 0.68],
  paperIlluminate: [0.58, 0.72],
  particleFlow: [0.40, 0.78],
  lineFill: [0.60, 0.82],
  blurStart: [0.80, 0.90],
  ctaAppear: [0.88, 1.00],
};

const ph = (s, a, b) => THREE.MathUtils.clamp((s - a) / (b - a), 0, 1);
const sm = t => t * t * (3 - 2 * t);
const ease = (s, a, b) => sm(ph(s, a, b));

/* ═══════════════════════════════════════════════════════
   TEXTURES
   ═══════════════════════════════════════════════════════ */
const createScribbleTexture = (seed = 0) => {
  const c = document.createElement('canvas'); c.width = 512; c.height = 720;
  const ctx = c.getContext('2d');
  const tints = ['#fbfbf8', '#f5f5f0', '#faf9f5', '#f0f0eb'];
  ctx.fillStyle = tints[seed % tints.length]; ctx.fillRect(0, 0, 512, 720);
  ctx.strokeStyle = 'rgba(0,0,0,0.15)'; ctx.lineWidth = 6; ctx.strokeRect(3, 3, 506, 714);
  let s2 = seed * 9301 + 49297;
  const rng = () => { s2 = (s2 * 9301 + 49297) % 233280; return s2 / 233280; };
  ctx.font = '700 42px "Sora",sans-serif'; ctx.fillStyle = '#1a1a1a';
  ctx.textAlign = 'left'; ctx.textBaseline = 'top';
  ctx.fillText('Research Paper', 40, 38);
  ctx.strokeStyle = 'rgba(17,17,17,0.6)'; ctx.lineWidth = 2.5;
  ctx.beginPath(); ctx.moveTo(40, 90); ctx.lineTo(380, 90); ctx.stroke();
  ctx.font = '500 14px "SF Mono",monospace'; ctx.fillStyle = 'rgba(100,100,100,0.6)';
  ctx.fillText(`DOC-${String(seed + 1).padStart(3, '0')}`, 400, 42);
  ctx.lineCap = 'round'; ctx.lineJoin = 'round';
  for (let l = 0; l < 22; l++) {
    const y = 115 + l * 26 + (rng() - 0.5) * 3;
    const isS = l >= 20 || l === 8 || l === 14;
    const w = isS ? 60 + rng() * 100 : 280 + rng() * 150;
    ctx.strokeStyle = `rgba(30,30,30,${0.3 + rng() * 0.25})`;
    ctx.lineWidth = 1.6 + rng() * 0.7; ctx.beginPath();
    let lx = 40; ctx.moveTo(lx, y);
    while (lx < 40 + w) { lx += 3 + rng() * 8; ctx.lineTo(Math.min(lx, 40 + w), y + (rng() - 0.5) * 1.6); }
    ctx.stroke();
  }
  const t = new THREE.CanvasTexture(c); t.needsUpdate = true; t.anisotropy = 16;
  t.repeat.set(-1, 1); t.offset.set(1, 0); return t;
};

/* ═══════════════════════════════════════════════════════
   BUILD CARDS
   ═══════════════════════════════════════════════════════ */
const buildSphereCards = () => {
  const cards = []; let idx = 0;
  for (let row = 0; row < ROWS; row++) {
    const phiA = (Math.PI * (row + 0.5)) / ROWS;
    const y = SPHERE_RADIUS * Math.cos(phiA);
    const rr = SPHERE_RADIUS * Math.sin(phiA);
    const ch = (Math.PI * SPHERE_RADIUS) / ROWS - GAP;
    const cw = ch * 0.72;
    const cnt = Math.max(2, Math.floor(2 * Math.PI * rr / (cw + GAP * 2)));
    for (let col = 0; col < cnt; col++) {
      const theta = (2 * Math.PI * col) / cnt;
      const x = rr * Math.cos(theta), z = rr * Math.sin(theta);
      const n = new THREE.Vector3(x, y, z).normalize();
      cards.push({
        index: idx++, row, col, count: cnt, phi: phiA, theta,
        position: new THREE.Vector3(x, y, z), normal: n, cardWidth: cw, cardHeight: ch, ringRadius: rr
      });
    }
  }
  return cards;
};

/* ═══════════════════════════════════════════════════════
   SPHERE PAPER CARD
   ═══════════════════════════════════════════════════════ */
const SpherePaperCard = ({ cardData }) => {
  const meshRef = useRef();
  const { index, phi, theta, count } = cardData;
  const texture = useMemo(() => createScribbleTexture(index), [index]);
  const segW = 12, segH = 16;
  const geometry = useMemo(() => new THREE.PlaneGeometry(1, 1, segW, segH), []);

  useFrame(({ clock }) => {
    if (!meshRef.current) return;
    const t = clock.getElapsedTime();
    const posArr = meshRef.current.geometry.attributes.position.array;
    const vpr = segW + 1, ts = (2 * Math.PI) / count, ps = Math.PI / ROWS;
    for (let j = 0; j <= segH; j++) for (let i = 0; i <= segW; i++) {
      const idx2 = (j * vpr + i) * 3; const u = i / segW, v = j / segH;
      const lt = theta + (u - 0.5) * ts * 0.92, lp = phi + (v - 0.5) * ps * 0.92;
      const br = Math.sin(t * 1.2 + index * 0.4) * 0.006;
      const r = SPHERE_RADIUS + br;
      posArr[idx2] = r * Math.sin(lp) * Math.cos(lt);
      posArr[idx2 + 1] = r * Math.cos(lp);
      posArr[idx2 + 2] = r * Math.sin(lp) * Math.sin(lt);
    }
    meshRef.current.geometry.attributes.position.needsUpdate = true;
    meshRef.current.geometry.computeVertexNormals();
  });

  return (
    <mesh ref={meshRef} geometry={geometry} castShadow>
      <meshStandardMaterial map={texture} side={THREE.DoubleSide} toneMapped={false}
        roughness={0.75} metalness={0} transparent opacity={1} />
    </mesh>
  );
};

/* ═══════════════════════════════════════════════════════
   MINI SPHERE (for solar system — smaller copies)
   ═══════════════════════════════════════════════════════ */
const MiniSphere = ({ scrollProgress, config }) => {
  const groupRef = useRef();
  const cards = useMemo(() => {
    // Fewer cards for mini spheres
    const miniCards = []; let idx = 0;
    const miniRows = 4;
    for (let row = 0; row < miniRows; row++) {
      const phiA = (Math.PI * (row + 0.5)) / miniRows;
      const y = SPHERE_RADIUS * Math.cos(phiA);
      const rr = SPHERE_RADIUS * Math.sin(phiA);
      const ch = (Math.PI * SPHERE_RADIUS) / miniRows - GAP;
      const cw = ch * 0.72;
      const cnt = Math.max(2, Math.floor(2 * Math.PI * rr / (cw + GAP * 2)) * 0.5);
      for (let col = 0; col < cnt; col++) {
        const theta = (2 * Math.PI * col) / cnt;
        miniCards.push({ index: idx++, phi: phiA, theta, count: cnt });
      }
    }
    return miniCards;
  }, []);

  useFrame(({ clock }) => {
    if (!groupRef.current) return;
    const t = clock.getElapsedTime();
    const fadeP = ease(scrollProgress.current, ...P.solarFade);
    groupRef.current.rotation.y = t * 0.15;
    groupRef.current.visible = fadeP < 0.99;
    groupRef.current.scale.setScalar(config.scale * (1 - fadeP));
  });

  return (
    <group ref={groupRef} position={[config.x, config.y, config.z]}>
      {cards.map((c, i) => {
        const p = c.phi, th = c.theta;
        return (
          <mesh key={i} position={[
            SPHERE_RADIUS * Math.sin(p) * Math.cos(th),
            SPHERE_RADIUS * Math.cos(p),
            SPHERE_RADIUS * Math.sin(p) * Math.sin(th),
          ]}>
            <planeGeometry args={[0.6, 0.85]} />
            <meshStandardMaterial color="#d4cbf7" transparent opacity={0.5}
              side={THREE.DoubleSide} toneMapped={false} />
          </mesh>
        );
      })}
    </group>
  );
};

/* ═══════════════════════════════════════════════════════
   SUN (behind main sphere)
   ═══════════════════════════════════════════════════════ */
const Sun = ({ scrollProgress }) => {
  const ref = useRef();
  const glowRef = useRef();

  useFrame(({ clock }) => {
    if (!ref.current) return;
    const t = clock.getElapsedTime();
    const fadeP = ease(scrollProgress.current, ...P.solarFade);
    const sc = (1 - fadeP);
    ref.current.visible = sc > 0.01;
    ref.current.scale.setScalar(sc);
    ref.current.rotation.y = t * 0.05;
    if (glowRef.current) {
      glowRef.current.scale.setScalar(sc * 4.5 + Math.sin(t * 0.8) * 0.3 * sc);
      glowRef.current.material.opacity = 0.08 * sc;
    }
  });

  return (
    <group position={[0, 0, -35]}>
      <mesh ref={ref}>
        <sphereGeometry args={[3, 32, 32]} />
        <meshStandardMaterial color="#fbbf24" emissive="#fbbf24" emissiveIntensity={2}
          toneMapped={false} />
      </mesh>
      <mesh ref={glowRef}>
        <sphereGeometry args={[1, 32, 32]} />
        <meshBasicMaterial color="#fbbf24" transparent opacity={0.08}
          blending={THREE.AdditiveBlending} depthWrite={false} />
      </mesh>
    </group>
  );
};

/* ═══════════════════════════════════════════════════════
   AXIS LINE (thin line through all spheres)
   ═══════════════════════════════════════════════════════ */
const AxisLine = ({ scrollProgress }) => {
  const ref = useRef();
  useFrame(() => {
    if (!ref.current) return;
    const fadeP = ease(scrollProgress.current, ...P.solarFade);
    ref.current.material.opacity = 0.12 * (1 - fadeP);
    ref.current.visible = fadeP < 0.99;
  });
  const pts = useMemo(() => [
    new THREE.Vector3(0, 0, 10),
    new THREE.Vector3(0, 0, -40),
  ], []);
  const geo = useMemo(() => new THREE.BufferGeometry().setFromPoints(pts), [pts]);
  return (
    <line ref={ref} geometry={geo}>
      <lineBasicMaterial color="#a78bfa" transparent opacity={0.12} />
    </line>
  );
};

/* ═══════════════════════════════════════════════════════
   AMBIENT PARTICLES
   ═══════════════════════════════════════════════════════ */
const AmbientParticles = ({ scrollProgress }) => {
  const ref = useRef(); const N = 80;
  const pos = useMemo(() => {
    const p = new Float32Array(N * 3);
    for (let i = 0; i < N; i++) {
      p[i * 3] = (Math.random() - 0.5) * 40;
      p[i * 3 + 1] = (Math.random() - 0.5) * 25;
      p[i * 3 + 2] = -10 - Math.random() * 10;
    }
    return p;
  }, []);
  useFrame(({ clock }) => {
    if (!ref.current) return;
    const t = clock.getElapsedTime();
    const a = ref.current.geometry.attributes.position.array;
    for (let i = 0; i < N; i++) a[i * 3 + 1] += Math.sin(t * 0.2 + i * 0.8) * 0.001;
    ref.current.geometry.attributes.position.needsUpdate = true;
    ref.current.material.opacity = 0.06 + (scrollProgress.current || 0) * 0.03;
  });
  return (
    <points ref={ref}>
      <bufferGeometry><bufferAttribute attach="attributes-position" args={[pos, 3]} /></bufferGeometry>
      <pointsMaterial color="#a78bfa" transparent opacity={0.06} size={0.04} sizeAttenuation />
    </points>
  );
};

/* ═══════════════════════════════════════════════════════
   3D MAGNIFYING GLASS (same look as logo icon)
   ═══════════════════════════════════════════════════════ */
const MagnifyingGlass3D = ({ scrollProgress }) => {
  const groupRef = useRef();

  useFrame(({ clock }) => {
    if (!groupRef.current) return;
    const s = scrollProgress.current;
    const t = clock.getElapsedTime();
    const detach = ease(s, ...P.glassDetach);
    const flipP = ease(s, ...P.glassFlip);
    const scaleP = ease(s, ...P.glassScale);

    // Start: logo position (top-left in world space)
    const sx = -6.8, sy = 4.5, sz = 5;
    // End: center of viewport, big
    const ex = -1.0, ey = 0.0, ez = 4;

    groupRef.current.position.set(
      THREE.MathUtils.lerp(sx, ex, sm(detach)),
      THREE.MathUtils.lerp(sy, ey, sm(detach)),
      THREE.MathUtils.lerp(sz, ez, sm(detach)),
    );
    groupRef.current.rotation.y = flipP * Math.PI * 6 + Math.sin(t * 0.3) * 0.02;
    groupRef.current.rotation.z = THREE.MathUtils.lerp(0.1, 0, detach);

    // Scale: starts small (logo size), ends VERY big
    const sc = THREE.MathUtils.lerp(0.06, 2.0, sm(scaleP));
    groupRef.current.scale.setScalar(Math.max(sc, 0.001));
    groupRef.current.visible = detach > 0.001;
  });

  return (
    <group ref={groupRef} visible={false}>
      <mesh>
        <torusGeometry args={[1.2, 0.09, 16, 64]} />
        <meshStandardMaterial color="#c4b5fd" metalness={0.85} roughness={0.15}
          emissive="#7c3aed" emissiveIntensity={0.5} />
      </mesh>
      <mesh>
        <circleGeometry args={[1.18, 64]} />
        <meshPhysicalMaterial color="#a5b4fc" transparent opacity={0.12}
          transmission={0.7} roughness={0.03} metalness={0} side={THREE.DoubleSide} />
      </mesh>
      <mesh position={[0.85, -1.65, 0]} rotation={[0, 0, 0.42]}>
        <cylinderGeometry args={[0.06, 0.08, 1.8, 12]} />
        <meshStandardMaterial color="#8b7ec8" metalness={0.6} roughness={0.3} />
      </mesh>
      <mesh position={[-0.35, 0.35, 0.05]}>
        <circleGeometry args={[0.2, 32]} />
        <meshBasicMaterial color="#ffffff" transparent opacity={0.08} side={THREE.DoubleSide} />
      </mesh>
    </group>
  );
};

/* ═══════════════════════════════════════════════════════
   AESTHETIC LIGHT BEAMS from sphere surface → glass
   ═══════════════════════════════════════════════════════ */
const LightBeams = ({ scrollProgress }) => {
  const beamGroupRef = useRef();
  const refractRef = useRef();
  const glowRef = useRef();
  const RAY_COUNT = 18;

  const rayData = useMemo(() => {
    const data = [];
    for (let i = 0; i < RAY_COUNT; i++) {
      const golden = Math.PI * (3 - Math.sqrt(5));
      const y = 1 - (i / (RAY_COUNT - 1)) * 2;
      const radius = Math.sqrt(1 - y * y);
      const th = golden * i;
      data.push({
        nx: -Math.abs(radius * Math.cos(th)) * 0.8,
        ny: y * 0.7,
        nz: radius * Math.sin(th) * 0.5,
        width: 0.015 + Math.random() * 0.025,
        glow: 0.3 + Math.random() * 0.7,
        phase: Math.random() * Math.PI * 2,
      });
    }
    return data;
  }, []);

  useFrame(({ clock }) => {
    const s = scrollProgress.current;
    const t = clock.getElapsedTime();
    const extP = ease(s, ...P.beamExtend);
    const refP = ease(s, ...P.beamRefract);

    const retreatP = ease(s, ...P.sphereRetreat);
    const sphereX = THREE.MathUtils.lerp(0, 9, retreatP);
    const sphereY = THREE.MathUtils.lerp(0, 5.5, retreatP);

    const detach = ease(s, ...P.glassDetach);
    const glassX = THREE.MathUtils.lerp(-6.8, -1.0, sm(detach));
    const glassY = THREE.MathUtils.lerp(4.5, 0.0, sm(detach));
    const glassZ = THREE.MathUtils.lerp(5, 4, sm(detach));

    if (beamGroupRef.current) {
      const children = beamGroupRef.current.children;
      for (let i = 0; i < Math.min(children.length, RAY_COUNT); i++) {
        const ray = children[i];
        const d = rayData[i];
        if (!ray) continue;

        const pulse = 0.7 + Math.sin(t * 2 + d.phase) * 0.3;
        const ox = sphereX + d.nx * SPHERE_RADIUS * 0.85;
        const oy = sphereY + d.ny * SPHERE_RADIUS * 0.85;
        const oz = d.nz * SPHERE_RADIUS * 0.4;

        const dx = glassX - ox, dy = glassY - oy, dz = glassZ - oz;
        const len = Math.sqrt(dx * dx + dy * dy + dz * dz);

        ray.position.set(
          THREE.MathUtils.lerp(ox, (ox + glassX) / 2, extP),
          THREE.MathUtils.lerp(oy, (oy + glassY) / 2, extP),
          THREE.MathUtils.lerp(oz, (oz + glassZ) / 2, extP),
        );
        ray.lookAt(glassX, glassY, glassZ);
        ray.scale.set(
          d.width * (1 + extP * 0.5) * pulse,
          d.width * (1 + extP * 0.5) * pulse,
          len * extP * 0.95,
        );
        ray.children[0].material.opacity = extP * d.glow * 0.12 * pulse;
        ray.visible = extP > 0.01;
      }
    }

    if (glowRef.current) {
      glowRef.current.position.set(glassX, glassY, glassZ + 0.5);
      glowRef.current.material.opacity = extP * 0.2 + Math.sin(t * 3) * 0.03 * extP;
      glowRef.current.scale.setScalar(1.5 + extP * 1.2 + Math.sin(t * 2) * 0.2 * extP);
      glowRef.current.visible = extP > 0.01;
    }

    if (refractRef.current) {
      const paperX = 4.5, paperY = 0, paperZ = 0;
      refractRef.current.position.set(glassX + 0.3, glassY, glassZ - 0.5);
      refractRef.current.lookAt(paperX, paperY, paperZ);
      const refLen = Math.sqrt((paperX - glassX) ** 2 + (paperY - glassY) ** 2 + (paperZ - glassZ) ** 2);
      refractRef.current.scale.set(0.15 * refP, 0.15 * refP, refLen * refP * 0.7);
      refractRef.current.children[0].material.opacity = refP * 0.1;
      refractRef.current.visible = refP > 0.01;
    }
  });

  return (
    <group>
      <group ref={beamGroupRef}>
        {rayData.map((_, i) => (
          <group key={i} visible={false}>
            <mesh>
              <cylinderGeometry args={[1, 0.3, 1, 6, 1, true]} />
              <meshBasicMaterial color="#a78bfa" transparent opacity={0}
                blending={THREE.AdditiveBlending} depthWrite={false} side={THREE.DoubleSide} />
            </mesh>
          </group>
        ))}
      </group>
      <mesh ref={glowRef} visible={false}>
        <sphereGeometry args={[1, 32, 32]} />
        <meshBasicMaterial color="#c4b5fd" transparent opacity={0}
          blending={THREE.AdditiveBlending} depthWrite={false} />
      </mesh>
      <group ref={refractRef} visible={false}>
        <mesh>
          <coneGeometry args={[1, 1, 8, 1, true]} />
          <meshBasicMaterial color="#fbbf24" transparent opacity={0}
            blending={THREE.AdditiveBlending} depthWrite={false} side={THREE.DoubleSide} />
        </mesh>
      </group>
    </group>
  );
};

/* ═══════════════════════════════════════════════════════
   ALPHABET PARTICLES — random chars from sphere → glass
   ═══════════════════════════════════════════════════════ */
const AlphabetParticles = ({ scrollProgress }) => {
  const meshRef = useRef();
  const N = 200;
  const CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789αβγδεζηθλμπσφψω∑∏∫√∂∇';
  const dummy = useMemo(() => new THREE.Object3D(), []);

  // Individual char textures for variety
  const charTextures = useMemo(() => {
    const texs = [];
    for (let c = 0; c < 20; c++) {
      const cv = document.createElement('canvas'); cv.width = 64; cv.height = 64;
      const ctx = cv.getContext('2d'); ctx.clearRect(0, 0, 64, 64);
      ctx.font = `bold 42px "SF Mono","Fira Code",monospace`;
      ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      ctx.fillStyle = '#ffffff';
      ctx.fillText(CHARS[Math.floor(Math.random() * CHARS.length)], 32, 32);
      const t = new THREE.CanvasTexture(cv); t.needsUpdate = true; texs.push(t);
    }
    return texs;
  }, []);

  const particleData = useMemo(() => Array.from({ length: N }, () => {
    const phi2 = Math.acos(2 * Math.random() - 1);
    const theta2 = Math.random() * Math.PI * 2;
    return {
      sx: Math.sin(phi2) * Math.cos(theta2) * SPHERE_RADIUS,
      sy: Math.cos(phi2) * SPHERE_RADIUS,
      sz: Math.sin(phi2) * Math.sin(theta2) * SPHERE_RADIUS,
      speed: 0.06 + Math.random() * 0.15,
      offset: Math.random(),
      size: 0.04 + Math.random() * 0.035,
      wobF: 1 + Math.random() * 2, wobA: 0.08 + Math.random() * 0.15, wobP: Math.random() * Math.PI * 2,
    };
  }), []);

  useFrame(({ clock }) => {
    if (!meshRef.current) return;
    const s = scrollProgress.current;
    const t = clock.getElapsedTime();
    const flowP = ease(s, ...P.particleFlow);

    const retreatP = ease(s, ...P.sphereRetreat);
    const sphCx = THREE.MathUtils.lerp(0, 9, retreatP);
    const sphCy = THREE.MathUtils.lerp(0, 5.5, retreatP);

    const detach = ease(s, ...P.glassDetach);
    const gx = THREE.MathUtils.lerp(-6.8, -1.0, sm(detach));
    const gy = THREE.MathUtils.lerp(4.5, 0.0, sm(detach));
    const gz = THREE.MathUtils.lerp(5, 4, sm(detach));

    for (let i = 0; i < N; i++) {
      const d = particleData[i];
      if (flowP < 0.005) {
        dummy.scale.setScalar(0); dummy.updateMatrix();
        meshRef.current.setMatrixAt(i, dummy.matrix); continue;
      }

      const p = ((t * d.speed * 0.1 + d.offset) % 1);
      const pathT = Math.min(p * (0.2 + flowP * 0.8), 1);

      const startX = sphCx + d.sx, startY = sphCy + d.sy, startZ = d.sz;
      const st = sm(pathT);
      const x = THREE.MathUtils.lerp(startX, gx, st);
      const y = THREE.MathUtils.lerp(startY, gy, st);
      const z = THREE.MathUtils.lerp(startZ, gz, st);

      const wobble = Math.sin(t * d.wobF + d.wobP) * d.wobA * (1 - pathT);
      dummy.position.set(x + wobble, y + wobble * 0.6, z + wobble * 0.3);

      const fadeIn = THREE.MathUtils.smoothstep(pathT, 0, 0.12);
      const fadeOut = THREE.MathUtils.smoothstep(pathT, 0.82, 1);
      const alpha = fadeIn * (1 - fadeOut) * flowP;

      dummy.scale.setScalar(d.size * alpha * 3);
      dummy.rotation.z = t * 0.6 + i;
      dummy.updateMatrix();
      meshRef.current.setMatrixAt(i, dummy.matrix);
    }
    meshRef.current.instanceMatrix.needsUpdate = true;
  });

  return (
    <instancedMesh ref={meshRef} args={[null, null, N]} frustumCulled={false}>
      <planeGeometry args={[1, 1]} />
      <meshBasicMaterial map={charTextures[0]} transparent opacity={0.9}
        blending={THREE.AdditiveBlending} depthWrite={false} side={THREE.DoubleSide} />
    </instancedMesh>
  );
};

/* ═══════════════════════════════════════════════════════
   CAMERA
   ═══════════════════════════════════════════════════════ */
const CameraController = ({ scrollProgress, isDragging, dragRotation }) => {
  const { camera } = useThree();
  const mouse = useRef({ x: 0, y: 0 });
  useEffect(() => {
    const h = e => {
      mouse.current.x = (e.clientX / window.innerWidth - 0.5) * 2;
      mouse.current.y = (e.clientY / window.innerHeight - 0.5) * 2;
    };
    window.addEventListener('mousemove', h);
    return () => window.removeEventListener('mousemove', h);
  }, []);

  useFrame(() => {
    const s = scrollProgress.current;
    const retreatP = ease(s, ...P.sphereRetreat);
    const mx = mouse.current.x * 0.4 * (1 - retreatP * 0.5);
    const my = -mouse.current.y * 0.3 * (1 - retreatP * 0.5) + 0.5;
    const tx = THREE.MathUtils.lerp(0, 2, retreatP);
    const ty = THREE.MathUtils.lerp(0, 0.8, retreatP);
    camera.position.x += (mx + tx - camera.position.x) * 0.06;
    camera.position.y += (my + ty - camera.position.y) * 0.06;
    camera.position.z += (15 - camera.position.z) * 0.06;
    camera.lookAt(tx * 0.15, ty * 0.15, 0);
  });
  return null;
};

/* ═══════════════════════════════════════════════════════
   SCENE
   ═══════════════════════════════════════════════════════ */
const Scene = ({ scrollProgress, isDragging, dragRotation }) => {
  const cards = useMemo(() => buildSphereCards(), []);
  const sGroupRef = useRef();
  const autoRot = useRef(0);

  useFrame(({ clock }) => {
    const s = scrollProgress.current; const t = clock.getElapsedTime();
    if (sGroupRef.current) {
      const retreatP = ease(s, ...P.sphereRetreat);
      sGroupRef.current.position.set(
        THREE.MathUtils.lerp(0, 9, retreatP),
        THREE.MathUtils.lerp(0, 5.5, retreatP),
        THREE.MathUtils.lerp(0, -2, retreatP),
      );
      const ga = 1 - retreatP * 0.4;
      if (!isDragging.current) autoRot.current += 0.003 * ga;
      sGroupRef.current.rotation.y = autoRot.current + dragRotation.current.x * ga;
      sGroupRef.current.rotation.x = (0.15 + Math.sin(t * 0.12) * 0.04) * ga + dragRotation.current.y * ga;
    }
  });

  return (
    <group>
      <CameraController scrollProgress={scrollProgress} isDragging={isDragging} dragRotation={dragRotation} />
      <AmbientParticles scrollProgress={scrollProgress} />

      {/* Sun */}
      <Sun scrollProgress={scrollProgress} />

      {/* Axis through all spheres */}
      <AxisLine scrollProgress={scrollProgress} />

      {/* Small solar-system spheres */}
      {SOLAR_SPHERES.map((cfg, i) => (
        <MiniSphere key={i} scrollProgress={scrollProgress} config={cfg} />
      ))}

      {/* Main sphere */}
      <group ref={sGroupRef}>
        {cards.map(card => (<SpherePaperCard key={card.index} cardData={card} />))}
      </group>

      <MagnifyingGlass3D scrollProgress={scrollProgress} />
      <LightBeams scrollProgress={scrollProgress} />
      <AlphabetParticles scrollProgress={scrollProgress} />

      <EffectComposer>
        <Bloom intensity={0.45} luminanceThreshold={0.78} luminanceSmoothing={0.4} />
        <Vignette eskil={false} offset={0.1} darkness={0.65} />
      </EffectComposer>
    </group>
  );
};

/* ═══════════════════════════════════════════════════════
   SIMPLE COMPONENTS
   ═══════════════════════════════════════════════════════ */
const ProgressBar = ({ scrollProgress }) => {
  const ref = useRef();
  useEffect(() => {
    let raf; const tick = () => { if (ref.current) ref.current.style.transform = `scaleX(${scrollProgress.current})`; raf = requestAnimationFrame(tick); }; tick();
    return () => cancelAnimationFrame(raf);
  }, [scrollProgress]);
  return <div ref={ref} className="progress-bar" />;
};

function TitleOverlay({ scrollProgress, totalCards }) {
  const ref = useRef();
  useEffect(() => {
    let raf; const tick = () => {
      if (ref.current) {
        const fo = 1 - sm(ph(scrollProgress.current, ...P.titleFade));
        ref.current.style.opacity = fo; ref.current.style.transform = `translateX(-50%) translateY(${(1 - fo) * -30}px)`;
      } raf = requestAnimationFrame(tick);
    }; tick();
    return () => cancelAnimationFrame(raf);
  }, [scrollProgress]);
  return (
    <div ref={ref} className="sphere-title-container">
      <div className="sphere-badge"><span className="sphere-badge-dot" />3D Document Sphere</div>
      <h1 className="sphere-title">Research Paper<br /><span className="sphere-title-gradient">Globe Gallery</span></h1>
      <p className="sphere-subtitle">Scroll to explore • {totalCards} documents</p>
    </div>
  );
}

const CardCountDisplay = ({ count, scrollProgress }) => {
  const ref = useRef();
  useEffect(() => {
    let raf; const tick = () => { if (ref.current) ref.current.style.opacity = 1 - sm(ph(scrollProgress.current, 0, 0.1)); raf = requestAnimationFrame(tick); }; tick();
    return () => cancelAnimationFrame(raf);
  }, [scrollProgress]);
  return (
    <div ref={ref} className="card-count-display">
      <div className="card-count-item"><span className="card-count-label">DOCUMENTS</span><span className="card-count-value">{count}</span></div>
      <div className="card-count-item"><span className="card-count-label">ROWS</span><span className="card-count-value">{ROWS}</span></div>
      <div className="card-count-item"><span className="card-count-label">RADIUS</span><span className="card-count-value">{SPHERE_RADIUS.toFixed(1)}</span></div>
    </div>
  );
};

function BottomHint({ scrollProgress }) {
  const ref = useRef();
  useEffect(() => {
    let raf; const tick = () => {
      if (ref.current) {
        const s = scrollProgress.current; const h = ref.current.querySelector('.hint-text');
        if (s < 0.05) h.textContent = 'Drag to rotate • Scroll to begin';
        else if (s < 0.25) h.textContent = 'Sphere retreating...';
        else if (s < 0.5) h.textContent = 'Magnifying glass descending...';
        else if (s < 0.8) h.textContent = 'Extracting knowledge...';
        else h.textContent = 'Summary complete';
      } raf = requestAnimationFrame(tick);
    }; tick();
    return () => cancelAnimationFrame(raf);
  }, [scrollProgress]);
  return (
    <div ref={ref} className="drag-hint">
      <svg className="drag-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
        <path d="M12 2v4m0 12v4M2 12h4m12 0h4M7.05 7.05l2.83 2.83m4.24 4.24l2.83 2.83M7.05 16.95l2.83-2.83m4.24-4.24l2.83-2.83" strokeLinecap="round" /></svg>
      <span className="hint-text">Drag to rotate • Scroll to begin</span>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════
   SUMMARY PAPER OVERLAY
   ═══════════════════════════════════════════════════════ */
const SummaryPaperOverlay = ({ scrollProgress }) => {
  const ref = useRef(); const lineRefs = useRef([]);
  useEffect(() => {
    let raf; const tick = () => {
      if (!ref.current) { raf = requestAnimationFrame(tick); return; }
      const s = scrollProgress.current;
      const revealP = ease(s, ...P.paperReveal);
      const illumP = ease(s, ...P.paperIlluminate);
      const fillP = ease(s, ...P.lineFill);
      ref.current.style.opacity = revealP;
      ref.current.style.transform = `translateY(-50%) scale(${THREE.MathUtils.lerp(0.85, 1, sm(revealP))})`;
      if (revealP > 0.01) ref.current.classList.add('visible'); else ref.current.classList.remove('visible');
      if (illumP > 0.3) ref.current.classList.add('illuminated'); else ref.current.classList.remove('illuminated');
      lineRefs.current.forEach((line, i) => {
        if (!line) return; const ld = i * 0.11;
        const lp = THREE.MathUtils.clamp((fillP - ld) / (1 - ld), 0, 1); line.style.transform = `scaleX(${sm(lp)})`;
      });
      raf = requestAnimationFrame(tick);
    }; tick();
    return () => cancelAnimationFrame(raf);
  }, [scrollProgress]);
  return (
    <div ref={ref} className="summary-paper-overlay" style={{ opacity: 0 }}>
      <div className="summary-paper">
        <div className="summary-paper-badge"><span className="summary-paper-badge-dot" />AI GENERATED SUMMARY</div>
        <h3>Research Synthesis Complete</h3>
        <div className="summary-paper-lines">
          {Array.from({ length: 8 }, (_, i) => (
            <div key={i} className="summary-line">
              <div ref={el => lineRefs.current[i] = el} className="summary-line-fill"
                style={{ width: i === 7 ? '60%' : '100%' }} />
            </div>
          ))}
        </div>
        <div className="summary-paper-meta"><span>TOKENS: 2,847</span><span>CONFIDENCE: 97.3%</span></div>
      </div>
    </div>
  );
};

/* ═══════════════════════════════════════════════════════
   BLUR OVERLAY (before CTA)
   ═══════════════════════════════════════════════════════ */
const BlurOverlay = ({ scrollProgress }) => {
  const cRef = useRef(); const tRef = useRef();
  useEffect(() => {
    let raf; const tick = () => {
      if (!cRef.current) { raf = requestAnimationFrame(tick); return; }
      const s = scrollProgress.current;
      const bp = ease(s, ...P.blurStart);
      cRef.current.style.opacity = bp > 0.01 ? 1 : 0;
      cRef.current.style.pointerEvents = bp > 0.3 ? 'all' : 'none';
      cRef.current.style.backdropFilter = `blur(${bp * 24}px)`;
      cRef.current.style.webkitBackdropFilter = `blur(${bp * 24}px)`;
      cRef.current.style.background = `rgba(6,6,8,${bp * 0.55})`;
      if (tRef.current) {
        const ta = sm(ph(bp, 0.3, 0.8));
        tRef.current.style.opacity = ta; tRef.current.style.transform = `translateY(${(1 - ta) * 35}px)`;
      }
      raf = requestAnimationFrame(tick);
    }; tick();
    return () => cancelAnimationFrame(raf);
  }, [scrollProgress]);
  return (
    <div ref={cRef} className="blur-overlay" style={{ opacity: 0 }}>
      <div ref={tRef} className="blur-overlay-text" style={{ opacity: 0 }}>
        Tired of Reading<br />Those Big PDF's?
      </div>
    </div>
  );
};

/* ═══════════════════════════════════════════════════════
   PHASE LABELS
   ═══════════════════════════════════════════════════════ */
const PHASE_LABELS = [
  { r: [0.00, 0.07], step: 'Phase 01', title: 'Document Sphere' },
  { r: [0.07, 0.22], step: 'Phase 02', title: 'Sphere Retreats' },
  { r: [0.22, 0.42], step: 'Phase 03', title: 'Magnifying Glass Descends' },
  { r: [0.42, 0.56], step: 'Phase 04', title: 'Light Beam Activates' },
  { r: [0.56, 0.72], step: 'Phase 05', title: 'Knowledge Extraction' },
  { r: [0.72, 0.82], step: 'Phase 06', title: 'Summary Generated' },
  { r: [0.82, 1.00], step: 'Phase 07', title: 'Ready' },
];

/* ═══════════════════════════════════════════════════════
   LOGO SVG (with magnifying glass)
   ═══════════════════════════════════════════════════════ */
const LogoDocsSVG = () => (
  <svg viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path d="M4 10h10c.55 0 1 .45 1 1v10c0 .55-.45 1-1 1H4c-.55 0-1-.45-1-1V11c0-.55.45-1 1-1z"
      stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" opacity="0.5" />
    <path d="M6 7h10c.55 0 1 .45 1 1v10c0 .55-.45 1-1 1H6c-.55 0-1-.45-1-1V8c0-.55.45-1 1-1z"
      stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" opacity="0.75" />
    <path d="M8 4h10c.55 0 1 .45 1 1v10c0 .55-.45 1-1 1H8c-.55 0-1-.45-1-1V5c0-.55.45-1 1-1z"
      stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
    <path d="M10 8h6M10 11h5M10 14h5.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" opacity="0.8" />
  </svg>
);

const LogoGlassSVG = () => (
  <svg viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
    <circle cx="16" cy="16" r="11" stroke="currentColor" strokeWidth="2.8" />
    <circle cx="16" cy="16" r="7" stroke="currentColor" strokeWidth="1.2" opacity="0.3" />
    <path d="M12 12c1.5-1.5 4-2.5 6.5-1" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" opacity="0.35" />
    <path d="M24 24L35 35" stroke="currentColor" strokeWidth="3.5" strokeLinecap="round" />
  </svg>
);

/* ═══════════════════════════════════════════════════════
   FLYING GLASS (the logo glass icon — it IS the one that moves)
   ═══════════════════════════════════════════════════════ */
const FlyingGlass = ({ scrollProgress }) => {
  const ref = useRef();

  useEffect(() => {
    let raf;
    const tick = () => {
      if (!ref.current) { raf = requestAnimationFrame(tick); return; }
      const s = scrollProgress.current;
      const detach = ease(s, ...P.glassDetach);
      const flipP = ease(s, ...P.glassFlip);
      const scaleP = ease(s, ...P.glassScale);

      // Find the logo glass icon rect
      const logoGlass = document.querySelector('.nav-logo-glass-origin');
      if (!logoGlass) { raf = requestAnimationFrame(tick); return; }
      const rect = logoGlass.getBoundingClientRect();

      const sx = rect.left, sy = rect.top;
      const sw = rect.width, sh = rect.height;
      // End: large, center-left
      const ex = window.innerWidth * 0.28;
      const ey = window.innerHeight * 0.35;
      const ew = 240, eh = 240;

      const x = THREE.MathUtils.lerp(sx, ex, sm(detach));
      const y = THREE.MathUtils.lerp(sy, ey, sm(detach));
      const w = THREE.MathUtils.lerp(sw, ew, sm(scaleP));
      const h = THREE.MathUtils.lerp(sh, eh, sm(scaleP));

      ref.current.style.left = `${x}px`;
      ref.current.style.top = `${y}px`;
      ref.current.style.width = `${w}px`;
      ref.current.style.height = `${h}px`;

      // Show only during detach phase, hide once 3D takes over fully
      const showHTML = detach > 0.001 && scaleP < 0.85;
      ref.current.style.opacity = showHTML ? sm(Math.min(detach * 4, 1)) * (1 - sm(Math.max((scaleP - 0.5) / 0.35, 0))) : 0;
      ref.current.style.transform = `rotateY(${flipP * 1440}deg)`;

      // Hide original in logo
      const origin = document.querySelector('.nav-logo-glass-origin');
      if (origin) origin.style.opacity = detach > 0.02 ? String(1 - sm(Math.min(detach * 5, 1))) : '1';

      raf = requestAnimationFrame(tick);
    };
    tick();
    return () => cancelAnimationFrame(raf);
  }, [scrollProgress]);

  return (
    <div ref={ref} className="nav-logo-glass" style={{ opacity: 0 }}>
      <LogoGlassSVG />
    </div>
  );
};

/* ═══════════════════════════════════════════════════════
   APP
   ═══════════════════════════════════════════════════════ */
export default function App() {
  const scrollContainerRef = useRef();
  const pinWrapperRef = useRef();
  const ctaBtnRef = useRef();
  const scrollProgress = useRef(0);
  const ctaVisible = useRef(false);
  const isDragging = useRef(false);
  const dragStart = useRef({ x: 0, y: 0 });
  const dragRotation = useRef({ x: 0, y: 0 });
  const dragRotationStart = useRef({ x: 0, y: 0 });
  const [phaseInfo, setPhaseInfo] = useState({ step: '', title: '', visible: false });
  const totalCards = useMemo(() => buildSphereCards().length, []);

  const onPointerDown = useCallback(e => {
    if (scrollProgress.current > 0.08) return;
    isDragging.current = true;
    dragStart.current = { x: e.clientX, y: e.clientY };
    dragRotationStart.current = { ...dragRotation.current };
  }, []);
  const onPointerMove = useCallback(e => {
    if (!isDragging.current) return;
    dragRotation.current = {
      x: dragRotationStart.current.x + (e.clientX - dragStart.current.x) * 0.005,
      y: Math.max(-0.5, Math.min(0.5, dragRotationStart.current.y + (e.clientY - dragStart.current.y) * 0.003)),
    };
  }, []);
  const onPointerUp = useCallback(() => { isDragging.current = false; }, []);

  useEffect(() => {
    ScrollTrigger.getAll().forEach(t => t.kill());
    window.scrollTo(0, 0); scrollProgress.current = 0;
    if (ctaBtnRef.current) gsap.set(ctaBtnRef.current, { opacity: 0, y: 60 });

    const initTimer = setTimeout(() => {
      window.scrollTo(0, 0); ScrollTrigger.refresh(true);
      ScrollTrigger.create({
        trigger: scrollContainerRef.current,
        start: 'top top', end: 'bottom bottom',
        pin: pinWrapperRef.current, pinSpacing: false, scrub: 0.6,
        onUpdate: self => {
          scrollProgress.current = self.progress;
          if (self.progress > P.ctaAppear[0] + 0.02 && !ctaVisible.current) {
            ctaVisible.current = true;
            if (ctaBtnRef.current) gsap.to(ctaBtnRef.current, { opacity: 1, y: 0, duration: 0.8, ease: 'power3.out' });
          } else if (self.progress <= P.ctaAppear[0] + 0.02 && ctaVisible.current) {
            ctaVisible.current = false;
            if (ctaBtnRef.current) gsap.to(ctaBtnRef.current, { opacity: 0, y: 60, duration: 0.3, ease: 'power2.in' });
          }
          const active = PHASE_LABELS.find(l => self.progress >= l.r[0] && self.progress < l.r[1]);
          if (active) setPhaseInfo({ step: active.step, title: active.title, visible: true });
          else setPhaseInfo(prev => ({ ...prev, visible: false }));
        },
      });
    }, 200);

    const noOverscroll = e => {
      const max = document.documentElement.scrollHeight - window.innerHeight;
      if (window.scrollY >= max - 2 && e.deltaY > 0) e.preventDefault();
      if (window.scrollY <= 0 && e.deltaY < 0) e.preventDefault();
    };
    window.addEventListener('wheel', noOverscroll, { passive: false });
    document.body.style.overscrollBehavior = 'none';
    document.documentElement.style.overscrollBehavior = 'none';

    return () => {
      clearTimeout(initTimer); ScrollTrigger.getAll().forEach(t => t.kill());
      window.removeEventListener('wheel', noOverscroll);
      document.body.style.overscrollBehavior = '';
      document.documentElement.style.overscrollBehavior = '';
    };
  }, []);

  return (
    <div className="app-root-scroll" onPointerDown={onPointerDown} onPointerMove={onPointerMove}
      onPointerUp={onPointerUp} onPointerLeave={onPointerUp}>

      {/* SCROLL DRIVER — page ends exactly where animation ends */}
      <div ref={scrollContainerRef} className="scroll-driver">
        <div className="scroll-spacer scroll-spacer--hero" />
        <div className="scroll-spacer scroll-spacer--retreat" />
        <div className="scroll-spacer scroll-spacer--glass" />
        <div className="scroll-spacer scroll-spacer--beam" />
        <div className="scroll-spacer scroll-spacer--blur-cta" />
      </div>

      {/* PINNED */}
      <div ref={pinWrapperRef} className="pinned-viewport">
        <div className="bg-gradient" /><div className="grid-overlay" /><div className="scanline-overlay" /><div className="noise-overlay" />
        <div className="corner-deco corner-deco-tl" /><div className="corner-deco corner-deco-tr" />
        <div className="corner-deco corner-deco-bl" /><div className="corner-deco corner-deco-br" />
        <div className="ambient-glow ambient-glow-1" /><div className="ambient-glow ambient-glow-2" /><div className="ambient-glow ambient-glow-3" />

        <ProgressBar scrollProgress={scrollProgress} />

        <nav className="top-nav">
          <a className="nav-logo" href="#">
            <div className="nav-logo-icon-wrapper">
              <div className="nav-logo-docs"><LogoDocsSVG /></div>
              {/* This is the glass icon that stays in the logo — it will fade & be replaced by FlyingGlass */}
              <div className="nav-logo-glass-origin" style={{
                position: 'absolute', top: 0, right: -8, width: 18, height: 18, color: '#a78bfa',
              }}><LogoGlassSVG /></div>
            </div>
            <span className="nav-logo-text">CogniView<span className="nav-logo-dot">.</span>AI</span>
          </a>
          <div className="nav-status"><span className="status-dot" /><span className="status-text">EXTRACTION_PIPELINE // ACTIVE</span></div>
        </nav>

        {/* THE flying glass — IS the logo's glass icon, it just animates from there */}
        <FlyingGlass scrollProgress={scrollProgress} />

        <TitleOverlay scrollProgress={scrollProgress} totalCards={totalCards} />
        <CardCountDisplay count={totalCards} scrollProgress={scrollProgress} />

        <div className="canvas-container">
          <Canvas camera={{ position: [0, 0.5, 15], fov: 50 }} dpr={[1, 2]}
            gl={{ antialias: true, alpha: true, powerPreference: 'high-performance', toneMapping: THREE.NoToneMapping }}
            style={{ background: 'transparent' }}>
            <ambientLight intensity={1.0} color="#e8e4f0" />
            <directionalLight position={[5, 8, 8]} intensity={0.7} color="#c4b5fd" castShadow />
            <directionalLight position={[-6, -4, -6]} intensity={0.25} color="#fbbf24" />
            <pointLight position={[0, 0, 10]} intensity={0.4} color="#a78bfa" />
            <pointLight position={[0, 6, 4]} intensity={0.2} color="#e8e4f0" />
            <Scene scrollProgress={scrollProgress} isDragging={isDragging} dragRotation={dragRotation} />
          </Canvas>
        </div>

        <div className={`phase-label-overlay ${phaseInfo.visible ? 'visible' : ''}`}>
          <span className="phase-step">{phaseInfo.step}</span>
          <span className="phase-title">{phaseInfo.title}</span>
        </div>

        <SummaryPaperOverlay scrollProgress={scrollProgress} />
        <BlurOverlay scrollProgress={scrollProgress} />

        <div ref={ctaBtnRef} className="cta-button-wrapper" style={{ opacity: 0, transform: 'translateX(-50%) translateY(60px)' }}>
          <button className="cta-button cta-button-large">
            <span>Get Started</span>
            <svg className="cta-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M5 12h14M12 5l7 7-7 7" /></svg>
          </button>
          <span className="cta-subtext">No credit card required</span>
        </div>

        <div className="bottom-bar">
          <div className="bottom-bar-left"><span className="bottom-mono">SYS.RENDER</span><span className="bottom-separator">|</span><span className="bottom-mono dim">THREE.JS r{THREE.REVISION}</span></div>
          <div className="bottom-bar-center"><BottomHint scrollProgress={scrollProgress} /></div>
          <div className="bottom-bar-right"><span className="bottom-mono dim">CARDS: {totalCards}</span><span className="bottom-separator">|</span><span className="bottom-mono">R: {SPHERE_RADIUS}</span></div>
        </div>
      </div>
    </div>
  );
}
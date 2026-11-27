import React, { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { landDots, toVec } from './Globe.jsx';
import { reducedMotion } from './viz.jsx';
import { useI18n } from './i18n.jsx';

// The hero tells one story in four acts, using beams BRIDGE really chose in the flood-relief replay:
// calm beams -> demand starts to rise on the event cell -> the beam hops there -> the guard checks it.
export const ACTS = [
  ['Observe', 'Telemetry arrives one slot late'],
  ['Forecast', 'Demand starts rising in one cell'],
  ['Decide', 'BRIDGE moves a beam there early'],
  ['Check', 'The guard verifies every limit'],
];
const ACT_S = 3.6;
const ease = (x) => (x < 0.5 ? 4 * x * x * x : 1 - (-2 * x + 2) ** 3 / 2);

export default function HeroScene({ replay }) {
  const { t } = useI18n();
  const ref = useRef(null);
  const chip = useRef(null);
  const [act, setAct] = useState(0);
  const jump = useRef(null);
  useEffect(() => {
    const canvas = ref.current;
    let renderer;
    try { renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true }); } catch { return undefined; }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    const { cells, meta } = replay; const lit = replay.runs.OrbitFlow.series.lit;
    const ec = meta.event_cell;
    let calmT = 0; for (let t = 0; t < 22; t++) if (!lit[t].includes(ec)) calmT = t;
    const decideT = lit.findIndex((l, t) => t >= 23 && l.includes(ec));
    const calm = lit[calmT]; const decide = lit[decideT];
    const demand = replay.demand;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(30, 1, 0.1, 50);
    const center = { lat: 21, lon: 88 };
    const world = new THREE.Group(); scene.add(world);
    world.rotation.y = -(center.lon * Math.PI) / 180 + 0.08;
    world.rotation.x = (center.lat * Math.PI) / 180 - 0.78;
    world.add(new THREE.Mesh(new THREE.SphereGeometry(0.995, 64, 64), new THREE.MeshBasicMaterial({ color: 0x0f1419 })));
    const dots = new THREE.BufferGeometry(); dots.setAttribute('position', new THREE.Float32BufferAttribute(landDots(), 3));
    world.add(new THREE.Points(dots, new THREE.PointsMaterial({ color: 0x55626b, size: 0.008 })));
    const rim = new THREE.Mesh(new THREE.SphereGeometry(1.012, 64, 64), new THREE.ShaderMaterial({
      transparent: true, side: THREE.BackSide, depthWrite: false,
      vertexShader: 'varying vec3 n; void main(){ n = normalize(normalMatrix*normal); gl_Position = projectionMatrix*modelViewMatrix*vec4(position,1.); }',
      fragmentShader: 'varying vec3 n; void main(){ float a = pow(max(0., .5 - abs(n.z)), 3.); gl_FragColor = vec4(.37,.89,.75, a*.6); }',
    }));
    rim.scale.setScalar(1.05); scene.add(rim);

    // footprint
    const xs = cells.map((c) => c.x); const ys = cells.map((c) => c.y);
    const mx = (Math.min(...xs) + Math.max(...xs)) / 2; const my = (Math.min(...ys) + Math.max(...ys)) / 2;
    const deg = 17 / Math.max(Math.max(...xs) - Math.min(...xs), 1);
    const cosl = Math.cos((center.lat * Math.PI) / 180);
    const pos = cells.map((c) => ({ lat: center.lat + (c.y - my) * deg, lon: center.lon + ((c.x - mx) * deg) / cosl }));
    const hexR = Math.hypot(cells[1].x - cells[0].x, cells[1].y - cells[0].y) * deg * 0.55;
    const hexPts = (p, k = 0.94, r = 1.006) => { const s = []; for (let i = 0; i <= 6; i++) { const a = Math.PI / 6 + (i * Math.PI) / 3; s.push(toVec(p.lat + hexR * k * Math.sin(a), p.lon + (hexR * k * Math.cos(a)) / cosl, r)); } return s; };
    const fills = pos.map((p) => {
      const s = hexPts(p); const c = toVec(p.lat, p.lon, 1.006); const v = [];
      for (let i = 0; i < 6; i++) v.push(c.x, c.y, c.z, s[i].x, s[i].y, s[i].z, s[i + 1].x, s[i + 1].y, s[i + 1].z);
      const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(v, 3));
      const m = new THREE.Mesh(g, new THREE.MeshBasicMaterial({ color: 0x5fe3c0, transparent: true, opacity: 0.08, side: THREE.DoubleSide, depthWrite: false }));
      world.add(m);
      world.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(s), new THREE.LineBasicMaterial({ color: 0x5fe3c0, transparent: true, opacity: 0.35 })));
      return m;
    });
    const ring = new THREE.Line(new THREE.BufferGeometry().setFromPoints(hexPts(pos[ec], 1.0, 1.008)), new THREE.LineBasicMaterial({ color: 0xffa24d, transparent: true, opacity: 0 }));
    world.add(ring);
    const ringCenter = toVec(pos[ec].lat, pos[ec].lon, 1.008);

    // satellite: body, two wings, dish, blinking light
    const sat = new THREE.Group();
    const cream = new THREE.MeshBasicMaterial({ color: 0xece7dc });
    sat.add(new THREE.Mesh(new THREE.BoxGeometry(0.05, 0.05, 0.065), cream));
    const wingMat = new THREE.MeshBasicMaterial({ color: 0x3c9bdc });
    const edgeMat = new THREE.LineBasicMaterial({ color: 0x9fd2f5, transparent: true, opacity: 0.8 });
    [-1, 1].forEach((sgn) => {
      const w = new THREE.Mesh(new THREE.BoxGeometry(0.15, 0.004, 0.05), wingMat); w.position.x = sgn * 0.11; sat.add(w);
      const e = new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(0.15, 0.005, 0.05)), edgeMat); e.position.x = sgn * 0.11; sat.add(e);
      for (let k = 1; k < 4; k++) { const ln = new THREE.Mesh(new THREE.BoxGeometry(0.002, 0.006, 0.05), new THREE.MeshBasicMaterial({ color: 0x9fd2f5 })); ln.position.x = sgn * (0.035 + k * 0.0375); sat.add(ln); }
      const arm = new THREE.Mesh(new THREE.BoxGeometry(0.012, 0.004, 0.004), cream); arm.position.x = sgn * 0.031; sat.add(arm);
    });
    const dish = new THREE.Mesh(new THREE.ConeGeometry(0.022, 0.018, 24, 1, true), new THREE.MeshBasicMaterial({ color: 0xd9d3c6, side: THREE.DoubleSide }));
    dish.rotation.x = Math.PI / 2; dish.position.z = 0.042; sat.add(dish);
    const blink = new THREE.Mesh(new THREE.SphereGeometry(0.007, 12, 12), new THREE.MeshBasicMaterial({ color: 0x5fe3c0, transparent: true }));
    blink.position.set(0, 0.03, -0.02); sat.add(blink);
    sat.scale.setScalar(0.8);
    scene.add(sat);
    const orbitR = 1.5;
    const orbit = (f) => { const v = toVec(center.lat + 2 + f * 18, center.lon - 40 + f * 70, orbitR); return world.localToWorld(v); };
    const path = []; for (let i = 0; i <= 80; i++) path.push(orbit(i / 80));
    scene.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(path), new THREE.LineDashedMaterial({ color: 0x5a646c, dashSize: 0.02, gapSize: 0.02 })).computeLineDistances());

    // beams: translucent cones (sat -> cell edge) plus a bright core line
    const beams = [0, 1, 2, 3].map(() => {
      const cone = new THREE.Mesh(new THREE.BufferGeometry(), new THREE.MeshBasicMaterial({ color: 0x5fe3c0, transparent: true, opacity: 0.12, side: THREE.DoubleSide, depthWrite: false }));
      cone.geometry.setAttribute('position', new THREE.Float32BufferAttribute(new Array(9).fill(0), 3));
      const core = new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(), new THREE.Vector3()]), new THREE.LineBasicMaterial({ color: 0x5fe3c0, transparent: true, opacity: 0.9 }));
      scene.add(cone); scene.add(core); return { cone, core };
    });
    const cellW = (c) => world.localToWorld(toVec(pos[c].lat, pos[c].lon, 1.006));
    // choose which calm beam moves: the one whose cell is NOT in the decided set
    const leaving = calm.find((c) => !decide.includes(c));
    const arriving = ec;
    const pairs = calm.map((c) => [c, c === leaving ? arriving : c]);

    const resize = () => {
      const { clientWidth: w, clientHeight: h } = canvas; if (!w || !h) return;
      renderer.setSize(w, h, false); camera.aspect = w / h;
      camera.position.set(0, 0.56, w / h < 0.9 ? 4.1 : 3.3); camera.lookAt(0, 0.56, 0); camera.updateProjectionMatrix();
    };
    const ro = new ResizeObserver(resize); ro.observe(canvas); resize();
    let raf; let visible = true;
    const io = new IntersectionObserver(([e]) => { visible = e.isIntersecting; }); io.observe(canvas);
    const still = reducedMotion();
    let t0 = performance.now(); let lastAct = -1;
    jump.current = (a) => { t0 = performance.now() - a * ACT_S * 1000; };
    const tmp = new THREE.Vector3();
    const frame = (now) => {
      raf = requestAnimationFrame(frame);
      if (!visible) return;
      const secs = still ? 3.5 * ACT_S : ((now - t0) / 1000) % (4 * ACT_S);
      const a = Math.min(3, Math.floor(secs / ACT_S)); const p = (secs % ACT_S) / ACT_S;
      if (a !== lastAct) { lastAct = a; setAct(a); }
      const f = 0.42 + 0.16 * Math.sin(secs / (4 * ACT_S) * Math.PI * 2 - Math.PI / 2) * 0.5;
      const sp = orbit(f); sat.position.copy(sp); sat.lookAt(0, 0, 0);
      sat.position.y += Math.sin(now / 900) * 0.004;
      blink.material.opacity = 0.4 + 0.6 * (Math.sin(now / 260) > 0.6 ? 1 : 0);
      // demand: calm level for every cell; the event cell ramps during Forecast
      const rise = a === 0 ? 0 : a === 1 ? ease(p) : 1;
      const swing = a < 2 ? 0 : a === 2 ? ease(Math.min(1, p * 1.4)) : 1;
      const nowLit = new Set(pairs.map(([x, y]) => (swing > 0.5 ? y : x)));
      fills.forEach((m, i) => {
        const base = Math.min(1, demand[calmT][i] / 40);
        let target = 0.05 + base * 0.25 + (nowLit.has(i) ? 0.45 : 0);
        if (i === ec) { m.material.color.setHex(rise > 0.05 ? 0xffa24d : 0x5fe3c0); target = Math.max(target, 0.12 + rise * 0.6); }
        m.material.opacity += (target - m.material.opacity) * 0.12;
      });
      ring.material.opacity = a === 1 ? 0.9 * (0.5 + 0.5 * Math.sin(now / 160)) : a >= 2 ? 0.5 : 0;
      const sc = a === 1 ? 1 + 0.25 * ((now / 700) % 1) : 1;
      ring.scale.setScalar(1); ring.position.copy(ringCenter.clone().multiplyScalar(1 - sc)); ring.scale.setScalar(sc);
      beams.forEach((b, k) => {
        const [from, to] = pairs[k];
        const end = cellW(from).lerp(cellW(to), from === to ? 0 : swing);
        const side = tmp.copy(end).cross(sp).normalize().multiplyScalar(hexR * 0.0175 * 0.55);
        const l = end.clone().add(side); const r = end.clone().sub(side);
        const arr = b.cone.geometry.attributes.position.array; arr.set([sp.x, sp.y, sp.z, l.x, l.y, l.z, r.x, r.y, r.z]); b.cone.geometry.attributes.position.needsUpdate = true;
        b.core.geometry.setFromPoints([sp, end]);
        const moving = from !== to && a === 2;
        b.core.material.color.setHex(moving || (from !== to && a === 3) ? 0xffc785 : 0x5fe3c0);
      });
      // chip anchored to the event cell
      if (chip.current) {
        const v = cellW(ec).project(camera);
        const { clientWidth: w, clientHeight: h } = canvas;
        chip.current.style.transform = `translate(${((v.x + 1) / 2) * w + 18}px, ${((1 - v.y) / 2) * h - 14}px)`;
        chip.current.style.opacity = a === 0 ? 0 : 1;
      }
      renderer.render(scene, camera);
    };
    raf = requestAnimationFrame(frame);
    return () => { cancelAnimationFrame(raf); ro.disconnect(); io.disconnect(); renderer.dispose(); };
  }, [replay]);
  const chipText = act ? t(`chip.${act}`) : null;
  return (
    <div className="scene">
      <canvas ref={ref} className="scene-canvas" aria-label={t('hero.anim')} role="img" />
      <div ref={chip} className={`scene-chip act${act}`} aria-hidden="true">{chipText}</div>
      <ol className="acts">
        {ACTS.map((_, i) => (
          <li key={i} className={i === act ? 'on' : i < act ? 'done' : ''}>
            <button onClick={() => jump.current?.(i)}><span className="mono">{String(i + 1).padStart(2, '0')}</span> {t(`act.${i}`)}<small>{t(`act.${i}.sub`)}</small></button>
          </li>
        ))}
      </ol>
    </div>
  );
}

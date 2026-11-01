import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import '@fontsource/newsreader/400.css';
import '@fontsource/newsreader/400-italic.css';
import '@fontsource/ibm-plex-sans/400.css';
import '@fontsource/ibm-plex-sans/500.css';
import '@fontsource/ibm-plex-sans/600.css';
import '@fontsource/ibm-plex-mono/400.css';
import '@fontsource/ibm-plex-mono/500.css';
import './theme.css';
import App from './App.jsx';

const FILES = ['kpi_table', 'flood_mc', 'whatif_grid', 'flood_replay', 'kb_report', 'gaps', 'predictor_metrics', 'bridge_training', 'bridge_training_noforecast'];

function Root() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => {
    Promise.all(FILES.map((f) => fetch(`data/${f}.json`).then((r) => { if (!r.ok) throw new Error(f); return r.text(); }).then((t) => JSON.parse(t.replace(/\bNaN\b/g, 'null')))))
      .then((all) => setData(Object.fromEntries(FILES.map((f, i) => [f, all[i]]))))
      .catch((e) => setErr(String(e.message)));
  }, []);
  if (err) return <div style={{ padding: 48 }}><h2>Results not found ({err})</h2><p className="lede">Run <code>python scripts/run_eval.py</code>, then reload.</p></div>;
  if (!data) return <div style={{ padding: 48, fontFamily: 'monospace', color: '#868e94' }}>Loading results…</div>;
  return <App d={data} />;
}

createRoot(document.getElementById('root')).render(<Root />);

import React, { createContext, useContext, useEffect, useMemo, useState } from 'react';

// One language for the whole page. Strings live in i18n/locales/<lang>.json (copied to public/data/i18n_<lang>.json):
//   app.*  story chapters, hero, flowchart, game     ui.*  operations console     terms.*, scenarios.*  shared terms
export const LANGS = [['en', 'English'], ['ar', 'العربية'], ['hi', 'हिन्दी'], ['ta', 'தமிழ்']];
const Ctx = createContext(null);

const fill = (s, vars) => (vars ? s.replace(/\{(\w+)\}/g, (m, k) => (vars[k] ?? m)) : s);

export function LangProvider({ d, children }) {
  const [lang, setLang] = useState(() => { try { const l = localStorage.getItem('of-lang'); return d[`i18n_${l}`] ? l : 'en'; } catch { return 'en'; } });
  const loc = d[`i18n_${lang}`] || d.i18n_en;
  const dir = loc._meta.dir;
  useEffect(() => {
    try { localStorage.setItem('of-lang', lang); } catch { /* storage unavailable */ }
    document.documentElement.lang = lang;
    document.documentElement.dir = dir;
  }, [lang, dir]);
  const value = useMemo(() => {
    const en = d.i18n_en;
    const get = (sec, k) => loc[sec]?.[k] ?? en[sec]?.[k];
    return {
      lang, setLang, dir, loc,
      t: (k, vars) => fill(get('app', k) ?? k, vars),       // story/app strings
      ui: (k, vars) => fill(get('ui', k) ?? k, vars),       // console strings
      term: (k) => get('terms', k) ?? k,
      scen: (id, fb) => loc.scenarios?.[id] ?? fb,
    };
  }, [lang, loc, dir, d]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export const useI18n = () => useContext(Ctx);

export function LangSwitch() {
  const { lang, setLang, t } = useI18n();
  return (
    <div className="langswitch" role="group" aria-label={t('nav.language')}>
      {LANGS.map(([k, n]) => <button key={k} lang={k} className={k === lang ? 'on' : ''} aria-pressed={k === lang} onClick={() => setLang(k)}>{n}</button>)}
    </div>
  );
}

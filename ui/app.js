/* Gemma's voice + live transcript.
 * Watches Michael's server (/api/state + /api/progress via serve.py). Each new Gemma decision is
 * spoken aloud and written out line by line; the orb moves while it talks.
 * ?mock=1 replays a recorded run (R restarts). V toggles voice.
 */
const $ = id => document.getElementById(id);
const MOCK = new URLSearchParams(location.search).has('mock');

const ACTIONS = {
  pick_probe: 'Picking up the probe.', measure_input: 'Probing the supply side.', measure_output: 'Probing after the resistor.',
  dock_probe: 'Docking the probe.', remove_resistor: 'Pulling the faulty resistor.', discard_resistor: 'Dropping it in the reject bin.',
  pick_spare: 'Grabbing a spare resistor.', insert_resistor: 'Installing the spare.', finish: 'Repair verified.', abort: 'Stopping safely.',
};
const say = a => ACTIONS[a] || (a || '').replace(/_/g, ' ') + '.';

/* ---------- data: live or mock ---------- */
const getJSON = async p => { const r = await fetch(p); const j = await r.json(); if (!r.ok) throw Error(j.detail); return j; };
const live = { state: () => getJSON('api/state'), progress: () => getJSON('api/progress') };
const mock = (() => {
  let trace, st, pr, timers = [];
  async function start() {
    trace = trace || await (await fetch('mock/trace.json')).json();
    timers.forEach(clearTimeout); timers = [];
    st = { events: [], done: false, success: false, episode: String(Date.now()) }; pr = { phase: 'idle' };
    let t = 1500;
    for (const s of trace.steps) {
      const at = (ms, fn) => timers.push(setTimeout(fn, (t += ms) - ms));
      at(Math.max(1500, s.seconds * 1000), () => pr = { phase: 'inference' });
      at(5500, () => { st.events.push({ step: s.step, action: s.action, decision: { action: s.action, reason: s.reason } });
        pr = { phase: 'physics' }; if (s.action === 'finish') { st.done = true; st.success = trace.success; } });
    }
  }
  return { start, state: async () => structuredClone(st), progress: async () => ({ ...pr }) };
})();
const src = MOCK ? mock : live;

/* ---------- speech + transcript ---------- */
let voiceOn = true, queue = [], talking = false;
function addLine() {
  const t = $('transcript');
  t.querySelectorAll('.line.now').forEach(l => { l.classList.remove('now'); l.querySelector('.caret')?.remove(); });
  const el = document.createElement('p'); el.className = 'line now'; t.append(el);
  while (t.children.length > 8) t.firstChild.remove();
  return el;
}
function show(el, text, upto) {
  el.textContent = text.slice(0, upto);
  if (upto < text.length) { const c = document.createElement('span'); c.className = 'caret'; el.append(c); }
}
function next() {
  if (talking || !queue.length) return;
  talking = true;
  const text = queue.shift(), el = addLine();
  let shown = 0, gotBoundary = false, finished = false;
  const tick = setInterval(() => {   // fallback reveal (~16 chars/s) if the voice gives no word timing
    if (!gotBoundary) { shown = Math.min(text.length, shown + 1); show(el, text, shown); }
  }, 60);
  const done = () => {
    if (finished) return; finished = true;
    clearInterval(tick); show(el, text, text.length);
    document.body.classList.remove('speaking'); talking = false; setTimeout(next, 250);
  };
  if (voiceOn && 'speechSynthesis' in window) {
    const u = new SpeechSynthesisUtterance(text);
    u.rate = 1.05;
    const v = speechSynthesis.getVoices().find(v => /Samantha|Daniel|Google UK English Female|Ava|Alex/.test(v.name));
    if (v) u.voice = v;
    u.onstart = () => document.body.classList.add('speaking');
    u.onboundary = e => { gotBoundary = true; const end = text.indexOf(' ', e.charIndex + 1); shown = end < 0 ? text.length : end; show(el, text, shown); };
    u.onend = u.onerror = done;
    speechSynthesis.speak(u);
    setTimeout(done, text.length * 90 + 4000);   // safety net if the browser never fires onend
  } else {
    document.body.classList.add('speaking');
    setTimeout(done, text.length * 60 + 300);
  }
}
const similar = (a, b) => {
  const w = s => new Set(s.toLowerCase().replace(/[^a-z0-9 ]/g, '').split(' ').filter(x => x.length > 3));
  const A = w(a), B = w(b); if (!A.size || !B.size) return false;
  let n = 0; A.forEach(x => B.has(x) && n++); return n / Math.min(A.size, B.size) > 0.7;
};
function speak(text) { if (text) { queue.push(text); next(); } }

/* ---------- loop ---------- */
let seen = 0, lastReason = '', episode = null, ended = false;
async function poll() {
  try {
    const [st, pr] = await Promise.all([src.state(), src.progress()]);
    if (st.episode !== episode || st.events.length < seen) {   // new run: start fresh
      episode = st.episode; seen = 0; lastReason = ''; ended = false; queue = [];
      if ('speechSynthesis' in window) speechSynthesis.cancel();
      $('transcript').replaceChildren();
    }
    document.body.dataset.state = pr.phase === 'inference' || pr.phase === 'perception' ? 'thinking'
      : st.events.length || (pr.phase && pr.phase !== 'idle') ? 'active' : 'idle';
    for (const ev of st.events.slice(seen)) {
      const r = ev.decision?.reason || '';
      speak(r && !similar(r, lastReason) ? r : say(ev.action));   // skip Gemma's near-repeats
      if (r) lastReason = r;
    }
    seen = st.events.length;
    if (st.done && !ended) { ended = true; speak(st.success ? 'Circuit restored. No humans needed.' : 'I stopped without claiming a repair.'); }
  } catch { /* bench server not up yet; keep polling */ }
}

addEventListener('click', () => { $('hint').hidden = true; if ('speechSynthesis' in window) speechSynthesis.getVoices(); }, { once: true });
addEventListener('keydown', e => {
  if (e.key === 'v' || e.key === 'V') { voiceOn = !voiceOn; if (!voiceOn && 'speechSynthesis' in window) speechSynthesis.cancel(); }
  if ((e.key === 'r' || e.key === 'R') && MOCK) mock.start();
});
(async () => { if (MOCK) await mock.start(); poll(); setInterval(poll, 500); })();

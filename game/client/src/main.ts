import './styles.css';
import { DemoBackend, ReplayBackend, ServerBackend, type Backend } from './api';
import { Game } from './game';

function fit() {
  const s = Math.min(window.innerWidth / 1280, window.innerHeight / 720);
  document.getElementById('stage')!.style.transform = `scale(${s})`;
}
window.addEventListener('resize', fit); fit();

async function pickBackend(): Promise<Backend> {
  const q = new URLSearchParams(location.search);
  const replay = q.get('replay');
  if (replay) { const data = await fetch(replay).then(r => r.json()); return new ReplayBackend(data.rounds ?? data); }
  if (q.get('demo') === '1') return new DemoBackend();
  const server = new ServerBackend(q.get('market') ?? 'default', q.get('variant') ?? '96');
  try { await server.config(); return server; } catch { return new DemoBackend(); } // no server: static demo
}

pickBackend().then(b => new Game(b).init()).catch(e => {
  console.error(e);
  document.getElementById('loading')!.innerHTML = '<span class="d">Could not start the game</span>';
});
(window as any).__ready = true;

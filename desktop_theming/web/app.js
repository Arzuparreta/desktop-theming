'use strict';

const $ = id => document.getElementById(id);
const token = document.querySelector('meta[name="app-token"]').content;
let state, reviewedPlan = null, undoId = null, busy = false;
let selected = new Set();

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

async function api(path, body) {
  const response = await fetch(`/api/${path}`, {
    method: body === undefined ? 'GET' : 'POST',
    headers: {'Content-Type': 'application/json', 'X-Desktop-Theming-Token': token},
    ...(body === undefined ? {} : {body: JSON.stringify(body)}),
  });
  const value = await response.json();
  if (!response.ok) throw new Error(value.error || 'The operation could not be completed.');
  return value;
}

function notify(message, error = false) {
  $('notice').textContent = message;
  $('notice').className = error ? 'error' : '';
  $('notice').hidden = false;
  for (const name of ['review', 'undo']) {
    const box = $(`${name}-error`);
    box.hidden = !error || !$(`${name}-dialog`).open;
    box.textContent = message;
  }
}

function invalidate() {
  reviewedPlan = null;
  $('apply').disabled = true;
  $('palette-status').textContent = 'Settings changed. Preview again to update the colors.';
}

function profile() {
  return {version: 1, components: [...selected].sort(), wallpaper: $('wallpaper').value.trim(),
    mode: $('mode').value, polarity: $('polarity').value};
}

function selection() {
  const container = $('selected-components');
  container.replaceChildren();
  if (!selected.size) container.append(element('span', 'small-note', 'Choose a supported component on the left.'));
  for (const id of selected) {
    const item = state.components.find(item => item.id === id);
    container.append(element('span', 'selected-chip', item?.name || id));
  }
}

function renderComponents() {
  const groups = new Map();
  const search = $('search').value.toLowerCase();
  const all = $('show-all').checked;
  for (const item of state.components) {
    const configured = item.configs.some(config => config.exists);
    if (!all && !item.installed && !item.running && !configured && !selected.has(item.id)) continue;
    if (!`${item.name} ${item.category}`.toLowerCase().includes(search)) continue;
    if (!groups.has(item.category)) groups.set(item.category, []);
    groups.get(item.category).push(item);
  }
  const container = $('components');
  container.replaceChildren();
  let count = 0;
  for (const [category, items] of groups) {
    const group = element('section', 'component-group');
    group.append(element('h3', 'category-heading', category));
    for (const item of items) {
      count++;
      const card = element('div', `component-card${selected.has(item.id) ? ' selected' : ''}`);
      const icons = {Terminal: '>_', Session: '◫', Bar: '▤', Launcher: '⌘', Notifications: '◷', Applications: 'Aa', Shell: '$', Wallpaper: '▧'};
      card.append(element('span', 'component-icon', icons[category]));
      const details = element('div', 'component-details');
      const title = element('div', 'component-name', item.name);
      if (item.current_session) title.append(element('span', 'badge green', 'Current session'));
      details.append(title);
      const badges = element('div', 'component-status');
      badges.append(element('span', `badge ${item.installed ? 'neutral' : 'outline'}`,
        item.installed === null ? 'Installation unknown' : item.installed ? 'On PATH' : 'Not on PATH'));
      if (item.running) badges.append(element('span', 'badge green', 'Running'));
      if (item.configs.some(config => config.exists)) badges.append(element('span', 'badge neutral', 'Configured'));
      if (item.managed) badges.append(element('span', 'badge green', 'Managed'));
      details.append(badges);
      const existing = item.configs.filter(config => config.exists);
      const paths = existing.length ? existing : item.configs.slice(0, 1);
      for (const config of paths) {
        const path = element('span', 'component-path', `${config.path}${config.symlink ? ' ↗ symlink' : ''}`);
        path.title = config.path;
        details.append(path);
      }
      card.append(details);
      if (item.supported) {
        const label = element('label', 'connect-label');
        const input = document.createElement('input');
        input.type = 'checkbox';
        input.checked = selected.has(item.id);
        input.disabled = !item.installed && !selected.has(item.id);
        input.setAttribute('aria-label', `Connect ${item.name} to the theme`);
        label.title = item.installed ? 'Select for the next reviewed plan' : 'Install this application explicitly to enable theming';
        input.addEventListener('change', () => {
          input.checked ? selected.add(item.id) : selected.delete(item.id);
          invalidate(); renderComponents(); selection();
        });
        label.append(input, document.createTextNode('Connect'));
        card.append(label);
      } else card.append(element('span', 'discovery-label', 'Discovery only'));
      group.append(card);
    }
    container.append(group);
  }
  if (!count) container.append(element('p', 'empty', 'No matching components. Try “Show all” to explore supported discovery.'));
  $('component-count').textContent = count;
}

function renderPalette(value) {
  const preview = $('terminal-preview');
  preview.style.setProperty('--preview-bg', value.special.background);
  preview.style.setProperty('--preview-fg', value.special.foreground);
  $('swatches').replaceChildren();
  for (let i = 0; i < 16; i++) {
    preview.style.setProperty(`--c${i}`, value.colors[`color${i}`]);
    const swatch = element('span', 'swatch');
    swatch.style.backgroundColor = value.colors[`color${i}`];
    swatch.title = `ANSI ${i}: ${value.colors[`color${i}`]}`;
    $('swatches').append(swatch);
  }
  $('palette-status').textContent = `${value.effective === 'safe' ? 'Safe' : 'Wallpaper'} palette · ${value.polarity}. ${value.reason || 'Terminal contrast checks passed.'}`;
}

function renderHistory() {
  const container = $('transactions');
  container.replaceChildren();
  const active = state.history.find(item => ['applied', 'prepared', 'recovery-needed', 'undoing'].includes(item.status));
  if (!state.history.length) {
    container.className = 'history-empty';
    container.textContent = 'Your applied themes will appear here, with an option to undo.';
    return;
  }
  container.className = '';
  for (const transaction of state.history) {
    const row = element('div', 'transaction');
    const info = element('div');
    info.append(element('strong', '', transaction.components.length ? transaction.components.join(' + ') : 'Workspace preferences'));
    info.append(element('p', '', `${new Date(transaction.created).toLocaleString()} · ${transaction.files} files · ${transaction.status}`));
    row.append(info);
    if (transaction === active && transaction.status === 'applied') {
      const button = element('button', 'secondary', 'Undo changes');
      button.addEventListener('click', () => {
        undoId = transaction.id;
        $('undo-description').textContent = `Restore ${transaction.files} files from the ${new Date(transaction.created).toLocaleString()} transaction.`;
        $('undo-error').hidden = true;
        $('undo-dialog').showModal();
      });
      row.append(button);
    } else if (transaction === active) {
      info.append(element('p', '', `Recovery required: desktop-theming recover ${transaction.id} --yes`));
    }
    container.append(row);
  }
}

async function refresh(reset = false) {
  state = await api('overview');
  $('desktop').textContent = state.session.desktop;
  $('session-type').textContent = `${state.session.type === 'unknown' ? 'Session type unknown' : state.session.type === 'x11' ? 'X11 session' : 'Wayland session'} · current user`;
  $('installed-count').textContent = state.components.filter(item => item.installed).length;
  $('managed-count').textContent = state.components.filter(item => item.managed).length;
  $('discovery-scope').textContent = `${state.scope} Discovery does not change settings.`;
  if (reset) {
    selected = new Set(state.profile.components);
    for (const field of ['wallpaper', 'mode', 'polarity']) $(field).value = state.profile[field];
  }
  const preferences = Object.entries(state.gtk);
  $('gtk-settings').hidden = !preferences.length;
  $('gtk-values').replaceChildren();
  for (const [key, value] of preferences) $('gtk-values').append(element('dt', '', key.replace('gtk-', '')), element('dd', '', value));
  renderComponents(); selection(); renderHistory();
}

async function run(button, operation) {
  if (busy) return;
  busy = true; button.disabled = true;
  const text = button.textContent;
  button.textContent = 'Working…';
  try { await operation(); }
  catch (error) { notify(error.message, true); }
  finally { busy = false; button.disabled = false; button.textContent = text; }
}

$('show-all').addEventListener('change', renderComponents);
$('search').addEventListener('input', renderComponents);
for (const field of ['wallpaper', 'mode', 'polarity']) $(field).addEventListener('input', invalidate);
$('refresh').addEventListener('click', event => run(event.currentTarget, async () => {
  invalidate(); await refresh(); notify('Inventory refreshed. Your draft selection has been kept.');
}));
$('preview').addEventListener('click', event => run(event.currentTarget, async () => {
  const requested = profile();
  const value = await api('preview', requested);
  if (JSON.stringify(requested) === JSON.stringify(profile())) renderPalette(value);
}));
$('review').addEventListener('click', event => run(event.currentTarget, async () => {
  const requested = profile();
  reviewedPlan = await api('plan', requested);
  if (JSON.stringify(requested) !== JSON.stringify(profile())) {
    invalidate();
    notify('Your selection changed while the plan was prepared. Review the updated selection.');
    return;
  }
  renderPalette(reviewedPlan.palette);
  $('review-summary').textContent = `${reviewedPlan.changes.length} file change(s). Only the selected components and Desktop Theming preferences are included.`;
  $('review-warnings').replaceChildren(...reviewedPlan.warnings.map(warning => element('p', '', warning)));
  $('file-changes').replaceChildren();
  for (const item of reviewedPlan.changes) {
    const details = element('details', 'file-change');
    details.open = true;
    details.append(element('summary', '', `${item.path}${item.detach_symlink ? ' · detach symlink' : ''}`), element('pre', '', item.diff));
    $('file-changes').append(details);
  }
  $('apply').disabled = !reviewedPlan.changes.length;
  $('review-error').hidden = true;
  $('review-dialog').showModal();
}));
for (const id of ['close-review', 'cancel-review']) $(id).addEventListener('click', () => $('review-dialog').close());
$('apply').addEventListener('click', event => run(event.currentTarget, async () => {
  if (!reviewedPlan) throw new Error('Review a fresh plan before applying.');
  const result = await api('apply', {id: reviewedPlan.id, approved: true});
  $('review-dialog').close();
  invalidate(); await refresh(true);
  notify(result.status === 'unchanged' ? 'The theme is already up to date.' : 'Theme files applied. Restart the selected terminal or use its reload action. Your other components have been left as they were.');
}));
$('cancel-undo').addEventListener('click', () => $('undo-dialog').close());
$('confirm-undo').addEventListener('click', event => run(event.currentTarget, async () => {
  await api('undo', {id: undoId, approved: true});
  $('undo-dialog').close(); invalidate(); await refresh(true);
  renderPalette(await api('preview', profile()));
  notify('Previous configuration restored. Reload the selected terminal to see it.');
}));

(async () => {
  try { await refresh(true); renderPalette(await api('preview', profile())); }
  catch (error) { notify(error.message, true); }
})();

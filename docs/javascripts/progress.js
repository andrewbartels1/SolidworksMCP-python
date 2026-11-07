// Level and family filters for the progress page's tool table.
// Without scripts the full table still shows; this only hides rows.

function setUpProgressFilters() {
    const box = document.querySelector('.progress-filters');
    const table = document.querySelector('table[data-progress="tools"]');
    if (!box || !table || box.dataset.ready) return;
    box.dataset.ready = '1';

    const rows = Array.from(table.querySelectorAll('tbody tr'));
    const levels = ['stable', 'beta', 'experimental', 'planned'];
    const families = Array.from(new Set(rows.map(r => r.dataset.family))).sort();
    const chosen = { level: null, family: null };

    function apply() {
        let shown = 0;
        rows.forEach(function (row) {
            const ok = (!chosen.level || row.dataset.level === chosen.level) &&
                (!chosen.family || row.dataset.family === chosen.family);
            row.hidden = !ok;
            if (ok) shown += 1;
        });
        count.textContent = shown + ' of ' + rows.length + ' tools';
    }

    function group(label, key, values) {
        const line = document.createElement('div');
        line.className = 'progress-filter-group';
        line.append(label + ': ');
        [null].concat(values).forEach(function (value) {
            const chip = document.createElement('button');
            chip.type = 'button';
            chip.className = 'progress-chip' + (value && key === 'level' ? ' level-' + value : '');
            chip.textContent = value || 'all';
            chip.setAttribute('aria-pressed', String(value === null));
            chip.addEventListener('click', function () {
                chosen[key] = value;
                line.querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed', 'false'));
                chip.setAttribute('aria-pressed', 'true');
                apply();
            });
            line.append(chip);
        });
        return line;
    }

    const count = document.createElement('div');
    count.className = 'progress-count';
    box.append(group('Level', 'level', levels), group('Family', 'family', families), count);
    box.hidden = false;
    apply();
}

if (typeof document$ !== 'undefined') {
    document$.subscribe(setUpProgressFilters);
} else {
    document.addEventListener('DOMContentLoaded', setUpProgressFilters);
}

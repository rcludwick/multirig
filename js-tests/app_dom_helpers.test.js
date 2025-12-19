describe('multirig static/app.js DOM helpers', () => {
  beforeEach(() => {
    // reset module to ensure clean maps between tests
    jest.resetModules();
    document.body.innerHTML = '';
    require('../multirig/static/app.js');
  });

  test('section collapse state uses localStorage for non-debug sections', () => {
    const { getSectionCollapsed, setSectionCollapsed, applySections } = globalThis.__multirig_test;

    document.body.innerHTML = `
      <div id="rig-0" class="rig-card" data-index="0">
        <div class="rig-section" data-section="info">
          <div class="rig-section-body">hello</div>
        </div>
      </div>
    `;

    const card = document.getElementById('rig-0');

    // default is not collapsed
    expect(getSectionCollapsed(0, 'info')).toBe(false);

    setSectionCollapsed(0, 'info', true);
    applySections(card, 0);

    expect(card.querySelector('.rig-section')?.classList.contains('collapsed')).toBe(true);
    expect(card.querySelector('.rig-section-body')?.style.display).toBe('none');

    // and it should persist
    expect(getSectionCollapsed(0, 'info')).toBe(true);
  });

  test('debug section collapse state is in-memory and defaults to collapsed', () => {
    const { getSectionCollapsed, setSectionCollapsed } = globalThis.__multirig_test;

    expect(getSectionCollapsed(0, 'debug')).toBe(true);

    setSectionCollapsed(0, 'debug', false);
    expect(getSectionCollapsed(0, 'debug')).toBe(false);
  });

  test('renderVfoControls hides when no vfo, otherwise renders buttons with active state', () => {
    const { renderVfoControls } = globalThis.__multirig_test;

    const el = document.createElement('div');
    renderVfoControls(el, 2, '', true);
    expect(el.style.display).toBe('none');
    expect(el.textContent).toBe('');

    renderVfoControls(el, 2, 'VFOA', true);
    expect(el.style.display).toBe('');
    const btns = Array.from(el.querySelectorAll('button'));
    expect(btns).toHaveLength(2);
    expect(btns[0].textContent).toBe('VFO A');
    expect(btns[0].classList.contains('active')).toBe(true);
    expect(btns[1].classList.contains('active')).toBe(false);

    // disabled behavior
    renderVfoControls(el, 2, 'VFOB', false);
    const btns2 = Array.from(el.querySelectorAll('button'));
    expect(btns2[0].disabled).toBe(true);
    expect(btns2[1].disabled).toBe(true);
    expect(btns2[1].classList.contains('active')).toBe(true);
  });

  test('renderVfoFreqs renders cached A/B frequencies', () => {
    const { renderVfoFreqs, __setVfoFreqCache } = globalThis.__multirig_test;

    const el = document.createElement('div');

    renderVfoFreqs(el, 0, '');
    expect(el.style.display).toBe('none');

    __setVfoFreqCache(0, { A: 7074000, B: 14074000 });
    renderVfoFreqs(el, 0, 'VFOA');
    expect(el.style.display).toBe('');
    expect(el.textContent).toContain('A 7.074000 MHz');
    expect(el.textContent).toContain('B 14.074000 MHz');
  });

  test('setRigUiError writes to DOM and cache; clearRigUiError clears cache', () => {
    const { setRigUiError, clearRigUiError, __getRigUiError } = globalThis.__multirig_test;

    document.body.innerHTML = `
      <div id="rig-1">
        <div data-role="error" style="display:none">
          <div class="rig-error-body"></div>
        </div>
      </div>
    `;

    setRigUiError(1, ' Bad ');
    expect(__getRigUiError(1)).toBe('Bad');

    const err = document.querySelector('[data-role="error"]');
    const body = document.querySelector('.rig-error-body');
    expect(err.style.display).toBe('');
    expect(err.classList.contains('conn-error')).toBe(true);
    expect(body.textContent).toBe('Bad');

    clearRigUiError(1);
    expect(__getRigUiError(1)).toBeUndefined();

    // setting empty should delete
    setRigUiError(1, '   ');
    expect(__getRigUiError(1)).toBeUndefined();
  });
});

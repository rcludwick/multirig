describe('multirig static/app.js formatters', () => {
  beforeAll(() => {
    require('../multirig/static/app.js');
  });

  test('formatFreq formats kHz for < 1MHz and MHz otherwise', () => {
    const { formatFreq } = globalThis.__multirig_test;

    expect(formatFreq(null)).toEqual({ text: '—', unit: '' });
    expect(formatFreq('nope')).toEqual({ text: '—', unit: '' });

    expect(formatFreq(999)).toEqual({ text: '0.999', unit: 'kHz' });
    expect(formatFreq(14000)).toEqual({ text: '14.000', unit: 'kHz' });

    expect(formatFreq(1000000)).toEqual({ text: '1.000000', unit: 'MHz' });
    expect(formatFreq(14074000)).toEqual({ text: '14.074000', unit: 'MHz' });
  });

  test('formatRw returns RW/R/W/empty based on get/set capability', () => {
    const { formatRw } = globalThis.__multirig_test;

    expect(formatRw(true, true)).toBe('RW');
    expect(formatRw(true, false)).toBe('R');
    expect(formatRw(false, true)).toBe('W');
    expect(formatRw(false, false)).toBe('');
  });

  test('bandLabelToMeters parses m and cm labels', () => {
    const { bandLabelToMeters } = globalThis.__multirig_test;

    expect(bandLabelToMeters('20m')).toBe(20);
    expect(bandLabelToMeters(' 70cm ')).toBeCloseTo(0.7);
    expect(bandLabelToMeters('1.25m')).toBeCloseTo(1.25);

    expect(bandLabelToMeters('')).toBeNull();
    expect(bandLabelToMeters('bogus')).toBeNull();
    expect(bandLabelToMeters('m')).toBeNull();
  });
});

describe('multirig static/app.js helpers', () => {
  beforeAll(() => {
    // Importing the script in Jest should populate globalThis.__multirig_test
    require('../multirig/static/app.js');
  });

  test('exports test hook', () => {
    expect(globalThis.__multirig_test).toBeTruthy();
    expect(typeof globalThis.__multirig_test.parseFrequencyInput).toBe('function');
  });

  describe('parseFrequencyInput', () => {
    test('parses explicit unit suffixes', () => {
      const { parseFrequencyInput } = globalThis.__multirig_test;
      expect(parseFrequencyInput('14.074 mhz', 'auto')).toBe(14074000);
      expect(parseFrequencyInput('7074khz', 'auto')).toBe(7074000);
      expect(parseFrequencyInput('145000000hz', 'auto')).toBe(145000000);
    });

    test('uses selected unit when no suffix', () => {
      const { parseFrequencyInput } = globalThis.__multirig_test;
      expect(parseFrequencyInput('14.074', 'mhz')).toBe(14074000);
      expect(parseFrequencyInput('7074', 'khz')).toBe(7074000);
      expect(parseFrequencyInput('14074000', 'hz')).toBe(14074000);
    });

    test('auto heuristic treats decimals and small ints as MHz', () => {
      const { parseFrequencyInput } = globalThis.__multirig_test;
      expect(parseFrequencyInput('7.074', 'auto')).toBe(7074000);
      expect(parseFrequencyInput('7', 'auto')).toBe(7000000);
    });
  });

  describe('enabledBandPresetMatch', () => {
    test('matches when hz within enabled preset range', () => {
      const { enabledBandPresetMatch } = globalThis.__multirig_test;
      const presets = [
        { label: '20m', enabled: true, lower_hz: 14000000, upper_hz: 14350000 },
        { label: '40m', enabled: false, lower_hz: 7000000, upper_hz: 7300000 },
      ];
      const match = enabledBandPresetMatch(presets, 14074000);
      expect(match).toBeTruthy();
      expect(match.label).toBe('20m');
    });

    test('does not match disabled preset', () => {
      const { enabledBandPresetMatch } = globalThis.__multirig_test;
      const presets = [
        { label: '40m', enabled: false, lower_hz: 7000000, upper_hz: 7300000 },
      ];
      expect(enabledBandPresetMatch(presets, 7074000)).toBeNull();
    });
  });

  describe('bandForHz', () => {
    test('matches known bands from built-in table', () => {
      const { bandForHz } = globalThis.__multirig_test;
      expect(bandForHz(7074000)?.label).toBe('40m');
      expect(bandForHz(14074000)?.label).toBe('20m');
      expect(bandForHz(18100000)?.label).toBe('17m');
    });
  });
});

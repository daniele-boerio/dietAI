import { describe, expect, it } from 'vitest';
import { bundleDi } from './versione';

describe('bundleDi', () => {
  it('trova lo script di Vite', () => {
    const html =
      '<head><script type="module" crossorigin src="/assets/index-AbC123.js"></script>' +
      '<link rel="stylesheet" crossorigin href="/assets/index-x.css"></head>';
    expect(bundleDi(html)).toBe('/assets/index-AbC123.js');
  });
  it('senza script dice null', () => {
    expect(bundleDi('<html></html>')).toBeNull();
    expect(bundleDi(undefined)).toBeNull();
  });
});

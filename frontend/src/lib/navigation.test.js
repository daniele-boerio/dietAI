import { describe, expect, it } from 'vitest';
import { hasInAppHistory } from './navigation';

// Su iPhone DietAI si apre a schermo intero dalla home: se "Indietro" esce dall'app
// non si finisce sul browser, si finisce sul nero. Questa è la condizione che decide
// se c'è davvero qualcosa dietro di noi.
describe('c\'è una pagina dietro?', () => {
  it('no sulla prima pagina della sessione', () => {
    // iOS riapre l'app sull'ultimo indirizzo: quella pagina è l'unica in cronologia.
    expect(hasInAppHistory('default', { idx: 0 })).toBe(false);
    expect(hasInAppHistory('default', undefined)).toBe(false);
    expect(hasInAppHistory('default', {})).toBe(false);
  });

  it('sì dopo aver navigato dentro l\'app', () => {
    expect(hasInAppHistory('a1b2c3', { idx: 1 })).toBe(true);
  });

  it('sì dopo un ricaricamento a metà strada: la cronologia del browser c\'è ancora', () => {
    // Un F5 rimette `key` a "default", ma le voci precedenti non sono sparite.
    expect(hasInAppHistory('default', { idx: 3 })).toBe(true);
  });
});

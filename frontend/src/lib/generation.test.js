import { describe, expect, it } from 'vitest';
import { contaSelezione, daGenerare, giorniPredefiniti, oggiIso } from './generation';

// Il numero scritto sul pulsante è quello che si sta per pagare: qui si controlla che
// conti le stesse caselle che conterebbe `generate_week` sul server.

const pasto = (slot, nome, extra = {}) => ({
  slot_id: slot,
  slot_name: nome,
  slot_order: slot,
  self_managed: false,
  is_skipped: false,
  is_recurring: false,
  source: 'ai_generated',
  recipe: null,
  ...extra,
});

// Una settimana che parte lunedì 5 gennaio 2026, tre pasti al giorno, tutta vuota.
const settimana = (modifica = () => {}) => {
  const week = {
    days: Array.from({ length: 7 }, (_, dow) => ({
      day_of_week: dow,
      date: `2026-01-${String(5 + dow).padStart(2, '0')}`,
      day_name: ['Lunedì', 'Martedì', 'Mercoledì', 'Giovedì', 'Venerdì', 'Sabato', 'Domenica'][dow],
      is_skipped: false,
      meals: [pasto(0, 'Colazione'), pasto(1, 'Pranzo'), pasto(2, 'Cena')],
    })),
  };
  modifica(week);
  return week;
};

const OGGI = { oggi: '2026-01-05' }; // il lunedì di quella settimana

describe('cosa c\'è da generare', () => {
  it('una settimana vuota è tutta da fare', () => {
    const { celle, giorni, pasti } = daGenerare(settimana(), OGGI);
    expect(celle).toHaveLength(21);
    expect(giorni.map((g) => g.da_fare)).toEqual([3, 3, 3, 3, 3, 3, 3]);
    expect(pasti.map((p) => p.da_fare)).toEqual([7, 7, 7]);
  });

  it('le caselle già piene non si contano, a meno di rifare tutto', () => {
    const week = settimana((w) => {
      w.days[0].meals[1].recipe = { title: 'Pasta al pomodoro' };
    });
    expect(daGenerare(week, OGGI).celle).toHaveLength(20);
    expect(daGenerare(week, { ...OGGI, rifaiTutto: true }).celle).toHaveLength(21);
  });

  it('quello che la generazione non tocca mai resta fuori in tutti e due i casi', () => {
    // Le stesse quattro condizioni del server, una per riga.
    const week = settimana((w) => {
      w.days[0].is_skipped = true; // giornata saltata
      w.days[1].meals[0].is_skipped = true; // pasto rimandato altrove
      w.days[2].meals[0].self_managed = true; // "lo faccio io"
      w.days[3].meals[1].is_recurring = true; // pasto fisso
      w.days[4].meals[1].source = 'user_custom'; // scritto a mano
    });
    const opzioni = { ...OGGI, rifaiTutto: true };
    expect(daGenerare(week, opzioni).celle).toHaveLength(21 - 3 - 4);
  });

  it('i pasti escono tutti, anche quelli senza niente da fare', () => {
    // Sparire farebbe sembrare che la colazione non sia più nella dieta: resta in
    // elenco, spenta, col suo perché.
    const week = settimana((w) => w.days.forEach((d) => (d.meals[0].self_managed = true)));
    const { pasti } = daGenerare(week, OGGI);
    expect(pasti.map((p) => p.nome)).toEqual(['Colazione', 'Pranzo', 'Cena']);
    expect(pasti[0]).toMatchObject({ mio: true, da_fare: 0 });
  });
});

describe('la selezione', () => {
  it('incrocia giorni e pasti', () => {
    const { celle } = daGenerare(settimana(), OGGI);
    expect(contaSelezione(celle, [0, 1], [1, 2])).toBe(4);
    expect(contaSelezione(celle, [0, 1, 2, 3, 4, 5, 6], [2])).toBe(7);
    expect(contaSelezione(celle, [], [1, 2])).toBe(0);
    expect(contaSelezione(celle, [0], [])).toBe(0);
  });
});

describe('i giorni spuntati all\'apertura', () => {
  it('partono da oggi in avanti: il passato è pagato per niente', () => {
    const { giorni } = daGenerare(settimana(), { oggi: '2026-01-08' }); // giovedì
    expect(giorniPredefiniti(giorni)).toEqual([3, 4, 5, 6]);
  });

  it('ma se il da fare è tutto alle spalle si accendono lo stesso', () => {
    // Una settimana archiviata che si sta ricostruendo: spegnere tutto vorrebbe dire
    // aprire la dialog col pulsante disattivato e nessuna spiegazione.
    const { giorni } = daGenerare(settimana(), { oggi: '2026-03-01' });
    expect(giorniPredefiniti(giorni)).toEqual([0, 1, 2, 3, 4, 5, 6]);
  });

  it('salta i giorni dove non c\'è niente da riempire', () => {
    const week = settimana((w) => {
      w.days[4].meals.forEach((m) => (m.recipe = { title: 'Già pronto' }));
    });
    expect(giorniPredefiniti(daGenerare(week, OGGI).giorni)).toEqual([0, 1, 2, 3, 5, 6]);
  });
});

describe('oggi', () => {
  it('si legge nel fuso locale, non in UTC', () => {
    // Alle 23:30 del 5 gennaio `toISOString()` direbbe già il 6: il lunedì
    // risulterebbe passato mentre lo si sta ancora vivendo.
    expect(oggiIso(new Date(2026, 0, 5, 23, 30))).toBe('2026-01-05');
  });
});

import { describe, expect, it } from 'vitest';
import { QUOTA_MINIMA, aggiungi, normalizza, riparti, tetto, togli } from './quote';

const somma = (q) => Object.values(q).reduce((a, b) => a + b, 0);

describe('normalizza', () => {
  it('porta sempre la somma a 100', () => {
    for (const quote of [
      { italiana: 70, greca: 30 },
      { italiana: 1, greca: 1, giapponese: 1 },
      { italiana: 5, greca: 3 },
      { italiana: 999 },
      { a: 1, b: 1, c: 1, d: 1, e: 1, f: 1, g: 1 },
    ]) {
      expect(somma(normalizza(quote))).toBe(100);
    }
  });

  it('tiene le proporzioni', () => {
    expect(normalizza({ italiana: 7, greca: 3 })).toEqual({ italiana: 70, greca: 30 });
  });

  it('divide in parti uguali quando non ci sono proporzioni da rispettare', () => {
    expect(normalizza({ a: 0, b: 0 })).toEqual({ a: 50, b: 50 });
  });

  it('non lascia mai una cucina a zero', () => {
    // Una voce spuntata che non può mai uscire è una voce che mente: chi non la
    // vuole più ha la X accanto.
    const quote = normalizza({ italiana: 1000, greca: 1 });
    expect(quote.greca).toBeGreaterThanOrEqual(QUOTA_MINIMA);
    expect(somma(quote)).toBe(100);
  });

  it('non tocca niente quando è già a posto', () => {
    expect(normalizza({ italiana: 70, greca: 30 })).toEqual({ italiana: 70, greca: 30 });
  });
});

describe('riparti', () => {
  it('scrive il valore chiesto e stringe le altre in proporzione', () => {
    const quote = riparti({ italiana: 40, greca: 40, giapponese: 20 }, 'italiana', 70);

    expect(quote.italiana).toBe(70);
    expect(somma(quote)).toBe(100);
    // Le altre due pesavano 2:1 e restano 2:1 su quello che avanza.
    expect(quote.greca).toBe(20);
    expect(quote.giapponese).toBe(10);
  });

  it('lascia intatto il numero che si sta leggendo mentre si trascina', () => {
    // È il punto: vedere il proprio 70 diventare 69 da solo, per un arrotondamento
    // sulle altre, è il modo più rapido di non fidarsi più del cursore.
    for (let v = QUOTA_MINIMA; v <= 97; v++) {
      const quote = riparti({ italiana: 33, greca: 33, giapponese: 34 }, 'italiana', v);
      expect(quote.italiana).toBe(v);
      expect(somma(quote)).toBe(100);
    }
  });

  it('non manda le altre sotto il minimo', () => {
    const quote = riparti({ italiana: 50, greca: 30, giapponese: 20 }, 'italiana', 100);

    expect(quote.italiana).toBe(tetto({ italiana: 0, greca: 0, giapponese: 0 }, 'italiana'));
    expect(quote.greca).toBe(QUOTA_MINIMA);
    expect(quote.giapponese).toBe(QUOTA_MINIMA);
    expect(somma(quote)).toBe(100);
  });

  it('con una cucina sola non c’è niente da ripartire', () => {
    expect(riparti({ italiana: 40 }, 'italiana', 40)).toEqual({ italiana: 100 });
  });
});

describe('aggiungi e togli', () => {
  it('la nuova prende una quota media e il totale non cambia', () => {
    const quote = aggiungi({ italiana: 50, greca: 50 }, 'giapponese');

    expect(Object.keys(quote)).toHaveLength(3);
    expect(somma(quote)).toBe(100);
    expect(quote.giapponese).toBeGreaterThan(0);
  });

  it('la prima cucina prende tutto', () => {
    expect(aggiungi({}, 'italiana')).toEqual({ italiana: 100 });
  });

  it('aggiungere due volte la stessa non fa niente', () => {
    const prima = { italiana: 70, greca: 30 };
    expect(aggiungi(prima, 'italiana')).toEqual(prima);
  });

  it('togliendo una cucina la sua quota torna alle altre', () => {
    const quote = togli({ italiana: 50, greca: 30, giapponese: 20 }, 'italiana');

    expect(Object.keys(quote)).toEqual(['greca', 'giapponese']);
    expect(somma(quote)).toBe(100);
    // Pesavano 3:2 fra loro e restano 3:2.
    expect(quote.greca).toBe(60);
    expect(quote.giapponese).toBe(40);
  });

  it('togliendo l’ultima non resta niente', () => {
    expect(togli({ italiana: 100 }, 'italiana')).toEqual({});
  });
});

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  CalendarCheck,
  CalendarClock,
  Check,
  ChevronDown,
  ChevronRight,
  Copy,
  FolderInput,
  MessageSquare,
  ShoppingCart,
} from 'lucide-react';

// La domenica di questa settimana, in ISO locale: oltre quel giorno la lista sta
// comprando anche per le settimane generate dopo.
function domenicaCorrente() {
  const oggi = new Date();
  const domenica = new Date(
    oggi.getFullYear(),
    oggi.getMonth(),
    oggi.getDate() + (7 - ((oggi.getDay() + 6) % 7) - 1)
  );
  return `${domenica.getFullYear()}-${String(domenica.getMonth() + 1).padStart(2, '0')}-${String(
    domenica.getDate()
  ).padStart(2, '0')}`;
}
import { Link } from 'react-router-dom';
import { api, formatDate } from '../api';
import { useApp } from '../App';
import ConfirmDialog from '../components/ConfirmDialog';
import EmptyState from '../components/EmptyState';
import LoadError from '../components/LoadError';
import Modal from '../components/Modal';
import ShoppingChat from '../components/ShoppingChat';
import { useDueColonne } from '../lib/schermo';

/**
 * Il campo per dire quanto se n'è preso davvero.
 *
 * Vive dentro la riga, al posto della quantità, e si conferma uscendo o con Invio:
 * al supermercato si scrive un numero e si passa oltre, non si cercano pulsanti.
 * Vuoto significa "ho preso quello che c'era scritto", che è il caso normale.
 */
// Chiuso il campo, il focus torna sul pulsante da cui si era aperto: il campo prende
// il suo posto nel DOM, e senza questo il focus da tastiera finiva sul `body`.
function useRitornaSu(id) {
  useEffect(
    () => () => {
      setTimeout(() => document.getElementById(id)?.focus(), 0);
    },
    [id]
  );
}

function QuantityInput({ item, onDone, onCancel }) {
  useRitornaSu(`qty-${item.id}`);
  const [value, setValue] = useState(item.bought_quantity ?? '');
  const annullato = useRef(false);

  const conferma = () => {
    if (annullato.current) return;
    const numero = value === '' ? null : Number(value);
    onDone(Number.isFinite(numero) && numero > 0 ? numero : null);
  };

  return (
    <span className="shopping-qty-edit">
      <input
        type="number"
        inputMode="decimal"
        autoFocus
        value={value}
        placeholder={String(item.quantity)}
        aria-label={`Quanto ${item.name} hai preso, in ${item.unit}. Invio salva, Esc annulla`}
        onFocus={(e) => e.target.select()}
        onChange={(e) => setValue(e.target.value)}
        onBlur={conferma}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault();
            e.target.blur();
          } else if (e.key === 'Escape') {
            e.preventDefault();
            annullato.current = true;
            onCancel();
          }
        }}
      />
      <em>{item.unit}</em>
    </span>
  );
}

export default function ShoppingPage() {
  const { addToast } = useApp();
  const [list, setList] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [collapsed, setCollapsed] = useState({});
  const [confirmDone, setConfirmDone] = useState(false);
  const [busy, setBusy] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  // Sopra i 1100px la chat è una colonna in pagina, sotto è un cassetto: sono due
  // componenti diversi con due comandi diversi, non lo stesso pannello spostato.
  const dueColonne = useDueColonne();
  // L'articolo che si sta spostando di reparto (null = nessun dialogo aperto).
  const [moving, setMoving] = useState(null);
  // L'articolo di cui si sta scrivendo la quantità presa.
  const [quantityOf, setQuantityOf] = useState(null);

  const load = useCallback(
    async ({ silent = false } = {}) => {
      if (!silent) setLoading(true);
      try {
        setList(await api.getShoppingList());
        setError(null);
      } catch (e) {
        setError(e.message);
        addToast(e.message, 'error');
      } finally {
        if (!silent) setLoading(false);
      }
    },
    [addToast]
  );

  useEffect(() => {
    load();
  }, [load]);

  const toggleItem = async (item) => {
    // Aggiornamento ottimistico: al supermercato si spunta in fretta e aspettare il
    // server a ogni tocco renderebbe la lista inutilizzabile.
    const next = !item.is_checked;
    spunte.current += 1;
    setList((prev) => ({
      ...prev,
      checked_items: prev.checked_items + (next ? 1 : -1),
      categories: prev.categories.map((c) => ({
        ...c,
        items: c.items.map((i) =>
          i.id === item.id
            ? {
                ...i,
                is_checked: next,
                // "Non l'ho preso" cancella anche quanto ne avevo segnato: il server fa
                // lo stesso, qui si tiene solo il passo.
                ...(next ? {} : { bought_quantity: null, bought_label: null }),
              }
            : i
        ),
      })),
    }));
    try {
      await api.checkShoppingItem(item.id, next);
    } catch (e) {
      addToast(e.message, 'error');
      // In silenzio: con lo spinner la lista si smontava (e si perdeva il punto), e una
      // seconda spunta ancora in volo veniva sovrascritta.
      load({ silent: true });
    }
  };

  // La lista che torna dalla quantità è quella di quando il server ha risposto:
  // se nel frattempo si è spuntato qualcos'altro, rimetterla a schermo toglieva la
  // spunta appena data. In quel caso si tiene lo stato locale (la spunta ha la sua
  // richiesta in volo).
  const spunte = useRef(0);
  const mostraSeAttuale = (lista, versione) => {
    if (versione === spunte.current) setList(lista);
  };

  // Le confezioni non si tagliano a misura: per 140 g di tacchino si porta a casa il
  // pacco da 400. Segnarlo qui, davanti allo scaffale, evita di correggere la dispensa
  // a casa — ed è la dispensa a decidere cosa comprerà la lista successiva.
  const saveQuantity = async (item, quantity) => {
    setQuantityOf(null);
    if (quantity === item.bought_quantity) return;
    const versione = spunte.current;
    try {
      mostraSeAttuale(await api.setBoughtQuantity(item.id, quantity), versione);
    } catch (e) {
      addToast(e.message, 'error');
      load({ silent: true });
    }
  };

  // Il reparto giusto lo sa chi gira per il negozio, non il catalogo: la scelta resta
  // sull'ingrediente e vale per tutte le liste da qui in avanti.
  const moveTo = async (category) => {
    const item = moving;
    setMoving(null);
    try {
      const res = await api.moveIngredient(item.ingredient_id, category);
      await load({ silent: true });
      addToast(`${res.name} ora è in ${res.label} ✓`);
    } catch (e) {
      addToast(e.message, 'error');
    }
  };

  const complete = async () => {
    setBusy(true);
    try {
      const res = await api.completeShopping();
      setConfirmDone(false);
      addToast(`${res.detail} ✓`);
      await load();
      if (res.week_locked_until) {
        addToast(`Bloccato fino al ${formatDate(res.week_locked_until)}`, 'info');
      }
    } catch (e) {
      addToast(e.message, 'error');
    } finally {
      setBusy(false);
    }
  };

  const copyList = async () => {
    try {
      const text = await api.exportShoppingList();
      await navigator.clipboard.writeText(text);
      addToast('Lista copiata negli appunti ✓');
    } catch {
      addToast('Non sono riuscito a copiare la lista', 'error');
    }
  };

  if (loading) return <div className="spinner" />;
  if (!list) return <LoadError message={error} onRetry={load} />;

  // La lista non è "di" una settimana: comprende le ricette da cucinare da oggi fino
  // a domenica otto, quindi il periodo lo dicono i giorni coperti.
  const periodo = list.covers_from
    ? `Dal ${formatDate(list.covers_from)} al ${formatDate(list.covers_to)}`
    : 'Niente da comprare';
  // La spesa arriva oltre la domenica di questa settimana: sono le settimane
  // successive che hai già generato, comprate nello stesso giro.
  const oltre = list.covers_to && list.covers_to > domenicaCorrente();

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-title">Lista della spesa</h1>
          <p className="page-subtitle">
            {periodo} · {list.checked_items} di {list.total_items} presi
          </p>
        </div>
        <div className="page-actions">
          {/* Sul monitor la chat è già in pagina, in colonna: un pulsante che
              "apre" una cosa che si vede sarebbe un comando senza effetto. */}
          {!dueColonne && (
            <button className="btn btn-secondary" onClick={() => setChatOpen(true)}>
              <MessageSquare size={16} /> Chiedi alla lista
            </button>
          )}
          <button className="btn btn-secondary" onClick={copyList}>
            <Copy size={16} /> Copia
          </button>
        </div>
      </div>

      <div className="page-split" style={{ '--aside': '380px' }}>
        <div className="page-main">
          {/* Quanto manca alla fine del giro, in un filo. Al supermercato è l'unica
              domanda che ci si fa mentre si scorre: quante ne restano. */}
          {list.total_items > 0 && (
            <div className="shopping-progress">
              <span
                style={{
                  width: `${Math.round((100 * list.checked_items) / list.total_items)}%`,
                }}
              />
            </div>
          )}

          {/* La lista arriva più in là di domenica perché hai già generato la settimana
              prossima: dirlo evita che una lista lunga sembri un errore di conto. */}
          {oltre && (
            <div className="notice notice-skip">
              <CalendarCheck />
              <div>
                <strong>Spesa fino al {formatDate(list.covers_to)}</strong>: la lista
                comprende anche le ricette della settimana prossima, così di una confezione
                se ne compra una sola invece di due mezze.
              </div>
            </div>
          )}

          {/* Il contrario del riquadro qui sopra, e serve per lo stesso motivo: una lista
              più corta del piano non deve sembrare una lista che ha perso dei pezzi. */}
          {list.meals_beyond > 0 && (
            <div className="notice">
              <CalendarClock />
              <div>
                <strong>Il piano va più avanti della spesa.</strong> Dopo il{' '}
                {formatDate(list.horizon)} hai{' '}
                {list.meals_beyond === 1
                  ? 'un pasto pianificato'
                  : `${list.meals_beyond} pasti pianificati`}
                : non sono in lista e non è una dimenticanza — si comprano quando arriva il
                loro turno, altrimenti il carrello di oggi sarebbe pieno di roba per fra tre
                settimane.
              </div>
            </div>
          )}

          {list.completed_at && (
            <div className="notice">
              <CalendarCheck />
              <div>
                <strong>Ultima spesa {formatDate(list.completed_at)}</strong>: quello che
                avevi spuntato è passato in dispensa, ed è per questo che non compare più
                qui. Quello che resta è quello che manca ancora.
              </div>
            </div>
          )}

          {list.categories.length === 0 ? (
            <EmptyState
              icon={ShoppingCart}
              title="Non manca niente"
              text="Tutto quello che il piano chiede da oggi in avanti è già in dispensa. Genera altre ricette e qui comparirà quello che serve comprare."
            />
          ) : (
            /* I reparti stanno in due colonne: la lista è lunga e stretta, e su un
               monitor una colonna sola vorrebbe dire scorrere per due schermate con
               mezzo metro di vuoto a destra. `columns` e non una griglia perché
               bilancia le altezze da sé — i reparti hanno da due a dodici voci l'uno —
               e `break-inside: avoid` tiene un reparto tutto nella stessa colonna. */
            <div className="shopping-list">
              {list.categories.map((cat) => {
                const isCollapsed = collapsed[cat.key];
                const done = cat.items.filter((i) => i.is_checked).length;
                return (
                  <div key={cat.key} className="shopping-category">
                    <button
                      className="shopping-category-head"
                      onClick={() =>
                        setCollapsed((prev) => ({ ...prev, [cat.key]: !prev[cat.key] }))
                      }
                    >
                      {isCollapsed ? <ChevronRight size={16} /> : <ChevronDown size={16} />}
                      {cat.label}
                      <span className="count">
                        {done}/{cat.items.length}
                      </span>
                    </button>

                    {!isCollapsed &&
                      cat.items.map((item) => (
                        <div
                          key={item.id}
                          className={`shopping-item ${item.is_checked ? 'checked' : ''}`}
                        >
                          {/* Una casella da spuntare, e il lettore di schermo deve
                              saperlo: lo stato «preso» era solo il riquadro lime e il
                              testo barrato, che non si sentono. */}
                          <button
                            className="shopping-tick"
                            role="checkbox"
                            aria-checked={!!item.is_checked}
                            onClick={() => toggleItem(item)}
                          >
                            <span className="shopping-check">
                              <Check size={13} strokeWidth={3} />
                            </span>
                            <span className="shopping-name">{item.name}</span>
                          </button>

                          {/* La quantità è un pulsante a sé: al supermercato si tocca per
                              dire quanto se n'è preso davvero, e non deve far spuntare o
                              despuntare la riga per sbaglio. */}
                          {quantityOf === item.id ? (
                            <QuantityInput
                              item={item}
                              onDone={(quantity) => saveQuantity(item, quantity)}
                              onCancel={() => setQuantityOf(null)}
                            />
                          ) : (
                            <button
                              id={`qty-${item.id}`}
                              className={`shopping-qty ${item.bought_quantity ? 'bought' : ''}`}
                              onClick={() => setQuantityOf(item.id)}
                              title="Quanto ne hai preso?"
                            >
                              {item.bought_label || item.label}
                              {item.bought_quantity && <small>ne servono {item.label}</small>}
                            </button>
                          )}

                          <button
                            className="icon-button shopping-move"
                            onClick={() => setMoving({ ...item, from: cat.label })}
                            title="Sposta di reparto"
                            aria-label={`Sposta ${item.name} in un altro reparto`}
                          >
                            <FolderInput size={15} />
                          </button>

                          {/* Perché l'articolo è in lista pur avendone in casa. Sta qui
                              in fondo e non dentro il pulsante che spunta la riga: quando
                              l'unità non torna è un link alla dispensa, e un link dentro
                              un bottone non si può toccare. Va a capo da solo. */}
                          {item.pantry &&
                            (item.pantry.usable ? (
                              <span className="shopping-pantry">
                                già in dispensa: {item.pantry.label} — ne serve altro
                              </span>
                            ) : (
                              <Link
                                className="shopping-pantry fix"
                                to={`/pantry?fix=${item.ingredient_id}`}
                              >
                                in dispensa hai {item.pantry.label}, qui si conta a{' '}
                                {item.unit}: non posso scalarli — correggi la dispensa
                              </Link>
                            ))}
                        </div>
                      ))}
                  </div>
                );
              })}

            </div>
          )}
        </div>

        <aside className="page-aside">
          {/* Il riepilogo è **su carta**: è il foglietto che si tiene in mano al
              supermercato, ed è l'unica cosa chiara della pagina — quella su cui
              l'occhio cade tornando dalla lista. Fino alla migrazione 0032 ci stava
              il totale stimato, tolto con tutti i prezzi: medie nazionali che al
              negozio vero non dicevano niente. */}
          <div className="card shopping-total-card">
            <div className="card-title">Spesa</div>
            <div className="shopping-total">{list.total_items - list.checked_items}</div>
            {/* Sul telefono il titolo sparisce e restano numero e nota: la nota deve
                bastare da sola. */}
            <div className="shopping-total-note">
              da prendere, su {list.total_items}{' '}
              {list.total_items === 1 ? 'articolo' : 'articoli'}
            </div>
            <button
              className="btn btn-primary btn-block"
              disabled={list.checked_items === 0}
              onClick={() => setConfirmDone(true)}
            >
              <Check size={16} /> Ho fatto la spesa
            </button>
            <p className="shopping-total-hint">
              Quello che hai spuntato passa in dispensa nella quantità che hai preso
              davvero, e da lì sparisce dalla lista: quello che resta è quello che non
              hai preso.
            </p>
          </div>

          {/* Sul monitor la chat vive qui, accanto alla lista: è lì che si sta
              quando si riscrive una ricetta perché le zucchine non si trovano. */}
          {dueColonne && (
            <ShoppingChat
              key={`inline-${list.week_plan_id}`}
              weekId={list.week_plan_id}
              inline
              onListUpdated={(updated) => updated && setList(updated)}
            />
          )}
        </aside>
      </div>

      {moving && (
        <Modal title={`Dove tieni «${moving.name}»?`} onClose={() => setMoving(null)}>
          <p className="modal-text">
            Ora è in {moving.from}. Il reparto serve a farti girare il supermercato una
            volta sola: quello che scegli vale anche per tutte le liste che verranno.
          </p>
          <div className="category-picker">
            {list.all_categories.map((cat) => (
              <button
                key={cat.key}
                className={`category-option ${cat.key === moving.category ? 'active' : ''}`}
                onClick={() => moveTo(cat.key)}
                disabled={cat.key === moving.category}
              >
                {cat.label}
              </button>
            ))}
          </div>
          <div className="modal-actions">
            <button className="btn btn-secondary" onClick={() => setMoving(null)}>
              Annulla
            </button>
          </div>
        </Modal>
      )}

      {confirmDone && (
        <ConfirmDialog
          title="Hai fatto la spesa?"
          text={
            `I ${list.checked_items} articoli spuntati passano in dispensa, e da lì ` +
            `spariscono dalla lista: quello che resta è quello che non hai preso. Il ` +
            `piano resta modificabile — se cambi una ricetta, la scorta la sistemi tu.`
          }
          confirmLabel="Sì, spesa fatta"
          busy={busy}
          onConfirm={complete}
          onCancel={() => setConfirmDone(false)}
        />
      )}

      {chatOpen && !dueColonne && (
        <>
          <div className="chat-backdrop" onClick={() => setChatOpen(false)} />
          <ShoppingChat
            key={list.week_plan_id}
            weekId={list.week_plan_id}
            onClose={() => setChatOpen(false)}
            onListUpdated={(updated) => updated && setList(updated)}
          />
        </>
      )}
    </>
  );
}

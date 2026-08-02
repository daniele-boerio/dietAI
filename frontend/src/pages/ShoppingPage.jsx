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
import { api, formatDate, formatMoney } from '../api';
import { useApp } from '../App';
import ConfirmDialog from '../components/ConfirmDialog';
import EmptyState from '../components/EmptyState';
import LoadError from '../components/LoadError';
import ShoppingChat from '../components/ShoppingChat';

/**
 * Il campo per dire quanto se n'è preso davvero.
 *
 * Vive dentro la riga, al posto della quantità, e si conferma uscendo o con Invio:
 * al supermercato si scrive un numero e si passa oltre, non si cercano pulsanti.
 * Vuoto significa "ho preso quello che c'era scritto", che è il caso normale.
 */
function QuantityInput({ item, onDone, onCancel }) {
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

/**
 * Il campo per dire quanto è costato.
 *
 * Si chiede la cifra che si ha sotto gli occhi — quanto è costato quel pacco — non un
 * prezzo al chilo da ricavare a mente: il conto al kg lo fa il server, che conosce la
 * quantità della riga. Vuoto cancella il prezzo tuo e rimette la media del catalogo.
 */
function PriceInput({ item, onDone, onCancel }) {
  const [value, setValue] = useState(item.price_by_user ? (item.estimated_price ?? '') : '');
  const annullato = useRef(false);

  const conferma = () => {
    if (annullato.current) return;
    const numero = value === '' ? null : Number(String(value).replace(',', '.'));
    onDone(Number.isFinite(numero) && numero > 0 ? numero : null);
  };

  return (
    <span className="shopping-price-edit">
      <em>€</em>
      <input
        type="number"
        step="0.01"
        inputMode="decimal"
        autoFocus
        value={value}
        placeholder={item.estimated_price != null ? String(item.estimated_price) : '0,00'}
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
  // L'articolo che si sta spostando di reparto (null = nessun dialogo aperto).
  const [moving, setMoving] = useState(null);
  // L'articolo di cui si sta scrivendo la quantità presa, e quello del prezzo pagato.
  const [quantityOf, setQuantityOf] = useState(null);
  const [priceOf, setPriceOf] = useState(null);

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
                // "Non l'ho preso" cancella anche quanto ne avevo segnato: il server
                // fa lo stesso, qui si tiene solo il passo.
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
      load();
    }
  };

  // Le confezioni non si tagliano a misura: per 140 g di tacchino si porta a casa il
  // pacco da 400. Segnarlo qui, davanti allo scaffale, evita di correggere la dispensa
  // a casa — ed è la dispensa a decidere cosa comprerà la lista successiva.
  const saveQuantity = async (item, quantity) => {
    setQuantityOf(null);
    if (quantity === item.bought_quantity) return;
    try {
      setList(await api.setBoughtQuantity(item.id, quantity));
    } catch (e) {
      addToast(e.message, 'error');
      load({ silent: true });
    }
  };

  // Il prezzo del catalogo è una media italiana e nel negozio dove fai la spesa vale
  // poco: è per questo che il totale stimato non dice quasi niente. Ogni cifra segnata
  // qui insegna all'app un prezzo vero, e resta per tutte le liste che verranno.
  const savePrice = async (item, paid) => {
    setPriceOf(null);
    try {
      const aggiornata = await api.setPaidPrice(item.id, paid);
      setList(aggiornata);
      if (paid) addToast(`${item.name}: prezzo segnato ✓`);
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
          <button className="btn btn-secondary" onClick={() => setChatOpen(true)}>
            <MessageSquare size={16} /> Assistente
          </button>
          <button className="btn btn-secondary" onClick={copyList}>
            <Copy size={16} /> Copia
          </button>
        </div>
      </div>

      {/* La lista arriva più in là di domenica perché hai già generato la settimana
          prossima: dirlo evita che il totale alto sembri un errore di conto. */}
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
        <>
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
                  {cat.estimated_price != null && (
                    <span className="price">{formatMoney(cat.estimated_price)}</span>
                  )}
                </button>

                {!isCollapsed &&
                  cat.items.map((item) => (
                    <div
                      key={item.id}
                      className={`shopping-item ${item.is_checked ? 'checked' : ''}`}
                    >
                      <button
                        className="shopping-tick"
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
                          className={`shopping-qty ${item.bought_quantity ? 'bought' : ''}`}
                          onClick={() => setQuantityOf(item.id)}
                          title="Quanto ne hai preso?"
                        >
                          {item.bought_label || item.label}
                          {item.bought_quantity && <small>ne servono {item.label}</small>}
                        </button>
                      )}

                      {/* Il prezzo si tocca per dire quanto è costato davvero: da lì
                          l'app impara il prezzo unitario e smette di stimare a caso.
                          Si può fare anche a spesa fatta, scontrino alla mano. */}
                      {priceOf === item.id ? (
                        <PriceInput
                          item={item}
                          onDone={(paid) => savePrice(item, paid)}
                          onCancel={() => setPriceOf(null)}
                        />
                      ) : (
                        <button
                          className={`shopping-price ${item.price_by_user ? 'mine' : ''}`}
                          onClick={() => setPriceOf(item.id)}
                          title={
                            item.price_by_user
                              ? `Prezzo tuo: ${formatMoney(item.unit_price)}/${item.price_unit}${
                                  item.last_paid_at
                                    ? ` · segnato il ${formatDate(item.last_paid_at)}`
                                    : ''
                                }`
                              : 'Quanto è costato? Segnalo e la stima diventa la tua'
                          }
                        >
                          {item.estimated_price != null ? formatMoney(item.estimated_price) : '€ —'}
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
                    </div>
                  ))}
              </div>
            );
          })}

          <div className="shopping-footer">
            <div className="shopping-total">
              {formatMoney(list.estimated_cost) || '—'}
              {/* Un totale fatto di medie nazionali non serve a niente, e dirlo è
                  meglio che farlo sembrare un preventivo: la frase cambia man mano
                  che i prezzi veri prendono il posto di quelli del catalogo. */}
              <small>
                {list.priced_items === 0
                  ? `stima sui prezzi medi · ${list.total_items} articoli`
                  : list.priced_items === list.total_items
                    ? `sui tuoi prezzi · ${list.total_items} articoli`
                    : `${list.priced_items} di ${list.total_items} articoli a prezzo tuo`}
              </small>
            </div>
            <button
              className="btn btn-primary"
              style={{ marginLeft: 'auto' }}
              onClick={() => setConfirmDone(true)}
            >
              <Check size={16} /> Ho fatto la spesa
            </button>
          </div>
        </>
      )}

      {moving && (
        <div className="modal-overlay" onClick={() => setMoving(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h2 className="modal-title">Dove tieni «{moving.name}»?</h2>
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
          </div>
        </div>
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

      {chatOpen && (
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

import { useCallback, useEffect, useState } from 'react';
import {
  CalendarCheck,
  CalendarOff,
  Check,
  ChevronDown,
  ChevronRight,
  Copy,
  FolderInput,
  Lock,
  MessageSquare,
  ShoppingCart,
} from 'lucide-react';
import { api, formatDate, formatMoney } from '../api';
import { useApp } from '../App';
import ConfirmDialog from '../components/ConfirmDialog';
import EmptyState from '../components/EmptyState';
import ShoppingChat from '../components/ShoppingChat';

export default function ShoppingPage() {
  const { addToast } = useApp();
  const [list, setList] = useState(null);
  const [loading, setLoading] = useState(true);
  const [collapsed, setCollapsed] = useState({});
  const [confirmDone, setConfirmDone] = useState(false);
  const [busy, setBusy] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  // L'articolo che si sta spostando di reparto (null = nessun dialogo aperto).
  const [moving, setMoving] = useState(null);

  const load = useCallback(
    async ({ silent = false } = {}) => {
      if (!silent) setLoading(true);
      try {
        setList(await api.getShoppingList());
      } catch (e) {
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
        items: c.items.map((i) => (i.id === item.id ? { ...i, is_checked: next } : i)),
      })),
    }));
    try {
      await api.checkShoppingItem(item.id, next);
    } catch (e) {
      addToast(e.message, 'error');
      load();
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
  if (!list) return null;

  // La spesa segue il piano, non il calendario: copre tutte le settimane generate di
  // cui non si è ancora fatta la spesa, quindi il periodo va detto.
  const settimane = list.weeks_covered?.length || 0;
  const periodo =
    settimane > 1
      ? `Dal ${formatDate(list.week_start_date)} al ${formatDate(list.covers_to)}`
      : `Settimana del ${formatDate(list.week_start_date)}`;

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

      {list.is_completed && (
        <div className="notice notice-lock">
          <Lock />
          <div>
            <strong>Spesa già fatta</strong>
            {list.completed_at ? ` il ${formatDate(list.completed_at)}` : ''}. Gli articoli
            spuntati sono finiti in dispensa e il piano che copriva è bloccato. La
            prossima lista comparirà qui appena generi una settimana ancora da comprare.
          </div>
        </div>
      )}

      {/* La lista è saltata avanti perché questa settimana è già in frigo. */}
      {!list.is_completed && list.starts_ahead && (
        <div className="notice notice-skip">
          <CalendarCheck />
          <div>
            <strong>Questa settimana è già comprata</strong>: la spesa riparte dal{' '}
            {formatDate(list.week_start_date)}, con le ricette che hai generato dopo.
          </div>
        </div>
      )}

      {/* La spesa copre più di una settimana perché sono già state generate: dirlo
          evita che il totale alto sembri un errore di conto. */}
      {!list.is_completed && settimane > 1 && (
        <div className="notice notice-skip">
          <CalendarCheck />
          <div>
            <strong>Spesa per {settimane} settimane</strong>, fino al{' '}
            {formatDate(list.covers_to)}: la lista comprende tutte le ricette che hai
            generato e non ancora comprato. A spesa fatta si bloccano tutte.
          </div>
        </div>
      )}

      {/* La lista non parte da lunedì perché dei giorni sono passati senza spesa. */}
      {!list.is_completed && list.days_skipped > 0 && (
        <div className="notice notice-skip">
          <CalendarOff />
          <div>
            <strong>
              {list.days_skipped === 1
                ? 'Un giorno è già passato'
                : `${list.days_skipped} giorni sono già passati`}{' '}
              senza spesa.
            </strong>{' '}
            Si comincia a cucinare da {formatDate(list.covers_from)}: i giorni saltati non
            si comprano, ma le loro ricette sono slittate in avanti e restano in lista.
          </div>
        </div>
      )}

      {list.categories.length === 0 ? (
        <EmptyState
          icon={ShoppingCart}
          title="Lista vuota"
          text={
            list.is_locked
              ? 'Il cibo di questo piano è già stato comprato: non c’è niente da mettere nel carrello.'
              : 'La lista si compila da sola dalle ricette che generi — anche più settimane insieme, se le hai già generate.'
          }
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
                        disabled={list.is_completed}
                      >
                        <span className="shopping-check">
                          <Check size={13} strokeWidth={3} />
                        </span>
                        <span className="shopping-name">{item.name}</span>
                        <span className="shopping-qty">{item.label}</span>
                        <span className="shopping-price">
                          {item.estimated_price != null
                            ? formatMoney(item.estimated_price)
                            : ''}
                        </span>
                      </button>
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
              <small>totale stimato · {list.total_items} articoli</small>
            </div>
            {!list.is_completed && (
              <button
                className="btn btn-primary"
                style={{ marginLeft: 'auto' }}
                onClick={() => setConfirmDone(true)}
              >
                <Check size={16} /> Ho fatto la spesa
              </button>
            )}
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
            `Gli articoli spuntati finiranno in dispensa e ${
              settimane > 1
                ? `il piano di tutte e ${settimane} le settimane coperte verrà bloccato`
                : 'il piano di questa settimana verrà bloccato per 7 giorni'
            }: le ricette non si potranno più cambiare. È il modo per non buttare il cibo appena comprato.`
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
            locked={list.is_locked}
            onClose={() => setChatOpen(false)}
            onListUpdated={(updated) => updated && setList(updated)}
          />
        </>
      )}
    </>
  );
}

import { useCallback, useEffect, useState } from 'react';
import {
  CalendarOff,
  Check,
  ChevronDown,
  ChevronRight,
  Copy,
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
  const [which, setWhich] = useState('current');
  const [list, setList] = useState(null);
  const [loading, setLoading] = useState(true);
  const [collapsed, setCollapsed] = useState({});
  const [confirmDone, setConfirmDone] = useState(false);
  const [busy, setBusy] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setList(await api.getShoppingList(which));
    } catch (e) {
      addToast(e.message, 'error');
    } finally {
      setLoading(false);
    }
  }, [which, addToast]);

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

  const complete = async () => {
    setBusy(true);
    try {
      const res = await api.completeShopping(which);
      setConfirmDone(false);
      addToast('Spesa completata: piano bloccato per 7 giorni ✓');
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
      const text = await api.exportShoppingList(which);
      await navigator.clipboard.writeText(text);
      addToast('Lista copiata negli appunti ✓');
    } catch {
      addToast('Non sono riuscito a copiare la lista', 'error');
    }
  };

  if (loading) return <div className="spinner" />;
  if (!list) return null;

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-title">Lista della spesa</h1>
          <p className="page-subtitle">
            Settimana del {formatDate(list.week_start_date)} · {list.checked_items} di{' '}
            {list.total_items} presi
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

      <div className="week-toolbar">
        <div className="week-tabs">
          <button
            className={`week-tab ${which === 'current' ? 'active' : ''}`}
            onClick={() => setWhich('current')}
          >
            Questa settimana
          </button>
          <button
            className={`week-tab ${which === 'next' ? 'active' : ''}`}
            onClick={() => setWhich('next')}
          >
            Prossima
          </button>
        </div>
      </div>

      {list.is_completed && (
        <div className="notice notice-lock">
          <Lock />
          <div>
            <strong>Spesa già fatta</strong>
            {list.completed_at ? ` il ${formatDate(list.completed_at)}` : ''}. Gli articoli
            spuntati sono finiti in dispensa e il piano della settimana è bloccato.
          </div>
        </div>
      )}

      {/* La lista è più corta di una settimana perché dei giorni sono passati senza
          spesa: dirlo evita che il totale basso sembri un errore di conto. */}
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
            La lista copre i {7 - list.days_skipped} giorni che restano, da{' '}
            {formatDate(list.covers_from)}: gli ingredienti dei giorni saltati non servono
            più, e le loro ricette sono slittate in avanti.
          </div>
        </div>
      )}

      {list.categories.length === 0 ? (
        <EmptyState
          icon={ShoppingCart}
          title="Lista vuota"
          text="La lista si compila da sola dalle ricette della settimana: genera il piano e torna qui."
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
                    <button
                      key={item.id}
                      className={`shopping-item ${item.is_checked ? 'checked' : ''}`}
                      onClick={() => toggleItem(item)}
                      disabled={list.is_completed}
                    >
                      <span className="shopping-check">
                        <Check size={13} strokeWidth={3} />
                      </span>
                      <span className="shopping-name">{item.name}</span>
                      <span className="shopping-qty">{item.label}</span>
                      <span className="shopping-price">
                        {item.estimated_price != null ? formatMoney(item.estimated_price) : ''}
                      </span>
                    </button>
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

      {confirmDone && (
        <ConfirmDialog
          title="Hai fatto la spesa?"
          text="Gli articoli spuntati finiranno in dispensa e il piano di questa settimana verrà bloccato per 7 giorni: le ricette non si potranno più cambiare. È il modo per non buttare il cibo appena comprato."
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

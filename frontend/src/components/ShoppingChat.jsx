import { useEffect, useRef, useState } from 'react';
import { Send, ShoppingCart, Trash2, X } from 'lucide-react';
import { api } from '../api';
import { useApp } from '../App';
import ChatText from './ChatText';

const SUGGESTIONS = [
  'Non trovo le zucchine, con cosa le sostituisco?',
  'Togli il pesce da tutte le ricette',
  'Sostituisci il petto di pollo con il tacchino',
];

/**
 * Quanto spazio si è mangiato la tastiera del telefono, in pixel.
 *
 * Serve al foglio della chat, che è `position: fixed` in fondo allo schermo: iOS,
 * quando apre la tastiera, non sposta gli elementi fissi: li lascia dov'erano, cioè
 * dietro ai tasti. Si finisce a scrivere alla cieca in un campo che non si vede.
 * La `visualViewport` è l'unica a sapere quanta parte di schermo resta visibile.
 */
function useKeyboardInset() {
  const [inset, setInset] = useState(0);

  useEffect(() => {
    const vv = window.visualViewport;
    if (!vv) return undefined;

    const aggiorna = () =>
      setInset(Math.max(0, Math.round(window.innerHeight - vv.height - vv.offsetTop)));
    aggiorna();
    vv.addEventListener('resize', aggiorna);
    vv.addEventListener('scroll', aggiorna);
    return () => {
      vv.removeEventListener('resize', aggiorna);
      vv.removeEventListener('scroll', aggiorna);
    };
  }, []);

  return inset;
}

// Chat "da supermercato": lavora sulla settimana intera, non su un pasto. Quando il
// backend cambia delle ricette (`list_updated`) avvisa il genitore, che ricarica la
// lista della spesa perché rifletta i nuovi ingredienti.
export default function ShoppingChat({ weekId, onClose, onListUpdated }) {
  const { addToast } = useApp();
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState('');
  const [sending, setSending] = useState(false);
  const bodyRef = useRef(null);
  const keyboard = useKeyboardInset();

  useEffect(() => {
    if (weekId) api.getShoppingChat(weekId).then(setMessages).catch(() => {});
  }, [weekId]);

  useEffect(() => {
    bodyRef.current?.scrollTo({ top: bodyRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, sending]);

  const send = async (text) => {
    const content = (text ?? draft).trim();
    if (!content || sending) return;

    setDraft('');
    setSending(true);
    setMessages((prev) => [...prev, { id: `tmp-${Date.now()}`, role: 'user', content }]);

    try {
      const reply = await api.sendShoppingChat(weekId, content);
      setMessages((prev) => [
        ...prev,
        { id: `tmp-a-${Date.now()}`, role: 'assistant', content: reply.content },
      ]);
      if (reply.list_updated) {
        const n = reply.changed_meals?.length || 0;
        addToast(`${n} ricett${n === 1 ? 'a' : 'e'} aggiornat${n === 1 ? 'a' : 'e'} · lista rifatta ✓`);
        onListUpdated?.(reply.shopping_list);
      }
    } catch (e) {
      addToast(e.message, 'error');
      setMessages((prev) => prev.filter((m) => m.content !== content || m.role !== 'user'));
    } finally {
      setSending(false);
    }
  };

  const clear = async () => {
    try {
      await api.clearShoppingChat(weekId);
      setMessages([]);
    } catch (e) {
      addToast(e.message, 'error');
    }
  };

  return (
    <div
      className="shopping-chat"
      // Col foglio alzato sopra la tastiera va accorciato anche, o la sua testata
      // (dove sta la X per chiudere) esce dallo schermo dalla parte opposta.
      style={
        keyboard
          ? { bottom: keyboard, maxHeight: `calc(100dvh - ${keyboard}px - 12px)` }
          : undefined
      }
    >
      <div className="chat-head">
        <ShoppingCart />
        Assistente spesa
        {messages.length > 0 && (
          <button
            className="icon-button"
            style={{ marginLeft: 'auto' }}
            onClick={clear}
            title="Svuota la conversazione"
          >
            <Trash2 size={15} />
          </button>
        )}
        <button
          className="icon-button"
          style={{ marginLeft: messages.length > 0 ? 4 : 'auto' }}
          onClick={onClose}
          title="Chiudi"
        >
          <X size={16} />
        </button>
      </div>

      <div className="chat-body" ref={bodyRef}>
        {messages.length === 0 && !sending && (
          <div className="chat-hint">
            Non trovi un ingrediente o vuoi cambiarlo? Dimmelo: lo cambio in tutte le
            ricette che lo usano e rifaccio la lista.
            <div className="chat-suggestions">
              {SUGGESTIONS.map((s) => (
                <button key={s} className="chat-suggestion" onClick={() => send(s)}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m) => (
          <div key={m.id} className={`chat-bubble ${m.role}`}>
            <ChatText text={m.content} />
          </div>
        ))}

        {sending && (
          <div className="chat-bubble assistant">
            <span className="typing">
              DietAI sta rispondendo <i /> <i /> <i />
            </span>
          </div>
        )}
      </div>

      <div className="chat-input">
        <textarea
          rows={1}
          value={draft}
          placeholder="Scrivi un messaggio..."
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              send();
            }
          }}
        />
        <button className="chat-send" onClick={() => send()} disabled={sending || !draft.trim()}>
          <Send size={16} />
        </button>
      </div>
    </div>
  );
}

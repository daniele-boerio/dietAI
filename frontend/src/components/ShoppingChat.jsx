import { useEffect, useRef, useState } from 'react';
import { Send, ShoppingCart, Trash2, X } from 'lucide-react';
import { api } from '../api';
import { useApp } from '../App';

const SUGGESTIONS = [
  'Non trovo le zucchine, con cosa le sostituisco?',
  'Togli il pesce da tutte le ricette',
  'Sostituisci il petto di pollo con il tacchino',
];

// Chat "da supermercato": lavora sulla settimana intera, non su un pasto. Quando il
// backend cambia delle ricette (`list_updated`) avvisa il genitore, che ricarica la
// lista della spesa perché rifletta i nuovi ingredienti.
export default function ShoppingChat({ weekId, locked, onClose, onListUpdated }) {
  const { addToast } = useApp();
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState('');
  const [sending, setSending] = useState(false);
  const bodyRef = useRef(null);

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
    <div className="shopping-chat">
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
            {locked
              ? 'La spesa è già fatta: posso darti consigli, ma non cambiare le ricette (il cibo è comprato).'
              : "Non trovi un ingrediente o vuoi cambiarlo? Dimmelo: lo cambio in tutte le ricette che lo usano e rifaccio la lista."}
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
            {m.content}
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

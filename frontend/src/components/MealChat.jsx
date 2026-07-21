import { useEffect, useRef, useState } from 'react';
import { MessageSquare, Send, Trash2 } from 'lucide-react';
import { api } from '../api';
import { useApp } from '../App';

const SUGGESTIONS = [
  'Come lo preparo in meno tempo?',
  'Sostituisci un ingrediente',
  'Rendilo più proteico',
  'Posso prepararlo la sera prima?',
];

// Chat contestuale sul pasto. Quando la risposta contiene una ricetta aggiornata il
// backend lo segnala con `recipe_updated`: qui si avvisa il genitore, che ricarica.
export default function MealChat({ mealId, locked, onRecipeUpdated }) {
  const { addToast } = useApp();
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState('');
  const [sending, setSending] = useState(false);
  const bodyRef = useRef(null);

  useEffect(() => {
    api.getChat(mealId).then(setMessages).catch(() => {});
  }, [mealId]);

  useEffect(() => {
    bodyRef.current?.scrollTo({ top: bodyRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, sending]);

  const send = async (text) => {
    const content = (text ?? draft).trim();
    if (!content || sending) return;

    setDraft('');
    setSending(true);
    // Messaggio ottimistico: la risposta di Claude può metterci qualche secondo e
    // vedere il proprio testo sparire nel nulla è la cosa più fastidiosa di tutte.
    setMessages((prev) => [...prev, { id: `tmp-${Date.now()}`, role: 'user', content }]);

    try {
      const reply = await api.sendChat(mealId, content);
      setMessages((prev) => [
        ...prev,
        { id: `tmp-a-${Date.now()}`, role: 'assistant', content: reply.content },
      ]);
      if (reply.recipe_updated) {
        addToast('Ricetta aggiornata ✓');
        onRecipeUpdated?.(reply.recipe);
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
      await api.clearChat(mealId);
      setMessages([]);
    } catch (e) {
      addToast(e.message, 'error');
    }
  };

  return (
    <div className="chat-panel">
      <div className="chat-head">
        <MessageSquare />
        Chiedi a DietAI
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
      </div>

      <div className="chat-body" ref={bodyRef}>
        {messages.length === 0 && !sending && (
          <div className="chat-hint">
            {locked
              ? 'Il piano è bloccato: posso darti consigli su come cucinare questo piatto, ma non modificarlo.'
              : 'Chiedimi di modificare la ricetta, sostituire un ingrediente o spiegarti un passaggio.'}
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
            // Invio manda, Shift+Invio va a capo: come in qualunque chat.
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

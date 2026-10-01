import { useEffect, useState } from 'react';
import { Bell, BellOff, Send } from 'lucide-react';
import { api } from '../api';
import { useApp } from '../App';
import { iscrivi, iscrizioneCorrente, supportoPush } from '../lib/push';

// Il promemoria serale: «com'è andata oggi?» all'ora scelta, solo se oggi c'è ancora
// qualcosa da segnare. Due interruttori in uno: il dispositivo deve essere iscritto
// (permesso del browser) e l'ora deve essere impostata (sul server). Si accendono
// insieme e si spengono insieme, perché uno senza l'altro non fa niente.
export default function ReminderSettings() {
  const { addToast } = useApp();
  const [stato, setStato] = useState(null);
  const [qui, setQui] = useState(false); // questo dispositivo è iscritto?
  const [ora, setOra] = useState('21:00');
  const [busy, setBusy] = useState(false);
  const supporto = supportoPush();

  useEffect(() => {
    api
      .getPush()
      .then((s) => {
        setStato(s);
        if (s.reminder_time) setOra(s.reminder_time);
      })
      .catch(() => {});
    iscrizioneCorrente().then((sub) => setQui(Boolean(sub)));
  }, []);

  const attivo = Boolean(stato?.reminder_time) && qui;

  const accendi = async () => {
    setBusy(true);
    try {
      const sub = await iscrivi(stato.public_key);
      await api.subscribePush(sub);
      setStato(await api.setReminder(ora));
      setQui(true);
      addToast(`Promemoria alle ${ora} ✓`);
    } catch (e) {
      addToast(e.message, 'error');
    } finally {
      setBusy(false);
    }
  };

  const spegni = async () => {
    setBusy(true);
    try {
      setStato(await api.setReminder(null));
      addToast('Promemoria spento');
    } catch (e) {
      addToast(e.message, 'error');
    } finally {
      setBusy(false);
    }
  };

  const cambiaOra = async (valore) => {
    setOra(valore);
    if (!attivo || !valore) return;
    try {
      setStato(await api.setReminder(valore));
    } catch (e) {
      addToast(e.message, 'error');
    }
  };

  const prova = async () => {
    try {
      await api.testPush();
      addToast('Notifica di prova inviata: dovrebbe arrivare tra pochi secondi');
    } catch (e) {
      addToast(e.message, 'error');
    }
  };

  return (
    <div className="field">
      <label className="field-label">Promemoria serale</label>
      <p className="field-hint" style={{ marginBottom: 12 }}>
        All'ora che scegli ti chiedo com'è andata — solo se oggi c'è ancora qualche pasto
        da segnare. Un giorno mai segnato, per l'app, è un giorno andato storto.
      </p>

      {supporto === 'ios-da-installare' && (
        <p className="field-hint">
          Su iPhone le notifiche arrivano solo all'app installata: in Safari tocca
          Condividi → «Aggiungi alla schermata Home», apri DietAI da lì e torna qui.
        </p>
      )}
      {supporto === 'negato' && (
        <p className="field-hint">
          Le notifiche per DietAI sono bloccate nelle impostazioni del browser: vanno
          riattivate da lì.
        </p>
      )}
      {supporto === 'no' && (
        <p className="field-hint">Questo browser non riceve notifiche push.</p>
      )}

      {supporto === 'si' && stato && (
        <div className="reminder-row">
          <input
            type="time"
            value={ora}
            aria-label="Ora del promemoria"
            onChange={(e) => cambiaOra(e.target.value)}
          />
          {attivo ? (
            <>
              <button className="btn btn-secondary btn-sm" onClick={spegni} disabled={busy}>
                <BellOff size={14} /> Spegni
              </button>
              <button className="btn btn-ghost btn-sm" onClick={prova} disabled={busy}>
                <Send size={14} /> Prova
              </button>
            </>
          ) : (
            <button className="btn btn-primary btn-sm" onClick={accendi} disabled={busy || !ora}>
              {busy ? <span className="spinner-inline" /> : <Bell size={14} />}
              Attiva su questo dispositivo
            </button>
          )}
        </div>
      )}
    </div>
  );
}

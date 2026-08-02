import { useEffect, useState } from 'react';
import {
  Calculator,
  FileUp,
  Lock,
  MessageSquare,
  Save,
  Sparkles,
  Unlock,
  User,
  X,
} from 'lucide-react';
import { api } from '../api';
import { useApp } from '../App';
import Questionnaire from '../components/Questionnaire';
import { addMeal, dailyTotals, rebalanceField, removeMeal } from '../lib/macros';

const CAMPI = [
  { key: 'calories', label: 'kcal' },
  { key: 'protein_g', label: 'Prot.' },
  { key: 'carbs_g', label: 'Carb.' },
  { key: 'fat_g', label: 'Grassi' },
];

// La dieta è una pagina sua e non una scheda delle impostazioni: non è una preferenza,
// è l'ingresso da cui passa tutto il resto — le ricette nascono da questi numeri, la
// spesa dalle ricette, l'aderenza dal confronto con questi target. Averla in fondo a
// un menu di configurazione la faceva sembrare un dettaglio da sistemare una volta.
export default function DietPage() {
  const { addToast } = useApp();
  const [diet, setDiet] = useState(null);
  const [meals, setMeals] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [file, setFile] = useState(null);

  // Il lucchetto: chiuso, il totale del giorno non si muove — si sposta soltanto fra i
  // pasti. Nasce chiuso a ogni apertura della pagina perché è la cosa che si vuole nel
  // 90% dei casi (aggiungo uno spuntino, cambio gli orari) e perché cambiare la dieta
  // per sbaglio non si nota subito: si nota fra due settimane, dal peso.
  const [locked, setLocked] = useState(true);
  const [target, setTarget] = useState(null);

  // Quello che si sta battendo adesso, prima che il lucchetto lo rimetta a posto.
  // Ridistribuire a ogni tasto sarebbe illeggibile — scrivendo "600" gli altri pasti
  // ballerebbero su "6" e su "60" — quindi il riallineamento aspetta di uscire dal
  // campo. Finché si scrive, il totale in fondo mostra lo scarto: è il modo più corto
  // per dire perché gli altri pasti stanno per muoversi.
  const [draft, setDraft] = useState(null);

  const load = () =>
    api
      .getDiet()
      .then((d) => {
        setDiet(d);
        setMeals(d.meals);
        setTarget(dailyTotals(d.meals));
      })
      .catch(() => setDiet(null))
      .finally(() => setLoading(false));

  useEffect(() => {
    load();
  }, []);

  const withDraft = draft
    ? meals.map((m, i) =>
        i === draft.index ? { ...m, [draft.field]: Number(draft.value) || 0 } : m
      )
    : meals;

  // Chiude la modifica in corso e restituisce i pasti aggiornati, perché chi salva
  // possa mandarli senza aspettare il giro di render: premendo "Salva" da dentro un
  // campo il blur e il clic arrivano nello stesso batch, e `meals` sarebbe ancora
  // quello di prima.
  const commit = () => {
    if (!draft) return meals;
    const next =
      locked && target
        ? rebalanceField(withDraft, draft.index, draft.field, target[draft.field])
        : withDraft;
    setMeals(next);
    setDraft(null);
    return next;
  };

  const rename = (index, value) =>
    setMeals((prev) => prev.map((m, i) => (i === index ? { ...m, name: value } : m)));

  const save = async () => {
    const finali = commit();
    setBusy(true);
    try {
      const payload = finali.map((m, i) => ({
        name: m.name,
        order: i,
        calories: Number(m.calories) || 0,
        protein_g: Number(m.protein_g) || 0,
        carbs_g: Number(m.carbs_g) || 0,
        fat_g: Number(m.fat_g) || 0,
        notes: m.notes || null,
        auto_generate: m.auto_generate !== false,
      }));
      const updated = await api.updateDietMeals(diet.id, payload);
      setDiet(updated);
      setMeals(updated.meals);
      setTarget(dailyTotals(updated.meals));
      // Le ricette già assegnate restano quelle di prima: se i target sono cambiati
      // non sono più in bersaglio, e conviene dirlo subito invece di farlo scoprire
      // dalla percentuale di aderenza in Andamento.
      addToast('Dieta aggiornata ✓ — rigenera la settimana per adeguare le ricette');
    } catch (e) {
      addToast(e.message, 'error');
    } finally {
      setBusy(false);
    }
  };

  const upload = async () => {
    if (!file) return;
    setBusy(true);
    try {
      const updated = await api.uploadDiet(file);
      setDiet(updated);
      setMeals(updated.meals);
      setTarget(dailyTotals(updated.meals));
      setFile(null);
      addToast(`Nuova dieta caricata: ${updated.meals.length} pasti ✓`);
    } catch (e) {
      addToast(e.message, 'error');
    } finally {
      setBusy(false);
    }
  };

  // Col lucchetto chiuso, togliere o aggiungere un pasto non cambia quanto si mangia
  // in un giorno: cambia come lo si divide. Le calorie e i macro del pasto rimosso si
  // ridistribuiscono sugli altri, in proporzione a quanto pesavano già. Aperto, invece,
  // si toglie davvero: è il caso di chi sta riscrivendo la dieta, non di chi la
  // riorganizza.
  const dropMeal = (index) => {
    const base = commit();
    if (base.length <= 1) {
      addToast('La dieta deve avere almeno un pasto', 'error');
      return;
    }
    const removed = base[index];
    const kcal = Math.round(removed.calories) || 0;
    setMeals(locked ? removeMeal(base, index) : base.filter((_, i) => i !== index));
    addToast(
      locked
        ? `${removed.name || 'Pasto'} rimosso: le sue ${kcal} kcal sono andate sugli altri pasti`
        : `${removed.name || 'Pasto'} rimosso: la giornata cala di ${kcal} kcal`
    );
  };

  const appendMeal = () => {
    const base = commit();
    setMeals(
      locked
        ? addMeal(base, 'Nuovo pasto')
        : [...base, { name: 'Nuovo pasto', calories: 0, protein_g: 0, carbs_g: 0, fat_g: 0 }]
    );
    addToast(
      locked
        ? 'Pasto aggiunto: la giornata è stata ridivisa fra tutti'
        : 'Pasto aggiunto a zero: scrivi tu quanto vale'
    );
  };

  // Chiudere il lucchetto prende per buoni i totali di adesso: da lì in poi sono quelli
  // il vincolo. Aprirlo non tocca niente — dice solo che i numeri smettono di essere
  // una prescrizione e tornano a essere campi.
  const toggleLock = () => {
    const base = commit();
    if (locked) {
      setLocked(false);
      addToast('Totali sbloccati: adesso cambiare un pasto cambia la giornata');
    } else {
      setTarget(dailyTotals(base));
      setLocked(true);
      addToast(`Totali bloccati a ${dailyTotals(base).calories} kcal al giorno ✓`);
    }
  };

  // "Lo faccio io": DietAI smette di generarlo, ma i macro restano nel conto della
  // giornata — l'utente quel pasto lo mangia comunque, centrando i target.
  const toggleWho = (index) => {
    const mine = meals[index].auto_generate === false;
    setMeals((prev) =>
      prev.map((m, i) => (i === index ? { ...m, auto_generate: mine } : m))
    );
    addToast(
      mine
        ? `${meals[index].name || 'Pasto'}: torna a generarlo DietAI`
        : `${meals[index].name || 'Pasto'}: non verrà più generato, lo prepari tu`
    );
  };

  // Sul totale si vede anche quello che si sta scrivendo adesso: col lucchetto chiuso
  // è l'anticipo di quanto stanno per muoversi gli altri pasti.
  const totals = dailyTotals(withDraft);

  return (
    <>
      <div className="page-header">
        <div>
          <h1 className="page-title">La mia dieta</h1>
          <p className="page-subtitle">
            Quello che ha scritto il nutrizionista. Da qui nasce tutto il resto: le
            ricette, la lista della spesa e l'aderenza in Andamento.
          </p>
        </div>
      </div>

      {loading ? (
        <div className="spinner" />
      ) : (
        <>
          <div className="card settings-section">
            <div className="card-title">Pasti e macro</div>
            <p className="field-hint" style={{ marginBottom: 14 }}>
              Questi numeri sono il vincolo più duro di tutta l'app: ogni ricetta deve
              starci dentro con una tolleranza del 10%. Se il PDF è stato letto male,
              correggilo qui.
            </p>

            <div className="meal-editor-row meal-editor-head">
              <span>Pasto</span>
              {CAMPI.map(({ key, label }) => (
                <span key={key}>{label}</span>
              ))}
              <span>Chi lo prepara</span>
              <span />
            </div>

            {meals.map((meal, i) => (
              <div
                key={i}
                className={`meal-editor-row ${
                  meal.auto_generate === false ? 'self-managed' : ''
                }`}
              >
                {/* L'etichetta sta dentro ogni cella e su desktop non si vede: lassù
                    la dà l'intestazione della tabella, che sul telefono sparisce —
                    in due colonne non ci sono sei intestazioni da allineare, e senza
                    si finisce a scrivere le proteine nella casella dei grassi. */}
                <label className="meal-editor-cell wide">
                  <span>Pasto</span>
                  <input value={meal.name} onChange={(e) => rename(i, e.target.value)} />
                </label>
                {CAMPI.map(({ key, label }) => (
                  <label className="meal-editor-cell" key={key}>
                    <span>{label}</span>
                    <input
                      type="number"
                      inputMode="decimal"
                      value={
                        draft && draft.index === i && draft.field === key
                          ? draft.value
                          : meal[key]
                      }
                      onChange={(e) =>
                        setDraft({ index: i, field: key, value: e.target.value })
                      }
                      onBlur={commit}
                      onKeyDown={(e) => e.key === 'Enter' && e.currentTarget.blur()}
                    />
                  </label>
                ))}
                <button
                  className={`who-toggle ${meal.auto_generate === false ? 'mine' : 'ai'}`}
                  onClick={() => toggleWho(i)}
                  title={
                    meal.auto_generate === false
                      ? 'Lo prepari tu: non verrà generato, ma i suoi macro contano nella giornata'
                      : 'Lo genera DietAI a ogni piano settimanale'
                  }
                >
                  {meal.auto_generate === false ? (
                    <>
                      <User /> Lo faccio io
                    </>
                  ) : (
                    <>
                      <Sparkles /> DietAI
                    </>
                  )}
                </button>

                <button
                  className="icon-button danger"
                  onClick={() => dropMeal(i)}
                  title={
                    locked
                      ? 'Rimuovi il pasto (le sue calorie vanno sugli altri)'
                      : 'Rimuovi il pasto (la giornata cala delle sue calorie)'
                  }
                >
                  <X size={15} />
                </button>
              </div>
            ))}

            <div className="meal-editor-row totals-row">
              <strong className="totals-row-label">Totale giornaliero</strong>
              {CAMPI.map(({ key, label }) => {
                const fuori = locked && target && totals[key] !== target[key];
                return (
                  <div className="meal-editor-cell" key={key}>
                    <span>{label}</span>
                    <strong className={fuori ? 'off-target' : ''}>
                      {totals[key]}
                      {fuori && <em>torna a {target[key]}</em>}
                    </strong>
                  </div>
                );
              })}
              <button
                className={`lock-toggle ${locked ? '' : 'open'}`}
                onClick={toggleLock}
                title={
                  locked
                    ? 'Il totale del giorno non si muove: quello che togli a un pasto va sugli altri. Clicca per sbloccarlo.'
                    : 'I totali sono liberi: quello che scrivi cambia la giornata. Clicca per ribloccarli su questi numeri.'
                }
              >
                {locked ? <Lock size={13} /> : <Unlock size={13} />}
                {locked ? 'Bloccato' : 'Libero'}
              </button>
              <span />
            </div>

            <p className="field-hint" style={{ marginTop: 10 }}>
              {locked ? (
                <>
                  <strong>Totale bloccato:</strong> quanto mangi in un giorno è deciso, e
                  qui si decide solo come dividerlo. Cambiando un pasto la differenza va
                  sugli altri, e aggiungendone o togliendone uno la giornata si ridivide
                  fra quelli rimasti — a somma zero. Se invece è cambiata la dieta, apri il
                  lucchetto: i campi diventano liberi e il totale è quello che scrivi tu.
                </>
              ) : (
                <>
                  <strong>Totale libero:</strong> stai cambiando quanto mangi in un giorno,
                  non come lo dividi — è la strada giusta se il nutrizionista ti ha dato
                  numeri nuovi. Quando i conti tornano richiudi il lucchetto: da lì in poi
                  saranno questi i totali da difendere.
                </>
              )}
            </p>

            <p className="field-hint">
              <strong>Lo faccio io:</strong> per i pasti che hai già risolto — la colazione
              di sempre, il pranzo in mensa. DietAI non li genera e non compra i loro
              ingredienti, ma i macro restano nel conto della giornata: tu quel pasto lo
              mangi, e centra i suoi target.
            </p>

            <div className="meal-editor-actions">
              <button className="btn btn-secondary btn-sm" onClick={appendMeal}>
                Aggiungi pasto
              </button>
              <button className="btn btn-primary btn-sm" onClick={save} disabled={busy}>
                {busy ? <span className="spinner-inline" /> : <Save size={14} />}
                Salva
              </button>
            </div>
          </div>

          <DietRulesCard />

          <QuestionnaireCard
            diet={diet}
            onDone={(updated) => {
              setDiet(updated);
              setMeals(updated.meals);
              // Il questionario ha appena deciso i totali: sono loro il nuovo vincolo.
              setTarget(dailyTotals(updated.meals));
              setLocked(true);
              addToast(
                `Ricalcolata: ${updated.total_daily_calories} kcal al giorno ✓ — ` +
                  'rigenera la settimana per adeguare le ricette'
              );
            }}
          />

          <div className="card settings-section">
            <div className="card-title">Carica un nuovo PDF</div>
            <p className="field-hint" style={{ marginBottom: 12 }}>
              Il nutrizionista ti ha dato una dieta nuova? Caricala: quella attuale finisce
              in archivio e i pasti vengono riletti da capo.
            </p>
            <label className="dropzone">
              <FileUp />
              {file ? <strong>{file.name}</strong> : 'Scegli il PDF della dieta'}
              <input
                type="file"
                accept="application/pdf"
                hidden
                onChange={(e) => setFile(e.target.files?.[0] || null)}
              />
            </label>
            <button
              className="btn btn-primary btn-sm"
              style={{ marginTop: 12 }}
              onClick={upload}
              disabled={!file || busy}
            >
              {busy && <span className="spinner-inline" />}
              Leggi e sostituisci
            </button>
          </div>
        </>
      )}
    </>
  );
}

// ── Dieta calcolata ────────────────────────────────────────────────────────────

const ATTIVITA = {
  sedentario: 'sedentaria',
  leggero: 'poco attiva',
  moderato: 'moderatamente attiva',
  intenso: 'molto attiva',
  atleta: 'atleta',
};

// Chiusa di default anche per chi la dieta se l'è calcolata: aperta occuperebbe mezza
// pagina davanti ai numeri che si vengono a correggere qui il 90% delle volte. Ma il
// riassunto dei dati resta a vista, perché è quello che dice se vale la pena riaprirla:
// il peso di sei settimane fa si riconosce a colpo d'occhio.
function QuestionnaireCard({ diet, onDone }) {
  const [open, setOpen] = useState(false);
  const profile = diet?.profile;

  return (
    <div className="card settings-section">
      <div className="card-title">
        <Calculator /> Calcola i macro dai tuoi dati
      </div>

      <p className="field-hint" style={{ marginBottom: 12 }}>
        {profile ? (
          <>
            Questi numeri sono calcolati da: {profile.sex}, {profile.age} anni,{' '}
            {profile.height_cm} cm, <strong>{profile.weight_kg} kg</strong>, vita{' '}
            {ATTIVITA[profile.activity] || profile.activity}, obiettivo «{profile.goal}».
            Se il peso è cambiato, ricalcolare è la strada più corta — e sostituisce la
            dieta attuale, che finisce in archivio.
          </>
        ) : (
          <>
            La tua dieta di adesso non viene da qui. Se vuoi ripartire dai tuoi dati —
            sesso, età, altezza, peso, quanto ti muovi e che obiettivo hai — calcolo
            calorie e macro con la formula standard (Mifflin-St Jeor) e sostituisco
            quella attuale, che finisce in archivio. Nessuna chiamata AI: è aritmetica.
          </>
        )}
      </p>

      {open ? (
        <>
          <Questionnaire
            profile={profile}
            submitLabel={profile ? 'Ricalcola e sostituisci' : 'Calcola e sostituisci'}
            onDone={(updated) => {
              setOpen(false);
              onDone(updated);
            }}
          />
          <button
            className="btn btn-ghost btn-sm"
            style={{ marginTop: 10 }}
            onClick={() => setOpen(false)}
          >
            Lascia perdere
          </button>
        </>
      ) : (
        <button className="btn btn-secondary btn-sm" onClick={() => setOpen(true)}>
          <Calculator size={14} /> {profile ? 'Ricalcola' : 'Apri il questionario'}
        </button>
      )}
    </div>
  );
}

// ── Regole in linguaggio naturale ──────────────────────────────────────────────

const ESEMPI_REGOLE = `Niente insaccati.
Carne rossa al massimo due volte a settimana.
Il pesce mi piace ma non più di tre volte.
La sera preferisco piatti unici, veloci da preparare.
Non ripetere lo stesso primo due giorni di fila.`;

function DietRulesCard() {
  const { addToast } = useApp();
  const [prefs, setPrefs] = useState(null);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .getPreferences()
      .then((p) => {
        setPrefs(p);
        setDraft(p.notes || '');
      })
      .catch(() => {});
  }, []);

  const save = async () => {
    setBusy(true);
    try {
      // Le preferenze si salvano intere: il backend vuole anche gli interruttori.
      const updated = await api.updatePreferences({ ...prefs, notes: draft });
      setPrefs(updated);
      addToast('Regole salvate — valgono dalla prossima generazione ✓');
    } catch (e) {
      addToast(e.message, 'error');
    } finally {
      setBusy(false);
    }
  };

  if (!prefs) return null;

  const dirty = (prefs.notes || '') !== draft;

  return (
    <div className="card settings-section">
      <div className="card-title">
        <MessageSquare /> Regole e note per DietAI
      </div>
      <p className="field-hint" style={{ marginBottom: 12 }}>
        Scrivile come le diresti a voce: qui non servono caselle, dall'altra parte c'è
        un modello che legge l'italiano. È il posto per tutto ciò che non è un singolo
        ingrediente da escludere — quante volte a settimana vuoi un alimento, cosa
        preferisci la sera, abitudini che si ripetono.
      </p>

      <textarea
        rows={7}
        value={draft}
        placeholder={ESEMPI_REGOLE}
        onChange={(e) => setDraft(e.target.value)}
      />

      <p className="field-hint">
        Le regole a cadenza settimanale ("carne due volte") funzionano perché il piano
        viene generato tutto in una volta: il modello vede l'intera settimana mentre la
        costruisce. Valgono anche quando rigeneri un singolo pasto e quando chiedi una
        modifica in chat.
      </p>

      <button
        className="btn btn-primary btn-sm"
        style={{ marginTop: 12 }}
        onClick={save}
        disabled={busy || !dirty}
      >
        {busy ? <span className="spinner-inline" /> : <Save size={14} />}
        Salva le regole
      </button>
    </div>
  );
}

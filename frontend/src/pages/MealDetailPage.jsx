import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import {
  ArrowLeft,
  ArrowLeftRight,
  BookOpen,
  CalendarOff,
  Check,
  CheckCircle2,
  Heart,
  MessageCircle,
  Pin,
  RefreshCw,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import { api, formatDate } from "../api";
import { useApp } from "../App";
import ConfirmDialog from "../components/ConfirmDialog";
import EatenInstead from "../components/EatenInstead";
import EatenInsteadDialog from "../components/EatenInsteadDialog";
import EmptyState from "../components/EmptyState";
import LoadError from "../components/LoadError";
import Modal from "../components/Modal";
import MealChat from "../components/MealChat";
import RecipeView from "../components/RecipeView";
import StarRating from "../components/StarRating";
import { useGoBack } from "../lib/navigation";
import { nonScalatiDallaDispensa, scalatiDallaDispensa } from "../lib/pantry";

export default function MealDetailPage() {
  const { mealId } = useParams();
  const { addToast } = useApp();
  const [meal, setMeal] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  // Il pasto appena segnato «ho mangiato altro»: la modale chiede cosa.
  const [altro, setAltro] = useState(null);
  const [substituting, setSubstituting] = useState(false);
  const [substitution, setSubstitution] = useState(null);
  const [confirmClear, setConfirmClear] = useState(false);
  const [picker, setPicker] = useState(false);
  const [generator, setGenerator] = useState(false);
  const [swapping, setSwapping] = useState(false);

  // Lo spinner solo quando si è senza niente a schermo: `load()` si richiama anche
  // dopo una sostituzione, col dialogo del risultato aperto sopra la pagina, e
  // rimettere lo spinner lo farebbe sparire e ricomparire.
  // Il pasto che si sta guardando adesso: passando da un pasto all'altro la risposta
  // del primo poteva arrivare dopo, e la pagina mostrava il pasto sbagliato mentre i
  // pulsanti agivano su quello giusto.
  const pastoVisto = useRef(mealId);
  pastoVisto.current = mealId;
  const [segnando, setSegnando] = useState(false);

  const load = useCallback(
    async ({ spinner = false } = {}) => {
      if (spinner) setLoading(true);
      try {
        const data = await api.getMeal(mealId);
        if (pastoVisto.current !== mealId) return;
        setMeal(data);
        setError(null);
      } catch (e) {
        // Il toast dura tre secondi, la pagina resta: senza il messaggio anche qui,
        // chi torna sulla schermata trova solo il vuoto e non sa perché.
        setError(e.message);
        addToast(e.message, "error");
      } finally {
        setLoading(false);
      }
    },
    [mealId, addToast],
  );

  useEffect(() => {
    // Un pasto nuovo parte da zero: se il caricamento fallisce si vede LoadError, non
    // il pasto di prima con i pulsanti del nuovo.
    setMeal(null);
    setLoading(true);
  }, [mealId]);

  useEffect(() => {
    load();
  }, [load]);

  // Da dove si torna indietro quando questa è la prima pagina della sessione —
  // il caso normale sul telefono, che riapre l'app sull'ultimo indirizzo aperto.
  const tornaIndietro = useGoBack(
    meal?.week && !meal.week.is_current
      ? `/plan/${meal.week.week_start_date}`
      : "/plan",
  );

  // Due strade, due pulsanti: senza indicazioni sceglie il modello (un clic, niente
  // dialogo), con indicazioni ("ho del salmone da finire") sceglie l'utente e l'AI ci
  // pesa sopra i macro. Va chiamata sempre come `regenerate()`: passandola diretta a
  // un `onClick` arriverebbe qui l'evento del clic al posto della richiesta.
  const regenerate = async (userRequest = null) => {
    setBusy(true);
    try {
      setMeal(await api.regenerateMeal(mealId, userRequest));
      setGenerator(false);
      addToast(
        userRequest
          ? "Ricetta pronta su tua indicazione ✓"
          : "Nuova ricetta pronta ✓",
      );
    } catch (e) {
      addToast(e.message, "error");
    } finally {
      setBusy(false);
    }
  };

  const rate = async (rating) => {
    try {
      await api.rateRecipe(meal.recipe.id, rating);
      setMeal((m) => ({ ...m, recipe: { ...m.recipe, rating } }));
      addToast("Voto salvato — ne terrò conto la prossima volta ✓");
    } catch (e) {
      addToast(e.message, "error");
    }
  };

  const toggleFavorite = async () => {
    try {
      const next = !meal.recipe.is_favorite;
      await api.favoriteRecipe(meal.recipe.id, next);
      setMeal((m) => ({ ...m, recipe: { ...m.recipe, is_favorite: next } }));
    } catch (e) {
      addToast(e.message, "error");
    }
  };

  const toggleRecurring = async () => {
    try {
      const updated = await api.setRecurring(mealId, !meal.is_recurring);
      setMeal(updated);
      if (!meal.is_recurring) {
        addToast("Pasto fisso: si ripete sulle settimane che apri ✓");
      } else if (updated.cleared_forward) {
        // La spunta tolta si porta via le copie già scritte nei giorni successivi:
        // se ne succedono sette in silenzio, sembra che si sia rotto qualcosa.
        addToast(
          `Non è più fisso: tolto anche da ${updated.cleared_forward} ` +
            `${updated.cleared_forward === 1 ? "casella successiva" : "caselle successive"}`,
        );
      } else {
        addToast("Non è più fisso");
      }
    } catch (e) {
      addToast(e.message, "error");
    }
  };

  const setFollowed = async (value) => {
    // Già «ho mangiato altro»: ripremerlo riapre la domanda. Rimandarlo al server
    // cancellerebbe la nota scritta, e il piatto è già stato rimandato.
    if (value === false && meal.is_followed === false) {
      setAltro(meal);
      return;
    }
    // Due tocchi rapidi mandavano due richieste e due avvisi sulla dispensa.
    if (segnando) return;
    setSegnando(true);
    try {
      const updated = await api.setFollowed(mealId, value);
      setMeal(updated);
      if (value === false) setAltro(updated);
      // "Ho mangiato altro" non è solo un appunto: il piatto si sposta, e dove è
      // finito va detto subito o l'utente lo cerca dov'era.
      if (updated.moved_to) {
        addToast(
          `Ricetta rimandata a ${updated.moved_to.day_name.toLowerCase()}` +
            (updated.moved_to.next_week ? " della settimana prossima" : ""),
        );
      } else if (value) {
        addToast("Rimessa al suo posto ✓");
      }
      if (updated.pantry_used?.length) {
        addToast(scalatiDallaDispensa(updated.pantry_used), "info");
      } else if (value && updated.pantry_skipped?.length) {
        // Nessuna scorta toccata: il perché c'è sempre, e senza dirlo la dispensa
        // ferma sembra un errore dell'app.
        addToast(nonScalatiDallaDispensa(updated.pantry_skipped), "info");
      }
    } catch (e) {
      addToast(e.message, "error");
    } finally {
      setSegnando(false);
    }
  };

  const substitute = async (ingredient) => {
    setSubstituting(true);
    try {
      // Il pasto va passato: se lo stesso piatto è in programma anche altri giorni, la
      // sostituzione vale per questa casella e non per tutte.
      const result = await api.substituteIngredient(
        meal.recipe.id,
        ingredient.name,
        null,
        meal.id,
      );
      setSubstitution(result);
      await load();
    } catch (e) {
      addToast(e.message, "error");
    } finally {
      setSubstituting(false);
    }
  };

  const clearMeal = async () => {
    try {
      setMeal(await api.clearMeal(mealId));
      setConfirmClear(false);
      addToast("Casella svuotata");
    } catch (e) {
      addToast(e.message, "error");
    }
  };

  if (loading) return <div className="spinner" />;
  if (!meal)
    return (
      <LoadError message={error} onRetry={() => load({ spinner: true })} />
    );

  // Il `?.` non è pignoleria: questa pagina si ridisegna con la risposta dell'ultimo
  // pulsante premuto, e una risposta senza `week` non deve poter spegnere la schermata.
  // L'unica sola lettura rimasta: una casella saltata, la cui ricetta si è accodata
  // altrove. Tutto il resto — passato compreso — si modifica quando si vuole.
  const skipped = meal.day_is_skipped;
  const frozen = skipped || meal.is_skipped;

  return (
    <>
      {/* A casella piena questa testata non c'è: il titolo della pagina è il nome
          del piatto, ed è scritto sul foglio, con sopra la stessa riga di contesto e
          accanto il tondo per tornare indietro. Tenerla vorrebbe dire dire due volte
          dove ci si trova. A casella vuota invece il foglio non c'è, e allora è
          l'unica cosa che dice di che pasto si tratta. */}
      {!meal.recipe && (
        <div className="page-header page-header-magra">
          <div>
            <h1 className="page-title">
              {meal.slot_name} · {meal.day_name}
            </h1>
            <p className="page-subtitle">
              {formatDate(meal.date, {
                weekday: "long",
                day: "numeric",
                month: "long",
              })}{" "}
              · target {meal.target.calories} kcal
              {meal.target.notes ? ` · ${meal.target.notes}` : ""}
            </p>
          </div>
        </div>
      )}

      {skipped && (
        <div className="notice notice-skip">
          <CalendarOff />
          <div>
            <strong>Giornata saltata.</strong> Quello che c'era in programma si
            è accodato alle prime caselle libere, e qui non c'è più niente da
            cambiare.
          </div>
        </div>
      )}

      {meal.is_skipped && !skipped && (
        <div className="notice notice-skip">
          <CalendarOff />
          <div>
            <strong>Pasto saltato.</strong> Hai segnato di aver mangiato altro:
            la ricetta qui sotto resta per memoria, ma è stata rimandata alla
            prima casella libera di questo pasto. Se invece l'hai cucinata,
            premi "L'ho seguito" e torna al suo posto.
          </div>
        </div>
      )}

      {meal.is_followed === true && (
        <div className="notice notice-ok">
          <CheckCircle2 />
          <div>
            <strong>Pasto seguito.</strong> Gli ingredienti sono stati scalati
            dalla dispensa e questo piatto è uscito dalla lista della spesa.
          </div>
        </div>
      )}

      <div className="recipe-header">
        <button
          className="recipe-back"
          onClick={tornaIndietro}
          title="Indietro"
        >
          <ArrowLeft />
        </button>
      </div>

      <div className="detail-layout">
        <div>
          {meal.recipe ? (
            <>
              <RecipeView
                recipe={meal.recipe}
                target={meal.target}
                persone={meal.servings}
                onSubstitute={frozen ? null : substitute}
                substituting={substituting}
                eyebrow={`${meal.slot_name} di ${meal.day_name.toLowerCase()} ${formatDate(
                  meal.date,
                  { day: "numeric", month: "long" },
                )}`}
                indietro={null}
                /* Il cuore sale sulla fascia, in alto a destra: in fondo al foglio
                   sta in una riga di sei comandi che sul telefono va a capo tre
                   volte, e mettere «preferita» al terzo capo vuol dire non
                   premerlo mai. */
                preferita={
                  <button
                    className={`recipe-fav ${meal.recipe.is_favorite ? "on" : ""}`}
                    onClick={toggleFavorite}
                    title={
                      meal.recipe.is_favorite
                        ? "Togli dai preferiti"
                        : "Aggiungi ai preferiti"
                    }
                  >
                    <Heart
                      fill={meal.recipe.is_favorite ? "currentColor" : "none"}
                    />
                  </button>
                }
                azioni={
                  <>
                    {/* Le due risposte aprono la riga: sono la ragione per cui il
                        pasto si apre la sera, e stanno alla fine del procedimento —
                        cioè nel punto della pagina in cui si è quando si è cucinato.
                        Sul telefono le stesse due sono anche nella barra in fondo
                        (`.meal-bar`), e lì queste si nascondono per non doppiarle. */}
                    <div className="andata-answers">
                      <button
                        className={`btn ${
                          meal.is_followed === true
                            ? "btn-primary"
                            : "btn-secondary"
                        }`}
                        onClick={() => setFollowed(true)}
                      >
                        <Check size={16} /> L'ho seguito
                      </button>
                      <button
                        className={`btn ${
                          meal.is_followed === false
                            ? "btn-moved"
                            : "btn-secondary"
                        }`}
                        onClick={() => setFollowed(false)}
                      >
                        <X size={16} /> Ho mangiato altro
                      </button>
                    </div>

                    {meal.is_followed === false && (
                      <EatenInstead meal={meal} onSaved={setMeal} />
                    )}

                    <div className="andata-rating spinta">
                      <span>Voto</span>
                      <StarRating value={meal.recipe.rating} onChange={rate} />
                    </div>

                    <button
                      className="btn btn-secondary"
                      onClick={toggleRecurring}
                      disabled={frozen}
                      title={
                        meal.is_recurring
                          ? "Smetti di ripeterlo: lo toglie anche dai giorni successivi che lo hanno ricevuto"
                          : "Ripeti questo pasto ogni settimana"
                      }
                    >
                      <Pin
                        size={16}
                        color={
                          meal.is_recurring ? "var(--accent)" : "currentColor"
                        }
                      />
                      {meal.is_recurring ? "Fisso" : "Rendi fisso"}
                    </button>

                    {/* Spostare il piatto in un altro giorno (o a un altro pasto) è la
                        correzione più comune del piano: «giovedì sera esco, lo faccio
                        martedì». Fissi e pasti già segnati non si spostano, e il
                        pulsante lo dice prima invece di aprire una lista inutile. */}
                    <button
                      className="btn btn-secondary"
                      onClick={() => setSwapping(true)}
                      disabled={frozen || meal.is_recurring || meal.is_followed !== null}
                      title={
                        meal.is_recurring
                          ? "Un pasto fisso resta nel suo giorno"
                          : meal.is_followed !== null
                            ? "È già segnato: non si sposta"
                            : "Scambialo con un altro pasto della settimana"
                      }
                    >
                      <ArrowLeftRight size={16} /> Scambia
                    </button>

                    {/* Al posto del piatto generato, uno di quelli salvati: la spesa e la
                        dispensa seguono la ricetta nuova, la ricetta no — ha le sue
                        grammature, non quelle cucite sui target di questo pasto. */}
                    <button
                      className="btn btn-secondary"
                      onClick={() => setPicker(true)}
                      disabled={frozen || meal.is_recurring || meal.is_followed !== null}
                    >
                      <BookOpen size={16} /> Dal ricettario
                    </button>

                    <button
                      className="btn btn-secondary"
                      onClick={() => setGenerator(true)}
                      disabled={busy || frozen}
                    >
                      {/* Scintille e non la freccia circolare: qui l'icona vuol dire
                          "chiama il modello", ed è la stessa coppia dei due pulsanti
                          a casella vuota. */}
                      {busy ? (
                        <span className="spinner-inline" />
                      ) : (
                        <Sparkles size={16} />
                      )}
                      Rigenera
                    </button>

                    {!frozen && (
                      <div className="recipe-actions-quiet">
                        <button
                          className="btn btn-ghost btn-sm"
                          onClick={() => setConfirmClear(true)}
                        >
                          <Trash2 size={14} /> Svuota questa casella
                        </button>
                      </div>
                    )}
                  </>
                }
              />
            </>
          ) : (
            <EmptyState
              icon={RefreshCw}
              title="Nessuna ricetta per questo pasto"
              text={`Target: ${meal.target.calories} kcal, proteine ${meal.target.protein_g}g, carboidrati ${meal.target.carbs_g}g, grassi ${meal.target.fat_g}g.`}
              action={
                /* I tre modi di riempire la casella, incolonnati e larghi uguale
                   (`.empty-actions`): scelgo io, scegli tu cosa e faccio i conti,
                   oppure la ricetta ce l'hai già. In riga si allineavano solo a
                   schermo largo — vedi il commento sulla classe. */
                <div className="empty-actions">
                  <button
                    className="btn btn-primary"
                    onClick={() => regenerate()}
                    disabled={busy || frozen}
                  >
                    {busy ? (
                      <span className="spinner-inline" />
                    ) : (
                      <Sparkles size={16} />
                    )}
                    Scegli tu il piatto
                  </button>
                  <button
                    className="btn btn-ai"
                    onClick={() => setGenerator(true)}
                    disabled={busy || frozen}
                  >
                    <Sparkles size={16} />
                    Genera da una mia idea
                  </button>
                  <button
                    className="btn btn-secondary"
                    onClick={() => setPicker(true)}
                  >
                    <BookOpen size={16} />
                    Scegli dal ricettario
                  </button>
                  {!frozen && !meal.self_managed && (
                    <button
                      className="btn btn-secondary"
                      onClick={() => setSwapping(true)}
                    >
                      <ArrowLeftRight size={16} />
                      Sposta qui un piatto della settimana
                    </button>
                  )}
                </div>
              }
            />
          )}
        </div>

        <MealChat
          mealId={meal.id}
          locked={frozen}
          onRecipeUpdated={(recipe) => setMeal((m) => ({ ...m, recipe }))}
        />
      </div>

      {/* Le due risposte sotto il pollice. La sera il pasto si apre proprio per
          premerne una, e stavano in fondo alla ricetta, dopo ingredienti e
          procedimento. Il terzo pulsante porta alla chat, che sul telefono sta
          sotto la ricetta invece che di fianco. */}
      {meal.recipe && (
        <div className="meal-bar">
          <button
            className={`btn ${meal.is_followed === true ? "btn-primary" : "btn-secondary"}`}
            onClick={() => setFollowed(true)}
            disabled={skipped}
          >
            <Check size={16} /> L'ho seguito
          </button>
          <button
            className={`btn ${meal.is_followed === false ? "btn-moved" : "btn-secondary"}`}
            onClick={() => setFollowed(false)}
            disabled={skipped}
          >
            <X size={16} /> Ho mangiato altro
          </button>
          <button
            className="btn btn-secondary meal-bar-chat"
            onClick={() =>
              document.querySelector(".chat-panel")?.scrollIntoView({
                behavior: window.matchMedia("(prefers-reduced-motion: reduce)")
                  .matches
                  ? "auto"
                  : "smooth",
                block: "start",
              })
            }
            aria-label="Chiedi una modifica"
            title="Chiedi una modifica"
          >
            <MessageCircle size={16} />
          </button>
          {!skipped && (
            <button
              className="btn btn-ghost meal-bar-delete"
              onClick={() => setConfirmClear(true)}
              title="Svuota questa casella"
            >
              <Trash2 size={16} />
            </button>
          )}
        </div>
      )}

      {substitution && (
        <Modal title="Ingrediente sostituito" onClose={() => setSubstitution(null)}>
          <p className="modal-text">
            <strong>{substitution.original?.name}</strong> →{" "}
            <strong>{substitution.substitute?.name}</strong> (
            {substitution.substitute?.quantity}{" "}
            {substitution.substitute?.unit})
            <br />
            <br />
            {substitution.explanation}
          </p>
          <div className="modal-actions">
            <button
              className="btn btn-primary"
              onClick={() => setSubstitution(null)}
            >
              Ho capito
            </button>
          </div>
        </Modal>
      )}

      {confirmClear && (
        <ConfirmDialog
          title="Svuotare la casella?"
          text="La ricetta resta nel ricettario, ma questo pasto tornerà vuoto."
          confirmLabel="Svuota"
          danger
          onConfirm={clearMeal}
          onCancel={() => setConfirmClear(false)}
        />
      )}

      {altro && (
        <EatenInsteadDialog meal={altro} onSaved={setMeal} onClose={() => setAltro(null)} />
      )}

      {generator && (
        <GenerateDialog
          meal={meal}
          busy={busy}
          onGenerate={regenerate}
          onCancel={() => setGenerator(false)}
        />
      )}

      {swapping && (
        <SwapDialog
          meal={meal}
          onCancel={() => setSwapping(false)}
          onSwapped={(updated) => {
            setMeal(updated);
            setSwapping(false);
            const altro = updated.swapped_with;
            addToast(
              `Scambiato con ${altro.slot_name.toLowerCase()} di ${altro.day_name.toLowerCase()} ✓`,
            );
          }}
        />
      )}

      {picker && (
        <RecipePicker
          onCancel={() => setPicker(false)}
          onPick={async (recipeId) => {
            try {
              setMeal(await api.assignMeal(mealId, { recipe_id: recipeId }));
              setPicker(false);
              addToast("Ricetta assegnata ✓");
            } catch (e) {
              addToast(e.message, "error");
            }
          }}
        />
      )}
    </>
  );
}

const ESEMPI_RICHIESTA = `Ho del salmone da finire.
Qualcosa con la zucca, veloce.
Vorrei un piatto unico freddo da portare in ufficio.
Pasta e ceci, ma con le quantità giuste per i miei macro.`;

/**
 * Dove si dice cosa si vuole in quella casella.
 *
 * Il comando passa all'utente — un'idea, un ingrediente da finire, un piatto preciso —
 * e all'AI resta il mestiere: pesare gli ingredienti perché i macro del pasto tornino e
 * scrivere il procedimento. Il campo lasciato vuoto ricade sulla generazione di sempre,
 * quella in cui sceglie il modello: è la stessa cosa che fa "Scegli tu il piatto" a
 * casella vuota, e il pulsante prende quel nome per dirlo.
 */
function GenerateDialog({ meal, busy, onGenerate, onCancel }) {
  const [testo, setTesto] = useState("");
  const richiesta = testo.trim();

  return (
    <Modal
      title={meal.recipe ? "Rigenera questo pasto" : "Genera questo pasto"}
      onClose={onCancel}
      busy={busy}
    >
      <p className="modal-text">
        Target: {meal.target.calories} kcal · P {meal.target.protein_g}g · C{" "}
        {meal.target.carbs_g}g · G {meal.target.fat_g}g.
        <br />
        Scrivi cosa ti va: un'idea, un ingrediente da finire, un piatto
        preciso.
      </p>

      <textarea
        rows={4}
        value={testo}
        placeholder={ESEMPI_RICHIESTA}
        aria-label="Cosa ti va di mangiare"
        onChange={(e) => setTesto(e.target.value)}
        maxLength={500}
        disabled={busy}
        autoFocus
      />

      <p className="field-hint" style={{ marginTop: 8 }}>
        {richiesta
          ? "I macro restano il vincolo: le quantità le calcola l’AI per starci dentro."
          : "Lascialo vuoto e ti propongo un piatto diverso dagli altri della settimana."}
      </p>

      <div className="modal-actions" style={{ marginTop: 16 }}>
        <button
          className="btn btn-secondary"
          onClick={onCancel}
          disabled={busy}
        >
          Annulla
        </button>
        <button
          className="btn btn-primary"
          onClick={() => onGenerate(richiesta || null)}
          disabled={busy}
        >
          {busy ? (
            <span className="spinner-inline" />
          ) : (
            <Sparkles size={16} />
          )}
          {richiesta ? "Genera così" : "Scegli tu il piatto"}
        </button>
      </div>
    </Modal>
  );
}

/**
 * Lo scambio con un altro pasto della settimana.
 *
 * L'elenco è quello del server, col motivo accanto a chi non si può scegliere (fisso,
 * già segnato, saltato, «lo fai tu»): se la pagina decidesse da sé, prima o poi
 * proporrebbe uno scambio che il server rifiuta. I target restano ai pasti, quindi i
 * totali dei due giorni cambiano — quello della settimana no, ed è quello che conta.
 */
function SwapDialog({ meal, onSwapped, onCancel }) {
  const { addToast } = useApp();
  const [candidati, setCandidati] = useState(null);
  const [errore, setErrore] = useState(null);
  const [inCorso, setInCorso] = useState(null);

  useEffect(() => {
    api
      .getSwapCandidates(meal.id)
      .then(setCandidati)
      .catch((e) => setErrore(e.message));
  }, [meal.id]);

  const scambia = async (otherId) => {
    setInCorso(otherId);
    try {
      onSwapped(await api.swapMeal(meal.id, otherId));
    } catch (e) {
      addToast(e.message, "error");
      setInCorso(null);
    }
  };

  // Un gruppo per giorno, nell'ordine della settimana: è così che si pensa a uno
  // spostamento («lo faccio mercoledì»), non per nome del piatto.
  const giorni = [];
  for (const c of candidati || []) {
    const ultimo = giorni[giorni.length - 1];
    if (ultimo && ultimo.date === c.date) ultimo.items.push(c);
    else giorni.push({ date: c.date, day_name: c.day_name, items: [c] });
  }

  return (
    <Modal
      title={meal.recipe ? "Scambia con un altro pasto" : "Sposta qui un piatto"}
      onClose={onCancel}
      busy={inCorso !== null}
      className="modal-lg"
    >
      <p className="modal-text">
        {meal.recipe ? (
          <>
            <strong>{meal.recipe.title}</strong> va al pasto che scegli, e quel piatto
            viene qui.
          </>
        ) : (
          "Il piatto che scegli si sposta in questa casella, e la sua resta vuota."
        )}{" "}
        I totali dei due giorni cambiano; quello della settimana resta lo stesso.
      </p>

      {errore ? (
        <p className="field-hint">{errore}</p>
      ) : !candidati ? (
        <div className="spinner" />
      ) : (
        <div className="swap-list">
          {giorni.map((g) => (
            <div key={g.date}>
              <div className="swap-day">
                {g.day_name} {formatDate(g.date, { day: "numeric", month: "short" })}
              </div>
              {g.items.map((c) => (
                <div key={c.meal_id} className={`list-row ${c.blocked ? "is-blocked" : ""}`}>
                  <div className="list-row-main">
                    <strong>{c.slot_name}</strong>
                    <span>
                      {c.recipe
                        ? `${c.recipe.title} · ${c.recipe.calories} kcal`
                        : "vuoto"}
                      {c.blocked ? ` · ${c.blocked}` : ""}
                    </span>
                  </div>
                  {!c.blocked && (c.recipe || meal.recipe) && (
                    <button
                      className="btn btn-secondary btn-sm"
                      onClick={() => scambia(c.meal_id)}
                      disabled={inCorso !== null}
                      aria-label={`Scambia con ${c.slot_name} di ${c.day_name}`}
                    >
                      {inCorso === c.meal_id ? (
                        <span className="spinner-inline" />
                      ) : (
                        <ArrowLeftRight size={14} />
                      )}
                      {meal.recipe ? "Scambia" : "Sposta qui"}
                    </button>
                  )}
                </div>
              ))}
            </div>
          ))}
        </div>
      )}

      <div className="modal-actions" style={{ marginTop: 16 }}>
        <button className="btn btn-secondary" onClick={onCancel} disabled={inCorso !== null}>
          Chiudi
        </button>
      </div>
    </Modal>
  );
}

function RecipePicker({ onPick, onCancel }) {
  const [items, setItems] = useState([]);
  const [search, setSearch] = useState("");

  useEffect(() => {
    const t = setTimeout(() => {
      api
        .getRecipes({ search, per_page: 30, scope: "proposable" })
        .then((d) => setItems(d.items))
        .catch(() => {});
    }, 250);
    return () => clearTimeout(t);
  }, [search]);

  return (
    <Modal title="Scegli dal ricettario" onClose={onCancel} className="modal-lg">
      <p className="field-hint" style={{ marginBottom: 10 }}>
        Le preferite, quelle votate da 3 stelle in su e le tue. La ricetta resta con le
        sue grammature: i macro del pasto possono scostarsi dal target.
      </p>
      <input
        type="text"
        placeholder="Cerca..."
        aria-label="Cerca nel ricettario"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        style={{ marginBottom: 12 }}
      />
      <div
        className="list-rows"
        style={{ maxHeight: 380, overflowY: "auto" }}
      >
        {items.map((r) => (
          <div key={r.id} className="list-row">
            <div className="list-row-main">
              <strong>{r.title}</strong>
              <span>
                {r.calories} kcal · P {r.protein_g}g · C {r.carbs_g}g · G{" "}
                {r.fat_g}g
              </span>
            </div>
            <button
              className="btn btn-secondary btn-sm"
              onClick={() => onPick(r.id)}
            >
              Scegli
            </button>
          </div>
        ))}
        {items.length === 0 && (
          <p className="field-hint">Nessuna ricetta trovata.</p>
        )}
      </div>
      <div className="modal-actions" style={{ marginTop: 16 }}>
        <button className="btn btn-secondary" onClick={onCancel}>
          Chiudi
        </button>
      </div>
    </Modal>
  );
}

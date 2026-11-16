import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Check, ChefHat, ChevronRight, MessageCircle, UtensilsCrossed, X } from 'lucide-react';
import { api, formatNumber } from '../api';
import { useApp } from '../App';
import EatenInsteadDialog from './EatenInsteadDialog';
import MacroBar from './MacroBar';
import { nonScalatiDallaDispensa, scalatiDallaDispensa } from '../lib/pantry';
import { useTelefono } from '../lib/schermo';
import { dettagliMangiati, niente, todayTotals } from '../lib/today';

// La giornata: quanto si è mangiato contro la dieta, e i pasti uno sotto l'altro coi
// pulsanti per segnarli. È la parte centrale della home, e la stessa che si apre
// toccando un giorno nella settimana: una sola versione, perché le due schermate
// non dicano due cose diverse della stessa giornata.

const PARZIALE =
  'Il ≥ vuol dire che qualche pasto segnato quel valore non lo sa (un «lo prepari tu», ' +
  'un ingrediente senza composizione): il conto vero è almeno questo.';

// Quanto si mangia oggi, sommando i piatti in programma. Un pasto rimandato non
// conta (si cucina un altro giorno) e uno che prepara l'utente conta col suo target:
// è la stessa aritmetica di `serialize_week`, e senza la seconda metà la giornata
// sembrerebbe più corta di quello che è.
// Cosa dice la riga di un pasto «ho mangiato altro»: la stima, se c'è, al posto del
// piatto rimandato — è quello che conta nel totale qui sopra.
function altroMangiato(meal) {
  if (!(meal.is_skipped || meal.is_followed === false)) return null;
  const stima = meal.eaten_nutrition;
  if (!stima) return { kcal: null, testo: 'Hai mangiato altro: cosa?' };
  // «Non ho mangiato niente» è uno zero saputo, non una stima: niente «≈».
  if (niente(meal)) return { kcal: 0, niente: true, testo: 'Non hai mangiato niente' };
  return { kcal: stima.calories, testo: meal.deviation_notes || 'Hai mangiato altro' };
}

// Le calorie di un pasto «ho mangiato altro», come le dice la riga.
function kcalAltro(altro) {
  if (altro.kcal == null) return 'non stimato';
  return altro.niente ? '0 kcal' : `≈ ${altro.kcal} kcal stimate`;
}


// Un pasto della giornata, in riga. Il tondo a sinistra dice com'è andata — o che
// quel pasto non lo genera nessuno — poi il nome del pasto con le sue calorie in
// monospaziato e sotto il piatto. È la forma che il telefono chiede: quattro righe
// per una giornata, contro quattro card da 215px l'una.
function MealRow({ meal }) {
  const stato = meal.is_followed === true ? 'done' : meal.is_skipped ? 'moved' : '';
  const Icona =
    meal.is_followed === true
      ? Check
      : meal.is_skipped
        ? X
        : meal.self_managed
          ? ChefHat
          : UtensilsCrossed;
  const altro = altroMangiato(meal);
  return (
    <Link className={`meal-row ${stato}`} to={`/meals/${meal.meal_id}`}>
      <span className={`meal-tondo ${stato} ${meal.self_managed ? 'mine' : ''}`}>
        <Icona />
      </span>
      <span className="meal-row-testo">
        <span className="meal-slot">
          {meal.slot_name} ·{' '}
          {altro
            ? kcalAltro(altro)
            : `${meal.recipe ? meal.recipe.calories : meal.target_calories} kcal`}
        </span>
        <span className="meal-row-titolo">
          {altro
            ? altro.testo
            : meal.recipe
              ? meal.recipe.title
              : meal.self_managed
                ? 'Lo prepari tu'
                : 'Scegli cosa mangiare'}
        </span>
      </span>
      <ChevronRight className="meal-row-freccia" />
    </Link>
  );
}

export default function DayMeals({ meals, onChanged, vuoto = null, conAdesso = true, dettagli = false }) {
  const { addToast } = useApp();
  const navigate = useNavigate();
  // Sul telefono i pasti già decisi sono righe di elenco, non card: vedi
  // `lib/schermo.js`. Il pasto di adesso resta una card in tutti e due i casi.
  const telefono = useTelefono();
  // Il pasto appena segnato «ho mangiato altro»: la modale chiede cosa.
  const [altro, setAltro] = useState(null);
  // Il pasto che si sta segnando: due tocchi rapidi su «l'ho seguito» mandavano due
  // richieste e due avvisi sulla dispensa.
  const [segnando, setSegnando] = useState(null);

  const markFollowed = async (mealId, followed) => {
    if (segnando) return;
    // Già «ho mangiato altro»: ripremerlo riapre la domanda invece di rimandarlo al
    // server, che cancellerebbe la nota scritta.
    const prima = meals.find((m) => m.meal_id === mealId);
    if (followed === false && prima?.is_followed === false) {
      setAltro({ id: mealId, slot_name: prima.slot_name, deviation_notes: prima.deviation_notes });
      return;
    }
    setSegnando(mealId);
    try {
      const updated = await api.setFollowed(mealId, followed);
      if (followed === false) setAltro(updated);
      // "Saltato" qui rimanda davvero il piatto: va detto dov'è finito.
      if (updated.moved_to) {
        addToast(
          `Ricetta rimandata a ${updated.moved_to.day_name.toLowerCase()}` +
            (updated.moved_to.next_week ? ' della settimana prossima' : '')
        );
      }
      if (updated.pantry_used?.length) {
        addToast(scalatiDallaDispensa(updated.pantry_used), 'info');
      } else if (followed && updated.pantry_skipped?.length) {
        addToast(nonScalatiDallaDispensa(updated.pantry_skipped), 'info');
      }
      onChanged();
    } catch (e) {
      addToast(e.message, 'error');
    } finally {
      setSegnando(null);
    }
  };

  const totali = todayTotals(meals);
  const micro = dettagli ? dettagliMangiati(meals) : [];
  // Il pasto che viene adesso è l'unico messo in evidenza: è quello per cui si è
  // aperta l'app, e in una fila di card tutte uguali si perdeva fra le altre. È il
  // primo della giornata che ha una ricetta e su cui non si è ancora detto niente —
  // quelli già segnati sono storia, e una casella vuota non è un piatto. Solo oggi:
  // in un altro giorno «adesso» non c'è.
  const adesso = conAdesso
    ? meals.find((m) => m.recipe && !m.is_skipped && m.is_followed === null)
    : null;

  return (
    <>
      {meals.length > 0 && (
        <div className="day-summary">
          {/* Il numero grande è quello che si è mangiato davvero, solo coi pasti
              segnati e coi loro valori (un pranzo da 700 conta 700 anche se la
              dieta ne chiedeva 500); il piano della giornata va sotto, piccolo. */}
          <div className="day-summary-top">
            <strong>{formatNumber(totali.mangiato.calories)}</strong>
            <span>
              / {formatNumber(totali.target)} kcal
              <br />
              {totali.stime > 0 ? 'mangiate, con le stime' : 'mangiate'}
            </span>
          </div>
          <MacroBar
            className="macro-holder"
            protein={totali.mangiato.protein_g}
            carbs={totali.mangiato.carbs_g}
            fat={totali.mangiato.fat_g}
            legend
          />
          <span className="day-summary-tracked">
            {totali.segnati} di {meals.length} segnati · in programma{' '}
            {formatNumber(totali.calories)} kcal
          </span>
        </div>
      )}

      {/* Il resto della giornata in due righe piccole: i macro mangiati contro quelli
          che la dieta chiede, e le voci oltre ai macro (fibre, zuccheri...). Solo nel
          riepilogo di un giorno: sulla home basta il numero grande. */}
      {dettagli && meals.length > 0 && (
        <div className="day-extra">
          <span>
            Proteine {formatNumber(totali.mangiato.protein_g)} / {formatNumber(totali.target_protein_g)} g
            {' · '}Carboidrati {formatNumber(totali.mangiato.carbs_g)} /{' '}
            {formatNumber(totali.target_carbs_g)} g
            {' · '}Grassi {formatNumber(totali.mangiato.fat_g)} / {formatNumber(totali.target_fat_g)} g
          </span>
          {micro.length > 0 && (
            <span title={micro.some((v) => v.parziale) ? PARZIALE : undefined}>
              {micro
                .map(
                  (v) =>
                    `${v.label} ${v.parziale ? '≥ ' : ''}${formatNumber(
                      v.valore,
                      v.unit === 'mg' ? 0 : 1
                    )} ${v.unit}`
                )
                .join(' · ')}
            </span>
          )}
        </div>
      )}

      {meals.length === 0 ? (
        vuoto
      ) : (
        <div className="today-grid">
          {meals.map((meal) =>
            telefono && !(adesso && adesso.meal_id === meal.meal_id) ? (
              <MealRow key={meal.meal_id} meal={meal} />
            ) : (
            <div
              key={meal.meal_id}
              className={`card today-card ${meal.is_skipped ? 'skipped' : ''} ${
                meal.is_followed === true ? 'followed' : ''
              } ${adesso && adesso.meal_id === meal.meal_id ? 'adesso' : ''}`}
            >
              <div className="meal-slot">
                <span className="meal-slot-name">
                  {meal.slot_name}
                  {adesso && adesso.meal_id === meal.meal_id && ' · adesso'}
                </span>
                {/* Il cappello dice che quel pasto lo prepari tu — è lo stesso
                    segno della griglia della settimana. Distinguerli basta: la
                    giornata è una sola, e un pasto che mangi conta come gli
                    altri, quindi va segnato come gli altri. */}
                {meal.self_managed && (
                  <ChefHat className="meal-mark mine" aria-label="Lo prepari tu" />
                )}
                {meal.is_followed === true && (
                  <span className="slot-state" title="L'hai seguito">
                    <Check />
                  </span>
                )}
                {meal.is_skipped && (
                  <span className="slot-state moved" title="Hai mangiato altro">
                    <X />
                  </span>
                )}
              </div>

              {meal.recipe ? (
                <>
                  {/* Il piatto non ha una fotografia: al suo posto un
                      segnaposto dichiarato, che tiene il posto all'immagine
                      senza far sembrare rotta la card finché non c'è. */}
                  <Link
                    className="dish"
                    to={`/meals/${meal.meal_id}`}
                    aria-label={meal.recipe.title}
                  >
                    <UtensilsCrossed />
                  </Link>
                  {/* `title` perché il nome tagliato dall'ellissi resta leggibile
                      passandoci sopra, senza aprire il pasto. */}
                  <div
                    className="today-card-title"
                    title={meal.recipe.title}
                    onClick={() => navigate(`/meals/${meal.meal_id}`)}
                  >
                    {meal.recipe.title}
                  </div>
                  <div className="today-card-foot">
                    <span className="meal-facts">
                      {altroMangiato(meal)
                        ? altroMangiato(meal).niente
                          ? 'non hai mangiato niente · 0 kcal'
                          : altroMangiato(meal).kcal != null
                            ? `al suo posto ≈ ${altroMangiato(meal).kcal} kcal: ${altroMangiato(meal).testo}`
                            : 'hai mangiato altro: non stimato'
                        : `${meal.recipe.calories} kcal`}{' '}
                      · target {meal.target_calories} ·{' '}
                      {meal.recipe.prep_time_min + meal.recipe.cook_time_min} min
                    </span>
                    <div className="today-card-actions">
                      <button
                        className={`btn btn-sm ${
                          meal.is_followed === true ? 'btn-primary' : 'btn-secondary'
                        }`}
                        onClick={() => markFollowed(meal.meal_id, true)}
                      >
                        <Check size={14} /> L&rsquo;ho mangiato
                      </button>
                      <button
                        className={`btn btn-sm btn-icon ${
                          meal.is_followed === false ? 'btn-moved' : 'btn-secondary'
                        }`}
                        title="Ho mangiato altro"
                        onClick={() => markFollowed(meal.meal_id, false)}
                      >
                        <X size={15} />
                      </button>
                      <Link
                        className="btn btn-sm btn-secondary btn-icon"
                        title="Apri il pasto"
                        to={`/meals/${meal.meal_id}`}
                      >
                        <MessageCircle size={15} />
                      </Link>
                    </div>
                  </div>
                </>
              ) : meal.self_managed ? (
                /* Non è una casella vuota da riempire: è un pasto che hai già
                   risolto per conto tuo. Non ha una ricetta e non ne avrà una,
                   ma lo mangi — quindi le due risposte ci vogliono uguali, e
                   contano nella giornata e nell'aderenza come tutte le altre. */
                <>
                  {/* Il segnaposto non è tratteggiato come quello di una
                      casella vuota: qui non manca niente da riempire, il pasto
                      c'è e lo cucini tu. */}
                  <Link className="dish mio" to={`/meals/${meal.meal_id}`} aria-label="Lo prepari tu">
                    <ChefHat />
                  </Link>
                  <div className="today-card-title">Lo prepari tu</div>
                  <div className="today-card-foot">
                    <span className="meal-facts">{meal.target_calories} kcal · lo fai tu</span>
                    <div className="today-card-actions">
                      <button
                        className={`btn btn-sm ${
                          meal.is_followed === true ? 'btn-primary' : 'btn-secondary'
                        }`}
                        onClick={() => markFollowed(meal.meal_id, true)}
                      >
                        <Check size={14} /> L&rsquo;ho mangiato
                      </button>
                      <button
                        className={`btn btn-sm btn-icon ${
                          meal.is_followed === false ? 'btn-moved' : 'btn-secondary'
                        }`}
                        title="Ho mangiato altro"
                        onClick={() => markFollowed(meal.meal_id, false)}
                      >
                        <X size={15} />
                      </button>
                      <Link
                        className="btn btn-sm btn-secondary btn-icon"
                        title="Apri il pasto"
                        to={`/meals/${meal.meal_id}`}
                      >
                        <MessageCircle size={15} />
                      </Link>
                    </div>
                  </div>
                </>
              ) : (
                <>
                  <Link
                    className="dish vuoto"
                    to={`/meals/${meal.meal_id}`}
                    aria-label="Scegli cosa mangiare"
                  >
                    <UtensilsCrossed />
                  </Link>
                  <div className="today-card-title vuoto">Ancora niente</div>
                  <div className="today-card-foot">
                    <span className="meal-facts">target {meal.target_calories} kcal</span>
                    <div className="today-card-actions">
                      <Link className="btn btn-sm btn-secondary" to={`/meals/${meal.meal_id}`}>
                        Scegli cosa mangiare
                      </Link>
                    </div>
                  </div>
                </>
              )}
            </div>
            )
          )}
        </div>
      )}

      {altro && (
        <EatenInsteadDialog meal={altro} onSaved={() => onChanged()} onClose={() => setAltro(null)} />
      )}
    </>
  );
}

const BASE = '/api';

// Chiamato quando la sessione è irrecuperabile: l'AuthContext ci aggancia il logout.
let onSessionExpired = null;
export const setSessionExpiredHandler = (fn) => {
  onSessionExpired = fn;
};

// Su questi un 401 è una risposta legittima (credenziali sbagliate, sessione assente),
// non un access token scaduto: ritentare col refresh non avrebbe senso, e su /refresh
// stesso creerebbe un ciclo infinito.
const NO_REFRESH_RETRY = ['/auth/login', '/auth/refresh', '/auth/logout'];

async function raw(path, options = {}, allowRefresh = true) {
  const res = await fetch(`${BASE}${path}`, {
    // I cookie di sessione sono httpOnly: il browser li allega da solo, JS non li vede.
    credentials: 'same-origin',
    ...options,
  });

  // L'access token dura 30 minuti, il refresh 90 giorni: senza questo rientro
  // l'utente verrebbe buttato fuori ogni mezz'ora pur avendo una sessione valida.
  if (res.status === 401 && allowRefresh && !NO_REFRESH_RETRY.includes(path)) {
    const refreshed = await fetch(`${BASE}/auth/refresh`, {
      method: 'POST',
      credentials: 'same-origin',
    });
    if (refreshed.ok) return raw(path, options, false); // un solo tentativo
    onSessionExpired?.();
    throw new Error('Sessione scaduta');
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Errore ${res.status}`);
  }
  return res;
}

async function request(path, options = {}) {
  const res = await raw(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (res.status === 204) return null;
  return res.json();
}

// Upload multipart: niente Content-Type a mano, lo scrive il browser col boundary.
async function upload(path, file) {
  const form = new FormData();
  form.append('file', file);
  const res = await raw(path, { method: 'POST', body: form });
  return res.json();
}

async function text(path) {
  const res = await raw(path);
  return res.text();
}

export const api = {
  // ── Auth ──
  login: (email, password) =>
    request('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) }),

  logout: () => request('/auth/logout', { method: 'POST' }),

  me: () => request('/auth/me'),

  setApiKey: (api_key) =>
    request('/auth/api-key', { method: 'PUT', body: JSON.stringify({ api_key }) }),

  deleteApiKey: () => request('/auth/api-key', { method: 'DELETE' }),

  changePassword: (current_password, new_password) =>
    request('/auth/change-password', {
      method: 'POST',
      body: JSON.stringify({ current_password, new_password }),
    }),

  // ── Dieta ──
  getDiet: () => request('/diet/current'),

  uploadDiet: (file) => upload('/diet/upload', file),

  createDietManually: (meals) =>
    request('/diet/manual', { method: 'POST', body: JSON.stringify({ meals }) }),

  updateDietMeals: (dietId, meals) =>
    request(`/diet/${dietId}/meals`, { method: 'PUT', body: JSON.stringify({ meals }) }),

  // ── Configurazione ──
  getBaseIngredients: () => request('/config/base-ingredients'),

  addBaseIngredient: (ingredient_name) =>
    request('/config/base-ingredients', {
      method: 'POST',
      body: JSON.stringify({ ingredient_name }),
    }),

  addDefaultBaseIngredients: () =>
    request('/config/base-ingredients/defaults', { method: 'POST' }),

  removeBaseIngredient: (id) =>
    request(`/config/base-ingredients/${id}`, { method: 'DELETE' }),

  getExcluded: () => request('/config/excluded'),

  addExcluded: (ingredient_name, reason) =>
    request('/config/excluded', {
      method: 'POST',
      body: JSON.stringify({ ingredient_name, reason }),
    }),

  removeExcluded: (id) => request(`/config/excluded/${id}`, { method: 'DELETE' }),

  getPantry: () => request('/config/pantry'),

  addPantryItem: (payload) =>
    request('/config/pantry', { method: 'POST', body: JSON.stringify(payload) }),

  updatePantryItem: (id, payload) =>
    request(`/config/pantry/${id}`, { method: 'PUT', body: JSON.stringify(payload) }),

  removePantryItem: (id) => request(`/config/pantry/${id}`, { method: 'DELETE' }),

  getPreferences: () => request('/config/preferences'),

  updatePreferences: (payload) =>
    request('/config/preferences', { method: 'PUT', body: JSON.stringify(payload) }),

  searchIngredients: (q) =>
    request(`/config/ingredients/search?q=${encodeURIComponent(q)}`),

  // ── Modelli AI ──
  getAiConfig: () => request('/config/ai'),

  getAiModels: (q = '') => request(`/config/ai/models?q=${encodeURIComponent(q)}`),

  updateAiModels: (payload) =>
    request('/config/ai/models', { method: 'PUT', body: JSON.stringify(payload) }),

  // ── Pianificazione ──
  getCurrentWeek: () => request('/planning/weeks/current'),

  getNextWeek: () => request('/planning/weeks/next'),

  // Di default riempie solo le caselle vuote; regenerateAll rifà tutta la settimana
  // (una chiamata al modello su tutti i pasti: la UI la fa confermare).
  generateWeek: (weekId, regenerateAll = false) =>
    request(
      `/planning/weeks/${weekId}/generate${regenerateAll ? '?regenerate_all=true' : ''}`,
      { method: 'POST' }
    ),

  lockWeek: (weekId) => request(`/planning/weeks/${weekId}/lock`, { method: 'POST' }),

  unlockWeek: (weekId) => request(`/planning/weeks/${weekId}/unlock`, { method: 'POST' }),

  getMeal: (mealId) => request(`/planning/meals/${mealId}`),

  regenerateMeal: (mealId) =>
    request(`/planning/meals/${mealId}/regenerate`, { method: 'POST' }),

  assignMeal: (mealId, payload) =>
    request(`/planning/meals/${mealId}/assign`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),

  clearMeal: (mealId) => request(`/planning/meals/${mealId}/recipe`, { method: 'DELETE' }),

  setRecurring: (mealId, is_recurring, recurring_rule = null) =>
    request(`/planning/meals/${mealId}/recurring`, {
      method: 'PUT',
      body: JSON.stringify({ is_recurring, recurring_rule }),
    }),

  setFollowed: (mealId, is_followed, deviation_notes = null) =>
    request(`/planning/meals/${mealId}/followed`, {
      method: 'PUT',
      body: JSON.stringify({ is_followed, deviation_notes }),
    }),

  // Salta l'intera giornata: le ricette si accodano ai giorni successivi.
  setDaySkipped: (dayId, is_skipped) =>
    request(`/planning/days/${dayId}/skip`, {
      method: 'PUT',
      body: JSON.stringify({ is_skipped }),
    }),

  // ── Ricette ──
  getRecipes: (params = {}) => {
    const qs = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== null && v !== undefined && v !== '')
    ).toString();
    return request(`/recipes${qs ? `?${qs}` : ''}`);
  },

  getRecipe: (id) => request(`/recipes/${id}`),

  createRecipe: (payload) =>
    request('/recipes', { method: 'POST', body: JSON.stringify(payload) }),

  rateRecipe: (id, rating) =>
    request(`/recipes/${id}/rate`, { method: 'PUT', body: JSON.stringify({ rating }) }),

  favoriteRecipe: (id, is_favorite) =>
    request(`/recipes/${id}/favorite`, {
      method: 'PUT',
      body: JSON.stringify({ is_favorite }),
    }),

  deleteRecipe: (id) => request(`/recipes/${id}`, { method: 'DELETE' }),

  substituteIngredient: (id, ingredient_to_replace, reason) =>
    request(`/recipes/${id}/substitute`, {
      method: 'POST',
      body: JSON.stringify({ ingredient_to_replace, reason }),
    }),

  // ── Chat per pasto ──
  getChat: (mealId) => request(`/chat/meals/${mealId}/messages`),

  sendChat: (mealId, content) =>
    request(`/chat/meals/${mealId}/messages`, {
      method: 'POST',
      body: JSON.stringify({ content }),
    }),

  clearChat: (mealId) => request(`/chat/meals/${mealId}/messages`, { method: 'DELETE' }),

  // ── Spesa ──
  getShoppingList: (which = 'current') => request(`/shopping/${which}`),

  checkShoppingItem: (itemId, is_checked) =>
    request(`/shopping/items/${itemId}/check`, {
      method: 'PUT',
      body: JSON.stringify({ is_checked }),
    }),

  completeShopping: (which = 'current') =>
    request(`/shopping/${which}/complete`, { method: 'POST' }),

  exportShoppingList: (which = 'current') => text(`/shopping/export?which=${which}`),

  // ── Tracking ──
  getTracking: (weekStartDate) =>
    request(`/tracking/weekly${weekStartDate ? `?week_start_date=${weekStartDate}` : ''}`),

  getWeeks: () => request('/tracking/weeks'),

  getDashboard: () => request('/tracking/dashboard'),
};

// ── Formattatori condivisi ──

export const formatDate = (iso, options = { day: 'numeric', month: 'long' }) =>
  new Date(iso).toLocaleDateString('it-IT', options);

export const formatMoney = (value) =>
  value == null ? null : `€ ${value.toFixed(2).replace('.', ',')}`;

export const formatNumber = (value, digits = 0) =>
  value == null ? '—' : Number(value).toFixed(digits).replace('.', ',');

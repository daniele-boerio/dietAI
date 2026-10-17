import { afterEach, describe, expect, it, vi } from 'vitest';
import { api, setSessionExpiredHandler } from './api';

const json = (status, body = {}) =>
  Promise.resolve(new Response(JSON.stringify(body), { status }));

// Un server finto: le rotte normali rispondono 401 finché non c'è stato un refresh.
function server({ refreshStatus = 200 } = {}) {
  const stato = { rinnovata: false, refresh: 0 };
  globalThis.fetch = vi.fn((url) => {
    if (url.endsWith('/auth/refresh')) {
      stato.refresh += 1;
      if (refreshStatus === 200) stato.rinnovata = true;
      return json(refreshStatus);
    }
    return stato.rinnovata ? json(200, { ok: url }) : json(401);
  });
  return stato;
}

afterEach(() => {
  setSessionExpiredHandler(null);
  vi.restoreAllMocks();
});

describe('refresh della sessione', () => {
  it('le richieste parallele aspettano un solo refresh', async () => {
    const stato = server();
    const scaduta = vi.fn();
    setSessionExpiredHandler(scaduta);

    await Promise.all([api.me(), api.getDashboard(), api.me()]);

    expect(stato.refresh).toBe(1);
    expect(scaduta).not.toHaveBeenCalled();
  });

  it('un refresh rifiutato riporta al login', async () => {
    server({ refreshStatus: 401 });
    const scaduta = vi.fn();
    setSessionExpiredHandler(scaduta);

    await expect(api.me()).rejects.toThrow('Sessione scaduta');
    expect(scaduta).toHaveBeenCalledOnce();
  });

  it('un server giù non butta fuori chi ha una sessione valida', async () => {
    server({ refreshStatus: 502 });
    const scaduta = vi.fn();
    setSessionExpiredHandler(scaduta);

    await expect(api.me()).rejects.toThrow('Server non raggiungibile');
    expect(scaduta).not.toHaveBeenCalled();
  });
});

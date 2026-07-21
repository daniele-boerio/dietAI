import { useState } from 'react';
import { Sprout } from 'lucide-react';
import { useAuth } from '../AuthContext';

export default function LoginPage() {
  const { login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError('');
    setBusy(true);
    try {
      await login(email.trim().toLowerCase(), password);
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  return (
    <div className="auth-layout">
      <form className="auth-card" onSubmit={submit}>
        <div className="auth-logo">
          <Sprout size={26} />
          DietAI
        </div>
        <p className="auth-subtitle">
          La tua dieta, tradotta in ricette e in una lista della spesa.
        </p>

        {error && <div className="auth-error">{error}</div>}

        <div className="field">
          <label className="field-label" htmlFor="email">
            Email
          </label>
          <input
            id="email"
            type="email"
            autoComplete="username"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </div>

        <div className="field">
          <label className="field-label" htmlFor="password">
            Password
          </label>
          <input
            id="password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </div>

        <button className="btn btn-primary btn-block" type="submit" disabled={busy}>
          {busy && <span className="spinner-inline" />}
          Entra
        </button>
      </form>
    </div>
  );
}

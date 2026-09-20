import { useState, type FormEvent } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { ApiError } from '../api/client';
import Disclaimer from '../components/Disclaimer';
import { useAuth } from '../hooks/useAuth';
import { useToasts } from '../hooks/useToasts';

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const { push } = useToasts();
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const from = (location.state as { from?: string } | null)?.from ?? '/detect';

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(identifier.trim(), password);
      push('登录成功', 'success');
      navigate(from, { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '登录失败，请稍后重试');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="mx-auto max-w-md space-y-5 py-4">
      <div className="card p-6">
        <h1 className="text-xl font-bold text-slate-900">登录</h1>
        <p className="mt-1 text-sm text-slate-600">使用邮箱或用户名登录以进行检测并查看历史记录。</p>

        <form className="mt-6 space-y-4" onSubmit={onSubmit} noValidate>
          <div>
            <label className="label" htmlFor="identifier">
              邮箱或用户名
            </label>
            <input
              id="identifier"
              name="identifier"
              className="input"
              autoComplete="username"
              required
              value={identifier}
              onChange={(event) => setIdentifier(event.target.value)}
              data-testid="login-identifier"
            />
          </div>
          <div>
            <label className="label" htmlFor="password">
              密码
            </label>
            <input
              id="password"
              name="password"
              type="password"
              className="input"
              autoComplete="current-password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              data-testid="login-password"
            />
          </div>

          {error && (
            <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700" data-testid="login-error">
              {error}
            </p>
          )}

          <button type="submit" className="btn-primary w-full" disabled={submitting} data-testid="login-submit">
            {submitting ? '登录中…' : '登录'}
          </button>
        </form>

        <p className="mt-4 text-center text-sm text-slate-600">
          还没有账号？{' '}
          <Link to="/register" className="font-semibold text-brand-700 hover:underline">
            立即注册
          </Link>
        </p>
      </div>
      <Disclaimer variant="compact" />
    </div>
  );
}

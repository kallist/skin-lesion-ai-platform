import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ApiError } from '../api/client';
import Disclaimer from '../components/Disclaimer';
import { useAuth } from '../hooks/useAuth';
import { useToasts } from '../hooks/useToasts';

export default function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const { push } = useToasts();
  const [form, setForm] = useState({
    email: '',
    username: '',
    password: '',
    confirm: '',
    full_name: '',
  });
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const update = (key: keyof typeof form) => (event: React.ChangeEvent<HTMLInputElement>) =>
    setForm((current) => ({ ...current, [key]: event.target.value }));

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);

    if (form.password !== form.confirm) {
      setError('两次输入的密码不一致');
      return;
    }
    if (form.password.length < 8) {
      setError('密码长度至少需要 8 个字符');
      return;
    }

    setSubmitting(true);
    try {
      await register({
        email: form.email.trim(),
        username: form.username.trim(),
        password: form.password,
        full_name: form.full_name.trim() || undefined,
      });
      push('注册成功，已自动登录', 'success');
      navigate('/detect', { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '注册失败，请稍后重试');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="mx-auto max-w-md space-y-5 py-4">
      <div className="card p-6">
        <h1 className="text-xl font-bold text-slate-900">注册账号</h1>
        <p className="mt-1 text-sm text-slate-600">
          注册后即可上传图片进行检测，检测记录仅你自己可见。
        </p>

        <form className="mt-6 space-y-4" onSubmit={onSubmit} noValidate>
          <div>
            <label className="label" htmlFor="email">
              邮箱
            </label>
            <input
              id="email"
              type="email"
              className="input"
              autoComplete="email"
              required
              value={form.email}
              onChange={update('email')}
              data-testid="register-email"
            />
          </div>
          <div>
            <label className="label" htmlFor="username">
              用户名
            </label>
            <input
              id="username"
              className="input"
              autoComplete="username"
              required
              minLength={3}
              value={form.username}
              onChange={update('username')}
              data-testid="register-username"
            />
            <p className="mt-1 text-xs text-slate-500">3-64 个字符，可用字母、数字、下划线、点或短横线</p>
          </div>
          <div>
            <label className="label" htmlFor="full_name">
              昵称（可选）
            </label>
            <input
              id="full_name"
              className="input"
              autoComplete="name"
              value={form.full_name}
              onChange={update('full_name')}
            />
          </div>
          <div>
            <label className="label" htmlFor="password">
              密码
            </label>
            <input
              id="password"
              type="password"
              className="input"
              autoComplete="new-password"
              required
              value={form.password}
              onChange={update('password')}
              data-testid="register-password"
            />
            <p className="mt-1 text-xs text-slate-500">
              至少 8 位，且包含大小写字母、数字或符号中的至少两类
            </p>
          </div>
          <div>
            <label className="label" htmlFor="confirm">
              确认密码
            </label>
            <input
              id="confirm"
              type="password"
              className="input"
              autoComplete="new-password"
              required
              value={form.confirm}
              onChange={update('confirm')}
              data-testid="register-confirm"
            />
          </div>

          {error && (
            <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700" data-testid="register-error">
              {error}
            </p>
          )}

          <button type="submit" className="btn-primary w-full" disabled={submitting} data-testid="register-submit">
            {submitting ? '注册中…' : '注册并登录'}
          </button>
        </form>

        <p className="mt-4 text-center text-sm text-slate-600">
          已有账号？{' '}
          <Link to="/login" className="font-semibold text-brand-700 hover:underline">
            去登录
          </Link>
        </p>
      </div>
      <Disclaimer variant="compact" />
    </div>
  );
}

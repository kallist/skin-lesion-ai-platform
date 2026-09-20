import { useEffect, useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { api, ApiError } from '../api/client';
import ConfirmDialog from '../components/ConfirmDialog';
import Disclaimer from '../components/Disclaimer';
import { useAuth } from '../hooks/useAuth';
import { useToasts } from '../hooks/useToasts';
import type { ModelInfo } from '../types';
import { formatDateTime } from '../utils/format';

export default function ProfilePage() {
  const { user, setUser, logout } = useAuth();
  const { push } = useToasts();
  const navigate = useNavigate();
  const [fullName, setFullName] = useState(user?.full_name ?? '');
  const [username, setUsername] = useState(user?.username ?? '');
  const [saving, setSaving] = useState(false);
  const [model, setModel] = useState<ModelInfo | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    api
      .modelInfo()
      .then(setModel)
      .catch(() => setModel(null));
  }, []);

  const onSave = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    try {
      const updated = await api.updateProfile({
        full_name: fullName.trim() || null,
        username: username.trim() || undefined,
      });
      setUser(updated);
      push('个人信息已更新', 'success');
    } catch (err) {
      push(err instanceof ApiError ? err.message : '更新失败', 'error');
    } finally {
      setSaving(false);
    }
  };

  const onDelete = async () => {
    setDeleting(true);
    try {
      await api.deleteAccount();
      await logout();
      push('账号已删除', 'success');
      navigate('/', { replace: true });
    } catch (err) {
      push(err instanceof ApiError ? err.message : '删除账号失败', 'error');
    } finally {
      setDeleting(false);
      setConfirmOpen(false);
    }
  };

  if (!user) return null;

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold text-slate-900">个人信息</h1>
        <p className="mt-1 text-sm text-slate-600">管理账号基本信息，或删除账号与全部检测数据。</p>
      </header>

      <div className="grid gap-6 lg:grid-cols-2 lg:items-start">
        <section className="card p-5" aria-labelledby="profile-heading">
          <h2 id="profile-heading" className="text-base font-semibold text-slate-900">
            账号资料
          </h2>
          <form className="mt-4 space-y-4" onSubmit={onSave}>
            <div>
              <label className="label" htmlFor="profile-email">
                邮箱（不可修改）
              </label>
              <input id="profile-email" className="input bg-slate-100" value={user.email} readOnly />
            </div>
            <div>
              <label className="label" htmlFor="profile-username">
                用户名
              </label>
              <input
                id="profile-username"
                className="input"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                data-testid="profile-username"
              />
            </div>
            <div>
              <label className="label" htmlFor="profile-fullname">
                昵称
              </label>
              <input
                id="profile-fullname"
                className="input"
                value={fullName}
                onChange={(event) => setFullName(event.target.value)}
                placeholder="可留空"
                data-testid="profile-fullname"
              />
            </div>
            <div className="rounded-lg bg-slate-50 p-3 text-xs text-slate-600">
              <p>注册时间：{formatDateTime(user.created_at)}</p>
              <p>最近更新：{formatDateTime(user.updated_at)}</p>
            </div>
            <button type="submit" className="btn-primary" disabled={saving} data-testid="profile-save">
              {saving ? '保存中…' : '保存修改'}
            </button>
          </form>
        </section>

        <div className="space-y-6">
          <section className="card p-5" aria-labelledby="model-heading">
            <h2 id="model-heading" className="text-base font-semibold text-slate-900">
              当前模型信息
            </h2>
            {model ? (
              <dl className="mt-3 space-y-2 text-sm">
                <div className="flex justify-between gap-3">
                  <dt className="text-slate-500">模型版本</dt>
                  <dd className="break-all text-right font-medium text-slate-800">{model.model_version}</dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="text-slate-500">网络结构</dt>
                  <dd className="font-medium text-slate-800">{model.architecture}</dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="text-slate-500">输入尺寸</dt>
                  <dd className="font-medium text-slate-800">{model.input_size} × {model.input_size}</dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="text-slate-500">推理设备</dt>
                  <dd className="font-medium text-slate-800">{model.device}</dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="text-slate-500">概率校准</dt>
                  <dd className="font-medium text-slate-800">{model.calibration}</dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="text-slate-500">服务状态</dt>
                  <dd className={`font-medium ${model.available ? 'text-risk-low' : 'text-risk-high'}`}>
                    {model.available ? '可用' : '不可用'}
                  </dd>
                </div>
              </dl>
            ) : (
              <p className="mt-3 text-sm text-slate-500">模型信息暂时无法获取。</p>
            )}
          </section>

          <section className="card border-red-200 p-5" aria-labelledby="danger-heading">
            <h2 id="danger-heading" className="text-base font-semibold text-red-700">
              危险操作
            </h2>
            <p className="mt-1 text-sm text-slate-600">
              删除账号会同时删除全部检测记录和已加密存储的图片，且不可恢复。
            </p>
            <button
              type="button"
              className="btn-danger mt-3"
              onClick={() => setConfirmOpen(true)}
              data-testid="delete-account-button"
            >
              删除我的账号
            </button>
          </section>
        </div>
      </div>

      <Disclaimer variant="compact" />

      <ConfirmDialog
        open={confirmOpen}
        title="确认删除账号？"
        description="该操作会永久删除你的账号、全部检测记录以及加密存储的皮肤图片。"
        confirmLabel="永久删除"
        danger
        busy={deleting}
        onConfirm={onDelete}
        onCancel={() => setConfirmOpen(false)}
      />
    </div>
  );
}

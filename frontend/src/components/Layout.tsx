import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { useState } from 'react';
import ToastHost from './ToastHost';
import { useToasts } from '../hooks/useToasts';

const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  `rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
    isActive ? 'bg-brand-50 text-brand-700' : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
  }`;

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);
  const { toasts, push, dismiss } = useToasts();

  const handleLogout = async () => {
    await logout();
    push('已安全退出登录', 'success');
    navigate('/');
  };

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/95 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3">
          <Link to="/" className="flex items-center gap-2" aria-label="返回首页">
            <span
              aria-hidden="true"
              className="grid h-9 w-9 place-items-center rounded-xl bg-brand-600 text-lg font-bold text-white"
            >
              ✚
            </span>
            <span className="leading-tight">
              <span className="block text-sm font-bold text-slate-900">皮肤病变智能识别</span>
              <span className="block text-[11px] font-medium uppercase tracking-wide text-brand-600">
                Skin Lesion AI Platform
              </span>
            </span>
          </Link>

          <button
            type="button"
            className="btn-secondary md:hidden"
            aria-expanded={menuOpen}
            aria-controls="primary-navigation"
            onClick={() => setMenuOpen((open) => !open)}
          >
            菜单
          </button>

          <nav
            id="primary-navigation"
            aria-label="主导航"
            className={`${menuOpen ? 'flex' : 'hidden'} absolute left-0 right-0 top-full flex-col gap-1 border-b border-slate-200 bg-white p-3 md:static md:flex md:flex-row md:items-center md:gap-1 md:border-0 md:bg-transparent md:p-0`}
          >
            {user && (
              <>
                <NavLink to="/detect" className={navLinkClass} onClick={() => setMenuOpen(false)}>
                  AI 智能检测
                </NavLink>
                <NavLink to="/history" className={navLinkClass} onClick={() => setMenuOpen(false)}>
                  检测档案
                </NavLink>
                <NavLink to="/compare" className={navLinkClass} onClick={() => setMenuOpen(false)}>
                  结果对比
                </NavLink>
              </>
            )}
            <NavLink to="/about" className={navLinkClass} onClick={() => setMenuOpen(false)}>
              关于
            </NavLink>
            <NavLink to="/evaluation" className={navLinkClass} onClick={() => setMenuOpen(false)}>
              模型评测
            </NavLink>

            {user ? (
              <div className="mt-2 flex items-center gap-2 md:mt-0 md:ml-2">
                <NavLink to="/profile" className={navLinkClass} onClick={() => setMenuOpen(false)}>
                  {user.username}
                </NavLink>
                <button type="button" className="btn-secondary" onClick={handleLogout}>
                  退出
                </button>
              </div>
            ) : (
              <div className="mt-2 flex items-center gap-2 md:mt-0 md:ml-2">
                <Link to="/login" className="btn-secondary" onClick={() => setMenuOpen(false)}>
                  登录
                </Link>
                <Link to="/register" className="btn-primary" onClick={() => setMenuOpen(false)}>
                  注册
                </Link>
              </div>
            )}
          </nav>
        </div>
      </header>

      <main id="main" className="mx-auto w-full max-w-6xl flex-1 px-4 py-6">
        <Outlet />
      </main>

      <footer className="border-t border-slate-200 bg-white">
        <div className="mx-auto max-w-6xl px-4 py-6 text-xs leading-relaxed text-slate-500">
          <p className="font-semibold text-slate-700">
            本系统仅作为皮肤健康辅助自检工具，检测结果仅供参考，不能替代专业医生诊断。
          </p>
          <p className="mt-1">
            模型输出为统计意义上的倾向判断，<strong>模型置信度并不等同于真实临床患病概率</strong>。
            如有疑虑请及时就医。
          </p>
          <p className="mt-2">
            © {new Date().getFullYear()} Skin Lesion AI Platform · 皮肤病变智能识别与辅助分析平台
            <span className="block">
              校企联合 AI 应用实习实践项目，由广州泰迪智能科技有限公司相关人员参与指导与实践。
            </span>
          </p>
        </div>
      </footer>

      <ToastHost toasts={toasts} onDismiss={dismiss} />
    </div>
  );
}

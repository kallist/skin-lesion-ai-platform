import { Link } from 'react-router-dom';

export default function NotFoundPage() {
  return (
    <div className="card mx-auto max-w-md p-10 text-center">
      <span aria-hidden="true" className="text-4xl">
        🧭
      </span>
      <h1 className="mt-3 text-xl font-bold text-slate-900">页面不存在</h1>
      <p className="mt-1 text-sm text-slate-600">你访问的页面可能已被移动或删除。</p>
      <Link to="/" className="btn-primary mt-5">
        返回首页
      </Link>
    </div>
  );
}

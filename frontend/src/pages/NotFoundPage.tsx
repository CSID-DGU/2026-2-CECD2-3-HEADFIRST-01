import { Link } from 'react-router-dom'

export function NotFoundPage() {
  return (
    <div className="py-24 text-center">
      <p className="text-sm font-semibold text-brand-600">404</p>
      <h1 className="mt-2 text-2xl font-bold text-slate-900">페이지를 찾을 수 없습니다</h1>
      <Link
        to="/"
        className="mt-6 inline-block rounded-lg bg-brand-700 px-4 py-2 text-sm font-medium text-white hover:bg-brand-800"
      >
        상담 데모로 돌아가기
      </Link>
    </div>
  )
}

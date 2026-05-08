import Link from 'next/link'

export default function NotFound() {
  return (
    <div className="mx-auto flex min-h-[60vh] w-full max-w-[640px] flex-col items-center justify-center gap-4 px-6 py-24 text-center">
      <p className="text-sm font-medium uppercase tracking-wider text-[#A3A3A3]">
        404
      </p>
      <h1 className="text-2xl font-semibold text-[#1a1a1a]">
        页面未找到
        <span className="ml-2 text-base font-normal text-[#737373]">
          Page not found
        </span>
      </h1>
      <p className="text-sm text-[#737373]">
        你访问的内容可能已被移除、链接错误，或该 Help Center 尚未对外发布。
      </p>
      <Link
        href="/"
        className="mt-2 inline-flex h-10 items-center rounded-lg bg-[#1a1a1a] px-5 text-sm font-medium text-white transition-colors hover:bg-[#333]"
      >
        返回首页
      </Link>
    </div>
  )
}

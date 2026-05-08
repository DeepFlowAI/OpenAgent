/**
 * AGPLv3 §13 source-availability notice.
 *
 * AGPL §13 requires that users interacting with a modified version of the
 * program through a network be offered an opportunity to receive the
 * Corresponding Source. Rendering a small, persistent attribution link in
 * every page's footer satisfies that obligation.
 *
 * Override the link target via `NEXT_PUBLIC_SOURCE_URL` to point at the
 * specific fork/branch that's actually running in production.
 */
const SOURCE_URL =
  process.env.NEXT_PUBLIC_SOURCE_URL ||
  'https://github.com/DeepFlowAI/OpenAgent'

export default function SourceAttribution() {
  return (
    <div
      role="contentinfo"
      className="pointer-events-none fixed bottom-1 left-1/2 z-[1] -translate-x-1/2 select-none text-[10px] leading-none text-slate-400/80 dark:text-slate-500/80 print:hidden"
      aria-label="open source attribution"
    >
      <a
        href={SOURCE_URL}
        target="_blank"
        rel="noopener noreferrer"
        className="pointer-events-auto hover:underline"
      >
        OpenAgent · AGPL-3.0 · Source code
      </a>
    </div>
  )
}

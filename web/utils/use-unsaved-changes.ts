'use client'

import { useEffect } from 'react'

/**
 * Warn the user before they close / refresh / navigate away while a form has
 * unsaved changes. Modern browsers ignore the custom message and show their
 * own; we only need to call `event.preventDefault()` and set `returnValue`.
 *
 * In-app `<Link>` navigation cannot be intercepted reliably from this hook
 * alone, so detail pages should additionally guard their own "Back" button
 * with a ConfirmModal when `dirty === true`.
 */
export function useUnsavedChangesGuard(dirty: boolean): void {
  useEffect(() => {
    if (!dirty) return

    const handler = (event: BeforeUnloadEvent) => {
      event.preventDefault()
      event.returnValue = ''
    }

    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [dirty])
}

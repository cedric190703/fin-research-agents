import { useEffect, useRef, useState } from 'react'
import { api, subscribeToRun } from '../lib/api'
import type { RunDetail, RunEvent } from '../lib/types'

/**
 * Loads a run and, while it is still running, follows its SSE stream. When the
 * stream closes the detail is re-fetched so `result` is populated.
 */
export function useRun(runId: string | null, onFinished?: (detail: RunDetail) => void) {
  const [detail, setDetail] = useState<RunDetail | null>(null)
  const [events, setEvents] = useState<RunEvent[]>([])
  // Kept in a ref so a new callback identity never tears down the subscription.
  const onFinishedRef = useRef(onFinished)
  useEffect(() => {
    onFinishedRef.current = onFinished
  }, [onFinished])

  useEffect(() => {
    if (!runId) return
    let cancelled = false
    let unsubscribe: (() => void) | undefined
    setDetail(null)
    setEvents([])

    void api.getRun(runId).then((d) => {
      if (cancelled) return
      setDetail(d)
      setEvents(d.events)
      if (d.status === 'queued' || d.status === 'running') {
        // Backlog is replayed by the server, so start from an empty list.
        setEvents([])
        unsubscribe = subscribeToRun(
          runId,
          (ev) => setEvents((prev) => [...prev, ev]),
          () => {
            void api.getRun(runId).then((final) => {
              if (cancelled) return
              setDetail(final)
              onFinishedRef.current?.(final)
            })
          },
        )
      }
    })
    return () => {
      cancelled = true
      unsubscribe?.()
    }
  }, [runId])

  return { detail, events }
}

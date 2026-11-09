// Live view of what gruntly's child (the local/small model) is doing while a `gruntly ...` Bash command runs.
// The parent (Claude) is already visible in the chat; this adds the child and gruntly's own steps under the command's row.
// Data: gruntly writes `.gruntly/runs/<id>/progress.jsonl` as the run goes; nothing here reaches the parent's context.
import { atom, read, update } from 'claude-code'
import type { Register } from 'claude-code'

import type { Row } from '../types'

const feeds = atom({ plugin: 'gruntly', key: 'feed' } as const, {}, { shape: 'feed-1' })

// `gruntly agent-run ...`, `gruntly run ...`, also through a path or gruntly.exe
const GRUNTLY = /(?:^|[\s;&|(])(?:[\w.:\\/~-]*[\\/])?gruntly(?:\.exe)?\s+(agent-run|run|do|continue|wait)\b/
const SHOWN_RUNNING = 8
const SHOWN_DONE = 3
const KEEP = 300

function body(r: Row): string {
  switch (r.k) {
    case 'tool':
      return `${r.kind === 'edit' ? 'edit' : r.kind === 'read' ? 'read' : r.kind === 'run' ? 'run ' : 'tool'} ${r.what || r.tool || ''}${r.ok === false ? '  (failed)' : ''}`
    case 'say':
      return `says: ${r.text ?? ''}`
    case 'step':
      return `model call done (${r.tokens_in ?? '?'} in, ${r.tokens_out ?? '?'} out)`
    case 'start':
      return `started: ${r.model ?? '?'} via ${r.harness ?? '?'}${r.provider ? ` on ${r.provider}` : ''}`
    case 'attempt':
      return `attempt ${r.n} started`
    case 'gates':
      return `checks: ${r.detail ?? (r.ok ? 'all passed' : 'failed')}`
    case 'wait':
      return `waiting ${r.secs}s (${r.why ?? 'rate limit'})`
    case 'done':
      return `finished: ${r.status}${r.reason ? ` (${r.reason})` : ''}`
    default:
      return r.k
  }
}

export const register: Register = on => {
  on('tool.call', { tool: 'Bash' }, async ($, e, next) => {
    if (!GRUNTLY.test(e.command)) {
      return next(e)
    }
    const id = e.tool_use_id
    const startedAt = await $.clock.now()
    let file: string | null = null
    let seen = 0
    let busy = false

    const poll = async () => {
      if (busy) {
        return
      }
      busy = true
      try {
        if (file === null) {
          const names = (await $.fs.list('.gruntly/runs'))
            .map(x => x.name)
            .filter(n => n.startsWith('r_'))
            .sort()
            .slice(-4)
            .reverse()
          for (const n of names) {
            const p = `.gruntly/runs/${n}/progress.jsonl`
            const st = await $.fs.stat(p).catch(() => null)
            if (st && st.mtimeMs >= startedAt - 2000) {
              file = p
              break
            }
          }
        }
        if (file === null) {
          return
        }
        const text = await $.fs.read(file)
        const rows: Row[] = []
        for (const line of text.split('\n').slice(seen)) {
          if (!line.trim().startsWith('{') || !line.trim().endsWith('}')) {
            break // a half-written line: take it next time
          }
          try {
            rows.push(JSON.parse(line) as Row)
          } catch {
            break
          }
          seen += 1
        }
        if (rows.length > 0) {
          await update($, feeds, all => ({
            ...all,
            [id]: [...(all[id] ?? []), ...rows].slice(-KEEP),
          }))
          const last = rows[rows.length - 1]
          $.ui.status(last.k === 'done' ? undefined : `${last.who}: ${body(last)}`.slice(0, 70))
        }
      } catch {
        // the run folder or file is not there yet
      } finally {
        busy = false
      }
    }

    const timer = $.clock.every(1000, poll)
    try {
      return await next(e)
    } finally {
      timer.cancel()
      await poll()
      $.ui.status(undefined)
    }
  }).catch(($, e, next) => next(e)) // a bug here must never block the gruntly command itself

  on('ui.render', { component: 'ToolUse', tool: 'Bash' }, async ($, e, next) => {
    const rows = (await read($, feeds))[e.tool_use_id]
    if (!rows || rows.length === 0) {
      return next(e)
    }
    const { Box, Text } = $.ui.resolve(e)
    const start = rows.find(r => r.k === 'start')
    const toolCalls = rows.filter(r => r.who === 'child' && r.k === 'tool').length
    const shown = rows.slice(e.isRunning ? -SHOWN_RUNNING : -SHOWN_DONE)

    return (
      <Box flexDirection="column">
        {await next(e)}
        <Text dimColor>
          {e.isRunning ? '  child (local model) working' : '  child (local model) finished'}
          {start?.model ? ` · ${start.model}` : ''} · {toolCalls} tool calls
        </Text>
        {shown.map((r, i) => (
          <Box key={`${r.t}-${i}`}>
            <Text color={r.who === 'child' ? 'cyan' : 'yellow'}>
              {r.who === 'child' ? '  ⟡ child   ' : '  ◆ gruntly '}
            </Text>
            <Text dimColor={r.k === 'say' || r.k === 'step'}>{body(r)}</Text>
          </Box>
        ))}
      </Box>
    )
  })
}

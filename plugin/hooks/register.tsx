// Live view of what gruntly's child (the local/small model) is doing while a `gruntly ...` Bash command runs.
// The parent (Claude) is already visible in the chat; this adds the child and gruntly's own steps under the command's row.
// Data: gruntly writes `.gruntly/runs/<id>/progress.jsonl` as the run goes; nothing here reaches the parent's context.
import { atom, read, update } from 'claude-code'
import type { Register } from 'claude-code'

import type { Mode, Row } from '../types'

const feeds = atom({ plugin: 'gruntly', key: 'feed' } as const, {}, { shape: 'feed-1' })
const modeAtom = atom({ plugin: 'gruntly', key: 'mode' } as const, { mode: 'auto', source: 'default' }, { shape: 'mode-1' })

// The switch: session beats project beats auto. The CLI (`gruntly mode`) reads and writes the same two files and is what
// enforces `off`; this module writes them for /gruntly and tells Claude the mode.
const MODES = ['auto', 'on', 'off']
const HINT_ON =
  'Gruntly mode is ON for this project: delegate every eligible change with `gruntly agent-run` without asking the person first ' +
  '(a bounded change where you can name the file, tests exist or the change is mechanical). Do design, security, and changes ' +
  'that need many files read first yourself. Follow the gruntly skill for how to brief it and check the diff.'
const HINT_OFF =
  'Gruntly mode is OFF: do all work yourself. Do not use gruntly (agent-run, run, do) in this chat; it will refuse anyway.'

async function rootPrefix($: any): Promise<string> {
  let prefix = ''
  for (let i = 0; i < 8; i++) {
    if (await $.fs.exists(`${prefix}.git`)) {
      return prefix
    }
    prefix += '../'
  }
  return ''
}

async function readMode($: any): Promise<{ mode: Mode; source: string }> {
  const root = await rootPrefix($)
  const sid = await $.session.id()
  const places: [string, string][] = [
    ['session', `${root}.gruntly/sessions/${sid}.mode`],
    ['project', `${root}.gruntly/mode`],
  ]
  for (const [source, path] of places) {
    const text = await $.fs.read(path).catch(() => null)
    const v = typeof text === 'string' ? text.trim().toLowerCase() : ''
    if (MODES.includes(v)) {
      return { mode: v as Mode, source }
    }
  }
  return { mode: 'auto', source: 'default' }
}

// `gruntly agent-run ...`, `gruntly run ...`, also through a path or gruntly.exe
const GRUNTLY = /(?:^|[\s;&|(])(?:[\w.:\\/~-]*[\\/])?gruntly(?:\.exe)?\s+(agent-run|run|do|continue|wait)\b/
const SHOWN_RUNNING = 8
const SHOWN_DONE_CHILD = 3 // when finished: the last few things the child did ...
const SHOWN_DONE_GRUNTLY = 2 // ... and gruntly's last steps, so both colours are visible
const DIFF_RUNNING = 14
const DIFF_DONE = 30
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
    case 'diff':
      return `changes: ${r.files ?? 0} file(s), +${r.ins ?? 0} -${r.dele ?? 0}`
    case 'done':
      return `finished: ${r.status}${r.reason ? ` (${r.reason})` : ''}`
    default:
      return r.k
  }
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'gruntly',
      description: 'Switch gruntly: on = delegate whenever eligible, off = never, auto = Claude decides',
      argumentHint: 'on|off|auto|follow [session]',
    })
    const m = await readMode($)
    await update($, modeAtom, () => m)
    return next(e)
  }).catch(($, e, next) => next(e))

  on('command.run', { command: 'gruntly' }, async ($, e) => {
    const [word, scopeWord] = e.args.trim().toLowerCase().split(/\s+/)
    const now = await readMode($)
    if (!word || word === 'status') {
      return {
        text: `gruntly mode: ${now.mode} (from ${now.source}). /gruntly on|off|auto sets it for this project; add "session" for this chat only; "follow session" returns this chat to the project's setting.`,
      }
    }
    const isFollow = word === 'follow'
    if (!MODES.includes(word) && !isFollow) {
      return { text: 'Usage: /gruntly on|off|auto [session]   or   /gruntly follow session' }
    }
    const scope = isFollow || scopeWord === 'session' ? 'session' : 'project'
    const root = await rootPrefix($)
    const path =
      scope === 'session' ? `${root}.gruntly/sessions/${await $.session.id()}.mode` : `${root}.gruntly/mode`
    await $.fs.write(path, isFollow ? '' : `${word}\n`)
    const after = await readMode($)
    await update($, modeAtom, () => after)
    const what = isFollow ? `this chat now follows the project (${after.mode})` : `gruntly is ${word.toUpperCase()} for this ${scope}`
    const note = !isFollow && after.mode !== word ? ` (note: ${after.source} setting ${after.mode} takes priority)` : ''
    return { text: `${what}${note}.` }
  })

  on('prompt.submit', async ($, e, next) => {
    const m = await readMode($) // the files may have been changed by `gruntly mode` in a terminal
    await update($, modeAtom, () => m)
    return next(e)
  }).catch(($, e, next) => next(e)) // a bug here must never block a prompt

  on('prompt.compose', async ($, e, next) => {
    const out = await next(e)
    const m = await readMode($)
    if (m.mode === 'auto') {
      return out
    }
    return {
      ...out,
      sections: [
        ...out.sections,
        { id: `${$.plugin.name}:mode`, text: m.mode === 'on' ? HINT_ON : HINT_OFF, scope: 'session' as const },
      ],
    }
  }).catch(($, e, next) => next(e))

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const m = await read($, modeAtom)
    if (e.props.hasSurvey || !m || m.mode === 'auto') {
      return next(e)
    }
    const { Box, Text } = $.ui.resolve(e)
    return (
      <Box>
        <Text color={m.mode === 'on' ? 'cyan' : 'yellow'}>
          {`◆ gruntly ${m.mode.toUpperCase()}`}
        </Text>
        <Text dimColor>{` (${m.source}) · /gruntly auto to let Claude decide`}</Text>
      </Box>
    )
  })

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
    const plain = rows.filter(r => r.k !== 'diff')
    const shown = e.isRunning
      ? plain.slice(-SHOWN_RUNNING)
      : [
          ...plain.filter(r => r.who === 'child').slice(-SHOWN_DONE_CHILD),
          ...plain.filter(r => r.who !== 'child').slice(-SHOWN_DONE_GRUNTLY),
        ].sort((a, b) => a.t - b.t)
    const diff = [...rows].reverse().find(r => r.k === 'diff')
    const diffLines = (diff?.lines ?? []).slice(0, e.isRunning ? DIFF_RUNNING : DIFF_DONE)
    const hidden = (diff?.lines?.length ?? 0) - diffLines.length + (diff?.more ?? 0)

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
        {diff ? (
          <Box flexDirection="column">
            <Text color="cyan">
              {`  ⟡ changes${diff.final ? ` (attempt ${diff.n}${diff.ok === false ? ', failed the checks' : ''})` : ' so far'}: ${diff.files ?? 0} file(s), `}
              <Text color="green">{`+${diff.ins ?? 0}`}</Text>
              {' '}
              <Text color="red">{`-${diff.dele ?? 0}`}</Text>
            </Text>
            {diffLines.map((ln, i) => (
              <Text
                key={i}
                color={ln.startsWith('+') ? 'green' : ln.startsWith('-') ? 'red' : undefined}
                bold={ln.startsWith('F ')}
                dimColor={!ln.startsWith('+') && !ln.startsWith('-') && !ln.startsWith('F ')}
              >
                {`    ${ln.startsWith('F ') ? ln.slice(2) : ln}`}
              </Text>
            ))}
            {hidden > 0 ? <Text dimColor>{`    … ${hidden} more lines (gruntly diff shows all)`}</Text> : null}
          </Box>
        ) : null}
      </Box>
    )
  })
}

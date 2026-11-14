import { expect, test } from 'claude-code/testing'

// The compaction hint: with gruntly ON a long chat is met with a request to compact, never with a compaction nobody asked for.

const measure = (tokens: number) =>
  ({ context: { tokens, window: 1_000_000, percent: Math.round(tokens / 10_000) }, rateLimits: [], changed: ['context'] }) as any

const files: { context?: string } = {}

function engine($: any, on: any, mode: string) {
  const seen = { toasts: [] as string[], compactions: [] as any[] }
  on('command.register', () => ({ value: { command: 'gruntly' } }))
  on('session.start', (_: any, e: any) => ({ cwd: e.cwd }))
  on('session.id', () => ({ value: 's1' }))
  on('session.measure', (_: any, e: any) => ({ changed: e.changed }))
  on('fs.exists', () => ({ value: true }))
  on('fs.read', (_: any, e: any) => {
    const path = String(e.path ?? e.args?.[0] ?? '')
    if (path.endsWith('context.json')) {
      return files.context === undefined ? { deny: 'not found' } : { value: files.context }
    }
    return { value: `${mode}\n` }
  })
  on('ui.toast', (_: any, e: any) => {
    seen.toasts.push(String(e.text ?? e.args?.[0] ?? ''))
    return { value: undefined }
  })
  on('session.compact', (_: any, e: any) => {
    seen.compactions.push(e)
    return { messages: [{ role: 'user', text: 'summary', toolUses: [] }], tokensBefore: 250_000, tokensAfter: 20_000 }
  })
  return seen
}

test('with gruntly ON it speaks in three steps: a quiet hint, a good moment, a request', async ($, on) => {
  const seen = engine($, on, 'on')
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })

  await $.session.measure(measure(90_000)) // below the first level: nothing
  expect(seen.toasts.length).toBe(0)

  await $.session.measure(measure(110_000)) // level 1: a hint in the row only, no pop-up
  expect(seen.toasts.length).toBe(0)

  await $.session.measure(measure(160_000)) // level 2: a good moment
  expect(seen.toasts.length).toBe(1)
  expect(seen.toasts[0]).toContain('good moment to /compact')

  await $.session.measure(measure(170_000)) // the same level again: no second pop-up
  expect(seen.toasts.length).toBe(1)

  await $.session.measure(measure(260_000)) // level 3: please
  expect(seen.toasts.length).toBe(2)
  expect(seen.toasts[1]).toContain('please /compact now')
  expect(seen.toasts[1]).not.toMatch(/\d+k/) // no numbers for the person to keep track of
})

test('with gruntly on auto or off it stays quiet', async ($, on) => {
  const seen = engine($, on, 'auto')
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await $.session.measure(measure(300_000))
  expect(seen.toasts.length).toBe(0)
})

test('it never compacts by itself, however large the context', async ($, on) => {
  const seen = engine($, on, 'on')
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  for (const t of [50_000, 150_000, 300_000, 600_000]) {
    await $.session.measure(measure(t))
  }
  expect(seen.compactions.length).toBe(0)
})

test('typing /compact with gruntly ON tells the summary what to keep, unless the person gave instructions', async ($, on) => {
  const seen = engine($, on, 'on')
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })

  await $.session.compact({ trigger: 'manual', messages: [{ role: 'user', text: 'hello', toolUses: [] }] } as any)
  expect(seen.compactions.length).toBe(1)
  expect(String(seen.compactions[0].instructions)).toContain('run ids')
  expect(String(seen.compactions[0].instructions)).toContain('never in code')

  await $.session.compact({ trigger: 'manual', messages: [{ role: 'user', text: 'hello', toolUses: [] }], instructions: 'keep only the plan' } as any)
  expect(String(seen.compactions[1].instructions)).toBe('keep only the plan') // their words win
})

test('typing /compact with gruntly off leaves the summary alone', async ($, on) => {
  const seen = engine($, on, 'off')
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await $.session.compact({ trigger: 'manual', messages: [{ role: 'user', text: 'hello', toolUses: [] }] } as any)
  expect(seen.compactions[0].instructions).toBeUndefined()
})

test('the warning starts where `gruntly context` says, and the defaults stay when there is no file', async ($, on) => {
  files.context = JSON.stringify({ levels: [50_000, 90_000, 150_000], source: 'formula' })
  const seen = engine($, on, 'on')
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await $.session.measure(measure(50_000))
  expect(seen.toasts.length).toBe(0)
  await $.session.measure(measure(95_000)) // the formula's second level is 90k, far below the default 150k
  expect(seen.toasts.length).toBe(1)
  files.context = undefined
})

test('a file that is not ours is ignored and the defaults stay', async ($, on) => {
  files.context = 'not json'
  const seen = engine($, on, 'on')
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await $.session.measure(measure(70_000))
  expect(seen.toasts.length).toBe(0) // the first default level is 100k
  files.context = undefined
})

export type Mode = 'auto' | 'on' | 'off'

export type Row = {
  t: number
  who: string // child = the local/small model, gruntly = its checks and waits
  k: string // start | attempt | tool | say | step | diff | gates | wait | done
  tool?: string
  kind?: string
  what?: string
  ok?: boolean
  text?: string
  model?: string
  harness?: string
  provider?: string
  n?: number
  status?: string
  reason?: string
  secs?: number
  why?: string
  detail?: string
  tokens_in?: number
  tokens_out?: number
  // diff rows: the child's changes so far (or, with final, at the end of attempt n)
  parts?: { path: string; tag?: string; text: string }[] // unified-diff hunks per file, drawn with the engine's own diff highlighter
  files?: number
  ins?: number
  dele?: number
  more?: number
  final?: boolean
}

declare module 'claude-code' {
  interface PluginState {
    gruntly: {
      feed: Record<string, Row[]>
      mode: { mode: Mode; source: string }
      ctx: { tokens: number; window: number; levels: number[] }
    }
  }
}

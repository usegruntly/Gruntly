export type Row = {
  t: number
  who: string // child = the local/small model, gruntly = its checks and waits
  k: string // start | attempt | tool | say | step | gates | wait | done
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
}

declare module 'claude-code' {
  interface PluginState {
    gruntly: { feed: Record<string, Row[]> }
  }
}

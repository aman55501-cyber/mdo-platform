export type Task = { line: number; pri: string; title: string; owner: string; due: string; note: string }
export type TaskView = { tasks: Task[]; error: string }

declare module 'claude-code' {
  interface PluginState {
    'mdo-tasks': { view: TaskView; expanded: boolean }
  }
}

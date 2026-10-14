export type Task = { line: number; pri: string; title: string; owner: string; due: string; note: string; done: boolean }
export type TaskView = { tasks: Task[]; error: string; at: number }

declare module 'claude-code' {
  interface PluginState {
    'mdo-tasks': { view: TaskView; expanded: boolean }
  }
}

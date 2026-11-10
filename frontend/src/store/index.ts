import { create } from 'zustand'

interface User {
  id: string
  email: string
  account_type: string | null
}

export interface Project {
  id: string
  name: string
  instrument: string
  timeframe: string
  current_stage: number
  oos_consumed?: boolean
}

interface AppState {
  user: User | null
  setUser: (user: User | null) => void
  token: string | null
  setToken: (token: string | null) => void

  activeProjectId: string | null
  setActiveProjectId: (id: string | null) => void
  projects: Project[]
  setProjects: (projects: Project[]) => void
  activeProject: Project | null
  updateProject: (id: string, updates: Partial<Project>) => void

  activeTab: string
  setActiveTab: (tab: string) => void
}

export const useAppStore = create<AppState>((set, get) => ({
  user: null,
  setUser: (user) => set({ user }),
  token: localStorage.getItem('forge_token'),
  setToken: (token) => {
    if (token) localStorage.setItem('forge_token', token)
    else localStorage.removeItem('forge_token')
    set({ token })
  },

  activeProjectId: null,
  setActiveProjectId: (id) => set({ activeProjectId: id }),
  projects: [],
  setProjects: (projects) => set({ projects }),
  get activeProject() {
    const { activeProjectId, projects } = get()
    return projects.find((p) => p.id === activeProjectId) ?? null
  },
  updateProject: (id, updates) =>
    set((s) => ({
      projects: s.projects.map((p) => (p.id === id ? { ...p, ...updates } : p)),
    })),

  activeTab: 'hypothesis',
  setActiveTab: (tab) => set({ activeTab: tab }),
}))

import type { Register } from 'claude-code'
import { registerLessons } from './lessons'
import { registerMission } from './mission'

// compound: the two halves of skill-compounder that run inside a session, as function
// hooks. ./lessons writes a lesson down after a failed call is fixed and states it back
// when the mistake recurs; ./mission states the user's own requests back at the moments a
// session tends to lose them. Each half has its own off switch (COMPOUND_LESSONS=0,
// COMPOUND_MISSION=0) and its own log under <state>/mod/.
export const register: Register = (on, options) => {
  registerLessons(on, options)
  registerMission(on, options)
}

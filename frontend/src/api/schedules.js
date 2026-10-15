/**
 * Scheduled commands API client (backend/schedules/routes.py).
 *
 * A schedule is an ordered list of steps (console command or power action,
 * each with a wait before it) fired by an interval, daily or cron trigger.
 */

import { get, post, put, del } from './client'

/** List a server's schedules, each annotated with `nextRunTime` and `lastRun`. */
export async function listSchedules(serverId) {
  return get(`/api/servers/${serverId}/schedules`)
}

/** Create a schedule. */
export async function createSchedule(serverId, payload) {
  return post(`/api/servers/${serverId}/schedules`, payload)
}

/** Replace a schedule (also used to toggle `enabled`). */
export async function updateSchedule(serverId, scheduleId, payload) {
  return put(`/api/servers/${serverId}/schedules/${scheduleId}`, payload)
}

/** Delete a schedule. */
export async function deleteSchedule(serverId, scheduleId) {
  return del(`/api/servers/${serverId}/schedules/${scheduleId}`)
}

/** Run a schedule now, in the background. */
export async function runSchedule(serverId, scheduleId) {
  return post(`/api/servers/${serverId}/schedules/${scheduleId}/run`)
}

export type ServiceStatus = "healthy" | "degraded" | "down"

export interface Service {
  id: string
  /** Matches the keys of `SERVICE_TO_ACCOUNT` in the account store. */
  name: string
  status: ServiceStatus
  /** Total SLOs defined for the service. */
  sloCount: number
  /** SLOs currently inside their target; never more than `sloCount`. */
  slosMeeting: number
  /** Health score samples (0-100), oldest first, for the sparkline. */
  healthTrend: number[]
}

// Placeholder services for the demo dashboard. Keep the names in step with
// `SERVICE_TO_ACCOUNT` in `lib/stores/account-store.ts`.
export const SERVICES: Service[] = [
  {
    id: "svc-gateway",
    name: "gateway",
    status: "healthy",
    sloCount: 4,
    slosMeeting: 4,
    healthTrend: [99, 99, 98, 99, 100, 99, 99, 100, 99, 99, 100, 99],
  },
  {
    id: "svc-auth",
    name: "auth-service",
    status: "healthy",
    sloCount: 3,
    slosMeeting: 3,
    healthTrend: [98, 99, 99, 98, 99, 99, 100, 99, 98, 99, 99, 99],
  },
  {
    id: "svc-user",
    name: "user-service",
    status: "healthy",
    sloCount: 3,
    slosMeeting: 3,
    healthTrend: [97, 98, 98, 99, 98, 98, 99, 99, 98, 99, 98, 99],
  },
  {
    id: "svc-order",
    name: "order-service",
    status: "degraded",
    sloCount: 4,
    slosMeeting: 3,
    healthTrend: [98, 97, 96, 94, 93, 91, 90, 92, 91, 89, 90, 88],
  },
  {
    id: "svc-payment",
    name: "payment-service",
    status: "healthy",
    sloCount: 5,
    slosMeeting: 5,
    healthTrend: [99, 99, 99, 100, 99, 99, 99, 100, 100, 99, 99, 99],
  },
  {
    id: "svc-notification",
    name: "notification-service",
    status: "down",
    sloCount: 2,
    slosMeeting: 0,
    healthTrend: [96, 95, 95, 90, 72, 40, 22, 10, 5, 4, 3, 3],
  },
  {
    id: "svc-search",
    name: "search-service",
    status: "degraded",
    sloCount: 3,
    slosMeeting: 2,
    healthTrend: [95, 94, 95, 93, 92, 94, 91, 90, 92, 90, 89, 91],
  },
]

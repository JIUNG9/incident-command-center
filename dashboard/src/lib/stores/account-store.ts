import { create } from "zustand"

export type AccountProvider = "aws" | "gcp" | "azure"
export type AccountRole = "hub" | "spoke" | "standalone"
export type AccountStatus = "connected" | "disconnected"

export interface CloudAccount {
  /** Stable key used in filters and URLs, e.g. "prod-a". */
  id: string
  name: string
  alias: string
  /** Provider-side identifier (AWS account ID, GCP project ID, Azure subscription ID). */
  accountId: string
  region: string
  provider: AccountProvider
  role: AccountRole
  status: AccountStatus
}

// Placeholder accounts for the demo dashboard. Real accounts come from the
// backend once it is connected; see docs for the account model.
export const DEFAULT_ACCOUNTS: CloudAccount[] = [
  {
    id: "hub",
    name: "Hub",
    alias: "acme-hub",
    accountId: "123456789012",
    region: "us-east-1",
    provider: "aws",
    role: "hub",
    status: "connected",
  },
  {
    id: "prod-a",
    name: "Prod A",
    alias: "acme-prod-a",
    accountId: "111122223333",
    region: "us-east-1",
    provider: "aws",
    role: "spoke",
    status: "connected",
  },
  {
    id: "prod-b",
    name: "Prod B",
    alias: "acme-prod-b",
    accountId: "987654321098",
    region: "eu-west-1",
    provider: "aws",
    role: "spoke",
    status: "connected",
  },
]

// Which account each service runs in. The names match the services in the
// mock data, so keep the two in step when adding a service.
export const SERVICE_TO_ACCOUNT: Record<string, string> = {
  gateway: "hub",
  "auth-service": "hub",
  "user-service": "prod-a",
  "order-service": "prod-a",
  "payment-service": "prod-a",
  "notification-service": "prod-b",
  "search-service": "prod-b",
}

/** Services that run in `accountId`; every known service when it is null (no filter). */
export function getServicesForAccount(accountId: string | null): string[] {
  const services = Object.keys(SERVICE_TO_ACCOUNT)
  if (!accountId) return services
  return services.filter((name) => SERVICE_TO_ACCOUNT[name] === accountId)
}

/** Display name for an account id; falls back to the id for an unknown account. */
export function getAccountName(accountId: string): string {
  return (
    DEFAULT_ACCOUNTS.find((account) => account.id === accountId)?.name ??
    accountId
  )
}

interface AccountState {
  /** null means "All Accounts". */
  activeAccountId: string | null
  accounts: CloudAccount[]
  setActiveAccount: (accountId: string | null) => void
}

export const useAccountStore = create<AccountState>()((set, get) => ({
  activeAccountId: null,
  accounts: DEFAULT_ACCOUNTS,
  // Ignore ids that aren't in `accounts` so a stale value can't leave the
  // dashboard filtered to an account that doesn't exist.
  setActiveAccount: (accountId) => {
    if (accountId !== null && !get().accounts.some((a) => a.id === accountId)) {
      return
    }
    set({ activeAccountId: accountId })
  },
}))

import { redirect } from "next/navigation"

// Setup wizard is pre-bypassed in vigil — go straight to the main dashboard.
export default function Home() {
  redirect("/logs")
}

// Server Component (Plan 2 F1).
//
// The interactive page tree lives in HomeClient; this module is intentionally
// minimal so the App Router can keep the route boundary on the server. Any
// future server-only data fetching (e.g. initial user prefs from D4, cached
// analyses from MongoDB) belongs here, then passes down as props.

import HomeClient from "./HomeClient";

export default function Page() {
  return <HomeClient />;
}

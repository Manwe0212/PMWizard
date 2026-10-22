import { InboxClient } from "@/components/inbox-client";

export default function Home() {
  const projectId = process.env.PMWIZARD_PROJECT_ID ?? "Project";

  return <InboxClient projectId={projectId} />;
}

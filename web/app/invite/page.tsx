import type { Metadata } from "next";

import { InvitationAcceptance } from "@/components/invitation-acceptance";

export const metadata: Metadata = {
  title: "Accept project invitation | PMWizard",
  robots: { index: false, follow: false },
  referrer: "no-referrer",
};

export default function InvitePage() {
  return <InvitationAcceptance />;
}

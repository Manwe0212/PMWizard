import type { Metadata } from "next";
import { PasswordResetRequestForm } from "@/components/password-recovery";

export const metadata: Metadata = {
  title: "Recover account | PMWizard",
  robots: { index: false, follow: false },
  referrer: "no-referrer",
};

export default function Page() {
  return <PasswordResetRequestForm />;
}

import type { Metadata } from "next";
import { PasswordResetConfirmForm } from "@/components/password-recovery";

export const metadata: Metadata = {
  title: "Reset password | PMWizard",
  robots: { index: false, follow: false },
  referrer: "no-referrer",
};

export default function Page() {
  return <PasswordResetConfirmForm />;
}

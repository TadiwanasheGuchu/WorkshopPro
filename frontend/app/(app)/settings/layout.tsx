import type { ReactNode } from "react";

import { PageHeader } from "@/components/ui/page";

import { SettingsTabs } from "./settings-tabs";

export default function SettingsLayout({ children }: { children: ReactNode }) {
  return (
    <>
      <PageHeader title="Settings" />
      <SettingsTabs />
      {children}
    </>
  );
}

import { countFolders } from "@/components/folders";
import { AppShell } from "@/components/app-shell";
import { Kit } from "@/components/kit";
import { Sidebar } from "@/components/sidebar";
import { useData } from "@/data/provider";

export default function KitPage() {
  const { threads, mailbox, mailboxes, selectMailbox, sync, syncing } = useData();
  const counts = countFolders(threads);
  return (
    <AppShell
      title="设计组件"
      sidebar={<Sidebar counts={counts} activeFolder="all" inInbox={false} mailbox={mailbox} mailboxes={mailboxes} onMailboxChange={selectMailbox} onSync={sync} syncing={syncing} />}
      main={<Kit />}
    />
  );
}

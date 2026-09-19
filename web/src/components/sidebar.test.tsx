import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { expect, it } from "vitest";
import type { MailboxInfo } from "@/data/types";
import { Sidebar } from "./sidebar";
import { TipProvider } from "./tip";

const counts = { all: 0, inbox: 0, quote: 0, replied: 0, invalid: 0 };

function show(mailbox: MailboxInfo) {
  render(
    <MemoryRouter>
      <TipProvider>
        <Sidebar counts={counts} activeFolder="all" inInbox mailbox={mailbox} />
      </TipProvider>
    </MemoryRouter>,
  );
}

it("shows the mailbox address and hides leads for a mailbox that only reads", () => {
  show({ address: "me@example.test", display_name: "Me", tasks: ["read"] });
  expect(screen.getByText("me@example.test")).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: /线索/ })).not.toBeInTheDocument();
});

it("keeps the leads entry for a mailbox that suggests leads", () => {
  show({ address: "sales@example.test", display_name: "Sales", tasks: ["read", "leads", "draft"] });
  expect(screen.getByRole("link", { name: /线索/ })).toBeInTheDocument();
});

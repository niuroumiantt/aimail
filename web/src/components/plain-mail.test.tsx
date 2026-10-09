import { render } from "@testing-library/react";
import { expect, it } from "vitest";
import { PlainMail } from "./plain-mail";

it("formats blank-line paragraphs while preserving every original character and intentional line break", () => {
  const text = 'Dear team,\r\n\r\nExact part K4-123; USD 20–35.\r\n10 units\r\n  \r\n\r\nRegards,\r\nGrace';
  const { container } = render(<PlainMail text={text} />);
  expect(container.firstChild?.textContent).toBe(text);
  expect(container.querySelectorAll('p')).toHaveLength(3);
  expect(container.querySelectorAll('p')[1].textContent).toBe('Exact part K4-123; USD 20–35.\r\n10 units');
});

it("renders plaintext HTML characters as text and keeps specification columns unchanged", () => {
  const text = '<img src=x onerror=alert(1)>\nPart    Qty\nA-123   10\nB-456   20';
  const { container } = render(<PlainMail text={text} />);
  expect(container.querySelector('img')).toBeNull();
  expect(container.firstChild?.textContent).toBe(text);
});

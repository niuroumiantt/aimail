import { render } from "@testing-library/react";
import { expect, it } from "vitest";
import { Avatar } from "./avatar";

it("gives the same person the same tint every time", () => {
  const a = render(<Avatar name="Mikko Laine" />).container.firstElementChild!;
  const b = render(<Avatar name="Mikko Laine" />).container.firstElementChild!;
  expect(a.className).toBe(b.className);
  expect(a.textContent).toBe("ML");
});

it("uses the first character for CJK names", () => {
  const el = render(<Avatar name="王婷" />).container.firstElementChild!;
  expect(el.textContent).toBe("王");
});

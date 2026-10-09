/** Blank lines become paragraph spacing; every original character stays in the DOM. */
export function PlainMail({ text }: { text: string }) {
  return <div className="mail-plain-original">{text.split(/(\r?\n[\t ]*\r?\n(?:[\t ]*\r?\n)*)/).map((part, index) =>
    index % 2 ? part : <p key={index}>{part}</p>,
  )}</div>;
}

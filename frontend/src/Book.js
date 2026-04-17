export default function Book({ title, x, y }) {
  return (
    <div
      style={{
        position: "absolute",
        left: x,
        top: y,
        padding: "6px 10px",
        border: "1px solid #333",
        background: "#fafafa",
        fontSize: "12px",
      }}
    >
      {title}
    </div>
  );
}

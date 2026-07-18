import React from "react";

export default function KeywordChips({ label, items, tone }) {
  if (!items || items.length === 0) return null;
  return (
    <div className="chip-strip">
      <div className="chip-strip__label">{label}</div>
      <div className="chip-strip__row">
        {items.map((item) => (
          <span key={item} className={`chip chip--${tone}`}>
            {item}
          </span>
        ))}
      </div>
    </div>
  );
}

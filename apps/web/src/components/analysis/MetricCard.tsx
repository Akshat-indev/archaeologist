interface MetricCardProps {
  label: string;
  value: number;
  note: string;
  accent?:
    | "blue"
    | "violet"
    | "green"
    | "amber";
}

export function MetricCard({
  label,
  value,
  note,
  accent = "blue",
}: MetricCardProps) {
  return (
    <article
      className={`metric-card metric-card-${accent}`}
    >
      <div className="metric-card-heading">
        <span>{label}</span>

        <span
          className={`metric-mark ${accent}`}
          aria-hidden="true"
        />
      </div>

      <strong>
        {value.toLocaleString()}
      </strong>

      <span className="metric-note">
        {note}
      </span>
    </article>
  );
}
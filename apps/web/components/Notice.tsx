export function Notice({
  notice,
  error,
}: {
  notice?: string;
  error?: string;
}) {
  if (!notice && !error) {
    return null;
  }
  return (
    <div className={error ? "error" : "notice"} role={error ? "alert" : "status"}>
      {error || notice}
    </div>
  );
}

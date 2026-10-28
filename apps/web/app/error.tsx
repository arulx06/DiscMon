"use client";

export default function ErrorPage({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="card">
      <h1>Something went wrong</h1>
      <p className="muted">
        The page could not be loaded. No opportunity was marked closed or changed by this
        failure.
      </p>
      <p className="small muted">{error.message}</p>
      <button type="button" className="primary" onClick={reset}>
        Try again
      </button>
    </div>
  );
}

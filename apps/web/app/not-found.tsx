import Link from "next/link";

export default function NotFound() {
  return (
    <div className="card">
      <h1>Not found</h1>
      <p className="muted">That record does not exist or is no longer available.</p>
      <Link className="button" href="/">
        Back to dashboard
      </Link>
    </div>
  );
}

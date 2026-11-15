import Link from "next/link";

export default function NotFound() {
  return (
    <div className="max-w-xl">
      <h1 className="text-xl font-semibold">Not found</h1>
      <p className="mt-1 text-muted">This record does not exist, or you do not have access to it.</p>
      <Link href="/" className="mt-4 inline-block text-steel hover:underline">
        Go to dashboard
      </Link>
    </div>
  );
}

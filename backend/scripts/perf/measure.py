"""Time the API calls behind the main screens against a seeded database.

    uv run python scripts/perf/measure.py [--load] [name-filter ...]

Each call runs 7 times; the first is discarded (warm-up) and the median and maximum of the
rest are printed. --load also runs 10 concurrent users making 30 random calls each.
See docs/architecture/performance.md for how to seed the database and the last results.
"""

import argparse
import random
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import httpx


def client(base: str, email: str, password: str) -> httpx.Client:
    c = httpx.Client(base_url=base, timeout=30, trust_env=False)
    c.get("/auth/csrf")
    res = c.post(
        "/auth/login",
        json={"email": email, "password": password},
        headers={"X-CSRF-Token": c.cookies["wp_csrf"]},
    )
    res.raise_for_status()
    return c


def cases(c: httpx.Client) -> list[tuple[str, str, dict[str, Any]]]:
    job = c.get("/job-cards", params={"status": "completed"}).json()["items"][0]
    inv = c.get("/invoices").json()["items"][0]
    month = {"date_from": "2026-10-01", "date_to": "2026-10-31"}
    year = {"date_from": "2025-11-01", "date_to": "2026-10-31"}
    return [
        ("job cards: open", "/job-cards", {"open_only": "true"}),
        ("job cards: all, page 1", "/job-cards", {}),
        ("job cards: completed", "/job-cards", {"status": "completed"}),
        ("job cards: overdue", "/job-cards", {"overdue": "true"}),
        ("job cards: search number", "/job-cards", {"search": "JC-02999"}),
        ("job cards: search reg", "/job-cards", {"search": "N 4521"}),
        ("job cards: search name", "/job-cards", {"search": "Shikongo"}),
        ("job cards: summary (dashboard)", "/job-cards/summary", {}),
        ("job card detail", f"/job-cards/{job['id']}", {}),
        ("customers: page 1", "/customers", {}),
        ("customers: search name", "/customers", {"search": "Ndapewa Haufiku"}),
        ("customers: search phone", "/customers", {"search": "0814521"}),
        ("customers: search reg", "/customers", {"search": "N 4521 W"}),
        ("customer detail", f"/customers/{job['customer']['id']}", {}),
        ("vehicles: search reg", "/vehicles", {"search": "N 4521"}),
        ("vehicles: search make", "/vehicles", {"search": "Toyota Hilux"}),
        ("vehicle detail", f"/vehicles/{job['vehicle']['id']}", {}),
        ("invoices: page 1", "/invoices", {}),
        ("invoices: search name", "/invoices", {"search": "van Wyk"}),
        ("invoices: by customer", "/invoices", {"customer_id": job["customer"]["id"]}),
        ("invoice detail", f"/invoices/{inv['id']}", {}),
        ("payments: page 1", "/payments", {}),
        ("payments: search", "/payments", {"search": "Angula"}),
        ("notifications: page 1", "/notifications", {}),
        ("notifications: failed", "/notifications", {"status": "failed"}),
        ("audit log: page 1", "/audit-logs", {}),
        ("audit log: entity", "/audit-logs", {"entity_id": job["id"]}),
        ("report: financial, 1 month", "/reports/financial", month),
        ("report: financial, 1 year", "/reports/financial", year),
        ("report: operations, 1 month", "/reports/operations", month),
        ("report: operations, 1 year", "/reports/operations", year),
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8010/api/v1")
    parser.add_argument("--email", default="perf-owner@example.com")
    parser.add_argument("--password", default="perf-owner-password-1")
    parser.add_argument("--load", action="store_true", help="also run 10 concurrent users")
    parser.add_argument("only", nargs="*", help="run only calls whose name contains these")
    args = parser.parse_args()

    c = client(args.base_url, args.email, args.password)
    all_cases = cases(c)
    print(f"{'call':34} {'median':>7} {'max':>7}  status")
    for name, path, params in all_cases:
        if args.only and not any(o in name for o in args.only):
            continue
        times = []
        for _ in range(7):
            t = time.perf_counter()
            res = c.get(path, params=params)
            times.append((time.perf_counter() - t) * 1000)
        times = times[1:]
        print(f"{name:34} {statistics.median(times):6.0f}ms {max(times):6.0f}ms  {res.status_code}")

    if args.load:
        lists = [(p, q) for n, p, q in all_cases if "detail" not in n]

        def user(_: int) -> list[tuple[float, int]]:
            u = client(args.base_url, args.email, args.password)
            out = []
            for _ in range(30):
                path, params = random.choice(lists)  # noqa: S311 - load test, not security
                t = time.perf_counter()
                res = u.get(path, params=params)
                out.append(((time.perf_counter() - t) * 1000, res.status_code))
            return out

        start = time.perf_counter()
        with ThreadPoolExecutor(10) as pool:
            results = [r for batch in pool.map(user, range(10)) for r in batch]
        ms = sorted(r[0] for r in results)
        errors = sum(1 for r in results if r[1] != 200)
        print(
            f"\nload: {len(ms)} requests, 10 concurrent users, {time.perf_counter() - start:.1f}s; "
            f"median {statistics.median(ms):.0f}ms, p95 {ms[int(len(ms) * 0.95)]:.0f}ms, "
            f"max {ms[-1]:.0f}ms; errors {errors}"
        )


if __name__ == "__main__":
    main()

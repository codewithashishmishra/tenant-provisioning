import threading

from app.errors import AppError
from tests.support import arrive_active, fresh_slug


def _run(calls):
    barrier = threading.Barrier(len(calls))
    results = []
    lock = threading.Lock()

    def go(fn):
        barrier.wait()
        try:
            fn()
            code = "ok"
        except AppError as exc:
            code = exc.code
        except Exception as exc:
            code = f"err:{type(exc).__name__}:{exc}"
        with lock:
            results.append(code)

    threads = [threading.Thread(target=go, args=(fn,)) for fn in calls]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return results


def test_one_slug_wins(svc):
    slug = fresh_slug("race")
    calls = [lambda: svc.create_tenant(slug, "Race") for _ in range(8)]
    results = _run(calls)
    assert results.count("ok") == 1
    assert results.count("tenant_already_exists") == 7
    listed = svc.list_tenants(None, 100, 0)
    assert len([row for row in listed["items"] if row["slug"] == slug]) == 1


def test_one_patch_wins(svc):
    tenant = arrive_active(svc)
    version = tenant["version"]
    calls = [lambda: svc.update_tenant(tenant["id"], "Renamed", version) for _ in range(8)]
    results = _run(calls)
    assert results.count("ok") == 1
    assert results.count("tenant_version_conflict") == 7
    current = svc.get_tenant(tenant["id"])
    assert current["status"] == "updating"
    assert current["version"] == version + 1
    assert current["name"] == "Renamed"

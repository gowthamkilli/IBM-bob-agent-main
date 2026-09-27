"""
proof_tests.py — library of hand-written proof tests for each guarantee.

Each test is designed to:
  - PASS on a clean base branch
  - FAIL on a branch that defeats the guarantee
"""

# G1: a single order request results in at most one gateway charge call
G1_TEST_SOURCE = '''\
"""
G1 proof test: a single order request results in at most one gateway charge call.
Counts _do_charge() calls. base=PASS (no retry or ceiling=1), head=FAIL (retry or weakened ceiling).
"""
import app.gateway as gw

def test_single_order_results_in_at_most_one_gateway_charge():
    has_retry = hasattr(gw, "_do_charge")

    if not has_retry:
        attempts = 1
    else:
        original = gw._do_charge
        attempts_list = []
        fail_first = {"done": False}

        def counting_do_charge(amount, idempotency_key):
            attempts_list.append(1)
            if not fail_first["done"]:
                fail_first["done"] = True
                raise gw.GatewayError("transient")
            return original(amount, idempotency_key)

        gw._do_charge = counting_do_charge
        try:
            gw.charge(1.0, "g1-proof-key")
        except gw.GatewayError:
            pass
        finally:
            gw._do_charge = original

        attempts = len(attempts_list)

    assert attempts <= 1, (
        f"G1 VIOLATED: {attempts} gateway charge attempts for one logical request "
        f"(ceiling=1). A single order request must result in at most one "
        f"gateway charge call (docs/ADR-001.md:14)."
    )
'''

# G1 weakened ceiling proof test: ceiling raised from 1 to > 1
G1_CEILING_TEST_SOURCE = '''\
"""
G1 ceiling proof test: the enforced ceiling must be exactly 1.
PASS when no limiter (main) or ceiling=1, FAIL when ceiling is weakened (e.g. 5).
"""
import sys

def test_g1_ceiling_is_one():
    # If limiter module exists, its ceiling must be 1 per ADR-001
    try:
        import app.limiter as lim
        ceiling = getattr(lim, "_G1_CEILING", 1)
    except ImportError:
        # No limiter on base — ceiling concept not yet implemented, PASS
        ceiling = 1
    assert ceiling == 1, (
        f"G1 VIOLATED: ceiling is {ceiling}, ADR-001 requires ceiling=1 "
        f"(docs/ADR-001.md:14). A weakened ceiling defeats the guarantee."
    )
'''

# G2: same idempotency key creates exactly one order
G2_TEST_SOURCE = '''\
"""
G2 proof test: same idempotency key must create exactly one order.
PASS when idempotency works, FAIL when key is regenerated.
"""
import os
os.environ["ORDER_DB"] = ":memory:"
import app.db as db_module
from app.orders import create_order

def test_duplicate_key_creates_one_order():
    db_module.reset_connection()
    key = "g2-proof-idem-key"
    create_order(key, "item-1", 1, 9.99)
    create_order(key, "item-1", 1, 9.99)
    conn = db_module.get_connection()
    count = conn.execute(
        "SELECT COUNT(*) FROM orders"
    ).fetchone()[0]
    assert count == 1, (
        f"G2 VIOLATED: {count} orders created for the same idempotency key. "
        f"Guarantee: same key must create exactly one order (docs/ADR-002.md:16)."
    )
    db_module.reset_connection()
'''

# G3: every order write passes through validate_order()
G3_TEST_SOURCE = '''\
"""
G3 proof test: an order with invalid inputs (quantity=0) must be rejected.
PASS when validate_order() blocks it, FAIL when validate_order() is bypassed.
"""
import os
os.environ["ORDER_DB"] = ":memory:"
import app.db as db_module
from fastapi.testclient import TestClient
from app.api import app

client = TestClient(app)

def test_invalid_order_rejected_via_all_routes():
    db_module.reset_connection()
    # The /orders route should reject quantity=0
    r1 = client.post("/orders", json={
        "idempotency_key": "g3-proof-key-std",
        "item_id": "item-1",
        "quantity": 0,
        "amount": 9.99,
    })
    assert r1.status_code == 422, (
        f"G3: /orders accepted quantity=0 (status {r1.status_code}). "
        f"validate_order() must be called for all order writes (docs/ADR-003.md:16)."
    )

    # If a /orders/bulk or /orders/fast route exists, it must also reject
    bulk_resp = client.post("/orders/bulk", json={"orders": [{
        "idempotency_key": "g3-proof-key-bulk",
        "item_id": "item-1",
        "quantity": 0,
        "amount": 9.99,
    }]})
    fast_resp = client.post("/orders/fast", json={
        "idempotency_key": "g3-proof-key-fast",
        "item_id": "item-1",
        "quantity": 0,
        "amount": 9.99,
    })

    # If the route exists and accepts invalid orders, G3 is defeated
    bulk_ok = bulk_resp.status_code not in (404, 405)
    fast_ok = fast_resp.status_code not in (404, 405)

    if bulk_ok:
        assert bulk_resp.status_code == 422, (
            f"G3 VIOLATED: /orders/bulk accepted quantity=0 (status {bulk_resp.status_code}). "
            f"Every order write must pass through validate_order() (docs/ADR-003.md:16)."
        )
    if fast_ok:
        assert fast_resp.status_code == 422, (
            f"G3 VIOLATED: /orders/fast accepted quantity=0 (status {fast_resp.status_code}). "
            f"Every order write must pass through validate_order() (docs/ADR-003.md:16)."
        )
    db_module.reset_connection()
'''

# G4: catalog reads served from cache; DB hit rate < 20% once warm
G4_TEST_SOURCE = '''\
"""
G4 proof test: cache must serve warm reads without hitting the DB.
PASS when cache works, FAIL when write-through defeats cache.
"""
import app.cache as cache_module

def test_cache_serves_warm_reads_without_db():
    cache_module.clear()
    db_calls = {"count": 0}

    def db_lookup(item_id):
        db_calls["count"] += 1
        return {"item_id": item_id, "name": "Widget", "price": 9.99}

    # First call: allowed to hit DB
    cache_module.get_item("item-1", db_lookup)
    assert db_calls["count"] == 1

    # Next 9 calls: must be served from cache (0 DB calls)
    for _ in range(9):
        cache_module.get_item("item-1", db_lookup)

    total_db_calls = db_calls["count"]
    hit_rate = (10 - (total_db_calls - 1)) / 10  # subtract the first miss

    assert total_db_calls == 1, (
        f"G4 VIOLATED: DB was called {total_db_calls} times for 10 reads of the same item. "
        f"Once warm, cache must serve reads without hitting DB (docs/ADR-004.md:17). "
        f"DB hit rate: {total_db_calls/10*100:.0f}% (max allowed: 20%)."
    )
    cache_module.clear()
'''

# Map guarantee ID -> proof test source
PROOF_TESTS = {
    "G1": G1_TEST_SOURCE,
    "G1_CEILING": G1_CEILING_TEST_SOURCE,
    "G2": G2_TEST_SOURCE,
    "G3": G3_TEST_SOURCE,
    "G4": G4_TEST_SOURCE,
}

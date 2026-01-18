# Design and Revision Logic Flaws Analysis

## Executive Summary
This document identifies critical design flaws and issues in the revision/spaced repetition logic, database transaction handling, and overall architecture of the Animals Bot codebase.

---

## 1. CRITICAL: Race Conditions in Revision Logic

### Issue: Non-Atomic Read-Modify-Write Operations

**Location:** `bot/storage/repositories.py` - `ItemProgressRepository.record_correct()` and `record_wrong()`

**Problem:**
The revision logic uses a read-modify-write pattern that is not atomic. Concurrent requests can cause lost updates and incorrect spacing intervals.

**Example from `record_correct()` (lines 644-687):**
```644:687:bot/storage/repositories.py
async def record_correct(self, user_id: int, level: int, content_id: str, now_utc: datetime) -> None:
    await self._ensure_row(user_id, level, content_id)
    async with self.database.connect() as conn:
        row_cursor = await conn.execute(
            "SELECT learn_correct_count, review_stage FROM item_progress WHERE user_id=? AND level=? AND content_id=?",
            (user_id, level, content_id),
        )
        row = await row_cursor.fetchone()
        learn_count = int(row["learn_correct_count"]) if row and row["learn_correct_count"] is not None else 0
        review_stage = int(row["review_stage"]) if row and row["review_stage"] is not None else 0

        if review_stage == 0 and learn_count < 2:
            learn_count += 1
            if learn_count >= 2:
                review_stage = 1
                next_due_at = now_utc + timedelta(minutes=10)
            else:
                next_due_at = None
        elif review_stage == 1:
            review_stage = 2
            next_due_at = now_utc + timedelta(days=2)
        elif review_stage == 2:
            review_stage = 3
            next_due_at = None
        else:
            next_due_at = None

        await conn.execute(
            """
            UPDATE item_progress
            SET learn_correct_count=?, review_stage=?, next_due_at=?, last_seen_at=?
            WHERE user_id=? AND level=? AND content_id=?
            """,
            (
                learn_count,
                review_stage,
                next_due_at,
                now_utc,
                user_id,
                level,
                content_id,
            ),
        )
        await conn.commit()
```

**Race Condition Scenario:**
1. Request A reads `learn_count=1, review_stage=0`
2. Request B reads `learn_count=1, review_stage=0` (before A commits)
3. Request A calculates `learn_count=2, review_stage=1, next_due_at=now+10min`
4. Request B calculates `learn_count=2, review_stage=1, next_due_at=now+10min`
5. Both write, potentially causing:
   - Lost increment (should be 2, but both write 2)
   - Incorrect spacing (item might advance too quickly)
   - State corruption

**Impact:** High - Can cause incorrect spaced repetition intervals, leading to poor learning outcomes.

**Fix Required:** Wrap SELECT and UPDATE in a transaction with proper isolation, or use SQL-level atomic operations (e.g., `UPDATE ... SET learn_correct_count = learn_correct_count + 1 WHERE ...`).

---

## 2. CRITICAL: Missing Transaction Boundaries

### Issue: No Explicit Transactions for Multi-Step Operations

**Location:** Throughout `bot/storage/repositories.py`

**Problem:**
Most repository methods perform multiple database operations without explicit transaction boundaries. Even though SQLite has autocommit enabled by default, operations that should be atomic are not guaranteed to be.

**Examples:**

1. **`record_correct()` and `record_wrong()`**: SELECT followed by UPDATE without BEGIN/COMMIT
2. **`DailyStatsRepository.update_stats()` (lines 445-469)**: Uses ON CONFLICT but no explicit transaction for related operations
3. **`SessionStateRepository.increment_correct()` (lines 287-297)**: Increments and then reads back - should be atomic

**Impact:** Medium-High - Data inconsistency, especially under concurrent load.

**Fix Required:** Use explicit `BEGIN TRANSACTION` / `COMMIT` blocks for multi-step operations.

---

## 3. DESIGN FLAW: Inconsistent `learn_correct_count` Handling

### Issue: `learn_correct_count` Not Updated in `record_wrong()`

**Location:** `bot/storage/repositories.py` - `ItemProgressRepository.record_wrong()` (lines 689-714)

**Problem:**
```689:714:bot/storage/repositories.py
async def record_wrong(self, user_id: int, level: int, content_id: str, now_utc: datetime) -> None:
    await self._ensure_row(user_id, level, content_id)
    async with self.database.connect() as conn:
        row_cursor = await conn.execute(
            "SELECT review_stage FROM item_progress WHERE user_id=? AND level=? AND content_id=?",
            (user_id, level, content_id),
        )
        row = await row_cursor.fetchone()
        review_stage = int(row["review_stage"]) if row and row["review_stage"] is not None else 0
        if review_stage > 0:
            review_stage = max(0, review_stage - 1)
        if review_stage >= 2:
            next_due_at = now_utc + timedelta(days=2)
        elif review_stage == 1:
            next_due_at = now_utc + timedelta(minutes=10)
        else:
            next_due_at = now_utc + timedelta(minutes=2)
        await conn.execute(
            """
            UPDATE item_progress
            SET review_stage=?, next_due_at=?, last_seen_at=?
            WHERE user_id=? AND level=? AND content_id=?
            """,
            (review_stage, next_due_at, now_utc, user_id, level, content_id),
        )
        await conn.commit()
```

The `record_wrong()` method doesn't reset or adjust `learn_correct_count`. If a user gets a wrong answer during the learning phase (`review_stage=0`), the `learn_correct_count` remains unchanged, which could lead to incorrect state transitions.

**Impact:** Medium - Could cause items to prematurely advance to review stage despite errors.

**Fix Required:** Reset `learn_correct_count` to 0 when `review_stage=0` and answer is wrong, or implement a more nuanced learning phase logic.

---

## 4. DESIGN FLAW: Logic Error in Wrong Answer Handling

### Issue: Wrong Answer During Learning Phase Doesn't Reset Learning Progress

**Scenario:**
- User is learning (review_stage=0, learn_correct_count=1)
- User answers incorrectly
- `record_wrong()` only adjusts `review_stage` (which is 0, so it stays 0)
- `learn_correct_count` remains 1
- Next correct answer will immediately advance to review_stage=1

**Expected Behavior:** Wrong answers during learning should reset `learn_correct_count` to maintain learning integrity.

**Impact:** Medium - Reduces learning effectiveness, items can be promoted without proper mastery.

---

## 5. DESIGN FLAW: Inefficient Database Connection Lock

### Issue: Lock Only Protects Connection Creation, Not Operations

**Location:** `bot/storage/repositories.py` - `Database.connect()` (lines 31-39)

```31:39:bot/storage/repositories.py
@asynccontextmanager
async def connect(self) -> AsyncIterator[aiosqlite.Connection]:
    async with self._connect_lock:
        db = await aiosqlite.connect(self.path)
    db.row_factory = aiosqlite.Row
    try:
        yield db
    finally:
        await db.close()
```

**Problem:**
The `_connect_lock` only protects the connection creation, not the database operations. Once the connection is yielded, the lock is released, allowing concurrent operations that could interfere with each other. SQLite does handle concurrency at the database level, but the connection-level lock gives a false sense of protection.

**Impact:** Low-Medium - May contribute to race conditions under high load. SQLite's own locking should handle most cases, but the pattern is misleading.

**Fix Required:** Remove the lock or document that SQLite handles concurrency, OR implement row-level locking/optimistic locking for critical updates.

---

## 6. DESIGN FLAW: No Optimistic Locking or Versioning

### Issue: Updates Don't Check for Concurrent Modifications

**Location:** All UPDATE operations in repositories

**Problem:**
Update operations don't use version numbers or timestamps to detect concurrent modifications. This means:
- Last write wins (potential data loss)
- No detection of stale data updates

**Example:** If two handlers update session_state.item_index simultaneously, the final value depends on commit order, potentially losing one update.

**Impact:** Medium - Can cause lost updates in session state and progress tracking.

**Fix Required:** Implement optimistic locking using `updated_at` timestamps or version columns, or use SQL-level atomic operations.

---

## 7. DESIGN FLAW: Spaced Repetition Logic Gaps

### Issue: Stage 3 Items Can Never Be Reviewed Again

**Location:** `bot/storage/repositories.py` - `record_correct()` lines 665-667

```665:667:bot/storage/repositories.py
elif review_stage == 2:
    review_stage = 3
    next_due_at = None
```

**Problem:**
When an item reaches `review_stage=3`, `next_due_at` is set to `NULL` permanently. This means:
- Items in stage 3 will never appear in `get_due_items()` (which filters `next_due_at IS NOT NULL`)
- Once "mastered" (stage 3), items are forgotten forever
- No long-term review mechanism

**Impact:** Medium - Violates spaced repetition principles. Learners need periodic reviews even for mastered items.

**Fix Required:** Implement a long-term review schedule (e.g., every 30 days, 90 days) for stage 3 items, or add a separate "mastered" review queue.

---

## 8. DESIGN FLAW: Inconsistent State Updates in Session Operations

### Issue: Multiple Separate Updates Instead of Atomic State Changes

**Location:** `bot/services/session_service.py` - `advance_item()` (lines 176-182)

```176:182:bot/services/session_service.py
async def advance_item(self, session_id: int) -> None:
    state_row = await self.repositories.session_state.get_state(session_id)
    if not state_row:
        return
    next_index = state_row["item_index"] + 1
    await self.repositories.session_state.update_index(session_id, next_index)
    await self.repositories.session_state.update_attempts(session_id, 0)
```

**Problem:**
Two separate UPDATE operations instead of one atomic update. Between these operations:
- State could be inconsistent (index updated but attempts not)
- Concurrent operations could see partial state
- Rollback handling is more complex

**Impact:** Medium - Can lead to inconsistent session state under concurrency.

**Fix Required:** Combine into a single UPDATE statement or wrap in a transaction.

---

## 9. DESIGN FLAW: Missing Validation in Revision Stage Transitions

### Issue: No Bounds Checking or Validation

**Location:** `bot/storage/repositories.py` - Revision logic

**Problem:**
- `review_stage` can theoretically exceed 3 (if database is corrupted or manually modified)
- No validation that stage transitions are valid
- `learn_correct_count` has no upper bound

**Impact:** Low - Mostly defensive, but could cause edge cases.

**Fix Required:** Add validation/constraints in database schema or application logic.

---

## 10. ARCHITECTURE FLAW: Separation of Concerns

### Issue: Business Logic in Repository Layer

**Location:** `bot/storage/repositories.py` - `ItemProgressRepository`

**Problem:**
The spaced repetition algorithm logic (calculating `next_due_at`, stage transitions) is embedded in the repository layer. This violates separation of concerns:
- Hard to test business logic in isolation
- Difficult to change algorithms without touching database code
- Repository should handle data access, not business rules

**Impact:** Medium - Reduces maintainability and testability.

**Fix Required:** Move revision logic to a dedicated service class (e.g., `RevisionService` or `SpacedRepetitionService`).

---

## 11. CRITICAL: Non-Atomic Multi-Step Operations in Voice Handler

### Issue: Multiple Separate Database Operations Without Transactions

**Location:** `bot/telegram/routers/voice.py` - Voice answer handling (lines 426-446)

**Problem:**
When processing a correct or wrong answer, multiple database operations are performed sequentially without transaction boundaries:

```426:446:bot/telegram/routers/voice.py
now_utc = datetime.now(timezone.utc)

if ok:
    await ctx.repositories.item_progress.record_correct(
        user["id"], deck_item.level, deck_item.content_id, now_utc=now_utc
    )
    await ctx.repositories.session_state.increment_correct(state.session_id)
    await ctx.session_service.advance_item(state.session_id)
    await message.answer("✅ Добре!")
else:
    await ctx.repositories.session_state.increment_wrong_total(state.session_id)
    await ctx.repositories.item_progress.record_wrong(
        user["id"], deck_item.level, deck_item.content_id, now_utc=now_utc
    )
    attempts = state.current_attempts + 1
    if attempts >= 5:
        await message.answer("Йдемо далі")
        await ctx.session_service.advance_item(state.session_id)
    else:
        await ctx.repositories.session_state.update_attempts(state.session_id, attempts)
        await message.answer("❌ Спробуй ще раз")
```

**Scenario:**
1. `record_correct()` succeeds (item progress updated)
2. `increment_correct()` succeeds (session state updated)
3. `advance_item()` fails (connection timeout, database error)
4. **Result:** Item progress reflects correct answer, but session state shows wrong item_index/attempts

**Impact:** Critical - Can cause session state corruption, incorrect scoring, and user confusion.

**Fix Required:** Wrap related operations in a transaction, or implement compensation/rollback logic.

---

## 12. DESIGN FLAW: Order of Operations Dependency

### Issue: Operations Depend on Previous Operation Success

**Location:** `bot/telegram/routers/voice.py` - Voice handler

**Problem:**
The code assumes all operations succeed in sequence. If `record_correct()` succeeds but `increment_correct()` fails, the item progress is updated but session tracking is inconsistent.

**Impact:** High - Data inconsistency between item_progress and session_state tables.

**Fix Required:** Use database transactions or implement idempotent operations with proper error handling.

---

## 13. DESIGN FLAW: Potential Lost Update in `update_after_attempt()`

### Issue: Race Condition in Daily Stats Updates

**Location:** `bot/services/progress_service.py` - `update_after_attempt()` (lines 17-35)

```17:35:bot/services/progress_service.py
async def update_after_attempt(self, user_id: int, level: int, is_correct: bool, is_first_try: bool) -> int:
    today = date.today().isoformat()
    current_stats = await self.daily_stats_repository.get_stats(user_id, today)
    streak = current_stats["streak"] if current_stats else 0
    streak = streak + 1 if is_correct else 0
    attempts = 1
    correct = 1 if is_correct else 0
    first_try_total = 1 if is_first_try else 0
    first_try_errors = 1 if is_first_try and not is_correct else 0
    await self.daily_stats_repository.update_stats(
        user_id,
        today,
        attempts,
        correct,
        streak,
        first_try_total=first_try_total,
        first_try_errors=first_try_errors,
    )
    return streak
```

**Problem:**
1. Read current stats
2. Calculate new streak (read-modify-write pattern)
3. Update stats using `ON CONFLICT ... DO UPDATE` which adds to existing values

**Race Condition:**
- If two attempts are processed simultaneously, both read the same `streak` value
- Both calculate `streak + 1` based on the same base value
- The final streak might be incorrect

**Note:** The `update_stats()` method does use `ON CONFLICT` with increment (`attempts+excluded.attempts`), but streak is **set** not incremented (`streak=excluded.streak`), which could overwrite a concurrently updated value.

**Impact:** Medium - Daily stats may show incorrect streak values under concurrent load.

**Fix Required:** Use atomic increment for streak calculation or implement proper transaction isolation.

---

## Summary of Severity

| Flaw | Severity | Impact Area |
|------|----------|-------------|
| 1. Race Conditions in Revision Logic | **CRITICAL** | Data integrity, learning effectiveness |
| 2. Missing Transaction Boundaries | **HIGH** | Data consistency |
| 3. Inconsistent `learn_correct_count` Handling | **MEDIUM** | Learning phase logic |
| 4. Wrong Answer Learning Phase Logic | **MEDIUM** | Learning effectiveness |
| 5. Inefficient Connection Lock | **LOW-MEDIUM** | Performance, concurrency |
| 6. No Optimistic Locking | **MEDIUM** | Lost updates |
| 7. Stage 3 Items Never Reviewed | **MEDIUM** | Spaced repetition effectiveness |
| 8. Inconsistent Session State Updates | **MEDIUM** | Session integrity |
| 9. Missing Validation | **LOW** | Edge cases, robustness |
| 10. Separation of Concerns | **MEDIUM** | Maintainability |
| 11. Non-Atomic Multi-Step Operations | **CRITICAL** | Session state corruption |
| 12. Order of Operations Dependency | **HIGH** | Data consistency |
| 13. Lost Update in Daily Stats | **MEDIUM** | Statistics accuracy |

---

## Recommended Priority Fixes

### Immediate (Critical) - Fix Before Production
1. **Fix race conditions in `record_correct()` and `record_wrong()`** - Use transactions or atomic SQL operations (SQL-level increments)
2. **Wrap voice handler operations in transactions** - Make `record_correct()`/`record_wrong()`, `increment_correct()`/`increment_wrong_total()`, and `advance_item()` atomic

### High Priority
3. **Add transaction boundaries** - Ensure all multi-step database operations use explicit transactions
4. **Fix order-of-operations dependencies** - Implement proper error handling and rollback for sequence-dependent operations
5. **Fix `learn_correct_count` reset logic** - Consider whether wrong answers during learning should reset progress

### Medium Priority
6. **Implement long-term review for stage 3 items** - Add periodic reviews for "mastered" items
7. **Refactor revision logic into a service layer** - Separate business logic from data access
8. **Implement optimistic locking** - Add version/timestamp checks to prevent lost updates
9. **Fix daily stats streak race condition** - Use atomic operations for streak calculation

### Low Priority
10. **Add validation and bounds checking** - Prevent invalid state transitions
11. **Review and optimize connection locking** - Clarify or remove misleading connection-level locks

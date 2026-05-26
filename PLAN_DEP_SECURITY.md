# Dependency Security Remediation Plan

**Based on**: Dependency Supply-Chain Security Audit (2026-05-25)  
**Goal**: Fix all High and Medium dependency-level findings

---

## Phase 1 — Tighten version pins (Medium — R-1)

**Summary**: Replace loose `>=` pins with tighter ranges to prevent accidental upgrades to breaking or unpatched versions.

### Files changed
| File | Change |
|------|--------|
| `requirements.txt` | `langchain>=1.0.0` → `langchain>=1.3.0,<2.0.0` |
| `requirements.txt` | `langgraph>=1.0.0` → `langgraph>=1.2.0,<1.3.0` |
| `requirements.txt` | `Pillow>=10.0.0` → `Pillow>=12.2.0` |

### Verification
```bash
source .venv/bin/activate && pip install -r requirements.txt && python3 run_tests.py --unit
```

---

## Phase 2 — Restrict env vars in MCP subprocess (High — L-2 fix)

**Summary**: Replace `env=dict(os.environ)` with a whitelist of only needed variables. Resolves existing L-2 finding, elevated to HIGH by the dependency audit (any compromised transitive dep in the MCP subprocess's web stack would have access to all secrets).

### Files changed
| File | Change |
|------|--------|
| `src/agents.py` | `env=dict(os.environ)` → whitelist of `PATH`, `HOME`, `DBUS_SESSION_BUS_ADDRESS`, `LANG` |

### Verification
```bash
source .venv/bin/activate && python3 -c "from src.agents import Agents; import asyncio; asyncio.run(Agents().start()); print('MCP subprocess started OK')"
```
(Requires Ollama running. Unit tests still pass without it.)

---

## Phase 3 — Add pip-audit to test suite (High — R-4)

**Summary**: Run `pip-audit --requirement requirements.txt` as part of the unit test suite in `run_tests.py`, or as a separate check. Catches new CVEs in dependencies on every test run.

### Files changed
| File | Change |
|------|--------|
| `run_tests.py` | Add `--audit` flag and/or automatic pip-audit check before test discovery |

### Verification
```bash
source .venv/bin/activate && python3 run_tests.py --audit
# Expected: "No known vulnerabilities found" + normal test summary
```

---

## Phase 4 — Hash-pinned lockfile (High — R-2)

**Summary**: Generate `requirements.lock.txt` with hash pins using `pip-compile --generate-hashes`. Prevents supply-chain attacks where a compromised PyPI upload passes version constraints but has different content.

### Files changed
| File | Change |
|------|--------|
| `requirements.lock.txt` | Create (new) |
| `.gitignore` | Ensure `.lock.txt` is NOT ignored (committed intentionally) |

### Generation
```bash
source .venv/bin/activate && pip install pip-tools && pip-compile --generate-hashes -o requirements.lock.txt
```

### Verification
```bash
source .venv/bin/activate && pip install --require-hashes -r requirements.lock.txt
```

---

## Phase 5 — Update SECURITY_AUDIT.md

**Summary**: Add new D-1 finding (dependency supply-chain) and update L-2 severity, counts, and action plan.

### Files changed
| File | Change |
|------|--------|
| `SECURITY_AUDIT.md` | Add D-1, update L-2 → HIGH, update summary counts, add to action plan |

---

## Dependency graph

```
Phase 1 (version pins) ──┐
                          ├── all independent
Phase 2 (L-2 env fix) ───┤
                          │
Phase 3 (pip-audit) ──────┤
                          │
Phase 4 (lockfile) ───────┤
                          │
Phase 5 (security md) ────┘
```

All phases are independent and can be executed in any order.

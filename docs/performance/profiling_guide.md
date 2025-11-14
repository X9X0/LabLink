# LabLink Performance Profiling Guide

**Date:** 2025-11-14
**Branch:** `claude/phase-3-production-hardening-co-011RTGZXBncqa4Zmo1NGNNZe`
**Purpose:** Guide for profiling LabLink critical paths to identify performance bottlenecks

---

## Overview

This guide covers profiling tools and techniques for analyzing LabLink performance. Use profiling to:
- Identify CPU-bound operations
- Find I/O bottlenecks
- Optimize critical paths
- Validate optimization efforts

**Profiling vs. Benchmarking:**
- **Benchmarks** (baseline_metrics.md): Measure overall operation time
- **Profiling**: Break down time spent in each function/line

---

## Quick Start

### 1. Profile a Specific Operation

```python
import cProfile
import pstats
from server.security.auth import hash_password

# Profile password hashing
profiler = cProfile.Profile()
profiler.enable()

hash_password("TestPassword123!")

profiler.disable()
stats = pstats.Stats(profiler)
stats.sort_stats('cumulative')
stats.print_stats(20)  # Top 20 functions
```

### 2. Profile with Decorator

```python
from server.utils.profiling import profile

@profile
def my_slow_function():
    # Your code here
    pass
```

### 3. Profile Entire Script

```bash
python -m cProfile -o output.prof server/main.py
python -m pstats output.prof
```

---

## Profiling Tools

### 1. cProfile (Built-in)

**Best for:** Finding which functions consume the most time

**Usage:**
```python
import cProfile
import pstats

profiler = cProfile.Profile()
profiler.enable()

# Code to profile
result = some_expensive_operation()

profiler.disable()
stats = pstats.Stats(profiler)
stats.sort_stats('cumulative')  # Sort by cumulative time
stats.print_stats(30)  # Print top 30 functions
```

**Output Columns:**
- `ncalls`: Number of calls
- `tottime`: Total time in function (excluding subcalls)
- `percall`: tottime / ncalls
- `cumtime`: Cumulative time (including subcalls)
- `percall`: cumtime / ncalls
- `filename:lineno(function)`: Function location

**Example Output:**
```
   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
        1    0.000    0.000    0.263    0.263 auth.py:45(hash_password)
        1    0.263    0.263    0.263    0.263 {bcrypt.hashpw}
```

---

### 2. line_profiler (Line-by-Line)

**Best for:** Finding slow lines within a function

**Installation:**
```bash
pip install line_profiler
```

**Usage:**
```python
from line_profiler import LineProfiler

profiler = LineProfiler()
profiler.add_function(my_function)
profiler.enable()

my_function()

profiler.disable()
profiler.print_stats()
```

**Decorator Usage:**
```python
@profile  # Requires kernprof
def slow_function():
    # Line-by-line timing will be shown
    pass
```

**Run with kernprof:**
```bash
kernprof -l -v your_script.py
```

**Example Output:**
```
Line #      Hits         Time  Per Hit   % Time  Line Contents
==============================================================
    45         1        100.0    100.0     38.0      x = expensive_operation()
    46         1        150.0    150.0     57.0      y = another_operation(x)
    47         1         13.0     13.0      5.0      return x + y
```

---

### 3. py-spy (Sampling Profiler)

**Best for:** Profiling running applications without code changes

**Installation:**
```bash
pip install py-spy
```

**Usage:**
```bash
# Profile running process
py-spy top --pid 12345

# Generate flamegraph
py-spy record -o profile.svg -- python server/main.py

# Profile for duration
py-spy record --duration 60 --pid 12345
```

**Advantages:**
- ✅ No code modification required
- ✅ Low overhead (sampling-based)
- ✅ Works on running processes
- ✅ Generates visual flamegraphs

---

### 4. memory_profiler (Memory Usage)

**Best for:** Finding memory leaks and high memory operations

**Installation:**
```bash
pip install memory_profiler
```

**Usage:**
```python
from memory_profiler import profile

@profile
def memory_intensive_function():
    large_list = [0] * (10 ** 6)
    return large_list
```

**Run:**
```bash
python -m memory_profiler your_script.py
```

**Example Output:**
```
Line #    Mem usage    Increment   Line Contents
================================================
    10     50.0 MiB     50.0 MiB   large_list = [0] * (10 ** 6)
    11     50.0 MiB      0.0 MiB   return large_list
```

---

## Critical Paths to Profile

### 1. User Login Flow

**Path:**
```
1. Password verification (server/security/auth.py::verify_password)
2. TOTP verification (server/security/mfa.py::verify_totp_token)
3. Session creation (server/security/auth.py::SessionManager.create_session)
4. Token generation (server/security/auth.py::create_access_token)
```

**Profile Script:**
```python
import cProfile
import pstats
from server.security.auth import hash_password, verify_password, create_access_token
from server.security.mfa import generate_totp_secret, verify_totp_token, get_current_totp_token

# Profile complete login flow
profiler = cProfile.Profile()
profiler.enable()

# Simulate login
password = "TestPassword123!"
hashed = hash_password(password)
verified = verify_password(password, hashed)

# MFA
secret = generate_totp_secret()
token = get_current_totp_token(secret)
mfa_verified = verify_totp_token(secret, token)

# Token generation
access_token = create_access_token(
    subject="testuser",
    additional_claims={"role": "admin"}
)

profiler.disable()
stats = pstats.Stats(profiler)
stats.sort_stats('cumulative')
stats.print_stats(30)
```

**Expected Bottlenecks:**
- ✅ `bcrypt.hashpw` - ~263ms (intentional)
- ✅ `pyotp.TOTP.verify` - ~0.5ms
- ❓ Token generation - profile to confirm <1ms

---

### 2. Command Execution Flow

**Path:**
```
1. Model validation (server/database/models.py::CommandRecord)
2. Equipment command execution (equipment-specific)
3. Command logging (server/database/manager.py::log_command)
4. Response serialization (Pydantic model_dump)
```

**Profile Script:**
```python
import cProfile
import pstats
import tempfile
from pathlib import Path
from server.database.manager import DatabaseManager
from server.database.models import CommandRecord, DatabaseConfig

# Setup
temp_dir = tempfile.mkdtemp()
db_path = str(Path(temp_dir) / "profile.db")
config = DatabaseConfig(db_path=db_path)
manager = DatabaseManager(config=config)
manager.initialize()

# Profile command logging
profiler = cProfile.Profile()
profiler.enable()

for i in range(100):
    record = CommandRecord(
        equipment_id=f"scope-{i % 10}",
        equipment_type="oscilloscope",
        command="*IDN?",
        response=f"RIGOL TECHNOLOGIES DS1054Z {i}",
        execution_time_ms=42.5 + i
    )
    manager.log_command(record)

profiler.disable()
stats = pstats.Stats(profiler)
stats.sort_stats('cumulative')
stats.print_stats(30)
```

**Expected Bottlenecks:**
- ❓ SQLite write operations - profile to confirm <10ms
- ❓ Pydantic validation - should be <1μs (per benchmarks)
- ❓ JSON serialization - profile to confirm

---

### 3. Backup Creation Flow

**Path:**
```
1. Model validation (server/backup/models.py::BackupRequest)
2. File collection (server/backup/manager.py::_collect_files)
3. Archive creation (tarfile operations)
4. Compression (gzip/bz2/xz)
5. Verification (optional hash calculation)
```

**Profile Script:**
```python
import cProfile
import pstats
import tempfile
import asyncio
from pathlib import Path
from server.backup.manager import BackupManager
from server.backup.models import BackupConfig, BackupRequest, BackupType, CompressionType

# Setup
temp_dir = tempfile.mkdtemp()
config_dir = Path(temp_dir) / "config"
config_dir.mkdir()

# Create realistic test data
for i in range(10):
    (config_dir / f"settings_{i}.json").write_text('{"test": true}' * 1000)

config = BackupConfig(backup_dir=temp_dir)
manager = BackupManager(config)

# Profile backup creation
async def profile_backup():
    request = BackupRequest(
        backup_type=BackupType.CONFIG,
        compression=CompressionType.GZIP,
        description="Profile test",
        verify_after_backup=True
    )

    profiler = cProfile.Profile()
    profiler.enable()

    result = await manager.create_backup(request)

    profiler.disable()
    return profiler

profiler = asyncio.run(profile_backup())
stats = pstats.Stats(profiler)
stats.sort_stats('cumulative')
stats.print_stats(30)
```

**Expected Bottlenecks:**
- ❓ File I/O operations - profile to confirm
- ❓ Compression - compare gzip vs bz2 vs xz
- ❓ Hash calculation (SHA256) - profile to confirm

---

## Profiling Workflow

### Step 1: Identify Slow Operation

Use benchmarks to find operations >10ms (or slower than expected).

```bash
# Run benchmarks
pytest tests/performance/ --benchmark-only
```

### Step 2: Profile the Operation

Use cProfile to find which function(s) consume the most time.

```python
# Profile the slow operation
profiler = cProfile.Profile()
profiler.enable()
slow_operation()
profiler.disable()
stats = pstats.Stats(profiler)
stats.sort_stats('cumulative')
stats.print_stats(20)
```

### Step 3: Drill Down with line_profiler

If a specific function is slow, profile it line-by-line.

```bash
# Add @profile decorator to the function
kernprof -l -v script.py
```

### Step 4: Optimize

Make targeted optimizations based on profiling data:
- Cache expensive computations
- Reduce redundant operations
- Use more efficient algorithms
- Batch database operations
- Add database indexes
- Use async for I/O operations

### Step 5: Validate

Re-run benchmarks to confirm optimization:

```bash
pytest tests/performance/ --benchmark-only --benchmark-compare
```

---

## Visualization Tools

### 1. SnakeViz (Interactive Profiler)

**Installation:**
```bash
pip install snakeviz
```

**Usage:**
```bash
python -m cProfile -o output.prof script.py
snakeviz output.prof
```

Opens interactive visualization in browser with:
- Icicle chart (top-down call hierarchy)
- Sunburst chart (circular hierarchy)
- Function table with sorting

---

### 2. FlameGraph (py-spy)

**Generate flamegraph:**
```bash
py-spy record -o flamegraph.svg -- python server/main.py
```

**Interpretation:**
- X-axis: Alphabetical function order (not time!)
- Y-axis: Stack depth
- Width: Time spent in function
- Color: Random (for distinction)

**Finding Bottlenecks:**
- Look for wide bars at the top (leaf functions)
- Look for tall stacks (deep call chains)
- Click on bars to zoom and filter

---

### 3. Pstats Browser

**Built-in statistics browser:**
```python
import pstats

stats = pstats.Stats('output.prof')
stats.strip_dirs()
stats.sort_stats('cumulative')
stats.print_stats(30)
stats.print_callers(10)  # Who calls these functions?
stats.print_callees(10)  # What do these functions call?
```

---

## Common Performance Patterns

### 1. Database N+1 Queries

**Symptom:** Many small queries instead of one large query
**Detection:** Profile shows many `execute()` calls
**Solution:** Use joins, batch queries, or eager loading

**Example:**
```python
# Bad: N+1 queries
for equipment_id in equipment_ids:
    commands = db.get_commands(equipment_id)  # N queries

# Good: Single query
commands = db.get_commands_batch(equipment_ids)  # 1 query
```

---

### 2. Unnecessary Model Validation

**Symptom:** High cumtime in Pydantic validators
**Detection:** Profile shows repeated validation
**Solution:** Validate once, pass validated objects

**Example:**
```python
# Bad: Validate multiple times
for data in records:
    record = CommandRecord(**data)  # Validates each time
    process(record)

# Good: Validate once
validated = [CommandRecord(**data) for data in records]
for record in validated:
    process(record)
```

---

### 3. Blocking I/O in Async Code

**Symptom:** Async operations still slow
**Detection:** Profile shows blocking calls in async functions
**Solution:** Use async versions or run_in_executor

**Example:**
```python
# Bad: Blocking in async
async def backup():
    with open('file.txt') as f:  # Blocks event loop
        return f.read()

# Good: Use aiofiles
import aiofiles
async def backup():
    async with aiofiles.open('file.txt') as f:
        return await f.read()
```

---

### 4. Inefficient Data Structures

**Symptom:** High time in list operations
**Detection:** Profile shows time in `in` operator, `list.remove`, etc.
**Solution:** Use sets for membership, dicts for lookups

**Example:**
```python
# Bad: O(n) lookup
if item in large_list:  # Linear search
    pass

# Good: O(1) lookup
if item in large_set:  # Constant time
    pass
```

---

## Profiling Best Practices

### DO ✅
- Profile with realistic data sizes
- Profile with production-like workloads
- Focus on critical paths (login, commands, queries)
- Measure before and after optimizations
- Profile on target hardware when possible
- Use multiple profiling tools for different insights

### DON'T ❌
- Don't profile with empty datasets (unrealistic)
- Don't optimize without profiling first (premature optimization)
- Don't ignore async/await in profiles (check event loop)
- Don't profile debug builds (use production-like settings)
- Don't profile single iterations (use statistically significant samples)

---

## Integration with CI/CD

### Automated Profiling

Add profiling to CI for major changes:

```yaml
# .github/workflows/profile.yml
name: Performance Profiling

on:
  pull_request:
    branches: [main]
    paths:
      - 'server/**'
      - 'shared/**'

jobs:
  profile:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -r requirements-test.txt
          pip install py-spy

      - name: Profile critical paths
        run: |
          py-spy record -o flamegraph.svg -- python scripts/profile_critical_paths.py

      - name: Upload flamegraph
        uses: actions/upload-artifact@v4
        with:
          name: performance-profile
          path: flamegraph.svg
```

---

## Continuous Monitoring

### Production Profiling

For production systems, use low-overhead sampling:

```python
# server/utils/profiling.py (conditional profiling)
import os
import cProfile
from functools import wraps

PROFILE_ENABLED = os.getenv('LABLINK_PROFILING', 'false').lower() == 'true'

def profile_if_enabled(func):
    """Profile function if LABLINK_PROFILING=true."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not PROFILE_ENABLED:
            return func(*args, **kwargs)

        profiler = cProfile.Profile()
        profiler.enable()
        try:
            result = func(*args, **kwargs)
        finally:
            profiler.disable()
            stats = pstats.Stats(profiler)
            stats.dump_stats(f'/tmp/{func.__name__}.prof')
        return result
    return wrapper
```

**Usage:**
```bash
# Enable profiling in production (temporarily)
export LABLINK_PROFILING=true
python server/main.py

# Collect profiles
scp server:/tmp/*.prof ./profiles/
snakeviz profiles/login.prof
```

---

## Troubleshooting Profiles

### Profile is Empty

**Cause:** Function executed too quickly
**Solution:** Increase iterations or use line_profiler

### Profile Shows No Bottleneck

**Cause:** Operation is I/O bound, not CPU bound
**Solution:** Use py-spy or async profiling tools

### Profile Shows Unexpected Functions

**Cause:** Measuring wrong operation or including overhead
**Solution:** Narrow profiling scope, exclude setup/teardown

---

## Next Steps

After profiling, refer to:
1. **baseline_metrics.md** - Compare against established baselines
2. **Optimization guides** - Apply targeted optimizations
3. **Re-benchmark** - Validate improvements

**Regular Profiling Schedule:**
- After major feature additions
- When benchmarks show regression (>20% slower)
- Before production releases
- When users report performance issues

---

**Document Version:** 1.0
**Last Updated:** 2025-11-14
**Next Review:** After first profiling session or Phase 3 completion

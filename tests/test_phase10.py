"""
Phase 10: Final Validation — Standalone Test
Run with: python tests/test_phase10.py
(No pytest required, no API calls, validates project completeness)

Tests:
  1. README.md is complete (required sections present)
  2. docker-compose.yml is valid YAML with correct services
  3. Dockerfile exists and has required directives
  4. scripts/setup.sh exists and has required commands
  5. .env.example covers all required config keys
  6. requirements.txt has all required packages
  7. Static files endpoint is configured in main.py
  8. All phase test files exist (phase 1–9)
"""

import os
import sys
import types
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ---------------------------------------------------------------------------
# Stub heavy optional dependencies so conftest.py autouse fixtures can run
# (mirrors the pattern used in test_phase8.py / test_phase9.py)
# ---------------------------------------------------------------------------
os.environ.setdefault("GEMINI_API_KEY", "fake-test-key-for-testing")
os.environ["MATHPIX_ENABLED"] = "false"

for _mod in ["google", "google.generativeai", "fitz", "rapidfuzz", "rapidfuzz.fuzz", "openai"]:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

_motor_mod = types.ModuleType("motor.motor_asyncio")
_motor_mod.AsyncIOMotorClient = MagicMock
if "motor" not in sys.modules:
    sys.modules["motor"] = MagicMock()
if "motor.motor_asyncio" not in sys.modules:
    sys.modules["motor.motor_asyncio"] = _motor_mod

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def print_header(text):
    print(f"\n{text}")
    print("=" * 70)


def print_step(num, text):
    print(f"\n{num}️⃣  {text}...")


def print_ok(text=""):
    if text:
        print(f"✅ {text}")
    else:
        print("✅")


def print_error(text):
    print(f"❌ {text}")
    sys.exit(1)


# ============================================================================
# Test 1 — README.md completeness
# ============================================================================

def test_readme_completeness():
    print_step(1, "README.md completeness check")

    readme_path = os.path.join(REPO_ROOT, "README.md")
    if not os.path.exists(readme_path):
        print_error("README.md not found")

    with open(readme_path, encoding="utf-8") as f:
        content = f.read()

    required_sections = [
        ("Project description / title", "SGK"),
        ("Stack table", "| Layer"),
        ("Prerequisites section", "Python"),
        ("Gemini API key instructions", "aistudio.google.com"),
        ("Mathpix key instructions", "Mathpix"),
        ("Installation steps", "pip install"),
        ("Docker usage", "docker-compose"),
        ("API endpoints table", "/api/v1/books"),
        ("Example curl commands", "curl"),
        ("Testing section", "pytest"),
        ("Accuracy notes", "85"),
        ("Cost estimation / free tier info", "250"),
    ]

    for label, keyword in required_sections:
        if keyword not in content:
            print_error(f"README.md missing '{label}' (expected keyword: '{keyword}')")
        print_ok(f"README has: {label}")

    # Check file is substantial (> 3KB)
    size_kb = len(content.encode("utf-8")) / 1024
    if size_kb < 3:
        print_error(f"README.md too short ({size_kb:.1f} KB), expected > 3 KB")
    print_ok(f"README.md size: {size_kb:.1f} KB")


# ============================================================================
# Test 2 — docker-compose.yml validity
# ============================================================================

def test_docker_compose():
    print_step(2, "docker-compose.yml structure validation")

    dc_path = os.path.join(REPO_ROOT, "docker-compose.yml")
    if not os.path.exists(dc_path):
        print_error("docker-compose.yml not found")

    try:
        import yaml  # pyyaml is not in requirements; fall back to manual check
    except ImportError:
        yaml = None

    with open(dc_path, encoding="utf-8") as f:
        raw = f.read()

    # Required content checks (works without yaml)
    required_items = [
        ("mongo service", "mongo:"),
        ("app service", "app:"),
        ("MongoDB 7 image", "mongo:7"),
        ("Dockerfile build instruction", "build: ."),
        ("env_file reference", "env_file"),
        ("storage volume mount", "storage"),
        ("data volume mount", "data"),
        ("named volume for MongoDB", "mongo_data"),
        ("depends_on", "depends_on"),
    ]

    for label, keyword in required_items:
        if keyword not in raw:
            print_error(f"docker-compose.yml missing: {label} (keyword: '{keyword}')")
        print_ok(f"docker-compose.yml has: {label}")

    # Try YAML parse if available
    if yaml:
        try:
            doc = yaml.safe_load(raw)
            services = doc.get("services", {})
            assert "mongo" in services, "mongo service missing"
            assert "app" in services, "app service missing"
            print_ok("docker-compose.yml YAML parses correctly")
        except yaml.YAMLError as e:
            print_error(f"docker-compose.yml YAML parse error: {e}")
    else:
        print_ok("PyYAML not installed — skipping YAML parse (content checks passed)")


# ============================================================================
# Test 3 — Dockerfile existence and directives
# ============================================================================

def test_dockerfile():
    print_step(3, "Dockerfile existence and required directives")

    df_path = os.path.join(REPO_ROOT, "Dockerfile")
    if not os.path.exists(df_path):
        print_error("Dockerfile not found")

    with open(df_path, encoding="utf-8") as f:
        content = f.read()

    required = [
        ("Python 3.11-slim base image", "FROM python:3.11"),
        ("WORKDIR instruction", "WORKDIR"),
        ("requirements.txt copy", "requirements.txt"),
        ("pip install", "pip install"),
        ("application code copy", "COPY . ."),
        ("EXPOSE port", "EXPOSE"),
        ("uvicorn CMD", "uvicorn"),
        ("host 0.0.0.0", "0.0.0.0"),
    ]

    for label, keyword in required:
        if keyword not in content:
            print_error(f"Dockerfile missing: {label} (keyword: '{keyword}')")
        print_ok(f"Dockerfile has: {label}")


# ============================================================================
# Test 4 — scripts/setup.sh existence and required commands
# ============================================================================

def test_setup_script():
    print_step(4, "scripts/setup.sh existence and required commands")

    script_path = os.path.join(REPO_ROOT, "scripts", "setup.sh")
    if not os.path.exists(script_path):
        print_error(f"scripts/setup.sh not found at {script_path}")

    with open(script_path, encoding="utf-8") as f:
        content = f.read()

    required = [
        ("shebang", "#!/"),
        (".env creation from .env.example", ".env.example"),
        ("storage directory creation", "storage"),
        ("data directory creation", "data/books"),
        ("pip install -r requirements.txt", "pip install"),
        ("Docker Compose MongoDB start", "docker-compose"),
        ("Next steps / instructions", "Next steps"),
    ]

    for label, keyword in required:
        if keyword not in content:
            print_error(f"setup.sh missing: {label} (keyword: '{keyword}')")
        print_ok(f"setup.sh has: {label}")


# ============================================================================
# Test 5 — .env.example covers required keys
# ============================================================================

def test_env_example():
    print_step(5, ".env.example has all required config keys")

    env_path = os.path.join(REPO_ROOT, ".env.example")
    if not os.path.exists(env_path):
        # Fallback: check .env (might be on some machines)
        env_path = os.path.join(REPO_ROOT, ".env")
        if not os.path.exists(env_path):
            print_error(".env.example (or .env) not found")

    with open(env_path, encoding="utf-8") as f:
        content = f.read()

    required_keys = [
        "MONGO_URL",
        "MONGO_DB",
        "GEMINI_API_KEY",
        "GEMINI_MODEL",
        "STORAGE_PATH",
        "MAX_FILE_SIZE_MB",
        "PORT",
    ]

    for key in required_keys:
        if key not in content:
            print_error(f".env.example missing required key: {key}")
        print_ok(f".env.example has: {key}")


# ============================================================================
# Test 6 — requirements.txt has all required packages
# ============================================================================

def test_requirements():
    print_step(6, "requirements.txt has all required packages")

    req_path = os.path.join(REPO_ROOT, "requirements.txt")
    if not os.path.exists(req_path):
        print_error("requirements.txt not found")

    with open(req_path, encoding="utf-8") as f:
        content = f.read().lower()

    required_packages = [
        ("fastapi", "fastapi"),
        ("uvicorn", "uvicorn"),
        ("motor (async MongoDB)", "motor"),
        ("pymongo", "pymongo"),
        ("pydantic", "pydantic"),
        ("pydantic-settings", "pydantic-settings"),
        ("python-dotenv", "python-dotenv"),
        ("python-multipart (file upload)", "python-multipart"),
        ("httpx (async HTTP)", "httpx"),
        ("pymupdf (PDF rendering)", "pymupdf"),
        ("pillow (image processing)", "pillow"),
        ("google-generativeai (Gemini)", "google-generativeai"),
        ("pytest", "pytest"),
        ("reportlab (test PDF fixtures)", "reportlab"),
    ]

    for label, pkg in required_packages:
        if pkg not in content:
            print_error(f"requirements.txt missing: {label} (package: '{pkg}')")
        print_ok(f"requirements.txt has: {label}")


# ============================================================================
# Test 7 — app/main.py has static files and all routers registered
# ============================================================================

def test_main_app_config():
    print_step(7, "app/main.py: static files + all controllers registered")

    main_path = os.path.join(REPO_ROOT, "app", "main.py")
    if not os.path.exists(main_path):
        print_error("app/main.py not found")

    with open(main_path, encoding="utf-8") as f:
        content = f.read()

    required = [
        ("StaticFiles mount", "StaticFiles"),
        ("/static mount path", '"/static"'),
        ("book_controller registered", "book_controller"),
        ("chapter_controller registered", "chapter_controller"),
        ("lesson_controller registered", "lesson_controller"),
        ("search_controller registered", "search_controller"),
        ("/health endpoint", "/health"),
        ("startup indexes", "create_indexes"),
        ("lesson_contents text index", "lesson_contents"),
    ]

    for label, keyword in required:
        if keyword not in content:
            print_error(f"app/main.py missing: {label} (keyword: '{keyword}')")
        print_ok(f"app/main.py has: {label}")


# ============================================================================
# Test 8 — All phase test files exist (phase 1–9)
# ============================================================================

def test_all_phase_files_exist():
    print_step(8, "All phase test files exist (test_phase1.py through test_phase9.py)")

    tests_dir = os.path.join(REPO_ROOT, "tests")
    docs_dir = os.path.join(REPO_ROOT, "app", "docs", "test")

    for i in range(1, 10):
        test_file = os.path.join(tests_dir, f"test_phase{i}.py")
        if not os.path.exists(test_file):
            print_error(f"Missing: tests/test_phase{i}.py")
        print_ok(f"tests/test_phase{i}.py exists")

        doc_file = os.path.join(docs_dir, f"PHASE{i}_TESTING.md")
        if not os.path.exists(doc_file):
            print_error(f"Missing: app/docs/test/PHASE{i}_TESTING.md")
        print_ok(f"app/docs/test/PHASE{i}_TESTING.md exists")


# ============================================================================
# Main runner
# ============================================================================

def main():
    print_header("PHASE 10: Final Validation — Project Completeness")

    results = []

    def run(fn, name):
        try:
            fn()
            results.append((name, True))
        except SystemExit:
            results.append((name, False))
        except Exception as e:
            print(f"❌ {name}: unexpected error — {e}")
            results.append((name, False))

    run(test_readme_completeness, "README.md completeness")
    run(test_docker_compose, "docker-compose.yml structure")
    run(test_dockerfile, "Dockerfile directives")
    run(test_setup_script, "setup.sh commands")
    run(test_env_example, ".env.example keys")
    run(test_requirements, "requirements.txt packages")
    run(test_main_app_config, "app/main.py config")
    run(test_all_phase_files_exist, "all phase test files exist")

    passed = sum(1 for _, ok in results if ok)
    total = len(results)

    print_header(f"{'✅' if passed == total else '⚠️ '} {passed}/{total} TESTS PASSED")
    print("\n📊 SUMMARY:")
    for name, ok in results:
        icon = "✅" if ok else "❌"
        print(f"  {icon} {name}")

    if passed < total:
        print(f"\n❌ {total - passed} test(s) failed.")
        sys.exit(1)
    else:
        print("\n🎉 PROJECT COMPLETE — all phase-10 checks passed!")


if __name__ == "__main__":
    main()

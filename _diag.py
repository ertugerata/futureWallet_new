import sys
import subprocess

print("=== ENV ===")
print("python:", sys.executable)
print("version:", sys.version)
print("prefix:", sys.prefix)
print("path[0:4]:", sys.path[:4])

print("\n=== PIP CHECK ===")
try:
    import importlib.metadata as md
    print("fastapi:", md.version("fastapi") if md.version("fastapi") else "NOT FOUND")
    print("jinja2:", md.version("jinja2") if md.version("jinja2") else "NOT FOUND")
    print("sqlalchemy:", md.version("sqlalchemy") if md.version("sqlalchemy") else "NOT FOUND")
except Exception as e:
    print("metadata hatası:", e)

print("\n=== FALLBACK PIP SHOW ===")
r = subprocess.run([sys.executable, "-m", "pip", "show", "fastapi"], capture_output=True, text=True)
print("pip show fastapi rc:", r.returncode)
print(r.stdout[-300:] if r.stdout else r.stderr[-300:])

print("\n=== SITE-PACKAGES ===")
import site
print("site-packages paths:")
for p in site.getsitepackages():
    print(" ", p)

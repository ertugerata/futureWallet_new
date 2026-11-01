import sys, traceback
sys.path.insert(0, '.')
try:
    from api.app import app
    print("OK:", app.title)
    print("Routes (first 10):")
    for r in app.routes:
        if hasattr(r, 'path'):
            print(" ", r.path)
except Exception as e:
    print("ERROR:", e)
    traceback.print_exc()

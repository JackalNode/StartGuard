"""
debug_scan.py - Run this from the SmartGuard root folder to see
exactly what raw names and sources are being read for duplicates.
Usage: python debug_scan.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.database import ProcessDatabase
from core.scanner import StartupScanner
from platforms.windows import (
    read_registry_hkcu, read_registry_hklm,
    read_task_manager_startup, read_startup_folder
)

print("=" * 60)
print("RAW ITEMS FROM EACH SOURCE (before deduplication)")
print("=" * 60)

sources = [
    ("registry_hkcu",   read_registry_hkcu),
    ("registry_hklm",   read_registry_hklm),
    ("task_manager",    read_task_manager_startup),
    ("startup_folder",  read_startup_folder),
]

all_raw = []
for source_name, fn in sources:
    try:
        items = fn()
        print(f"\n--- {source_name} ({len(items)} items) ---")
        for item in items:
            print(f"  raw_name={repr(item.raw_name)!s:40} source_path={repr(item.source_path)!s:40} enabled={item.enabled}")
            all_raw.append(item)
    except PermissionError:
        print(f"  [Permission denied]")
    except Exception as e:
        print(f"  [Error: {e}]")

print("\n" + "=" * 60)
print("DEDUP KEYS (what the deduplicator sees)")
print("=" * 60)

db = ProcessDatabase()
scanner = StartupScanner(db)

from collections import defaultdict
key_map = defaultdict(list)
for item in all_raw:
    key = scanner._dedup_key(item.raw_name)
    key_map[key].append((item.source, item.raw_name, item.enabled))

print("\nItems that share a dedup key (potential duplicates):")
for key, entries in sorted(key_map.items()):
    if len(entries) > 1:
        print(f"\n  key={repr(key)}")
        for source, raw, enabled in entries:
            print(f"    source={source:20} raw_name={repr(raw):35} enabled={enabled}")


print("\n" + "=" * 60)
print("AFTER DEDUPLICATION (what the app actually shows)")
print("=" * 60)

db = ProcessDatabase()
scanner = StartupScanner(db)
result = scanner.scan()
print(f"\nTotal items after dedup: {len(result.items)}\n")
for item in sorted(result.items, key=lambda i: i.friendly_name.lower()):
    print(f"  {item.friendly_name:40} source={item.source:20} enabled={item.enabled}")

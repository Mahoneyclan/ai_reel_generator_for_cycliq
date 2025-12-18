#!/usr/bin/env python3
"""Analyze how enriched.csv pairs are structured."""

import csv
from pathlib import Path
from collections import defaultdict

# Update path to your enriched.csv
csv_path = Path("/Volumes/GDrive/Fly_Projects/2025-12-18 Highvale - Mount Cootha/working/enriched.csv")

if not csv_path.exists():
    print("Update csv_path in script to point to your enriched.csv")
    exit(1)

with csv_path.open() as f:
    rows = list(csv.DictReader(f))

print(f"Total rows in enriched.csv: {len(rows)}")

# Check cameras
cameras = defaultdict(int)
for r in rows:
    cameras[r.get("camera", "")] += 1
print(f"\nCameras: {dict(cameras)}")

# Check pairing
all_indices = {r["index"] for r in rows}
index_map = {r["index"]: r for r in rows}

with_partner = sum(1 for r in rows if r.get("partner_index"))
valid_partners = sum(1 for r in rows if r.get("partner_index") in all_indices)
print(f"\nRows with partner_index: {with_partner}/{len(rows)}")
print(f"Rows with valid partner_index: {valid_partners}/{len(rows)}")

# Check reciprocal relationships
reciprocal = 0
for r in rows:
    idx = r["index"]
    partner_idx = r.get("partner_index", "")
    if partner_idx and partner_idx in index_map:
        partner = index_map[partner_idx]
        if partner.get("partner_index") == idx:
            reciprocal += 1

print(f"Rows with reciprocal partner: {reciprocal}/{len(rows)}")
print(f"Expected complete pairs: {reciprocal // 2}")

# Build actual pairs
pairs = []
seen = set()

for r in rows:
    idx = r["index"]
    if idx in seen:
        continue
    
    partner_idx = r.get("partner_index", "")
    if not partner_idx or partner_idx not in index_map:
        continue
    
    partner = index_map[partner_idx]
    
    # Verify reciprocal
    if partner.get("partner_index") != idx:
        continue
    
    # Verify different cameras
    if r.get("camera") == partner.get("camera"):
        continue
    
    seen.add(idx)
    seen.add(partner_idx)
    pairs.append((r, partner))

print(f"\nActual valid pairs found: {len(pairs)}")
print(f"Rows in pairs: {len(seen)}")
print(f"Unpaired rows: {len(rows) - len(seen)}")

# Show sample pairs
print("\nSample pairs:")
for i, (r1, r2) in enumerate(pairs[:3]):
    print(f"\nPair {i+1}:")
    print(f"  Row 1: {r1['camera']} | {r1['index'][:40]}")
    print(f"  Row 2: {r2['camera']} | {r2['index'][:40]}")
    print(f"  Time diff: {r1.get('partner_abs_time_diff', 'N/A')}s")
    print(f"  Score 1: {r1.get('score_weighted', 'N/A')}")
    print(f"  Score 2: {r2.get('score_weighted', 'N/A')}")
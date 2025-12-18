#!/usr/bin/env python3
"""Analyze select.csv to find pairing issues."""

import csv
from pathlib import Path
from collections import defaultdict

# Update this path to your select.csv
csv_path = Path("/Volumes/GDrive/Fly_Projects/2025-12-18 Highvale - Mount Cootha/working/select.csv")

with csv_path.open() as f:
    rows = list(csv.DictReader(f))

print(f"Total rows: {len(rows)}")
print()

# Check cameras
cameras = {}
for r in rows:
    cam = r.get("camera", "")
    cameras[cam] = cameras.get(cam, 0) + 1
print(f"Cameras: {cameras}")
print()

# Check partner_index validity
all_indices = {r["index"] for r in rows}
print(f"Total unique indices: {len(all_indices)}")

with_partner = sum(1 for r in rows if r.get("partner_index"))
print(f"Rows with partner_index: {with_partner}/{len(rows)}")

valid_partners = sum(1 for r in rows if r.get("partner_index") in all_indices)
print(f"Rows with VALID partner_index: {valid_partners}/{len(rows)}")
print()

# Check reciprocal relationships
index_map = {r["index"]: r for r in rows}
reciprocal_count = 0

for r in rows:
    idx = r["index"]
    partner_idx = r.get("partner_index", "")
    
    if not partner_idx or partner_idx not in index_map:
        continue
    
    partner_row = index_map[partner_idx]
    partner_of_partner = partner_row.get("partner_index", "")
    
    if partner_of_partner == idx:
        reciprocal_count += 1

print(f"Rows with RECIPROCAL partner_index: {reciprocal_count}/{len(rows)}")
print(f"Expected pairs: {reciprocal_count // 2}")
print()

# Show first 5 rows with their partner info
print("Sample rows:")
print("-" * 100)
for i, r in enumerate(rows[:5]):
    idx = r["index"]
    partner_idx = r.get("partner_index", "")
    cam = r.get("camera", "")
    epoch = r.get("abs_time_epoch", "")
    recommended = r.get("recommended", "")
    
    partner_exists = "YES" if partner_idx in all_indices else "NO"
    
    if partner_idx and partner_idx in index_map:
        partner_cam = index_map[partner_idx].get("camera", "")
        partner_of_partner = index_map[partner_idx].get("partner_index", "")
        reciprocal = "YES" if partner_of_partner == idx else f"NO (points to {partner_of_partner[:20]})"
    else:
        partner_cam = "N/A"
        reciprocal = "N/A"
    
    print(f"Row {i}:")
    print(f"  index: {idx[:40]}")
    print(f"  camera: {cam}")
    print(f"  epoch: {epoch}")
    print(f"  recommended: {recommended}")
    print(f"  partner_index: {partner_idx[:40] if partner_idx else 'MISSING'}")
    print(f"  partner exists: {partner_exists}")
    print(f"  partner camera: {partner_cam}")
    print(f"  reciprocal: {reciprocal}")
    print()

# Find non-reciprocal pairs
print("Non-reciprocal pairs:")
print("-" * 100)
non_reciprocal = []
for r in rows[:10]:  # Check first 10
    idx = r["index"]
    partner_idx = r.get("partner_index", "")
    
    if partner_idx and partner_idx in index_map:
        partner_row = index_map[partner_idx]
        partner_of_partner = partner_row.get("partner_index", "")
        
        if partner_of_partner != idx:
            print(f"{idx[:40]} -> {partner_idx[:40]} -> {partner_of_partner[:40]}")
            non_reciprocal.append(idx)

if not non_reciprocal:
    print("All checked pairs are reciprocal!")
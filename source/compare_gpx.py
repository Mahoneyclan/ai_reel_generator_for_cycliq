import gpxpy
from pathlib import Path

ride_file = Path("/Volumes/GDrive/Fly/2025-12-06 House and Gardens/ride.gpx")
morning_file = Path("/Volumes/GDrive/Fly/2025-12-06 House and Gardens/Morning_Ride.gpx")

def summarize(path):
    try:
        with open(path) as f:
            gpx = gpxpy.parse(f)
        length = sum(trk.length_3d() for trk in gpx.tracks)
        elev_gain = sum(seg.get_uphill_downhill()[0] for trk in gpx.tracks for seg in trk.segments)
        start = gpx.tracks[0].segments[0].points[0].time
        end = gpx.tracks[0].segments[0].points[-1].time
        return (length/1000, elev_gain, (end - start), gpx)
    except Exception as e:
        return (0, 0, f"Error: {e}", None)

def compare_points_raw(gpx1, gpx2):
    pts1 = [(p.latitude, p.longitude, p.elevation, p.time)
            for trk in gpx1.tracks for seg in trk.segments for p in seg.points]
    pts2 = [(p.latitude, p.longitude, p.elevation, p.time)
            for trk in gpx2.tracks for seg in trk.segments for p in seg.points]
    if pts1 == pts2:
        return "✅ Track points are identical (raw)"
    else:
        return f"❌ Track points differ (Garmin: {len(pts1)} pts, Strava: {len(pts2)} pts)"

def compare_points_normalized(gpx1, gpx2):
    def norm_point(p):
        return (round(p.latitude, 5),   # 5 decimal places ≈ 1.1 m precision
                round(p.longitude, 5),
                round(p.elevation or 0, 1),  # 0.1 m precision
                p.time.replace(microsecond=0) if p.time else None)

    pts1 = [norm_point(p) for trk in gpx1.tracks for seg in trk.segments for p in seg.points]
    pts2 = [norm_point(p) for trk in gpx2.tracks for seg in trk.segments for p in seg.points]

    if pts1 == pts2:
        return "✅ Tracks are identical after normalization"
    else:
        for i, (a, b) in enumerate(zip(pts1, pts2)):
            if a != b:
                return f"❌ First mismatch at point {i}:\nGarmin: {a}\nStrava: {b}"
        return "❌ Tracks differ in length"

# Summaries
ride_stats, ride_gpx = summarize(ride_file)[:3], summarize(ride_file)[3]
morning_stats, morning_gpx = summarize(morning_file)[:3], summarize(morning_file)[3]

print(f"{'File':<20}{'Distance (km)':<15}{'Elevation Gain (m)':<20}{'Duration'}")
print(f"{'ride.gpx':<20}{ride_stats[0]:<15.2f}{ride_stats[1]:<20.0f}{ride_stats[2]}")
print(f"{'Morning_Ride.gpx':<20}{morning_stats[0]:<15.2f}{morning_stats[1]:<20.0f}{morning_stats[2]}")

# Comparison verdicts
if ride_gpx and morning_gpx:
    print(compare_points_raw(ride_gpx, morning_gpx))
    print(compare_points_normalized(ride_gpx, morning_gpx))

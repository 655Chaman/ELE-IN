"""
Three-Layer Paranoia Framework: Impossible Travel & Geodesic Velocity Guard
=============================================================================
- Layer 0: Computes Haversine great-circle distance and geodesic velocity (km/h)
           between consecutive account operations. Flags velocities > 800 km/h.
- Layer 1: Enforces an automatic 3-hour cooldown window when impossible travel is detected,
           preventing LinkedIn Akamai edge challenge storms and session invalidation.
           Provides strict Channel Mutex: mutes cloud background execution (inbox_sync, health checks)
           whenever the user's Chrome Extension is actively executing from their home residential connection.
- Layer 2: Human paranoia: Validates coordinate boundaries, handles missing timestamps,
           falls back to country centroids if sub-national coordinates are absent,
           and logs forensic anomalies for security auditing.
"""

import math
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, Tuple

logger = logging.getLogger(__name__)

# Max commercial aircraft velocity threshold before triggering impossible travel anomaly
MAX_CREDIBLE_VELOCITY_KMH = 800.0
# Minimum time between disparate geographic operations before velocity check applies
MIN_TIME_DELTA_SECONDS = 30.0
# Mandatory cooling period when impossible travel is flagged
IMPOSSIBLE_TRAVEL_COOLING_HOURS = 3
# Threshold in minutes to consider the extension actively running
EXTENSION_ACTIVE_WINDOW_MINUTES = 25

# Approximate latitude and longitude centroids for primary country codes
COUNTRY_CENTROIDS: Dict[str, Tuple[float, float]] = {
    "US": (37.0902, -95.7129),
    "CA": (56.1304, -106.3468),
    "GB": (55.3781, -3.4360),
    "DE": (51.1657, 10.4515),
    "FR": (46.2276, 2.2137),
    "IN": (20.5937, 78.9629),
    "AU": (-25.2744, 133.7751),
    "NL": (52.1326, 5.2913),
    "SG": (1.3521, 103.8198),
    "AE": (23.4241, 53.8478),
    "IE": (53.1424, -7.6921),
    "ES": (40.4637, -3.7492),
    "IT": (41.8719, 12.5674),
    "BR": (-14.2350, -51.9253),
    "JP": (36.2048, 138.2529),
    "CH": (46.8182, 8.2275),
    "SE": (60.1282, 18.6435),
    "NO": (60.4720, 8.4689),
    "PL": (51.9194, 19.1451),
}


class ImpossibleTravelAnomaly(Exception):
    """Raised when an operation is attempted with impossible geographic velocity."""
    pass


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Paranoia Layer 0: Calculates the great-circle distance between two points
    on the Earth using the Haversine formula.
    """
    R = 6371.0  # Earth radius in kilometers

    # Sanitize inputs
    lat1 = max(-90.0, min(90.0, float(lat1)))
    lat2 = max(-90.0, min(90.0, float(lat2)))
    lon1 = max(-180.0, min(180.0, float(lon1)))
    lon2 = max(-180.0, min(180.0, float(lon2)))

    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)

    a = (
        math.sin(d_lat / 2.0) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lon / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))
    return R * c


def resolve_geo_coordinates(
    country_code: Optional[str],
    lat: Optional[float] = None,
    lon: Optional[float] = None
) -> Optional[Tuple[float, float]]:
    """
    Paranoia Layer 2: Resolves explicit lat/lon, falling back to country centroid.
    """
    if lat is not None and lon is not None:
        try:
            return float(lat), float(lon)
        except (ValueError, TypeError):
            pass

    if country_code:
        norm_code = country_code.strip().upper()
        if "-" in norm_code:
            norm_code = norm_code.split("-")[0]
        if norm_code in COUNTRY_CENTROIDS:
            return COUNTRY_CENTROIDS[norm_code]

    return None


def calculate_geographic_velocity(
    prev_country: Optional[str],
    prev_lat: Optional[float],
    prev_lon: Optional[float],
    prev_timestamp: Optional[datetime],
    curr_country: Optional[str],
    curr_lat: Optional[float],
    curr_lon: Optional[float],
    curr_timestamp: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Paranoia Layer 0 & 1: Computes distance, time delta, and velocity in km/h.
    Detects impossible travel anomalies.
    """
    if curr_timestamp is None:
        curr_timestamp = datetime.now(timezone.utc)

    if prev_timestamp is None:
        return {
            "is_anomaly": False,
            "velocity_kmh": 0.0,
            "distance_km": 0.0,
            "delta_hours": 0.0,
            "reason": "No previous timestamp recorded",
        }

    # Ensure UTC timezone awareness
    if prev_timestamp.tzinfo is None:
        prev_timestamp = prev_timestamp.replace(tzinfo=timezone.utc)
    if curr_timestamp.tzinfo is None:
        curr_timestamp = curr_timestamp.replace(tzinfo=timezone.utc)

    delta_seconds = (curr_timestamp - prev_timestamp).total_seconds()
    if delta_seconds < 0:
        # Clock skew or out-of-order event; treat conservatively
        delta_seconds = abs(delta_seconds)

    prev_coords = resolve_geo_coordinates(prev_country, prev_lat, prev_lon)
    curr_coords = resolve_geo_coordinates(curr_country, curr_lat, curr_lon)

    if not prev_coords or not curr_coords:
        return {
            "is_anomaly": False,
            "velocity_kmh": 0.0,
            "distance_km": 0.0,
            "delta_hours": delta_seconds / 3600.0,
            "reason": "Insufficient coordinate data to evaluate velocity",
        }

    distance_km = haversine_distance_km(
        prev_coords[0], prev_coords[1], curr_coords[0], curr_coords[1]
    )

    # If within 50km (same city or metro region), consider safe regardless of time delta
    if distance_km < 50.0:
        return {
            "is_anomaly": False,
            "velocity_kmh": 0.0,
            "distance_km": distance_km,
            "delta_hours": delta_seconds / 3600.0,
            "reason": "Intra-metro operations within safe threshold",
        }

    # If occurred within minimum delta seconds across significant distance (> 50km)
    if delta_seconds < MIN_TIME_DELTA_SECONDS:
        return {
            "is_anomaly": True,
            "velocity_kmh": 99999.0,
            "distance_km": distance_km,
            "delta_hours": delta_seconds / 3600.0,
            "reason": f"Near-instantaneous cross-regional shift ({distance_km:.1f} km in {delta_seconds:.1f}s)",
        }

    delta_hours = delta_seconds / 3600.0
    velocity_kmh = distance_km / delta_hours

    is_anomaly = velocity_kmh > MAX_CREDIBLE_VELOCITY_KMH
    reason = (
        f"Velocity {velocity_kmh:.1f} km/h exceeds maximum threshold {MAX_CREDIBLE_VELOCITY_KMH} km/h"
        if is_anomaly
        else "Geographic velocity within credible commercial travel limits"
    )

    return {
        "is_anomaly": is_anomaly,
        "velocity_kmh": round(velocity_kmh, 2),
        "distance_km": round(distance_km, 2),
        "delta_hours": round(delta_hours, 4),
        "reason": reason,
    }


def should_mute_cloud_execution(account_row: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Paranoia Layer 1: Channel Mutex (Eradicates FLAW-03 - Dual-IP Flapping).
    If the account's execution channel is set to 'EXTENSION' and the Chrome Extension
    has reported activity within EXTENSION_ACTIVE_WINDOW_MINUTES, cloud background
    workers (inbox_sync, health check crons) MUST mute their execution to avoid
    firing simultaneous requests from cloud datacenter proxies while the user's
    residential browser session is active.
    """
    channel = (account_row.get("execution_channel") or "CLOUD").strip().upper()
    if channel != "EXTENSION":
        return False, "Account configured for cloud execution"

    last_active_raw = account_row.get("last_extension_active_at")
    if not last_active_raw:
        # Extension is set as channel, but no heartbeat yet. Mute by default for safety.
        return True, "Execution channel is EXTENSION (awaiting initial heartbeat)"

    try:
        if isinstance(last_active_raw, str):
            clean_ts = last_active_raw.replace("Z", "+00:00")
            last_active = datetime.fromisoformat(clean_ts)
        elif isinstance(last_active_raw, datetime):
            last_active = last_active_raw
        else:
            return True, "Execution channel is EXTENSION with unparseable timestamp"

        if last_active.tzinfo is None:
            last_active = last_active.replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        elapsed = (now - last_active).total_seconds() / 60.0

        if elapsed <= EXTENSION_ACTIVE_WINDOW_MINUTES:
            return True, (
                f"Chrome Extension was active {elapsed:.1f}m ago "
                f"(window: {EXTENSION_ACTIVE_WINDOW_MINUTES}m). "
                "Cloud execution muted to prevent dual-IP collision."
            )
        else:
            return False, f"Extension idle for {elapsed:.1f}m (> {EXTENSION_ACTIVE_WINDOW_MINUTES}m threshold)"
    except Exception as e:
        logger.warning(f"[ImpossibleTravelGuard] Error checking extension activity: {e}")
        return True, "Error checking extension activity — failing safe by muting cloud execution"


def record_and_verify_account_geodesic_hop(
    account_id: str,
    new_country: Optional[str],
    new_ip: Optional[str],
    channel: str,
    supabase: Any,
    new_lat: Optional[float] = None,
    new_lon: Optional[float] = None
) -> Dict[str, Any]:
    """
    Paranoia Layer 1 & 2: Inspects last recorded geographic footprint of the account in Supabase.
    If an impossible travel anomaly is tripped:
      1. Logs forensic record to 'impossible_travel_logs' table.
      2. Puts the account into a 3-hour cooldown window.
      3. Raises ImpossibleTravelAnomaly if in strict mode or returns anomaly details.
    """
    try:
        res = (
            supabase.table("accounts")
            .select("id, last_ip, last_country_code, last_geo_lat, last_geo_lon, last_activity_at, cooling_until")
            .eq("id", account_id)
            .single()
            .execute()
        )
        row = res.data or {}
    except Exception as fetch_err:
        logger.warning(f"[ImpossibleTravelGuard] Could not fetch account {account_id} geo footprint: {fetch_err}")
        return {"is_anomaly": False, "reason": "Failed to query historical footprint"}

    last_country = row.get("last_country_code")
    last_lat = row.get("last_geo_lat")
    last_lon = row.get("last_geo_lon")
    last_act_raw = row.get("last_activity_at")

    last_ts = None
    if last_act_raw:
        try:
            if isinstance(last_act_raw, str):
                clean_ts = last_act_raw.replace("Z", "+00:00")
                last_ts = datetime.fromisoformat(clean_ts)
            elif isinstance(last_act_raw, datetime):
                last_ts = last_act_raw
        except Exception:
            pass

    now = datetime.now(timezone.utc)
    evaluation = calculate_geographic_velocity(
        prev_country=last_country,
        prev_lat=last_lat,
        prev_lon=last_lon,
        prev_timestamp=last_ts,
        curr_country=new_country,
        curr_lat=new_lat,
        curr_lon=new_lon,
        curr_timestamp=now,
    )

    if evaluation.get("is_anomaly"):
        cooling_until = (now + timedelta(hours=IMPOSSIBLE_TRAVEL_COOLING_HOURS)).isoformat()
        logger.error(
            f"[ImpossibleTravelGuard] CRITICAL: Impossible travel detected for account {account_id}! "
            f"From {last_country} to {new_country} ({evaluation.get('distance_km')}km in "
            f"{evaluation.get('delta_hours')}h, velocity: {evaluation.get('velocity_kmh')} km/h). "
            f"Cooling account until {cooling_until}."
        )

        # Update account cooling
        try:
            supabase.table("accounts").update({
                "cooling_until": cooling_until,
                "cooling_reason": f"IMPOSSIBLE_TRAVEL: {evaluation.get('reason')}",
            }).eq("id", account_id).execute()
        except Exception as upd_err:
            logger.error(f"[ImpossibleTravelGuard] Failed to cool account: {upd_err}")

        # Attempt to insert audit log
        try:
            supabase.table("impossible_travel_logs").insert({
                "account_id": account_id,
                "prev_country": last_country,
                "curr_country": new_country,
                "prev_ip": row.get("last_ip"),
                "curr_ip": new_ip,
                "distance_km": evaluation.get("distance_km"),
                "velocity_kmh": evaluation.get("velocity_kmh"),
                "channel": channel,
                "detected_at": now.isoformat(),
            }).execute()
        except Exception:
            # Table might not exist yet before migration runs
            pass

        return evaluation

    # Safe hop: update account's current footprint
    resolved = resolve_geo_coordinates(new_country, new_lat, new_lon)
    upd_payload = {
        "last_country_code": new_country,
        "last_ip": new_ip,
        "last_activity_at": now.isoformat(),
    }
    if resolved:
        upd_payload["last_geo_lat"] = resolved[0]
        upd_payload["last_geo_lon"] = resolved[1]

    try:
        supabase.table("accounts").update(upd_payload).eq("id", account_id).execute()
    except Exception as save_err:
        logger.debug(f"[ImpossibleTravelGuard] Non-blocking error saving geo footprint: {save_err}")

    return evaluation

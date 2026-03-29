import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=10,
    name="candidate.tasks.geocode_candidate",
)
def geocode_candidate_task(self, candidate_id: str):
    """
    Geocodes a candidate's location string to lat/lng.
    Called on demand when geo filtering is needed.
    Uses Nominatim (free, no API key needed).
    """
    from candidate.models import Candidate

    try:
        candidate = Candidate.objects.get(id=candidate_id)
    except Candidate.DoesNotExist:
        logger.error(f"[geocode_candidate] Candidate {candidate_id} not found.")
        return

    if candidate.latitude and candidate.longitude:
        logger.info(
            f"[geocode_candidate] Candidate '{candidate.name}' "
            f"already has coordinates. Skipping."
        )
        return

    if not candidate.location:
        logger.warning(
            f"[geocode_candidate] Candidate '{candidate.name}' "
            f"has no location. Cannot geocode."
        )
        return

    try:
        from geopy.geocoders import Nominatim

        geolocator = Nominatim(user_agent="edukai_candidate_geocoder")
        location   = geolocator.geocode(candidate.location, timeout=10)

        if location:
            candidate.latitude  = round(location.latitude, 6)
            candidate.longitude = round(location.longitude, 6)
            candidate.save(update_fields=["latitude", "longitude", "updated_at"])
            logger.info(
                f"[geocode_candidate] ✅ '{candidate.name}' geocoded: "
                f"lat={candidate.latitude}, lng={candidate.longitude} "
                f"(query: '{candidate.location}')"
            )
        else:
            logger.warning(
                f"[geocode_candidate] ⚠️ No location found for "
                f"'{candidate.name}' with query '{candidate.location}'."
            )

    except Exception as exc:
        logger.error(
            f"[geocode_candidate] ❌ Geocoding failed for "
            f"'{candidate.name}': {exc}"
        )
        raise self.retry(exc=exc)
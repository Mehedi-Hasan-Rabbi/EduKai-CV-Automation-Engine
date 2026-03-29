import logging
import time
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=5,
    default_retry_delay=60,   # wait 60s before retrying after 429
    name="organization.tasks.geocode_organization",
)
def geocode_organization_task(self, organization_id: str):
    """
    Geocodes an organization's address using its postcode.
    Rate limited to 1 req/sec per Nominatim fair use policy.
    """
    from organization.models import Organization

    try:
        org = Organization.objects.get(id=organization_id)
    except Organization.DoesNotExist:
        logger.error(f"[geocode] Organization {organization_id} not found.")
        return

    if org.latitude and org.longitude:
        logger.info(f"[geocode] '{org.name}' already has coordinates. Skipping.")
        return

    if org.postcode:
        query = f"{org.postcode}, UK"
    elif org.town:
        query = f"{org.town}, {org.county or ''}, UK".strip(", ")
    else:
        logger.warning(f"[geocode] '{org.name}' has no postcode or town. Cannot geocode.")
        return

    try:
        from geopy.geocoders import Nominatim
        from geopy.exc import GeocoderRateLimited, GeocoderTimedOut, GeocoderServiceError

        geolocator = Nominatim(
            user_agent="edukai_geocoder",
            timeout=10,
        )

        # ✅ Respect Nominatim 1 req/sec rule
        time.sleep(1)

        location = geolocator.geocode(query)

        if location:
            org.latitude  = round(location.latitude, 6)
            org.longitude = round(location.longitude, 6)
            org.save(update_fields=["latitude", "longitude", "updated_at"])
            logger.info(
                f"[geocode] ✅ '{org.name}' geocoded: "
                f"lat={org.latitude}, lng={org.longitude} "
                f"(query: '{query}')"
            )
        else:
            logger.warning(f"[geocode] ⚠️ No result for '{org.name}' query='{query}'.")

    except GeocoderRateLimited as exc:
        # 429 — back off longer before retrying
        logger.warning(f"[geocode] Rate limited for '{org.name}'. Retrying in 60s.")
        raise self.retry(exc=exc, countdown=60)

    except GeocoderTimedOut as exc:
        logger.warning(f"[geocode] Timeout for '{org.name}'. Retrying in 30s.")
        raise self.retry(exc=exc, countdown=30)

    except Exception as exc:
        logger.error(f"[geocode] ❌ Failed for '{org.name}': {exc}")
        raise self.retry(exc=exc, countdown=60)
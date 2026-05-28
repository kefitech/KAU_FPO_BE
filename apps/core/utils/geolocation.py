"""
Geolocation Utilities for KAU-FPO Platform
===========================================

IP address to location lookup utilities.

Uses ip-api.com free service (no API key required):
- 45 requests/minute limit
- Free for non-commercial use
- Returns city, region, country, lat/lon

Author: Athul Gopan
Created: 22-04-2026
"""

import requests
from typing import Dict, Optional
from django.core.cache import cache
import logging

logger = logging.getLogger(__name__)


class GeoLocationService:
    """
    Service for IP address geolocation lookup.

    Uses ip-api.com with caching to minimize API calls.
    """

    # Free IP geolocation API (45 requests/minute)
    API_URL = "http://ip-api.com/json/{ip}?fields=status,message,country,countryCode,region,regionName,city,lat,lon,timezone,isp"

    # Cache timeout: 24 hours (IP locations don't change frequently)
    CACHE_TIMEOUT = 86400

    # Local/private IP ranges that shouldn't be looked up
    PRIVATE_IPS = ['127.0.0.1', 'localhost', '0.0.0.0']

    @classmethod
    def get_location(cls, ip_address: str) -> Optional[Dict[str, str]]:
        """
        Get location data for an IP address.

        Args:
            ip_address: IP address to lookup

        Returns:
            Dictionary with location data or None if lookup fails
            {
                'city': 'Thrissur',
                'region': 'Kerala',
                'region_code': 'KL',
                'country': 'India',
                'country_code': 'IN',
                'latitude': 10.5276,
                'longitude': 76.2144,
                'timezone': 'Asia/Kolkata',
                'isp': 'BSNL'
            }
        """
        if not ip_address or ip_address in cls.PRIVATE_IPS:
            return cls._get_default_location()

        # Check cache first (gracefully handle cache failures)
        cache_key = f"geo_location:{ip_address}"
        try:
            cached_location = cache.get(cache_key)
            if cached_location:
                logger.debug(f"Cache hit for IP: {ip_address}")
                return cached_location
        except Exception as e:
            logger.warning(f"Cache get failed (continuing without cache): {str(e)}")

        # Fetch from API
        try:
            response = requests.get(
                cls.API_URL.format(ip=ip_address),
                timeout=3  # 3 second timeout
            )

            if response.status_code == 200:
                data = response.json()

                if data.get('status') == 'success':
                    location = {
                        'city': data.get('city', ''),
                        'region': data.get('regionName', ''),
                        'region_code': data.get('region', ''),
                        'country': data.get('country', ''),
                        'country_code': data.get('countryCode', ''),
                        'latitude': data.get('lat'),
                        'longitude': data.get('lon'),
                        'timezone': data.get('timezone', ''),
                        'isp': data.get('isp', ''),
                    }

                    # Cache the result (gracefully handle cache failures)
                    try:
                        cache.set(cache_key, location, cls.CACHE_TIMEOUT)
                    except Exception as e:
                        logger.warning(f"Cache set failed (continuing without cache): {str(e)}")

                    logger.info(f"Geolocation fetched for IP {ip_address}: {location['city']}, {location['country']}")

                    return location
                else:
                    logger.warning(f"Geolocation API error for IP {ip_address}: {data.get('message')}")
                    return cls._get_default_location()

            else:
                logger.error(f"Geolocation API HTTP error: {response.status_code}")
                return cls._get_default_location()

        except requests.RequestException as e:
            logger.error(f"Geolocation API request failed: {str(e)}")
            return cls._get_default_location()

        except Exception as e:
            logger.error(f"Unexpected error in geolocation lookup: {str(e)}")
            return cls._get_default_location()

    @staticmethod
    def _get_default_location() -> Dict[str, str]:
        """
        Return default/unknown location data.

        Used for localhost, private IPs, or when API fails.
        """
        return {
            'city': 'Unknown',
            'region': 'Unknown',
            'region_code': '',
            'country': 'Unknown',
            'country_code': '',
            'latitude': None,
            'longitude': None,
            'timezone': '',
            'isp': '',
        }

    @classmethod
    def get_location_string(cls, ip_address: str) -> str:
        """
        Get a formatted location string for an IP address.

        Args:
            ip_address: IP address to lookup

        Returns:
            Formatted string like "Thrissur, Kerala, India" or "Unknown"
        """
        location = cls.get_location(ip_address)

        if not location:
            return "Unknown"

        # Build location string
        parts = []

        if location.get('city') and location['city'] != 'Unknown':
            parts.append(location['city'])

        if location.get('region') and location['region'] != 'Unknown':
            parts.append(location['region'])

        if location.get('country') and location['country'] != 'Unknown':
            parts.append(location['country'])

        return ', '.join(parts) if parts else 'Unknown'


def get_ip_location(ip_address: str) -> Optional[Dict[str, str]]:
    """
    Convenience function to get location for an IP address.

    Args:
        ip_address: IP address to lookup

    Returns:
        Location dictionary or None
    """
    return GeoLocationService.get_location(ip_address)


def get_ip_location_string(ip_address: str) -> str:
    """
    Convenience function to get formatted location string.

    Args:
        ip_address: IP address to lookup

    Returns:
        Formatted location string
    """
    return GeoLocationService.get_location_string(ip_address)

"""Network → Account Type mapping for the OpenFloat Data Formatter.

Maps Process Maker network names to OpenFloat Allowed Types,
as defined in the golden prompt §4.1.
"""

from __future__ import annotations

from .config import DEFAULT_NETWORK_MAP


def map_network(
    network: str,
    network_map: dict[str, str] | None = None,
) -> tuple[str, str | None]:
    """Map a Process Maker network name to an OpenFloat account type.

    Args:
        network: The raw network value from Process Maker (e.g. "Safaricom").
        network_map: Optional custom mapping. Defaults to DEFAULT_NETWORK_MAP.

    Returns:
        A tuple of (account_type, error_message).
        On success: ("Safaricom Prepaid", None)
        On failure: ("", f"Unrecognized network '{network}'")

    Examples:
        >>> map_network("Safaricom")
        ('Safaricom Prepaid', None)
        >>> map_network("Airtel")
        ('Airtel Prepaid', None)
        >>> map_network("Orange")
        ('', "Unrecognized network 'Orange'")
    """
    if network_map is None:
        network_map = DEFAULT_NETWORK_MAP

    account_type = network_map.get(network)
    if account_type is None:
        return ("", f"Unrecognized network '{network}'")

    return (account_type, None)
import json
from pathlib import Path

import requests

BASE_URL = "https://reconcile.gnd.network"

GND_TYPES = [
    "Person",
    "DifferentiatedPerson",
    "CorporateBody",
    "ConferenceOrEvent",
    "PlaceOrGeographicName",
    "TerritorialCorporateBodyOrAdministrativeUnit",
    "SubjectHeading",
    "SubjectHeadingSensoStricto",
    "Work",
]

OUTPUT_FILE = Path("config/gnd_properties.json")


def fetch_properties_for_type(type_id: str, limit: int = 500) -> list[dict[str, str]]:
    url = f"{BASE_URL}/properties"

    response = requests.get(
        url,
        params={
            "type": type_id,
            "limit": limit,
        },
        timeout=60,
    )
    response.raise_for_status()

    data = response.json()

    properties = data.get("properties", [])

    cleaned = []

    for prop in properties:
        prop_id = prop.get("id")
        prop_name = prop.get("name", prop_id)

        if not prop_id:
            continue

        cleaned.append(
            {
                "id": prop_id,
                "name": prop_name,
            }
        )

    return cleaned


def main() -> None:
    registry = {}

    for type_id in GND_TYPES:
        print(f"Fetching properties for type: {type_id}")

        try:
            registry[type_id] = fetch_properties_for_type(type_id)
        except Exception as error:
            print(f"Failed for {type_id}: {error}")
            registry[type_id] = []

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    OUTPUT_FILE.write_text(
        json.dumps(
            registry,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    print(f"Written: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()

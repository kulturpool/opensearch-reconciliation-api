import re


PROPERTY_LABEL_OVERRIDES = {
    "id": "GND ID",
    "uri": "URI",
    "preferredName": "Bevorzugter Name",
    "variantName": "Varianter Name",
    "type": "GND-Typ",
    "dateOfBirth": "Geburtsdatum",
    "dateOfDeath": "Sterbedatum",
    "professionOrOccupation": "Beruf oder Tätigkeit",
    "placeOfBirth": "Geburtsort",
    "placeOfDeath": "Sterbeort",
    "source": "Quelle",

    "gndIdentifier": "GND-ID",
    "academicDegree": "Akademischer Grad",
    "affiliation": "Affiliation",
    "biographicalOrHistoricalInformation": "Biografische/Historische Information",
    "familialRelationship": "Familiäre Beziehung",
    "gender": "Geschlecht",
    "geographicAreaCode": "Ländercode",
    "nobilityTitle": "Adelstitel",
    "placeOfActivity": "Wirkungsort",
    "publication": "Publikation",
    "relatedPerson": "Verwandte Person",
    "relatedTerm": "Verwandter Begriff",
    "broaderTermGeneral": "Oberbegriff allgemein",
    "broaderTermInstantial": "Instanzieller Oberbegriff",
    "broaderTermPartitive": "Partitiver Oberbegriff",
    "preferredNameForThePerson": "Bevorzugter Name der Person",
    "variantNameForThePerson": "Varianter Name der Person",
    "preferredNameForTheSubjectHeading": "Bevorzugter Name des Sachbegriffs",
    "variantNameForTheSubjectHeading": "Varianter Name des Sachbegriffs",
    "preferredNameForThePlaceOrGeographicName": "Bevorzugter Name des Geografikums",
    "variantNameForThePlaceOrGeographicName": "Varianter Name des Geografikums",
    "preferredNameForTheCorporateBody": "Bevorzugter Name der Körperschaft",
    "variantNameForTheCorporateBody": "Varianter Name der Körperschaft",
    "preferredNameForTheConferenceOrEvent": "Bevorzugter Name der Konferenz/des Ereignisses",
    "variantNameForTheConferenceOrEvent": "Varianter Name der Konferenz/des Ereignisses",
    "preferredNameForTheWork": "Bevorzugter Name des Werks",
    "variantNameForTheWork": "Varianter Name des Werks",
}


def property_label(property_id: str) -> str:
    """
    Returns a human-readable label for a property id.

    Uses:
    1. curated overrides for important GND properties
    2. automatic camelCase splitting as fallback
    """

    if not property_id:
        return ""

    if property_id in PROPERTY_LABEL_OVERRIDES:
        return PROPERTY_LABEL_OVERRIDES[property_id]

    return split_property_id(property_id)


def split_property_id(property_id: str) -> str:
    """
    Converts technical GND property ids into readable labels.

    Example:
    biographicalOrHistoricalInformation
    -> Biographical Or Historical Information
    """

    value = property_id.strip()

    value = value.replace("_", " ")
    value = value.replace("-", " ")

    value = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", value)
    value = re.sub(r"\s+", " ", value)

    return value[:1].upper() + value[1:]


def build_property_label_mapping(property_ids: list[str]) -> dict[str, str]:
    """
    Automatically builds a property label mapping from a list of property ids.
    """

    return {
        property_id: property_label(property_id)
        for property_id in sorted(set(property_ids))
        if property_id
    }
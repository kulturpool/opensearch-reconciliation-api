from typing import Any

from opensearchpy import OpenSearch
from opensearchpy.exceptions import NotFoundError, OpenSearchException, TransportError


def opensearch_index_exists_or_alias_exists(
    client: OpenSearch,
    name: str,
) -> bool:
    """
    Checks whether an OpenSearch index or alias exists.

    Used by bootstrap to decide whether the local GND index is usable or
    whether a full rebuild is required.
    """
    try:
        if client.indices.exists(index=name):
            return True
    except (TransportError, OpenSearchException):
        pass

    try:
        alias_response = client.indices.get_alias(name=name)
    except NotFoundError:
        return False
    except (TransportError, OpenSearchException):
        return False

    return isinstance(alias_response, dict) and bool(alias_response)


def get_alias_target_indices(
    client: OpenSearch,
    alias_name: str,
) -> list[str]:
    """
    Returns all indices currently attached to an alias.
    """
    try:
        response = client.indices.get_alias(name=alias_name)
    except NotFoundError:
        return []

    if not isinstance(response, dict):
        return []

    return list(response.keys())


def switch_gnd_alias(
    client: OpenSearch,
    new_index: str,
    alias_name: str = "gnd",
) -> None:
    """
    Atomically switches the public GND alias to a newly built index.

    Existing API and update code can keep using index name 'gnd'.
    OpenSearch resolves it to the actual index behind the alias.
    """
    old_indices = get_alias_target_indices(client=client, alias_name=alias_name)

    actions: list[dict[str, Any]] = []

    for old_index in old_indices:
        if old_index == new_index:
            continue

        actions.append(
            {
                "remove": {
                    "index": old_index,
                    "alias": alias_name,
                }
            }
        )

    actions.append(
        {
            "add": {
                "index": new_index,
                "alias": alias_name,
            }
        }
    )

    client.indices.update_aliases(body={"actions": actions})


def delete_index_if_exists(
    client: OpenSearch,
    index_name: str,
) -> None:
    """
    Deletes an index if it exists.

    Do not call this with an alias name unless you explicitly want to delete the
    concrete index behind that name.
    """
    if client.indices.exists(index=index_name):
        client.indices.delete(index=index_name)


def count_records(
    client: OpenSearch,
    index_name: str,
) -> int:
    """
    Counts all records in an index or alias.
    """
    response = client.count(index=index_name)
    return int(response.get("count", 0))


def count_term_records(
    client: OpenSearch,
    index_name: str,
    field_name: str,
    field_value: str | bool,
) -> int:
    """
    Counts records by exact term.
    """
    response = client.count(
        index=index_name,
        body={
            "query": {
                "term": {
                    field_name: field_value,
                }
            }
        },
    )
    return int(response.get("count", 0))


def validate_built_index(
    client: OpenSearch,
    index_name: str,
    minimum_documents: int = 1_000_000,
    minimum_family_records: int = 20_000,
) -> dict[str, int]:
    """
    Performs basic sanity checks before a freshly built index is marked complete
    or switched to the public alias.

    Adjust thresholds if your local dataset is intentionally smaller.
    """
    document_count = count_records(client=client, index_name=index_name)

    if document_count < minimum_documents:
        raise RuntimeError(
            f"Built index '{index_name}' has suspiciously few documents: "
            f"{document_count}. Expected at least {minimum_documents}."
        )

    family_count = count_term_records(
        client=client,
        index_name=index_name,
        field_name="type",
        field_value="Family",
    )

    if family_count < minimum_family_records:
        raise RuntimeError(
            f"Built index '{index_name}' has too few Family records: "
            f"{family_count}. Expected at least {minimum_family_records}. "
            "EntityFacts enrichment may not have completed."
        )

    entityfacts_count = count_term_records(
        client=client,
        index_name=index_name,
        field_name="entityfactsEnriched",
        field_value=True,
    )

    return {
        "document_count": document_count,
        "family_count": family_count,
        "entityfacts_count": entityfacts_count,
    }


def cleanup_incomplete_build_index(
    client: OpenSearch,
    state: dict[str, Any],
) -> None:
    """
    Deletes an incomplete build index recorded in index_state.json.

    This is only for build indices such as gnd_build_*. It deliberately never
    deletes the public index or alias 'gnd'.
    """
    build_index = state.get("build_index")
    status = state.get("status")

    if not build_index:
        return

    if status == "complete":
        return

    if not str(build_index).startswith("gnd_build_"):
        return

    delete_index_if_exists(client=client, index_name=str(build_index))

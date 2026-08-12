def format_class_name(grade_level: str | None, class_name: str) -> str:
    """Return the canonical class label used in snapshots and API responses."""
    normalized_name = " ".join(class_name.split())
    normalized_level = " ".join((grade_level or "").split())
    if not normalized_level:
        return normalized_name
    folded_name = normalized_name.casefold()
    folded_level = normalized_level.casefold()
    if folded_name == folded_level:
        return normalized_name
    for separator in (" - ", " — ", " · "):
        suffix = f"{separator}{folded_level}"
        if folded_name.endswith(suffix):
            suffix_length = len(separator) + len(normalized_level)
            return f"{normalized_level} {normalized_name[:-suffix_length].strip()}"
        prefix = f"{folded_level}{separator}"
        if folded_name.startswith(prefix):
            prefix_length = len(normalized_level) + len(separator)
            return f"{normalized_level} {normalized_name[prefix_length:].strip()}"
    if folded_name.startswith(f"{folded_level} "):
        return normalized_name
    return f"{normalized_level} {normalized_name}"

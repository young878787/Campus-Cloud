import logging

logger = logging.getLogger(__name__)


def to_punycode_hostname(hostname: str) -> str:
    """將 Unicode hostname 轉換為 Punycode（ACE 格式）傳給 PVE。"""
    if not isinstance(hostname, str):
        logger.error(
            "Expected str for hostname, got %s: %r", type(hostname).__name__, hostname
        )
        raise TypeError(
            f"hostname must be str, got {type(hostname).__name__!r}: {hostname!r}"
        )

    result_labels = []
    for label in hostname.split("."):
        if not label:
            raise ValueError("Hostname labels must not be empty")
        try:
            label.encode("ascii")
            ace = label
        except UnicodeEncodeError:
            try:
                ace = "xn--" + label.encode("punycode").decode("ascii")
            except Exception as exc:
                raise ValueError(
                    f"Cannot encode hostname label '{label}' to Punycode: {exc}"
                ) from exc

        if len(ace) > 63:
            raise ValueError(
                f"Encoded hostname label '{label}' exceeds 63 characters after Punycode conversion"
            )
        result_labels.append(ace)

    encoded_hostname = ".".join(result_labels)
    if len(encoded_hostname) > 253:
        raise ValueError(
            "Encoded hostname exceeds 253 characters after Punycode conversion"
        )
    return encoded_hostname

from flask import request


def is_valid_device_token(config) -> bool:
    """
    Verify the device auth token from the request.
    Accepts the token either as a Bearer token in the Authorization header
    or as auth_token in the JSON body (legacy device support).
    """
    # Prefer Authorization header: "Bearer <token>"
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:] == config["DEVICE_AUTH_TOKEN"]

    # Fallback: token in JSON body
    body = request.get_json(silent=True) or {}
    return body.get("auth_token") == config["DEVICE_AUTH_TOKEN"]
